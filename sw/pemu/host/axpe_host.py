#!/usr/bin/env python3
"""Load axpe runtime words through a Pico USB/SPI bridge, with full readback."""
import argparse
import hashlib
import json
from pathlib import Path
import sys
import time
import uuid

ROOT=Path(__file__).resolve().parents[3]
sys.path.insert(0,str(ROOT/'tools'))
import configure


class Loader:
    def __init__(self, request, capacity):
        if type(capacity) is not int or not 1 <= capacity <= 256:
            raise ValueError('instruction capacity exceeds host address encoding')
        self.request=request;self.capacity=capacity
    def exchange(self, data):
        result=self.request({'op':'exchange','data':list(data)})
        if not result.get('ok'):raise RuntimeError(result.get('error','bridge failed'))
        rx=result.get('data')
        if not isinstance(rx,list) or len(rx)!=len(data) or any(type(x) is not int or not 0<=x<=255 for x in rx):
            raise RuntimeError('invalid bridge response')
        return bytes(rx)
    def status(self):return int.from_bytes(self.exchange(bytes([5,0,0]))[-2:],'big')
    def load(self, words):
        if not 0<len(words)<=self.capacity or any(type(w) is not int or not 0<=w<=0xffffffff for w in words):
            raise ValueError('payload does not fit the selected instruction store')
        self.exchange(bytes([4]))
        for address,word in enumerate(words):
            self.exchange(bytes([1,address])+word.to_bytes(4,'big'))
        if self.status() & 0x0c00:raise RuntimeError('host refused load or reported fault')
        for address,word in enumerate(words):
            got=int.from_bytes(self.exchange(bytes([2,address,0,0,0,0]))[-4:],'big')
            if got!=word:raise RuntimeError('instruction readback mismatch at '+str(address))
        self.exchange(bytes([3]))
    def wait(self, timeout_ms):
        if type(timeout_ms) is not int or timeout_ms <= 0:
            raise ValueError('completion timeout must be positive')
        end=time.monotonic()+timeout_ms/1000
        while time.monotonic()<end:
            value=self.status()
            if value & 0x0c00:raise RuntimeError('fault/refused status: '+hex(value))
            if value & 0x0200:return value
            time.sleep(.001)
        self.exchange(bytes([4]))
        raise TimeoutError('axpe completion deadline exceeded; STOP sent')


class SerialRequests:
    """Bind each reply to one command; stale responses cannot verify a load."""
    def __init__(self, port, session=None):
        self.port, self.sequence = port, 0
        self.session = session or uuid.uuid4().hex

    def __call__(self, message):
        self.sequence += 1
        identity = self.session+':'+str(self.sequence)
        message = dict(message, id=identity)
        self.port.write((json.dumps(message)+'\n').encode())
        self.port.flush()
        line = self.port.readline()
        if not line:
            raise TimeoutError('Pico bridge response deadline exceeded')
        response = json.loads(line)
        if isinstance(response, dict) and response.get('ready'):
            line = self.port.readline()
            if not line:
                raise TimeoutError('Pico bridge response deadline exceeded')
            response = json.loads(line)
        if not isinstance(response, dict) or response.get('id') != identity:
            raise RuntimeError('unmatched bridge response')
        if response.get('ok') is not True:
            raise RuntimeError(response.get('error','bridge failed'))
        return response


def bridge_settings(path, clock, reset_cycles):
    spec=json.loads(path.read_text())
    if spec['schema'] != 'org.atomix.axpe-pico-bridge.v1':
        raise ValueError('unknown bridge settings schema')
    settings={k:s['default'] for k,s in spec['parameters'].items()}
    for name in ['poll_timeout_ms','serial_timeout_ms','reset_delay_us','cs_delay_us']:
        if type(settings[name]) is not int or settings[name] <= 0:
            raise ValueError(name+' must be positive')
    # Reset counter and two-stage selection settle before the first host frame.
    settings['reset_release_us']=max(settings['reset_delay_us'],
                                    ((reset_cycles+2)*1000000+clock-1)//clock)
    return settings


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--serial',required=True)
    parser.add_argument('--profile',type=Path,required=True)
    parser.add_argument('--hex',type=Path,required=True)
    parser.add_argument('--bridge-config',type=Path,default=Path(__file__).with_name('bridge.json'))
    parser.add_argument('--output',type=Path,required=True,help='fresh JSON lab receipt')
    args=parser.parse_args()
    if args.output.exists():parser.error('receipt already exists')
    resolved=configure.resolved_config(args.profile);configure.to_make(resolved)
    if resolved['components']['board']['id']!='board.tangprimer25k-axpe':parser.error('expected axpe Primer profile')
    def values(kind):
        c=resolved['components'][kind]
        return {k:resolved['parameters'].get(kind,{}).get(k,s['default']) for k,s in c['parameters'].items()}
    board=values('board');capacity=values('pemu')['imem_words']
    clock=board['capture_clock_hz'] if board['capture_mode'] else resolved['components']['board']['make']['FPGA_INPUT_CLOCK_HZ']//2
    settings=bridge_settings(args.bridge_config,clock,board['reset_cycles'])
    words=[int(line.strip(),16) for line in args.hex.read_text().splitlines() if line.strip()]
    if not 0<len(words)<=capacity:parser.error('payload does not fit the selected store')
    receipt={'schema':'org.atomix.axpe-physical-loader.v1','status':'failed','level':'physical SPI host observations; protocol peer verdict is separate','clock_hz_declared':clock,'clock_measured':False,'profile':str(args.profile),'payload_sha256':hashlib.sha256(args.hex.read_bytes()).hexdigest(),'payload_words':len(words),'serial':args.serial,'settings':settings,'inputs_sha256':{str(p):hashlib.sha256(p.read_bytes()).hexdigest() for p in [args.profile,args.bridge_config,Path(__file__),Path(__file__).with_name('pico_bridge.py')]}}
    try:
        import serial
        with serial.Serial(args.serial,115200,timeout=settings['serial_timeout_ms']/1000) as port:
            request=SerialRequests(port)
            receipt['bridge']=request({'op':'configure','values':settings,'clock_hz':clock,'capture':bool(board['capture_mode'])})
            loader=Loader(request,capacity);loader.load(words)
            receipt['status_word']=loader.wait(settings['poll_timeout_ms'])
            receipt['status']='passed'
    except Exception as error:receipt['error']=str(error)
    args.output.parent.mkdir(parents=True,exist_ok=True)
    args.output.write_text(json.dumps(receipt,indent=2)+'\n')
    print(json.dumps(receipt))
    return 0 if receipt['status']=='passed' else 1

if __name__=='__main__':raise SystemExit(main())
