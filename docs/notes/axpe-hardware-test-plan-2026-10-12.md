# axpe physical hardware test plan — 2026-10-12

This is the PE-09 execution plan requested by the maintainer on October 12.
It schedules physical FPGA tests before further PE-08 width/profile work.
It records planned physical work and implemented preflight, not a completed hardware result. Dates use
Asia/Calcutta and assume regular board access and roughly three bench sessions
per week, alongside development. Missing prerequisites move the affected gate;
they do not turn it into a pass.

The maintainer confirms possession of the Tang Primer 25K Dock, a USB–UART
adapter, Pico 2, an AT24C256 EEPROM module and a logic analyzer marked
24M 8CH (declared 24 MS/s, eight channels). EEPROM vendor/suffix, address
straps, module pull-ups, adapter logic voltage and miscellaneous wiring still
need inventory; no measured sampling or electrical result is implied.
Previous Tang Primer CPU/GPU/kernel achievements do not establish an axpe pass.

## Deliverable and current implementation gaps

Deliver a reproducible FPGA image containing the selected axpe architecture,
64 instruction words, a runtime host port, real bidirectional/open-drain pads,
reset/selection controls and an observable capture clock. Load different
protocol programs into that image without resynthesis or reprogramming the
FPGA between programs. Freeze and hash the image before physical testing.

The existing Primer profile/top implements the RISC-V SoC, not this axpe
bench. Its CST constrains only oscillator, S1 and debugger UART. PE-09 must
provide an axpe board wrapper/profile, reviewed Pmod constraints, a physical
SPI loader bridge and host runner, peer firmware, capture analysis, and an
EEPROM-specific payload. The adapter/profiles/CST and host-bridge prototype now have local preflight;
EEPROM byte-operation payloads and the preservation/polling host runner now
pass digital checks. Physical bridge execution, remaining peer firmware and
capture analysis remain prerequisites. See the
[adapter instructions](../../components/board/tangprimer25k-axpe/README.md).
The existing `sw/host/axhost.py` UART/aXos loader is a different contract.

Use the maintained axpe core/host/store sources and the selected architecture;
keep vendor pads and clocking in the FPGA wrapper. Leave the CMOS5L candidate
and existing Primer SoC profiles intact. Wrapper clock modes and test limits
belong in their owning manifests/profiles, with defaults, docs, bounds and a
non-default exercise. Firmware rates remain runtime inputs.

## Timeline and exit gates

| Dates, 2026 | Work | Exit gate |
|---|---|---|
| Oct 12–14 | Inventory and wiring design | Record board/peer markings; confirm 3.3 V logic, pull-ups and analyzer capabilities; review connector-to-FPGA pin map, common ground and reset access |
| Oct 15–20 | FPGA adapter and bench tooling | Wrapper/profile/CST simulated; output-enable and open-drain behavior checked; normal/capture clocks constrained and routed; Pico SPI bridge works against the loader contract; proposed EEPROM payloads fit 64 words |
| Oct 21–23 | First physical SRAM load and host readback | Detect the Dock, load the hashed image, verify quiet outputs, reset/STOP, WRITE and READ every payload word, RUN and inspect STATUS; replace programs without another FPGA load |
| Oct 24–27 | UART and SPI peers | UART TX and RX verified against USB–UART; SPI mode 0 exchanges known bytes against Pico; analyzer captures agree with integer periods and framing |
| Oct 28–Nov 1 | I2C EEPROM and negative cases | Matched EEPROM driver writes/reads a reserved location correctly; repeated START/ACK/NACK/STOP and bounded write-cycle handling verified; restore prior EEPROM data; wrong-address NACK releases the bus |
| Nov 2–6 | Timing, autobaud and recovery | Capture-mode edge intervals checked in axpe cycles; two unconfigured peer rates measured/reused; repeated reset/reload and real power-cycle/reload succeed |
| Nov 7–13 | Repair, repeat and freeze | Final image passes the complete physical matrix again; publish compact evidence, reproduction procedure and waveform/report inventory for maintainer review |

November 13 is the hardware evidence target, with repair time through November
20. If the October 20 preflight gate slips, finish loader/readback and one
physical UART demo first, then SPI and I2C. Defer extra SPI modes and speed
increases. Preserve the passing ASIC submission package and January 14 internal
submission target while recording any incomplete physical cases explicitly.
PE-12 maintainer review remains owed; this plan does not close any card.

## Equipment and wiring requirements

| Item | Role / remaining requirement |
|---|---|
| Tang Primer 25K Dock and data USB cable | Already available; verify core/Dock revision and WSL/JTAG access each session; FPGA configuration uses volatile SRAM only |
| Pico 2 and data USB cable | Already available; provide USB-to-axpe-SPI loader firmware and controlled SPI/I2C/UART stimuli. Separate loader and protocol-peer pins/peripherals; validate that one Pico can support the required roles |
| USB–UART adapter | Already available; record actual part and logic voltage; cross TX/RX and share ground; use as independent UART peer, not as the axpe SPI programmer |
| I2C EEPROM module | Already available; identify exact IC, address straps, WP, supply range, pull-ups, address width and write-cycle timing from its matched datasheet |
| Logic analyzer | Already available; verify sample rate, channel count, threshold/range and capture software. Connect ground plus the active protocol, clock reference and selection/reset as needed; test protocols separately if channels are limited |
| Breadboard, jumpers, Pmod breakout/adapter | Confirm availability; provide short, labelled wiring and accessible ground; check physical header numbering against the actual Dock schematic |
| Multimeter | Confirm or borrow; measure module supply and idle levels and verify continuity before applying signal drive |
| SDA/SCL pull-ups | Confirm on-module resistors and effective parallel resistance; add only if needed. Pull up to the reviewed 3.3 V rail and select values using device sink-current and bus-capacitance requirements |
| Oscilloscope and probes | Needed to substantiate analog rise/fall, overshoot and threshold-level electrical timing. Without it, report digital functionality and sampled edge timing only |

Use one documented power arrangement and common ground. Check adapter signal
voltage independently of its labelled power-output pins. Keep each push-pull
line to one active driver; map `uio_oe` to actual FPGA pad tri-state control.
Open-drain SDA/SCL must drive low or release, never actively drive high.
The [Sipeed hardware documentation](https://wiki.sipeed.com/hardware/en/tang/tang-primer-25k/primer-25k.html)
links the Dock schematic and its three Pmod connectors. The ETR connector map
in the submission wiring document is not a Tang Primer pin map.

## Clock, loader and payload requirements

Start with a nominal 25 MHz bench clock, following the existing Primer clock
approach, subject to fresh axpe synthesis/P&R and timing checks. The implemented 1 MHz capture profile accepts a Pico PWM clock on J6 pin 10
and constrains that input explicitly. The active clock is observed on J6 pin 8.
The earlier fabric divider failed hold timing; DCS and cascaded-divider attempts
also failed the open flow. Both modes now use separate images, changed under
reset; no dynamic clock switch is implemented. Measure the Pico clock before
accepting waveform periods.
Expose the active axpe clock on a reference pin. If two separately compiled
clock profiles are needed, pin each image separately and keep each unchanged
across its runtime programs. No 40 MHz physical FPGA claim follows from the
ASIC's 25 ns STA target.

The current firmware builder accepts these proposed bench settings and all
four existing demo programs fit 64 words:

| Mode | UART request / integer actual | SPI mode 0 | I2C request / cell actual |
|---|---|---|---|
| 25 MHz normal | 115200 / 115207.37 baud, 217 cycles | 500 kHz, 50 cycles | 100 kHz ceiling / 99.206 kHz, 252 cycles |
| 1 MHz capture | 9600 / 9615.38 baud, 104 cycles | 50 kHz, 20 cycles | 10 kHz / 10 kHz, 100 cycles |

Both settings use the firmware-owned 50 ns nominal I2C guard. These are
planning calculations, not clock measurements or new RTL/physical results.
The normal/capture assembly receipt is
`build/asic/axpe-hardware-plan-2026-10-12/evidence.json`, SHA-256
`d5a0ae2442f115fa338a47acc25eecc16e7c6cb5a5682233eb2e4567aa8f45d1`.
Payload sizes are UART 36, SPI 15, I2C 54 and autobaud 55 words. New UART RX,
EEPROM and negative-case payloads require their own capacity/behavior checks.

The [host contract](../pemu-host-protocol.md) requires mode-0 SPI, MSB first
and SCLK no faster than axpe clock/4. Use a conservative 100 kHz loader SCLK
initially; it satisfies both proposed modes. The Pico must implement full
WRITE/READ/RUN/STOP/STATUS frames and give the PC raw readback/status results.
The runner must reset/STOP, rewrite and compare every program word before RUN,
reject mismatches/refusals, and use bounded completion timeouts. Keep host SPI
separate from firmware's protocol SPI.

The existing I2C demo expects a synthetic target at 0x50 and is not an EEPROM
driver. The confirmed AT24C256 family uses two word address bytes and a self-timed
write cycle. Vendor/suffix and voltage-specific limits still need confirmation;
for the AT24C256C reference see Microchip's
[addressing](https://onlinedocs.microchip.com/oxy/GUID-FEEC2B39-7B05-43C4-AB92-C76A6F28FB70-en-US-2/GUID-10D69718-8BB5-49ED-90C1-D1FCE55222A8.html)
and [write-cycle timing](https://onlinedocs.microchip.com/oxy/GUID-FEEC2B39-7B05-43C4-AB92-C76A6F28FB70-en-US-2/GUID-9CCCF090-332F-4652-9638-E7C573C80B93.html).
Use the actual module's datasheet if its part differs. Support bounded ACK
polling or a documented host-managed write-cycle wait. At 25 MHz, a single
16-bit delay reaches only 2.6214 ms, so longer waits need a bounded loop or
host-managed sequencing. Separate write/read runtime programs may be used
to stay within 64 words; no store enlargement is implied.

## Physical pass matrix and evidence

| Case | Required observation |
|---|---|
| Host and programming | 100 consecutive complete load/readback/run attempts without word mismatch, refusal or unexpected fault; two unrelated programs run on the same FPGA image |
| UART | Known transmitted and received bytes/framing match an independent peer over 100 runs; record requested, integer-derived and measured baud rates |
| SPI | Mode-0 MOSI/MISO bytes and CS/SCK timing match over 100 transactions; peer drives MISO only as specified. Modes 1–3 are an extension after baseline passes |
| I2C | 100 successful reads, 10 write/read checks in a reserved scratch region, and explicit NACK/release handling. Back up and restore pre-existing scratch data |
| Autobaud | Measure two different unconfigured peer rates and transmit a correctly decoded reply at each; record measured period and observed frame timing |
| Capture timing | Check directed pin holds, shifts and relevant instruction handoffs against the expected cycles using the captured active clock; report analyzer quantization and any deviations |
| Reset/selection | 10 reset/deselect/reselect/reload repetitions; output state and host status follow the documented lifecycle, without assuming retained instructions |
| Power loss | Three real board power cycles. Rediscover USB/JTAG, reload the same SRAM image, fully reload axpe firmware and repeat a known protocol case |

For a power-loss test, release or disconnect peer signal/power paths that could
back-power the FPGA, then confirm the board supply is actually removed. A
reset or removal of only one of several power sources is a different test.

Implement repetition counts and deadlines as bounded bench-owned settings;
the counts above are initial acceptance targets, not hardcoded generic limits.
The confirmed analyzer is marked 24M 8CH: at its declared 24 MS/s maximum,
one sample is about 41.7 ns: 25 MHz cycles cannot be resolved reliably. At 1 MHz there are 24
samples per cycle. Capture the clock reference, measure intervals in cycles,
and allow only an explicitly stated sampling uncertainty; analog propagation
and threshold effects are not exact zero-delay behavior. Quantify deviations
and failure cases instead of calling a protocol decode a timing proof.

Each run records source commit, profile, tool versions, FPGA image hash,
peer firmware hash, runtime payload/clock receipts, board/peer identity, wiring,
sampling configuration, raw capture/log hashes, repeat counts and pass/fail
results. Raw files stay under `build/`; compact physical records belong in
`research/benchmarks/` and successful results in the
[Tang Primer achievements](../achievements/tangprimer25k.md). Use the existing
[lab procedure](../tangprimer25k-bringup.md) for attachment and SRAM recovery;
the axpe-specific commands will be documented once implemented and verified.

Digital I2C timing checks use [NXP UM10204 Table 11](https://www.nxp.com/docs/en/user-guide/UM10204.pdf).
Analog compliance requires suitable electrical measurements. FPGA results
support axpe functional and interface claims on this board; they do not
characterize CMOS5L pads or prove operation of fabricated silicon. Returned
ASIC/ETR testing starts only if fabrication is awarded and devices arrive;
repeat loader/recovery and protocol tests, then measure the real clock, pads
and safe operating range. No returned-silicon date is promised here.

## Plan preparation checks

The proposed normal/capture runtime profiles assemble within 64 words; plan
links and the planning receipt hash validate. Verification/registry gates and
all 14 smoke stages pass after these documentation changes. Smoke output is
under `build/verification/hardware-plan-2026-10-12/smoke/`; it validates existing
software/RTL checks and does not complete any physical gate in this plan.


## Implemented preflight checkpoint

The normal/capture wrappers pass shared protocol simulations at three startup
seeds each. A 2.5 MHz capture clock and 23-cycle reset pass the same suite.
The open Gowin flow produces both images without waived timing checks; no
physical programming has been performed. The FPGA store uses flip-flops after
the initial BRAM mapping failed hold checks. Earlier routing and simulation
failures remain in the compact preflight record with raw log hashes.

`make pemu-primer-check` includes board range/pin/runtime-image contracts and
eleven transport-fake tests, then both full adapter simulations. The optional
`make pemu-primer-pads-check` verifies isolated four-state pads; it is not full
Icarus core elaboration. `pemu-chip-check` includes the adapter gate, so normal
CI/smoke/nightly exercise it. Neither CI nor a routed bitstream establishes
Pico execution or a physical-board pass.

The bridge prototype and PC runner implement reset/STOP/WRITE/READ/RUN/STATUS,
full raw readback, request-ID matching and bounded completion. Deploying and
measuring the bridge, independent workload peers, waveform analysis and
completion of the full acceptance repetition runner remain work before the
October 20 preflight gate. The timeline remains the physical target.


## AT24C256 runtime tools checkpoint

The [EEPROM runtime tools](../../sw/pemu/firmware/eeprom/README.md) fit separate
byte write (54 words), ACK-only poll (46), and tagged low/high random read (60
each) in the unchanged 64-word image. The runner reconstructs each byte from
two tagged read transactions, backs up the original scratch byte before any
requested write, verifies test patterns and finally restores/reads the original.
Defaults are 100 reconstructed reads and 10 test writes plus one restoration
write; custom EEPROM settings profiles are bounded and exercised. Writes are
requested explicitly with the CLI flag; no physical access occurred here.

The host readiness deadline includes complete program reload/USB/SPI/probe
overhead. The default 1000 ms budget is not a device write-cycle claim; legacy
AT24C256 limits vary with voltage/process marking, as recorded in the
[matched-family reference](https://ww1.microchip.com/downloads/en/devicedoc/doc0670.pdf).
The reported marking alone does not supply those limits. The independent
digital peer uses its own configurable busy latency to force NACK and deferred
commit, not a measured EEPROM time. Digital timing/ACK/release and firmware
mutation checks pass; physical module WP/straps/pull-ups, bus quality and the
full acceptance/recovery matrix still need the lab.
