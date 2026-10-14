#!/usr/bin/env python3
"""Validate board pin/range/build contracts without synthesis or hardware."""
import hashlib
import json
from pathlib import Path
import re
import subprocess
import tempfile
import configure

ROOT=Path(__file__).resolve().parents[1]

def main():
    (ROOT/'build/pemu/primer').mkdir(parents=True,exist_ok=True)
    output=Path(tempfile.mkdtemp(prefix='contracts-',dir=ROOT/'build/pemu/primer'))
    inputs=[Path(__file__),ROOT/'tools/configure.py',ROOT/'rtl/fpga/Makefile',
        ROOT/'components/board/tangprimer25k-axpe/component.json',
        ROOT/'components/board/tangprimer25k-axpe/pins.json',
        ROOT/'components/board/tangprimer25k-axpe/axpe_primer.cst',
        ROOT/'configs/tangprimer25k-axpe.json',ROOT/'configs/tangprimer25k-axpe-capture.json']
    record={'status':'failed','scope':'resolver, pin/CST and dry build contracts; no synthesis/physical operation',
        'inputs_sha256':{str(p):hashlib.sha256(p.read_bytes()).hexdigest() for p in inputs},'checks':[],'commands':[]}
    def command(args):
        result=subprocess.run(args,cwd=ROOT,capture_output=True,text=True,timeout=30)
        log=output/f"command-{len(record['commands'])}.log"
        log.write_text(result.stdout+result.stderr)
        record['commands'].append({'argv':args,'returncode':result.returncode,'log':str(log),'log_sha256':hashlib.sha256(log.read_bytes()).hexdigest()})
        return result
    try:
        base=json.loads((ROOT/'configs/tangprimer25k-axpe-capture.json').read_text())
        for key,value in [('capture_mode',2),('reset_cycles',1),('capture_clock_hz',99999),('capture_clock_hz',5000001)]:
            data=json.loads(json.dumps(base));data['parameters']['board'][key]=value
            path=output/f'{key}-{value}.json';path.write_text(json.dumps(data)+'\n')
            try:configure.to_make(configure.resolved_config(path))
            except configure.ConfigError as error:
                record['checks'].append({'probe':f'{key}={value}','status':'rejected','diagnostic':str(error)})
            else:raise AssertionError('invalid board parameter accepted')
        pins=json.loads(inputs[4].read_text())['signals']
        cst=dict(re.findall(r'IO_LOC "([^"]+)" (\w+);',inputs[5].read_text()))
        assert pins==cst,'pin reference disagrees with CST'
        record['checks'].append({'probe':'all schematic pin references agree with CST','status':'passed'})
        make=['make','-C','rtl/fpga','COMPONENT_CONFIG='+str(inputs[6])]
        # Included makefiles are bootstrapped even under -n. Resolve once first.
        assert command([*make,'config']).returncode==0
        a=command([*make,'-n','all','PROGRAM=hello'])
        b=command([*make,'-n','all','PROGRAM=arbitrary-runtime-program'])
        assert a.returncode==b.returncode==0
        assert a.stdout==b.stdout,'runtime PROGRAM changes image recipes'
        assert 'sw/baremetal' not in a.stdout and 'chparam -set RAM_INIT_FILE' not in a.stdout
        record['checks'].append({'probe':'runtime PROGRAM does not affect image dependencies or recipes','status':'passed'})
        for key in ['RAM_INIT_FILE','ROM_INIT_FILE']:
            result=command([*make,'-n','all',key+'=/tmp/not-read.hex'])
            assert result.returncode and 'runtime-programmable profile forbids' in result.stderr
            record['checks'].append({'probe':key+' refused','status':'passed'})
        record['status']='passed'
    except (AssertionError,OSError,ValueError,subprocess.SubprocessError) as error:record['error']=str(error)
    (output/'evidence.json').write_text(json.dumps(record,indent=2)+'\n')
    print(f"axpe Primer contracts: {record['status'].upper()}: {output/'evidence.json'}")
    if 'error' in record:print(record['error'])
    return 0 if record['status']=='passed' else 1

if __name__=='__main__':raise SystemExit(main())
