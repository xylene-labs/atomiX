# axpe Tang Primer 25K bench adapter

This board component instantiates the unchanged axpe chip, host and writable
instruction store. `configs/tangprimer25k-axpe.json` selects 64 words and a
nominal 25 MHz clock from the Dock oscillator's dedicated divide-by-two block.
`configs/tangprimer25k-axpe-capture.json` selects an external nominal 1 MHz
Pico PWM clock and an eight-cycle reset counter. Both expose their active clock
on J6 pin 8. Clock mode is selected at build time; change images under reset.
Runtime instruction words never enter the FPGA image or its artifact key.

These are simulation and open-flow implementation results. No axpe physical
operation has been recorded. The [hardware plan](../../../docs/notes/axpe-hardware-test-plan-2026-10-12.md)
owns lab acceptance and the remaining physical EEPROM, independent-peer, repetition,
capture and recovery work. The selected ASIC sources and GDS are unchanged.

The inferred FPGA store uses flip-flops (`-nobram -nolutram`): the initial
BRAM implementation failed hold checks. A fabric capture divider also failed
hold checks; DCS insertion failed clock packing and cascaded CLKDIVs failed
routing. Those failed attempts remain recorded. External capture clocking
avoids those paths without waiving hold checks. Its actual frequency and
quality still need measurement on the delivered Pico/FPGA kit.

## Wiring reference

[pins.json](pins.json) binds the map to page 1 of the
[Sipeed Dock 60033 schematic](https://api.dl.sipeed.com/file/download?file_url=TANG/Primer_25K/02_Schematic/Tang_Primer_25K_Dock_60033_Schematic.pdf).
Verify the delivered Dock revision, header orientation and voltage before
wiring. Each Pmod has ground on pins 5/11 and 3.3 V on pins 6/12. Connect common
ground; the FPGA and Pico are powered through their normal USB paths, without
connecting their power outputs together. Release/disconnect peer paths for a
real power-loss test. The constraints select LVCMOS33; 5 V peers are unsuitable.

| J6 pin | Loader/control | Default Pico GPIO |
|---|---|---|
| 1 | SCLK | 18 |
| 3 | MOSI | 19 |
| 7 | active-low CS | 17 |
| 9 | MISO | 16 |
| 2 | design enabled | 20 |
| 4 | active-low reset | 21 |
| 8 | active clock reference | analyzer input |
| 10 | external capture clock | 22, PWM in capture mode |

| J4 pin | axpe pin | Runtime protocol use |
|---|---|---|
| 1 | uio[0] | UART TX → USB–UART RX |
| 3 | uio[1] | UART RX ← USB–UART TX |
| 7 | uio[2] | I2C SDA |
| 9 | uio[3] | I2C SCL |
| 2 | uio[4] | workload SPI SCK |
| 4 | uio[5] | workload SPI MOSI |
| 8 | uio[6] | workload SPI MISO |
| 10 | uio[7] | workload SPI active-low CS |

The workload SPI port is separate from the J6 host SPI port. I2C requires
external/module pull-ups to 3.3 V. S1 asserts reset. Protocol outputs are released
after reset/deselection. The initial SPI/I2C demo peers are simulation peers;
the I2C demo is not an EEPROM driver.

## Reproduction and bench entry

The [workflow](../../../docs/workflow.md) is the command authority. It lists
`pemu-primer-check`, optional `pemu-primer-pads-check`, and open Gowin image
build/evidence commands for both profiles. Each simulation attempt writes a
fresh receipt under `build/pemu/primer/`; hardware build receipts bind the image,
profile, timing report and tools. The compact preflight benchmark additionally
binds all adapter/chip/ISA/build inputs and the failed raw logs.

The [Pico bridge source](../../../sw/pemu/host/pico_bridge.py) is a MicroPython
prototype: install it as `main.py` on the Pico after selecting a Pico 2 firmware
and recording its exact version/hash. It receives settings from the PC's
[bridge.json](../../../sw/pemu/host/bridge.json), uses SPI0 mode 0/MSB first,
and generates capture PWM only for that profile. API/pin choices follow the
[MicroPython RP2 reference](https://docs.micropython.org/en/latest/rp2/quickref.html).
Pico execution, SPI rate and PWM accuracy remain untested. GPIO/timing settings
are adjustable and exercised at non-default values by transport fakes; custom
SPI pins must use valid SPI0 functions and avoid Pico reserved pins. Adjust the
wiring together with these settings.

After verifying wiring and programming **FPGA SRAM**, use the PC loader command
in the workflow with a newly assembled runtime payload for the image's clock.
It asserts reset, waits for the selected reset counter, sends STOP, writes every
word, reads every word back, and sends RUN only after all comparisons pass.
Replies carry request IDs; stale replies, malformed data, refusal/fault and
bounded completion deadlines fail. Timeout sends STOP. A fresh JSON receipt
records declared clock/settings/payload/source hashes and host status.

HALT/readback success is a host-port observation. It needs an independent peer
and captured waveform to become a UART/SPI/I2C result. Add image hash, actual
board/Pico identities, wiring and measured clock to the lab record; the loader
cannot query or prove which FPGA image was physically programmed. The separate
[EEPROM runtime runner](../../../sw/pemu/firmware/eeprom/README.md) adds
byte write/read/poll and scratch preservation, with digital verification.
Physical Pico/EEPROM execution, remaining peers, capture/repetition and recovery
remain open PE-09 work.
