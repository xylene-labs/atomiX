#!/usr/bin/env python3
"""Build AT24C256 byte operations using the selected runtime clock profile."""
import argparse
import hashlib
import importlib.util
import json
from pathlib import Path
import sys
HERE=Path(__file__).resolve().parent
FIRMWARE=HERE.parent
ROOT=FIRMWARE.parents[2]
sys.path.insert(0,str(FIRMWARE.parent/'as'))
from axpe_as import assemble,format_listing,AsmError
sys.path.insert(0,str(FIRMWARE))
from build_demos import settings as rates, i2c_period


def settings(overrides=None):
    owner=json.loads((HERE/'parameters.json').read_text())
    values={k:s['default'] for k,s in owner['parameters'].items()}
    overrides={} if overrides is None else overrides
    if not isinstance(overrides,dict):raise ValueError('EEPROM overrides must be an object')
    if overrides.keys()-values.keys():raise ValueError('unknown EEPROM parameter')
    values.update(overrides)
    if any(type(v) is not int for v in values.values()):raise ValueError('EEPROM settings must be integers')
    if not 0x50<=values['device_address']<=0x57:raise ValueError('AT24C256 device address must be in 0x50..0x57')
    if not 0<=values['word_address']<32768:raise ValueError('AT24C256 word address must be in 0..32767')
    if not 0<=values['data_byte']<=255:raise ValueError('data byte must be in 0..255')
    if any(values[k]<=0 for k in ['write_timeout_ms','poll_interval_ms','program_timeout_ms','read_iterations','write_iterations']):raise ValueError('EEPROM deadlines/interval must be positive')
    if values['poll_interval_ms']>values['write_timeout_ms']:raise ValueError('poll interval exceeds write timeout')
    return values


def programs(profile, capacity, values):
    values=settings(values);clock=rates(profile)
    common={'CLK_HZ':clock['clock_hz'],'SCL_HZ':clock['i2c_hz'],
            'BIT_PERIOD':i2c_period(clock),'DEV_ADDR':values['device_address'],
            'WORD_ADDR':values['word_address'],'DATA_BYTE':values['data_byte']}
    result={}
    for name,source,extra in [('write','write.s',{}),('poll','poll.s',{}),
                             ('read-low','read.s',{'RETURN_SHIFT':0}),('read-high','read.s',{'RETURN_SHIFT':4})]:
        path=HERE/source
        result[name]=assemble(path.read_text(),path,capacity,dict({k:v for k,v in common.items() if k not in {'WORD_ADDR','DATA_BYTE'} or (k=='WORD_ADDR' and source!='poll.s') or (k=='DATA_BYTE' and source=='write.s')},**extra))
    return result,clock


def build(profile,output,capacity,overrides=None):
    if output.exists():raise ValueError('output already exists; preserve receipt and use a fresh directory')
    values=settings(overrides);assembled,clock=programs(profile,capacity,values)
    paths=[Path(__file__),HERE/'parameters.json',profile.resolve(),FIRMWARE/'demo.json',
           FIRMWARE/'build_demos.py',FIRMWARE/'i2c.s',FIRMWARE.parent/'as/axpe_as.py',
           ROOT/'tools/axpe_isa.py',FIRMWARE.parent/'isa/axpe-isa.json',*sorted(HERE.glob('*.s'))]
    hashes={str(p):hashlib.sha256(p.read_bytes()).hexdigest() for p in paths}
    output.mkdir(parents=True)
    for name,program in assembled.items():
        (output/(name+'.hex')).write_text(''.join(f'{i.word:08x}\n' for i in program))
        (output/(name+'.listing')).write_text(format_listing(program)+'\n')
    record={'schema':'org.atomix.axpe-eeprom-build.v1','scope':'runtime payload assembly; no physical EEPROM access',
        'parameters':values,'runtime_settings':clock,'i2c_period':i2c_period(clock),'imem_words':capacity,
        'word_counts':{k:len(v) for k,v in assembled.items()},'inputs_sha256':hashes,
        'outputs_sha256':{p.name:hashlib.sha256(p.read_bytes()).hexdigest() for p in sorted(output.iterdir())}}
    (output/'profile.json').write_text(json.dumps(record,indent=2)+'\n')
    return record


def main():
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('--profile',type=Path,required=True);p.add_argument('--output',type=Path,required=True)
    p.add_argument('--imem-words',type=int,required=True)
    for name in ['device_address','word_address','data_byte']:
        p.add_argument('--'+name.replace('_','-'),type=lambda s:int(s,0))
    args=p.parse_args()
    try:
        record=build(args.profile,args.output,args.imem_words,{k:getattr(args,k) for k in ['device_address','word_address','data_byte'] if getattr(args,k) is not None})
    except (ValueError,OSError,AsmError) as error:print('EEPROM build: FAIL:',error);return 1
    print('EEPROM build: PASS:',record['word_counts']);return 0

if __name__=='__main__':raise SystemExit(main())
