#!/usr/bin/env python3
"""AT24C256 runtime client: read-only by default; byte-write test preserves scratch."""
import argparse
import hashlib
import importlib.util
import json
from pathlib import Path
import sys
import time
from axpe_host import Loader,SerialRequests,bridge_settings,configure

ROOT=Path(__file__).resolve().parents[3]
spec=importlib.util.spec_from_file_location('eeprom_build',ROOT/'sw/pemu/firmware/eeprom/build.py')
builder=importlib.util.module_from_spec(spec);spec.loader.exec_module(builder)


class EepromClient:
    def __init__(self,execute,runtime_profile,capacity,parameters=None,clock=time.monotonic,sleep=time.sleep):
        self.values=builder.settings(parameters)
        self.execute,self.profile,self.capacity=execute,runtime_profile,capacity
        self.clock,self.sleep=clock,sleep
        self.operations=[]
        self.last_report={}
        self._source_hashes={p:hashlib.sha256(p.read_bytes()).hexdigest() for p in [runtime_profile,Path(builder.__file__),ROOT/'sw/pemu/firmware/i2c.s',ROOT/'sw/pemu/firmware/eeprom/parameters.json',ROOT/'sw/pemu/firmware/build_demos.py',ROOT/'sw/pemu/as/axpe_as.py',ROOT/'sw/pemu/isa/axpe-isa.json',*sorted((ROOT/'sw/pemu/firmware/eeprom').glob('*.s'))]}

    def run(self,name,byte=None):
        if any(hashlib.sha256(p.read_bytes()).hexdigest()!=h for p,h in self._source_hashes.items()):
            raise RuntimeError('runtime inputs changed during EEPROM session; backup retained')
        values=dict(self.values)
        if byte is not None:values['data_byte']=byte
        programs,_=builder.programs(self.profile,self.capacity,values)
        words=[instruction.word for instruction in programs[name]]
        status=self.execute(words,self.values['program_timeout_ms'])
        if type(status) is not int or not status&0x0200 or status&0x0c00:
            raise RuntimeError('EEPROM program did not halt cleanly')
        value=status&0xff
        self.operations.append({'operation':name,'result':value,'write_data_byte':byte,'payload_sha256':hashlib.sha256(''.join(f'{w:08x}\n' for w in words).encode()).hexdigest()})
        return value

    def read_byte(self):
        low,high=self.run('read-low'),self.run('read-high')
        if not 0x80<=low<=0x8f or not 0x80<=high<=0x8f:
            raise RuntimeError('EEPROM random read was NACKed or returned an invalid tag')
        return ((high&15)<<4)|(low&15)

    def wait_ready(self):
        end=self.clock()+self.values['write_timeout_ms']/1000
        attempts=0
        while self.clock()<end:
            result=self.run('poll');attempts+=1
            if result==0x80:
                if self.clock()>end:raise TimeoutError('EEPROM ready reply arrived after deadline')
                return attempts
            if result!=0:raise RuntimeError('invalid readiness result')
            remaining=end-self.clock()
            if remaining>0:self.sleep(min(remaining,self.values['poll_interval_ms']/1000))
        raise TimeoutError('EEPROM write-cycle readiness deadline exceeded')

    def write_byte(self,value):
        if type(value) is not int or not 0<=value<=255:raise ValueError('invalid data byte')
        if self.run('write',value)!=0x80:raise RuntimeError('EEPROM byte write was NACKed')
        return self.wait_ready()

    def exercise(self,reads,writes,save_backup):
        if type(reads) is not int or reads<=0 or type(writes) is not int or writes<0:
            raise ValueError('positive read count and nonnegative write count required')
        original=self.read_byte()
        backup={'device_address':self.values['device_address'],'word_address':self.values['word_address'],'original_byte':original}
        # Persist before the first write. Caller can recover after interruption.
        save_backup(backup)
        for _ in range(reads-1):
            if self.read_byte()!=original:raise RuntimeError('EEPROM repeated read changed')
        if not writes:return dict(backup,reads_passed=reads,writes_passed=0,restoration='no writes requested')
        restore_needed=False
        report=dict(backup,reads_passed=reads,writes_passed=0,restoration='pending')
        self.last_report=report
        try:
            for iteration in range(writes):
                value=(self.values['data_byte']+iteration)&255
                if value==original:value^=0x80
                # Even a failed/partial host exchange can have reached the device.
                restore_needed=True
                self.write_byte(value)
                if self.read_byte()!=value:raise RuntimeError('EEPROM byte-write verification mismatch (check WP)')
                report['writes_passed']+=1
        finally:
            if restore_needed:
                # A previous operation may have failed during a write cycle.
                try:
                    self.wait_ready();self.write_byte(original)
                    if self.read_byte()!=original:raise RuntimeError('EEPROM original byte restoration mismatch; backup retained')
                except Exception as error:
                    report['restoration']='failed';report['restoration_error']=str(error)
                    raise
                report['restoration']='verified'
        return report


def main():
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('--serial',required=True);p.add_argument('--profile',type=Path,required=True)
    p.add_argument('--runtime-profile',type=Path,required=True)
    p.add_argument('--image-receipt',type=Path,required=True,help='Gowin image receipt supplied by the operator; does not attest the programmed device')
    p.add_argument('--parameters',type=Path,help='optional JSON EEPROM settings profile (schema/settings)')
    p.add_argument('--device-address',type=lambda s:int(s,0),default=None)
    p.add_argument('--scratch-address',type=lambda s:int(s,0),required=True,help='operator-selected reserved byte; existing data is backed up and restored')
    p.add_argument('--write-test',action='store_true',help='run write/read checks; default only reads')
    p.add_argument('--bridge-config',type=Path,default=Path(__file__).with_name('bridge.json'))
    p.add_argument('--output',type=Path,required=True,help='fresh run directory, including durable backup')
    args=p.parse_args()
    if args.output.exists():p.error('run directory exists; use a fresh output')
    resolved=configure.resolved_config(args.profile);configure.to_make(resolved)
    if resolved['components']['board']['id']!='board.tangprimer25k-axpe':p.error('expected axpe Primer profile')
    def values(kind):return {k:resolved['parameters'].get(kind,{}).get(k,s['default']) for k,s in resolved['components'][kind]['parameters'].items()}
    board=values('board');capacity=values('pemu')['imem_words']
    clock=board['capture_clock_hz'] if board['capture_mode'] else resolved['components']['board']['make']['FPGA_INPUT_CLOCK_HZ']//2
    if builder.rates(args.runtime_profile)['clock_hz']!=clock:p.error('runtime clock differs from FPGA profile')
    image=json.loads(args.image_receipt.read_text())
    if image.get('result')!='PASS' or image['config']['sha256']!=hashlib.sha256(args.profile.read_bytes()).hexdigest():p.error('image receipt does not bind this passing FPGA profile')
    overrides={}
    if args.parameters:
        custom=json.loads(args.parameters.read_text())
        if set(custom)!={'schema','settings'} or custom['schema']!='org.atomix.axpe-eeprom-profile.v1':p.error('invalid EEPROM profile')
        overrides=builder.settings(custom['settings'])
    overrides['word_address']=args.scratch_address
    if args.device_address is not None:overrides['device_address']=args.device_address
    parameters=builder.settings(overrides);settings=bridge_settings(args.bridge_config,clock,board['reset_cycles'])
    args.output.mkdir(parents=True)
    receipt={'schema':'org.atomix.axpe-eeprom-lab.v1','status':'failed','level':'physical host status/readback; waveform/electrical verdict separate',
        'parameters':parameters,'declared_clock_hz':clock,'clock_measured':False,'serial':args.serial,'profile':str(args.profile),'runtime_profile':str(args.runtime_profile),
        'supplied_image':image['bitstream'],'programmed_image_attested':False,'write_test_requested':args.write_test,'source_inputs_sha256':{str(q):hashlib.sha256(q.read_bytes()).hexdigest() for q in [Path(__file__),Path(builder.__file__),args.profile,args.runtime_profile,args.bridge_config,ROOT/'sw/pemu/firmware/eeprom/parameters.json',ROOT/'sw/pemu/firmware/i2c.s',ROOT/'sw/pemu/firmware/build_demos.py',Path(__file__).with_name('axpe_host.py'),Path(__file__).with_name('pico_bridge.py'),ROOT/'sw/pemu/as/axpe_as.py',ROOT/'sw/pemu/isa/axpe-isa.json',args.image_receipt,*sorted((ROOT/'sw/pemu/firmware/eeprom').glob('*.s'))]}}
    client=None
    try:
        import serial
        with serial.Serial(args.serial,115200,timeout=settings['serial_timeout_ms']/1000) as port:
            request=SerialRequests(port)
            receipt['bridge']=request({'op':'configure','values':settings,'clock_hz':clock,'capture':bool(board['capture_mode'])})
            loader=Loader(request,capacity)
            def execute(words,timeout):loader.load(words);return loader.wait(timeout)
            client=EepromClient(execute,args.runtime_profile,capacity,parameters)
            def save_backup(backup):
                with (args.output/'backup.json').open('x') as stream:
                    json.dump(backup,stream,indent=2);stream.write('\n');stream.flush()
                    import os
                    os.fsync(stream.fileno())
            receipt['result']=client.exercise(parameters['read_iterations'],parameters['write_iterations'] if args.write_test else 0,save_backup)
            receipt['status']='passed'
    except (Exception,KeyboardInterrupt) as error:
        receipt['error']=str(error) or type(error).__name__
        receipt['error_type']=type(error).__name__
    if args.parameters:receipt['source_inputs_sha256'][str(args.parameters)]=hashlib.sha256(args.parameters.read_bytes()).hexdigest()
    if client:
        receipt['operations']=client.operations
        if client.last_report:receipt['result']=client.last_report
    receipt['restoration_on_error']='inspect backup and operation log; interruption/transport loss cannot guarantee restore'
    (args.output/'evidence.json').write_text(json.dumps(receipt,indent=2)+'\n')
    print(json.dumps(receipt));return 0 if receipt['status']=='passed' else 1

if __name__=='__main__':raise SystemExit(main())
