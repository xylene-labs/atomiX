"""Replay two intentionally broken EEPROM payloads against the same adapter."""
from pathlib import Path
import hashlib
import json
import shutil
import subprocess
import sys
ROOT=Path(__file__).resolve().parents[1]
FIRMWARE=ROOT/'sw/pemu/firmware'
sys.path.insert(0,str(FIRMWARE.parent/'as'))
from axpe_as import assemble
sys.path.insert(0,str(FIRMWARE))
from build_demos import settings,i2c_period


def check(output,runtime_profile,capacity):
    rates=settings(runtime_profile)
    base_values=json.loads((output/'eeprom/default/profile.json').read_text())['parameters']
    common={'CLK_HZ':rates['clock_hz'],'SCL_HZ':rates['i2c_hz'],'BIT_PERIOD':i2c_period(rates),
            'DEV_ADDR':base_values['device_address'],'WORD_ADDR':base_values['word_address']}
    mutations=[('swapped-word-address','EEPROM oracle: write address/data mismatch'),
               ('read-ack-instead-of-nack','EEPROM oracle: repeated START/master NACK/read pointer mismatch')]
    records=[]
    for name,witness in mutations:
        destination=output/'mutations'/name
        shutil.copytree(output/'eeprom',destination/'payloads')
        tree=destination/'source';(tree/'eeprom').mkdir(parents=True)
        (tree/'i2c.s').write_bytes((FIRMWARE/'i2c.s').read_bytes())
        if name=='swapped-word-address':
            original=(FIRMWARE/'eeprom/write.s').read_text()
            old='LDIL R0, (WORD_ADDR >> 8) & 0xFF, D=0'
            assert original.count(old)==1
            source=original.replace(old,'LDIL R0, WORD_ADDR & 0xFF, D=0')
            path=tree/'eeprom/write.s';path.write_text(source)
            programs={'write':assemble(source,path,capacity,dict(common,DATA_BYTE=base_values['data_byte']))}
        else:
            original=(tree/'i2c.s').read_text();prefix,tail=original.split('i2c_read_nack:',1)
            assert tail.count('LDIL   R2, RELEASED,')==1
            (tree/'i2c.s').write_text(prefix+'i2c_read_nack:'+tail.replace('LDIL   R2, RELEASED,','LDIL   R2, 0,'))
            path=tree/'eeprom/read.s';path.write_bytes((FIRMWARE/'eeprom/read.s').read_bytes())
            programs={label:assemble(path.read_text(),path,capacity,dict(common,RETURN_SHIFT=shift)) for label,shift in [('read-low',0),('read-high',4)]}
        for label,program in programs.items():
            (destination/'payloads/default'/f'{label}.hex').write_text(''.join(f'{i.word:08x}\n' for i in program))
        argv=[str(output/'obj/Vaxpe_primer_sim'),str(output/'fw'),str(destination/'payloads'),'+verilator+rand+reset+2','+verilator+seed+1']
        log=destination/'replay.log'
        with log.open('w') as stream:
            result=subprocess.run(argv,cwd=ROOT,stdout=stream,stderr=subprocess.STDOUT,timeout=180)
        passed=result.returncode==1 and witness in log.read_text()
        record={'name':name,'status':'passed' if passed else 'failed','expected_exit':1,'returncode':result.returncode,
                'required_oracle_witness':witness,'argv':argv,'log':str(log),'log_sha256':hashlib.sha256(log.read_bytes()).hexdigest(),
                'mutant_source_sha256':{str(p):hashlib.sha256(p.read_bytes()).hexdigest() for p in tree.rglob('*.s')},
                'mutant_payload_sha256':{label:hashlib.sha256((destination/'payloads/default'/f'{label}.hex').read_bytes()).hexdigest() for label in programs}}
        (destination/'evidence.json').write_text(json.dumps(record,indent=2)+'\n');records.append(record)
        if not passed:raise RuntimeError(f'EEPROM mutation {name} did not produce its intended oracle failure: {log}')
    return records
