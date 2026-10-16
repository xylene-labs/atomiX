#!/usr/bin/env python3
"""Simulate the physical axpe adapter with resolved board clock/reset knobs."""
from pathlib import Path
import argparse
import hashlib
import importlib.util
import json
import subprocess
import tempfile
import configure
import axpe_eeprom_mutations

ROOT = Path(__file__).resolve().parents[1]


def sha(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def run(profile, runtime_profile=None):
    resolved = configure.resolved_config(profile)
    configure.to_make(resolved)
    if {k: v['id'] for k, v in resolved['components'].items()} != {
            'board': 'board.tangprimer25k-axpe', 'pemu': 'pemu.axpe'}:
        raise ValueError('expected the axpe Primer board and pemu components')
    values = {}
    for kind, component in resolved['components'].items():
        values[kind] = {k: resolved['parameters'].get(kind, {}).get(k, s['default'])
                        for k, s in component['parameters'].items()}
    if values['pemu']['uio_pins'] != 8:
        raise ValueError('physical axpe chip adapter requires eight uio pins')
    board = resolved['components']['board']
    input_hz = board['make']['FPGA_INPUT_CLOCK_HZ']
    clock = values['board']['capture_clock_hz'] if values['board']['capture_mode'] else input_hz//2
    divisor = input_hz//clock
    capture_divisor = input_hz//values['board']['capture_clock_hz']
    if input_hz % clock or capture_divisor % 2:
        raise ValueError('simulation needs an even integer oscillator-to-capture ratio')
    runtime_profile = runtime_profile or ROOT/f'sw/pemu/firmware/profiles/primer/{clock}.json'
    output = Path(tempfile.mkdtemp(prefix='check-', dir=ROOT / 'build/pemu/primer'))
    sources = [configure.resolve_source(c, s) for c in resolved['components'].values()
               for s in c['sources']]
    bench = ROOT / 'sim/pemu/axpe_primer_tb.cpp'
    sim = ROOT / 'sim/pemu/axpe_primer_sim.sv'
    deps = [Path(__file__).resolve(), ROOT/'tools/axpe_eeprom_mutations.py', ROOT/'tools/configure.py', profile.resolve(), runtime_profile.resolve(),
            *sources, bench, sim, *sorted((ROOT/'sim/pemu').glob('*.h')),
            *sorted((ROOT/'sw/pemu/firmware').rglob('*.s')),
            ROOT/'sw/pemu/firmware/eeprom/build.py',ROOT/'sw/pemu/firmware/eeprom/parameters.json',ROOT/'sim/pemu/eeprom.json',
            ROOT/'sw/pemu/firmware/build_demos.py', ROOT/'sw/pemu/firmware/demo.json',
            ROOT/'sw/pemu/as/axpe_as.py', ROOT/'tools/axpe_isa.py',
            *sorted((ROOT/'sw/pemu/isa').glob('*')), ROOT/'sw/pemu/model/axpe_model.c',
            ROOT/'sw/pemu/model/axpe_model.h',
            *[Path(c['_path']) for c in resolved['components'].values()]]
    record = {'schema': 'org.atomix.axpe-primer-sim.v1', 'status': 'failed',
              'scope': 'digital FPGA adapter simulation; no physical operation or analog claim',
              'profile': str(profile), 'parameters': values, 'clock_hz': clock,
              'inputs_sha256': {str(p):sha(p) for p in deps}, 'commands': []}
    try:
        spec = importlib.util.spec_from_file_location('build_demos', ROOT/'sw/pemu/firmware/build_demos.py')
        builder = importlib.util.module_from_spec(spec); spec.loader.exec_module(builder)
        if builder.settings(runtime_profile)['clock_hz'] != clock:
            raise ValueError('runtime payload clock does not match the board clock')
        record['runtime'] = builder.build(runtime_profile, output/'fw', values['pemu']['imem_words'])
        spec = importlib.util.spec_from_file_location('build_eeprom', ROOT/'sw/pemu/firmware/eeprom/build.py')
        eeprom = importlib.util.module_from_spec(spec); spec.loader.exec_module(eeprom)
        cases = [('default', {}),('nondefault', {'device_address':0x53,'word_address':0x1234,'data_byte':0xee}),
                 ('first-byte', {'word_address':0,'data_byte':0}),
                 ('last-byte', {'device_address':0x57,'word_address':0x7fff,'data_byte':0xff})]
        peer_spec=json.loads((ROOT/'sim/pemu/eeprom.json').read_text())
        peer_cycles=peer_spec['parameters']['write_cycles']['default']
        limits=peer_spec['parameters']['write_cycles']
        if type(peer_cycles) is not int or not limits['minimum']<=peer_cycles<=limits['maximum']:
            raise ValueError('invalid EEPROM peer write-cycle setting')
        record['eeprom_peer_write_cycles']=peer_cycles
        record['eeprom'] = {}
        for name, overrides in cases:
            record['eeprom'][name] = eeprom.build(runtime_profile, output/'eeprom'/name, values['pemu']['imem_words'], overrides)
        (output/'eeprom/cases.txt').write_text(f"{builder.i2c_period(builder.settings(runtime_profile))} {clock} {builder.settings(runtime_profile)['i2c_hz']} {builder.settings(runtime_profile)['i2c_guard_ns']}\n"+
            ''.join(f"{name} {r['parameters']['device_address']} {r['parameters']['word_address']} {r['parameters']['data_byte']} {min(peer_cycles+peer_cycles//2,limits['maximum']) if name=='nondefault' else peer_cycles}\n"
                    for name,r in record['eeprom'].items()))

        flags = [f"+define+{s['define']}={values[kind][name]}" for kind,c in resolved['components'].items()
                 for name,s in c['parameters'].items()]
        command = ['verilator','--cc','--exe','--build','-j','2','-Wall',
                   '-Wno-DECLFILENAME', '-I'+str(ROOT/'sw/pemu/isa'), *flags,
                   '--top-module','axpe_primer_sim','--Mdir',str(output/'obj'),
                   '-CFLAGS', f"-DPRIMER_DIVISOR={divisor} "
                   f"-DPRIMER_CAPTURE_DIVISOR={capture_divisor} -DPRIMER_CAPTURE_MODE={values['board']['capture_mode']} "
                   f"-DPRIMER_RESET_CYCLES={values['board']['reset_cycles']}",
                   *map(str,sources),str(sim),str(bench),str(ROOT/'sw/pemu/model/axpe_model.c')]
        for name, argv in [('version',['verilator','--version']),('build',command), *[(f'seed-{seed}',
               [str(output/'obj/Vaxpe_primer_sim'),str(output/'fw'),str(output/'eeprom'),
                '+verilator+rand+reset+2',f'+verilator+seed+{seed}']) for seed in [1,17,91]]]:
            log=output/(name+'.log')
            with log.open('w') as stream:
                result=subprocess.run(argv,cwd=ROOT,stdout=stream,stderr=subprocess.STDOUT,timeout=180)
            record['commands'].append({'argv':argv,'returncode':result.returncode,'log':str(log),'log_sha256':sha(log)})
            if result.returncode:raise RuntimeError(log.read_text()[-3500:])
        record['eeprom_mutations']=axpe_eeprom_mutations.check(output,runtime_profile,values['pemu']['imem_words'])
        record['status']='passed'
    except (OSError,ValueError,RuntimeError,subprocess.SubprocessError) as error:
        record['error']=str(error)
    if any(sha(p)!=h for p,h in record['inputs_sha256'].items()):
        record['status']='failed';record['error']='inputs changed during check'
    (output/'evidence.json').write_text(json.dumps(record,indent=2)+'\n')
    print(f"axpe Primer {profile.name}: {record['status'].upper()}: {output/'evidence.json'}")
    if record.get('error'):print(record['error'])
    return record['status']=='passed'


def pads_check():
    output=Path(tempfile.mkdtemp(prefix='pads-',dir=ROOT/'build/pemu/primer'))
    sources=[ROOT/p for p in ['components/pemu/axpe/axpe_pads.sv',
        'components/board/tangprimer25k-axpe/axpe_primer_pads.sv',
        'sim/pemu/axpe_primer_pads_tb.sv']]
    record={'schema':'org.atomix.axpe-primer-pads.v1','status':'failed',
        'scope':'isolated four-state pad boundary; full core excluded; no analog/physical operation',
        'inputs_sha256':{str(p):sha(p) for p in [Path(__file__),*sources]},'commands':[]}
    try:
        for name,argv in [('version',['iverilog','-V']),('build',['iverilog','-g2012',
            '-s','axpe_primer_pads_tb','-o',str(output/'pads.vvp'),*map(str,sources)]),
            ('run',['vvp',str(output/'pads.vvp')])]:
            log=output/(name+'.log')
            with log.open('w') as stream:
                result=subprocess.run(argv,cwd=ROOT,stdout=stream,stderr=subprocess.STDOUT,timeout=60)
            record['commands'].append({'argv':argv,'returncode':result.returncode,'log':str(log),'log_sha256':sha(log)})
            if result.returncode:raise RuntimeError(log.read_text()[-3500:])
        record['status']='passed'
    except (OSError,RuntimeError,subprocess.SubprocessError) as error:record['error']=str(error)
    if any(sha(p)!=h for p,h in record['inputs_sha256'].items()):
        record['status']='failed';record['error']='inputs changed during check'
    (output/'evidence.json').write_text(json.dumps(record,indent=2)+'\n')
    print(f"axpe Primer pads: {record['status'].upper()}: {output/'evidence.json'}")
    if record.get('error'):print(record['error'])
    return record['status']=='passed'


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--profile',type=Path,action='append')
    parser.add_argument('--runtime-profile',type=Path,help='explicit runtime settings for a custom board profile')
    parser.add_argument('--pads-only',action='store_true',help='optional isolated Icarus pad check')
    args=parser.parse_args()
    (ROOT/'build/pemu/primer').mkdir(parents=True,exist_ok=True)
    if args.pads_only:return 0 if pads_check() else 1
    profiles=args.profile or [ROOT/'configs/tangprimer25k-axpe.json',ROOT/'configs/tangprimer25k-axpe-capture.json']
    return 0 if all([run(p,args.runtime_profile) for p in profiles]) else 1

if __name__=='__main__':
    raise SystemExit(main())
