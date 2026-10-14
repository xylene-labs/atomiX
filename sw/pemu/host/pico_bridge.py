"""Pico 2 MicroPython USB-line bridge to axpe's physical SPI loader.

Upload as main.py. The PC sends settings from bridge.json over USB.
Hardware execution remains a separate lab gate.
"""
import json
import sys


class Bridge:
    def __init__(self, machine, sleep_us):
        self.machine, self.sleep = machine, sleep_us
        self.spi = None
        self.pwm = None

    def configure(self, values, clock_hz, capture):
        if type(capture) is not bool:
            raise ValueError('capture must be a boolean')
        if type(clock_hz) is not int or clock_hz <= 0:
            raise ValueError('invalid axpe clock')
        if type(values['spi_hz']) is not int or not 0 < values['spi_hz'] <= clock_hz//4:
            raise ValueError('host SCLK exceeds axpe clock/4')
        pins=[values[k] for k in ['sck_gpio','mosi_gpio','miso_gpio','cs_gpio',
                                  'ena_gpio','reset_gpio','capture_gpio']]
        if len(set(pins)) != len(pins) or any(type(p) is not int or p<0 or p>28 or p in [23,24,25] for p in pins):
            raise ValueError('invalid or duplicate Pico GPIO')
        if pins[0] not in [2,6,18,22] or pins[1] not in [3,7,19] or pins[2] not in [0,4,16,20]:
            raise ValueError('pins must use Pico SPI0 SCK/MOSI/MISO functions')
        if any(type(values[k]) is not int or values[k]<=0 for k in ['reset_delay_us','reset_release_us','cs_delay_us']):
            raise ValueError('invalid bridge timing')
        Pin=self.machine.Pin
        if self.spi:
            self.ena(0); self.cs(1); self.spi.deinit()
        if self.pwm: self.pwm.deinit(); self.pwm=None
        self.values=values
        self.ena=Pin(values['ena_gpio'],Pin.OUT,value=0)
        self.reset_pin=Pin(values['reset_gpio'],Pin.OUT,value=0)
        self.cs=Pin(values['cs_gpio'],Pin.OUT,value=1)
        self.capture_pin=Pin(values['capture_gpio'],Pin.OUT,value=0)
        if capture:
            self.pwm=self.machine.PWM(self.capture_pin)
            self.pwm.freq(clock_hz); self.pwm.duty_u16(32768)
        self.spi=self.machine.SPI(0,baudrate=values['spi_hz'],polarity=0,phase=0,
                                 bits=8,firstbit=self.machine.SPI.MSB,
                                 sck=Pin(values['sck_gpio']),mosi=Pin(values['mosi_gpio']),
                                 miso=Pin(values['miso_gpio']))
        self.reset()

    def reset(self):
        if not self.spi: raise ValueError('configure first')
        self.ena(0); self.cs(1); self.reset_pin(0)
        self.sleep(self.values['reset_delay_us'])
        self.reset_pin(1); self.ena(1)
        self.sleep(self.values['reset_release_us'])

    def exchange(self, data):
        if not self.spi: raise ValueError('configure first')
        if not isinstance(data,list) or not 1<=len(data)<=6 or any(type(x) is not int or not 0<=x<=255 for x in data):
            raise ValueError('invalid SPI frame')
        tx=bytes(data);rx=bytearray(len(tx))
        self.cs(0); self.sleep(self.values['cs_delay_us'])
        try:
            self.spi.write_readinto(tx,rx)
        finally:
            self.cs(1); self.sleep(self.values['cs_delay_us'])
        return list(rx)

    def request(self, message):
        op=message['op']
        if op=='configure':
            self.configure(message['values'],message['clock_hz'],message['capture'])
            return {'ok':True,'spi':str(self.spi)}
        if op=='reset': self.reset();return {'ok':True}
        if op=='exchange':return {'ok':True,'data':self.exchange(message['data'])}
        raise ValueError('unknown bridge operation')


def main():
    import machine
    import time
    bridge=Bridge(machine,time.sleep_us)
    print(json.dumps({'ready':'axpe-pico-bridge-v1'}))
    while True:
        line=sys.stdin.readline()
        if not line: continue
        message={}
        try:
            message=json.loads(line)
            result=bridge.request(message)
        except Exception as error: result={'ok':False,'error':str(error)}
        result['id']=message.get('id') if isinstance(message,dict) else None
        print(json.dumps(result))

if __name__=='__main__':main()
