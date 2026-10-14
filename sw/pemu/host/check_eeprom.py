#!/usr/bin/env python3
"""Host polling/restore tests with transport fakes; no EEPROM is touched."""
import unittest
import json
import hashlib
import io
import sys
from contextlib import redirect_stdout
from types import SimpleNamespace
import eeprom
from pathlib import Path
from tempfile import TemporaryDirectory
from unittest.mock import patch
from eeprom import EepromClient,builder

ROOT=Path(__file__).resolve().parents[3]
PROFILE=ROOT/'sw/pemu/firmware/profiles/primer/1000000.json'

class HostEepromChecks(unittest.TestCase):
    def client(self,values=None):return EepromClient(lambda w,t:0x0280,PROFILE,64,values)
    def test_full_byte_decoder_has_no_error_alias(self):
        client=self.client()
        for value in range(256):
            with patch.object(client,'run',side_effect=[0x80|(value&15),0x80|(value>>4)]):
                self.assertEqual(client.read_byte(),value)
        for values in [[0,0x80],[0x80,0],[0xee,0x80],[0x80,0xff]]:
            with patch.object(client,'run',side_effect=values),self.assertRaises(RuntimeError):client.read_byte()
    def test_busy_then_ready_and_nondefault_interval(self):
        instant=[0.0]
        def pause(seconds):instant[0]+=seconds
        client=EepromClient(None,PROFILE,64,{'write_timeout_ms':20,'poll_interval_ms':3},clock=lambda:instant[0],sleep=pause)
        with patch.object(client,'run',side_effect=[0,0,0x80]):self.assertEqual(client.wait_ready(),3)
        self.assertAlmostEqual(instant[0],.006)
    def test_busy_and_late_reply_fail_with_bounded_deadline(self):
        instant=[0.0];client=EepromClient(None,PROFILE,64,{'write_timeout_ms':5,'poll_interval_ms':2},clock=lambda:instant[0],sleep=lambda n:instant.__setitem__(0,instant[0]+n))
        with patch.object(client,'run',return_value=0),self.assertRaises(TimeoutError):client.wait_ready()
        self.assertEqual(instant[0],.005)
        instant[0]=0
        def late(name):instant[0]=.01;return 0x80
        with patch.object(client,'run',side_effect=late),self.assertRaises(TimeoutError):client.wait_ready()
    def test_backup_before_write_repeats_and_restores(self):
        client=self.client({'data_byte':0xee});events=[];memory=[0x37]
        def write(value):events.append(('write',value));memory[0]=value
        with patch.object(client,'read_byte',side_effect=lambda:memory[0]),patch.object(client,'write_byte',side_effect=write),patch.object(client,'wait_ready'):
            report=client.exercise(3,2,lambda b:events.append(('backup',dict(b))))
        self.assertEqual(events[0][0],'backup');self.assertEqual(events[1:],[('write',0xee),('write',0xef),('write',0x37)])
        self.assertEqual(memory[0],0x37);self.assertEqual(report['restoration'],'verified')
        self.assertEqual(report['reads_passed'],3);self.assertEqual(report['writes_passed'],2)
    def test_transport_failure_after_device_write_still_restores(self):
        client=self.client();writes=[];memory=[0xa9]
        def write(value):
            writes.append(value);memory[0]=value
            if len(writes)==1:raise OSError('lost reply after write')
        with patch.object(client,'read_byte',side_effect=lambda:memory[0]),patch.object(client,'write_byte',side_effect=write),patch.object(client,'wait_ready'),self.assertRaises(OSError):client.exercise(1,1,lambda b:None)
        self.assertEqual(memory[0],0xa9);self.assertEqual(client.last_report['restoration'],'verified')
    def test_backup_failure_never_writes_and_read_only_never_writes(self):
        client=self.client()
        def bad_backup(backup):raise OSError('cannot persist backup')
        with patch.object(client,'read_byte',return_value=0x91),patch.object(client,'write_byte') as write:
            with self.assertRaises(OSError):client.exercise(1,1,bad_backup)
            write.assert_not_called()
            report=client.exercise(2,0,lambda b:None);write.assert_not_called()
            self.assertEqual(report['restoration'],'no writes requested')
    def test_write_protected_mismatch_and_failed_restore_report(self):
        client=self.client()
        with patch.object(client,'read_byte',return_value=0x21),patch.object(client,'write_byte'),patch.object(client,'wait_ready'),self.assertRaises(RuntimeError):client.exercise(1,1,lambda b:None)
        self.assertEqual(client.last_report['restoration'],'verified')
        with patch.object(client,'read_byte',return_value=0x21),patch.object(client,'write_byte',side_effect=OSError('lost link')),patch.object(client,'wait_ready'),self.assertRaises(OSError):client.exercise(1,1,lambda b:None)
        self.assertEqual(client.last_report['restoration'],'failed')
    def test_program_shape_counts_bounds_and_parameter_wiring(self):
        values=builder.settings({'device_address':0x53,'word_address':0x1234,'data_byte':0xee,'program_timeout_ms':27,'read_iterations':3,'write_iterations':2})
        programs,clock=builder.programs(PROFILE,64,values)
        self.assertEqual({k:len(v) for k,v in programs.items()},{'write':54,'poll':46,'read-low':60,'read-high':60})
        observed=[]
        client=EepromClient(lambda w,t:observed.append((w,t)) or 0x0280,PROFILE,64,values)
        client.run('write');self.assertEqual(observed[0][1],27)
        self.assertEqual(observed[0][0],[i.word for i in programs['write']])
        for overrides in [{'word_address':32768},{'word_address':-1},{'device_address':0x58},{'data_byte':256},{'data_byte':True},{'write_timeout_ms':0},{'poll_interval_ms':1001},{'read_iterations':0},{'bogus':1}]:
            with self.subTest(overrides=overrides),self.assertRaises(ValueError):builder.settings(overrides)
        with self.assertRaises(builder.AsmError):builder.programs(PROFILE,59,values)
        with TemporaryDirectory() as directory:
            out=Path(directory)/'fresh';builder.build(PROFILE,out,64,values)
            with self.assertRaises(ValueError):builder.build(PROFILE,out,64,values)
    def test_write_test_never_uses_unchanged_original_as_its_pattern(self):
        client=self.client({'data_byte':0x21});attempts=[]
        with patch.object(client,'read_byte',return_value=0x21),patch.object(client,'write_byte',side_effect=attempts.append),patch.object(client,'wait_ready'),self.assertRaises(RuntimeError):client.exercise(1,1,lambda b:None)
        self.assertEqual(attempts,[0xa1,0x21])
    def test_runtime_input_change_aborts_before_transport(self):
        with TemporaryDirectory() as directory:
            profile=Path(directory)/'runtime.json';profile.write_bytes(PROFILE.read_bytes())
            executed=[];client=EepromClient(lambda w,t:executed.append(w) or 0x0280,profile,64)
            profile.write_text(profile.read_text()+' ')
            with self.assertRaises(RuntimeError):client.run('write')
            self.assertEqual(executed,[])
    def test_interrupted_write_restores_backup_and_records_failed_cli_run(self):
        class Port:
            def __enter__(self):return self
            def __exit__(self,*args):pass
        class InterruptingLoader:
            def __init__(self,*args):self.loads=0
            def load(self,words):
                self.loads+=1
                if self.loads==3:raise KeyboardInterrupt()
            def wait(self,timeout):return 0x0280
        with TemporaryDirectory() as directory:
            base=Path(directory);image=base/'image.json';parameters=base/'settings.json';output=base/'run'
            profile=ROOT/'configs/tangprimer25k-axpe-capture.json'
            image.write_text(json.dumps({'result':'PASS','config':{'sha256':hashlib.sha256(profile.read_bytes()).hexdigest()},'bitstream':{'sha256':'0'*64,'path':'transport-fake-only'}}))
            parameters.write_text(json.dumps({'schema':'org.atomix.axpe-eeprom-profile.v1','settings':{'read_iterations':1,'write_iterations':1}}))
            args=['eeprom.py','--serial','transport-fake','--profile',str(profile),'--runtime-profile',str(PROFILE),'--image-receipt',str(image),'--scratch-address','0x1234','--parameters',str(parameters),'--write-test','--output',str(output)]
            with patch.object(sys,'argv',args),patch.dict(sys.modules,{'serial':SimpleNamespace(Serial=lambda *a,**kw:Port())}),patch.object(eeprom,'SerialRequests',return_value=lambda m:{'ok':True}),patch.object(eeprom,'Loader',InterruptingLoader),redirect_stdout(io.StringIO()):
                self.assertEqual(eeprom.main(),1)
            result=json.loads((output/'evidence.json').read_text())
            self.assertEqual(result['status'],'failed');self.assertEqual(result['error_type'],'KeyboardInterrupt')
            self.assertEqual(result['result']['restoration'],'verified')
            self.assertEqual(json.loads((output/'backup.json').read_text())['original_byte'],0)
    def test_bad_halting_status_and_refused_write_are_errors(self):
        for status in [0,0x0680,0x0a80,False]:
            client=EepromClient(lambda w,t:status,PROFILE,64)
            with self.assertRaises(RuntimeError):client.run('poll')
        client=self.client()
        with patch.object(client,'run',return_value=0),self.assertRaises(RuntimeError):client.write_byte(0x21)

if __name__=='__main__':unittest.main()
