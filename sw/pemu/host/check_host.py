#!/usr/bin/env python3
"""Transport fakes test wire encoding/refusals; they are not Pico evidence."""
import json
from pathlib import Path
import unittest
from unittest.mock import patch
from types import SimpleNamespace
from axpe_host import Loader, SerialRequests, bridge_settings
from pico_bridge import Bridge


class FakeChip:
    def __init__(self, corrupt=False, status=0):
        self.words = {}; self.frames = []; self.corrupt = corrupt; self.flags = status
    def __call__(self, message):
        data=bytes(message['data']); self.frames.append(data)
        rx=bytearray(len(data))
        if data[0]==1:
            self.words[data[1]]=int.from_bytes(data[2:],'big')
        elif data[0]==2:
            word=self.words[data[1]] ^ int(self.corrupt)
            rx[-4:]=word.to_bytes(4,'big')
        elif data[0]==5:
            rx[-2:]=self.flags.to_bytes(2,'big')
        return {'ok':True,'data':list(rx)}


class Pin:
    OUT=1
    def __init__(self, number, mode=None, value=0):self.number,self.value=number,value
    def __call__(self, value):self.value=value

class SPI:
    MSB=0
    def __init__(self, bus, **kw):self.bus,self.kw=bus,kw;self.fail=False;self.closed=False
    def deinit(self):self.closed=True
    def write_readinto(self, tx, rx):
        if self.fail:raise OSError('injected SPI error')
        rx[:]=tx

class PWM:
    def __init__(self,pin):self.pin=pin
    def freq(self,value):self.frequency=value
    def duty_u16(self,value):self.duty=value
    def deinit(self):self.closed=True


class HostChecks(unittest.TestCase):
    def test_complete_raw_readback_before_run(self):
        chip=FakeChip();Loader(chip,64).load([0x12345678,0x89abcdef])
        self.assertEqual(chip.frames[0],b'\x04')
        self.assertEqual(chip.frames[1],bytes.fromhex('010012345678'))
        self.assertEqual(chip.frames[2],bytes.fromhex('010189abcdef'))
        self.assertEqual(chip.frames[-3:-1],[bytes.fromhex('020000000000'),bytes.fromhex('020100000000')])
        self.assertEqual(chip.frames[-1],b'\x03')
    def test_mismatch_and_refused_never_run(self):
        for chip in [FakeChip(corrupt=True),FakeChip(status=0x0800),FakeChip(status=0x0400)]:
            with self.subTest(flags=chip.flags,corrupt=chip.corrupt):
                with self.assertRaises(RuntimeError):Loader(chip,64).load([0x12345678])
                self.assertNotIn(b'\x03',chip.frames)
    def test_nondefault_capacity_and_invalid_words(self):
        for words in [list(range(17)),[],[True],[-1],[1<<32]]:
            chip=FakeChip()
            with self.assertRaises(ValueError):Loader(chip,16).load(words)
            self.assertEqual(chip.frames,[])
        chip=FakeChip();Loader(chip,16).load(list(range(16)))
        self.assertEqual(chip.words[15],15)
    def test_halt_fault_and_bounded_stop(self):
        self.assertEqual(Loader(FakeChip(status=0x0200),64).wait(2),0x0200)
        with self.assertRaises(RuntimeError):Loader(FakeChip(status=0x0400),64).wait(2)
        chip=FakeChip()
        with patch('axpe_host.time.monotonic',side_effect=[0,0,1]),patch('axpe_host.time.sleep'):
            with self.assertRaises(TimeoutError):Loader(chip,64).wait(2)
        self.assertEqual(chip.frames[-1],b'\x04')
    def test_malformed_transport_data(self):
        for data in [[],[256],[True],'x']:
            with self.assertRaises(RuntimeError):Loader(lambda m,data=data:{'ok':True,'data':data},64).exchange(b'\x05')
    def test_sequence_and_stale_reply(self):
        class Port:
            def __init__(self,lines):self.lines=iter(lines);self.sent=[]
            def write(self,x):self.sent.append(json.loads(x))
            def flush(self):pass
            def readline(self):return next(self.lines,b'')
        port=Port([b'{"ready":"axpe-pico-bridge-v1"}\n',b'{"ok":true,"id":"test:1"}\n'])
        self.assertTrue(SerialRequests(port,session='test')({'op':'reset'})['ok'])
        self.assertEqual(port.sent[0]['id'],'test:1')
        for line in [b'{"ok":true,"id":0}',b'{"ok":true,"id":"old-session:1"}',b'[]',b'']:
            with self.assertRaises((RuntimeError,TimeoutError)):SerialRequests(Port([line]))({'op':'reset'})
    def settings(self,clock=1000000,reset=8):
        return bridge_settings(Path(__file__).with_name('bridge.json'),clock,reset)
    def bridge(self):
        delays=[]
        return Bridge(SimpleNamespace(Pin=Pin,SPI=SPI,PWM=PWM),delays.append),delays
    def test_gpio_timing_capture_and_spi_failure_cleanup(self):
        bridge,delays=self.bridge();values=self.settings()
        values.update(cs_gpio=8,ena_gpio=9,reset_gpio=10,capture_gpio=11,spi_hz=50000,cs_delay_us=7)
        bridge.configure(values,1000000,True)
        self.assertEqual(bridge.pwm.frequency,1000000)
        self.assertEqual(bridge.cs.number,8);self.assertEqual(bridge.spi.kw['baudrate'],50000)
        self.assertEqual(bridge.exchange([1,0,0x12,0x34,0x56,0x78]),[1,0,0x12,0x34,0x56,0x78])
        self.assertEqual(delays[-2:],[7,7]);self.assertEqual(bridge.cs.value,1)
        bridge.spi.fail=True
        with self.assertRaises(OSError):bridge.exchange([5,0,0])
        self.assertEqual(bridge.cs.value,1)
        oldspi,oldpwm=bridge.spi,bridge.pwm
        bridge.configure(values,1000000,False)
        self.assertTrue(oldspi.closed);self.assertTrue(oldpwm.closed)
        self.assertIsNone(bridge.pwm);self.assertEqual(bridge.capture_pin.value,0)
    def test_config_refusals_before_gpio_or_spi_creation(self):
        for override in [{'spi_hz':250001},{'sck_gpio':1},{'cs_gpio':18},{'cs_delay_us':0},{'reset_gpio':25}]:
            bridge,_=self.bridge();values=dict(self.settings(),**override)
            with self.assertRaises(ValueError):bridge.configure(values,1000000,True)
            self.assertIsNone(bridge.spi)
    def test_alternate_spi0_mapping_reaches_driver(self):
        bridge,_=self.bridge();values=self.settings();values.update(sck_gpio=2,mosi_gpio=3,miso_gpio=4)
        bridge.configure(values,1000000,False)
        self.assertEqual([bridge.spi.kw[k].number for k in ['sck','mosi','miso']],[2,3,4])
    def test_reset_release_tracks_nondefault_profile(self):
        settings=self.settings(100000,65535)
        self.assertEqual(settings['reset_release_us'],655370)
        bridge,delays=self.bridge();settings['spi_hz']=10000
        bridge.configure(settings,100000,False)
        self.assertEqual(delays,[1000,655370])
    def test_invalid_frames_do_not_select(self):
        bridge,_=self.bridge();bridge.configure(self.settings(),1000000,False)
        for data in [[],[0]*7,[256],[True],'x']:
            with self.assertRaises(ValueError):bridge.exchange(data)
            self.assertEqual(bridge.cs.value,1)

if __name__=='__main__':unittest.main()
