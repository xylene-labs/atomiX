# Demo wiring and reload procedure

This is the logical wiring contract for the shipped payloads, prepared for
review. No physical carrier, Pmod or protocol peer has been tested. Final
connector numbers must be checked against the delivered board revision.
Tiny Tapeout's [ETR documentation](https://tinytapeout.com/specs/pcb-etr/)
describes an RP2350 host and Pmod expansion. The organizer follow-up specifies
3.3 V digital demo-board I/O; it supplies no CMOS5L pad characterization.

## Loader host

| Chip signal | Connect to |
|---|---|
| `clk` | Continuous supplied chip clock, using the reviewed timing target |
| `rst_n` | Board reset control, active low |
| `ena` | Harness design selection |
| `ui_in[0]` | Host SPI SCLK |
| `ui_in[1]` | Host SPI MOSI |
| `ui_in[2]` | Host SPI CS, idle high |
| `uo_out[0]` | Host SPI MISO; sampled only during CS assertion |

The loader uses SPI mode 0, MSB first, with `SCLK <= clk/4`. At a supplied
40 MHz clock, that upper bound is 10 MHz; the simulated host uses `clk/8`.
The host clock is separate from firmware's SPI SCK. With CS high, `uo_out[0]`
belongs to the firmware's published result. Reserve `ui_in[3..7]` for firmware
inputs and keep unused inputs at defined logic levels. The complete frame
formats and status flags are in [the host contract](pemu-host-protocol.md).

## Protocol peers

| Demo | Chip pins and peer connection | External requirements |
|---|---|---|
| UART / autobaud | `uio[0]` TX to peer RX; peer TX to `uio[1]` RX | Logic-level 8N1 peer; idle-high RX; matching baud or the documented autobaud stimulus |
| SPI mode 0 | `uio[4]` SCK, `uio[5]` MOSI, `uio[6]` MISO, `uio[7]` active-low CS | Mode-0, MSB-first target; CS idle high; peer alone drives MISO |
| I2C | `uio[2]` SDA, `uio[3]` SCL | Separate pull-ups on SDA and SCL, open-drain target and common ground; no clock stretching |

Use a common ground and peers compatible with 3.3 V digital I/O. Other
voltage interfaces require appropriate external level shifting/transceivers.
I2C pull-up resistance and bus loading must be selected and measured against
the peer/carrier's electrical specifications; no uncharacterized chip current
or rise-time capability is inferred here.

The firmware mappings differ from the [recommended Tiny Tapeout pinouts](https://tinytapeout.com/specs/pinouts/).
For a Pmod wired to those recommendations, adapt SPI's CS/SCK (`uio[7]`/`uio[4]`
to the module's CS/SCK), swap I2C's SDA/SCL, and route UART TX/RX explicitly.
UART's optional CTS/RTS are unused. A direct plug-in compatibility claim would
be incorrect for these payloads. Firmware can adopt another mapping without
changing the hardened design.

## Reference ETR connector mapping

The published [ETR v3 schematic, revision 3.2](https://github.com/TinyTapeout/tt-demo-pcb/blob/bbf3dd1f771d5aed249b07ddf130b3ddc8261d60/doc/tt-etr-dbv3.pdf)
was checked at commit `bbf3dd1f771d5aed249b07ddf130b3ddc8261d60`.
It identifies J11 as input Pmod, J12 as bidirectional Pmod and J13 as output
Pmod. This is a reference carrier mapping; check the delivered board's markings
and schematic before attaching hardware, since the competition board revision
has not been supplied.

| Chip / function | Reference connector pin |
|---|---|
| `ui_in[0]` loader SCLK | J11 pin 1 |
| `ui_in[1]` loader MOSI | J11 pin 2 |
| `ui_in[2]` loader CS | J11 pin 3 |
| `uo_out[0]` loader MISO/result bit 0 | J13 pin 1 |
| `uio[0]` UART TX; `uio[1]` UART RX | J12 pins 1 and 2 |
| `uio[2]` I2C SDA; `uio[3]` I2C SCL | J12 pins 3 and 4 |
| `uio[4]` SPI SCK; `uio[5]` SPI MOSI | J12 pins 7 and 8 |
| `uio[6]` SPI MISO; `uio[7]` SPI CS | J12 pins 9 and 10 |
| Ground / 3.3 V on each Pmod | Pins 5/11 ground; pins 6/12 3.3 V |

Use the board controller for project selection/reset and a validated chip clock
source. Release its drivers on firmware-owned bidirectional lines before a
protocol runs, and avoid a second host driving the loader inputs simultaneously.
The reference board also connects output bits to display loads through jumpers;
disconnect the bit-0 display load when using it as loader MISO. These are
bring-up requirements, not a completed board electrical check.

The simulation peers expect UART byte `0x41`, SPI transmit `0xA5`/receive
`0x3C`, and an I2C target at address `0x50` accepting byte `0x5A` and returning
`0x39` after a repeated START. These are reproducible test-peer behaviors.
A real EEPROM can require additional memory-address bytes and write-cycle
handling; the current I2C demo is not an EEPROM driver. Consult the
[clock audit](submission-compliance.md) before configuring peer rates.

## After every selection or power loss

1. Select axpe on the harness, establish the chip clock, hold host CS high
   and SCLK low, and assert/release `rst_n` through the board's reset control.
2. Issue STOP. Do not inspect retained instructions as evidence of a valid
   image: the store has no reset contents and selection can follow power loss.
3. WRITE every word of the chosen payload, then READ every written address
   and compare all 32 bits with the assembled image. Confirm the payload fits
   the selected store, and abort the load on any mismatch or refusal.
4. Issue RUN and release CS. Poll STATUS; accept a clean HALT and the expected
   result. A fault or refused write is a failed attempt, not a passing demo.
5. Before changing programs, STOP and repeat load/readback/run. After
   deselection, start again from step 1 with a full reload.

The exported Tiny Tapeout suite now exercises this sequence in a fresh
simulator instance at each startup seed: load/readback/run UART, deselect a
driven TX pin, check quiet outputs, reset/reselect, then fully reload and decode
UART again. It also repeats reload after a warm external reset. Every shared
suite program is read back word for word before RUN, and a refused write
aborts loading. The design's `ena` clears the core but does not clear the host
running latch; the reset step is required before reselecting.

These are logical reset/selection tests. Toggling `ena` does not model actual
power removal, four-state memory startup or the carrier's isolation. Physical
power-loss/reload behavior and final connector/electrical validation remain
open. See [verification](verification.md) for the scope of mapped replay.
