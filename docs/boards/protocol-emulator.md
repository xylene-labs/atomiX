# Protocol emulator board

[All boards](README.md) · [Design document](../protocol-emulator.md) ·
[Execution targets](targets.md)

`axpe` is a timed-ISA protocol emulator built for the Jane Street open-source
CMOS5L ASIC competition. It is this project's execution of
[RX-08](../research-checklist.md#rx-08) and [RX-09](../research-checklist.md#rx-09):
the competition supplies the specific block, the accessible PDK and flow, a fixed
area budget, and an external deadline those two cards were missing.

The pull order follows the competition's own challenge statement: build an
open-source, general-purpose protocol emulator that remains programmable after
fabrication; start with UART, SPI and I2C; use the official CMOS5L template at
6x4; and run synthesis and place-and-route early. Unique functionality and
verification methodology strengthen a complete chip, but cannot substitute
for those baseline capabilities. See the [official announcement](https://blog.janestreet.com/protocol-emulator-asic-competition/).

## What winning means here

Three tiers, in strict order. A card's tier says what it is *for*; a card that
serves no tier does not belong on this board.

| Tier | Meaning | Contents |
|---|---|---|
| **T1 — Valid entry** | Without every one of these we are not competing at all, however good the rest is | Official 6x4 template; programmable after fabrication; UART, SPI and I2C working; the design passes the CMOS5L flow |
| **T2 — Competitive** | What distinguishes a complete chip from other complete chips | Measured time that firmware can actually *use*; the timing-determinism proof; generated-from-one-source artifacts and shared oracles |
| **T3 — Stretch** | Taken only from genuine surplus schedule | Further protocols; the fixed-logic comparison; extra platform evidence |

The ordering is not a preference. A T2 result cannot repair a missing T1
capability, and no amount of verification methodology makes an ASIC that cannot
be loaded after fabrication into an entry.

### Submission definition of done

One list, checkable by someone who did not build it:

1. `make tt-export` produces the Tiny Tapeout repository from this tree.
2. Two different protocol programs load into **one unchanged hardened design**
   after reset, and both run. This is the programmability test; a preinitialised
   memory image does not pass it.
3. UART, SPI and I2C each pass an independent reference peer.
4. A CMOS5L place-and-route report exists with actual area and timing, and every
   violation is recorded rather than omitted.
5. The write-up states what was *not* proved, and at which evidence level each
   claim sits.

### Descope order

Decided now, while there is no schedule pressure, because the worst time to
choose what to cut is the week it has to be cut. When a card slips, the next
item on this list goes, in order, and the board records that it went:

1. PE-13, the fixed-logic comparison
2. PE-09, Tang Primer bring-up — FPGA evidence is valuable but the submission
   is an ASIC entry and does not require it
3. PE-08, the knob sweep beyond what the RTL already elaborates
4. PE-11, gate-level replay, reduced to one protocol rather than three
5. PE-06, the formal proof, reduced from all instructions to the timing core

Nothing above the line is cuttable: T1 is the entry, and PE-15 below is what
makes the T2 functionality claim true rather than half-true.

The deadline is **2027-01-18** and is not ours to move. Cards are ordered by that
date rather than by priority alone; a card that slips takes scope out of a later
card instead of taking time from the submission. All owners are unassigned.

| Card / outcome | Tier | Priority | State | Depends on / blocker | First reviewable slice |
|---|---|---|---|---|---|
| PE-01: competition entry and official template baseline | T1 | P0 | Ready | Sign-up form and asic-competition@janestreet.com | Register, record the confirmed rules and template revision, resolve the template's current tile-shape metadata against the required 6x4 allocation, and pull it into `asic/tt-axpe/` unmodified |
| PE-14: post-fabrication programming and host contract | T1 | P0 | Next | PE-01 pin and wrapper contract | Freeze the host pins and framing for write-word, reset, run, stop/status and result readback; prove two different programs can be loaded and run against one unchanged simulated chip image |
| PE-02: instruction-memory and early-flow feasibility gate | T1 | P0 | Next | PE-01; PE-14 write/read semantics for the integrated trial | Put the writable instruction-store candidate and loader shell through the official 6x4 flow, recording mapped area, routability, timing and macro failures rather than relying on LEF footprint alone |
| PE-03: `axpe` ISA specification | T1 | P0 | Review | PE-02 budget | Done: `axpe-isa.json` is the single source, `axpe-isa.md` is generated from it, and `WAITE` returns its elapsed cycle count |
| PE-04: golden model and assembler | T1 | P0 | Review | PE-03 timing decisions | Model, assembler, UART/autobaud and four-mode clocked shifts pass via `make pemu-model-check`; close only after effect/reset/fault conventions receive commit-pinned review |
| PE-05: RTL and cycle-for-cycle cosimulation | T1 | P0 | Active | PE-04 | Scalar/control RTL matches the model across 64 deterministic randomized programs; remove the recorded one-cycle `WAITE`/shift handoff gap before promoting the gate to `make pemu-check` |
| PE-07: mandatory UART, SPI and I2C firmware | T1 | P0 | Next | PE-05; PE-14 runtime loading | Load all three as runtime programs into the same chip image; UART, SPI and I2C each pass an independent reference peer, including I2C ACK/NACK, repeated-start, STOP and bus release |
| PE-10: staged CMOS5L synthesis and place-and-route | T1 | P0 | Next | PE-01, PE-02 and PE-14 for the first integrated run; PE-07 for final closure | Harden the smallest programmable chip as soon as loader and memory compose, then repeat on the final mandatory-protocol architecture with actual area, timing and violations recorded |
| PE-15: a measured period firmware can use | T2 | P0 | Next | PE-03, PE-05; `b` field free in shift ops, two opcodes reserved | A delay register plus a per-instruction select bit, so `SHOUT`/`SHIN`/`SHIO` can take their bit period from a register. `autobaud.s` must measure an unknown peer and then transmit at that rate, end to end |
| PE-06: timing-determinism proof | T2 | P0 | Next | PE-05 | Every instruction proved to retire in its declared cycle count, `WAITE` bounded by its timeout |
| PE-08: profile knobs exercised | T2 | P1 | Next | PE-05 | `configs/sim-axpe-tiny.json` runs every declared knob at a non-default value with limits derived from the build's own defines |
| PE-09: Tang Primer bring-up | T3 | P1 | Next | PE-05, PE-14; Dock access; a `.cst` exposing a PMOD header; peer hardware arriving | Load firmware at runtime into one unchanged FPGA image, then run UART against CP2102, SPI against a Pi Pico 2 target, and I2C against an AT24C256. Add a capture-clock divider so the 24 MS/s analyzer can witness edge placement in `axpe` cycles |
| PE-11: gate-level firmware simulation | T3 | P1 | Next | PE-10 | The same three firmware images pass post-P&R netlist simulation |
| PE-13: firmware-vs-fixed-logic experiment | T3 | P2 | Next | PE-05, PE-07; only after baseline competition gates | Compare `axpe` with `uart.mmio16550` under one oracle if schedule remains; this is supporting co-design evidence, not a substitute for programmability, mandatory protocols or a hardened chip |
| PE-12: submission package | T1 | P0 | Next | PE-01, PE-06, PE-07, PE-10; PE-14 demonstrated | `make tt-export` produces the Tiny Tapeout repository, evidence index and a reproducible demo that loads multiple protocol images into one unchanged hardened design |

## Schedule

### PE-04 checkpoint — 2026-09-17

Codex added a host model for scalar instructions, measured waits and unclocked
shifts, with per-cycle pin observations and explicit fetch/stack diagnostics.
The gate checks generated ISA drift, the assembler, and model behavior. It is
wired into smoke, quick CI and nightly verification. Runtime program length
and stack capacity are exercised at non-default values; PE-08's full profile
knob wiring is still outstanding.

The model exposes two gaps in the existing firmware under its documented
timing conventions: all five UART workload cases miss the exact transition
oracle by two cycles after the start edge, and known low pulses of 20 and 53
cycles are measured as 18 and 51. Tests preserve these discrepancies rather
than weakening the oracle. Clocked and zero-period shifts explicitly report
unsupported until their timing is specified. See the
[model conventions](../../sw/pemu/model/README.md) and
[host evidence](../../research/benchmarks/axpe-model.json).

Validation: the 14 model test groups, assembler checks, ISA drift check,
verification-contract gate, registry gate and all 12 smoke stages pass. A
working-tree peer review found a receive-phase coverage gap; varying-input
tests now cover it. No commit-pinned approval or completed card is claimed.

This is a reviewable partial checkpoint, not PE-04 completion or protocol
conformance. Next: review pin-effect and shift timing, complete clocked shifts,
then repair and check firmware against independent references. PE-02's macro
flow gate remains open; no RTL, synthesis/P&R, FPGA or silicon result is claimed.

### PE-05 checkpoint — 2026-09-17

The first Verilated differential harness now compares `uio` latch, open-drain
enable, `uo_out`, terminal status and elapsed cycles against the C golden model.
Scalar/control timing passes a directed branch/call/return case and 64 seeded
random programs with varied delays, ALU operations, pin effects and input
sampling.

The comparison found and fixed four RTL defects: the core could not issue after
reset because the timer entered a non-ready zero state; HALT ignored its encoded
duration; the first MSB-first shift bit used the previous transfer's bit count;
and receive samples landed one cycle late, losing the final CPHA=1 bit. It also
fixed `WAITE` returning `D+1` on timeout and setting `T` incorrectly when an edge
arrived exactly at the bound.

One architectural gap remains explicit: returning from `WAITE` or any shift to
the main issue state inserts one cycle not declared by the ISA. Directed
unclocked, clocked, full-duplex CPHA=1 and timeout cases reproduce exactly one
removable cycle and are reported as XFAIL, so this is not yet the PE-05 passing
slice and PE-06 cannot start. Evidence is host RTL/model cosimulation only in
[`axpe-cosim.json`](../../research/benchmarks/axpe-cosim.json); no synthesis,
P&R, FPGA or silicon claim is made.

| Phase | Cards | By |
|---|---|---|
| 0 — official entry and template | PE-01 | 2026-09-22 |
| 1 — runtime programmability and early 6x4 hardening | PE-14, PE-02; first PE-10 run | 2026-10-08 |
| 2 — ISA, model and cycle-exact RTL | PE-03, PE-04, PE-05 | 2026-10-29 |
| 3 — mandatory runtime-loaded protocols | PE-07 | 2026-11-19 |
| 4 — usable measurement, proof, knob sweep, optional FPGA evidence | PE-15, PE-06, PE-08, PE-09 | 2026-12-10 |
| 5 — final ASIC flow and gate-level replay | PE-10, PE-11 | 2027-01-07 |
| 6 — submission | PE-12 | 2027-01-14 |

Four days of buffer remain before the deadline. They are buffer, not a phase.

## What closes a card here

Jane Street says it is particularly interested in unique functionality and in
novel design and verification methodologies. That is a selection signal, not a
published scoring rubric. Evidence discipline is part of the deliverable, but
methodology cannot compensate for an ASIC that is not runtime-programmable or
does not implement the three named starting protocols.

Every card keeps simulation, synthesis/P&R, and physical evidence explicitly
separate, exactly as the rest of the project does. A CMOS5L P&R result is not an
FPGA result and neither is a silicon claim; nothing taped out exists until it
comes back from the shuttle. Record failures, timing violations, and unresolved
verification alongside passes — a submission that states its own gaps is more
credible than one that hides them.

Firmware is never part of the FPGA bitstream or ASIC GDS identity. The closure
test for programmability is loading different firmware after reset into one
unchanged hardened design. A preinitialized SRAM image may help first bring-up,
but it does not satisfy the competition's after-fabrication requirement. On the
Primer, adding or changing protocol firmware likewise must not re-open a board
claim or trigger re-synthesis.

## Priority decisions

- 2026-09-17: added a three-tier win condition, a submission definition of done
  and a written descope order, so every card answers to an outcome rather than
  to its own completion. The descope order is decided now on purpose: the worst
  time to choose what to cut is the week it must be cut.
- 2026-09-17: opened PE-15, because the measured-time feature is currently half
  a feature. `WAITE` returns a period into a register and `D` is an immediate,
  so `autobaud.s` measures an unknown peer and then cannot transmit at that
  rate. It is cheap to close -- the `b` field is unused in `SHOUT`/`SHIN`/`SHIO`
  and two opcodes are reserved -- and until it closes, the unique-functionality
  claim has to be stated as measurement only. This is what the self-calibration
  walk-back below implies; PE-15 is the work that makes the claim true instead.
- 2026-09-17: reordered the board against the competition's exact wording.
  PE-01 is the first pull, followed by a new PE-14 runtime-programming contract
  and an integrated PE-02 early hardening run. A CPU with externally supplied
  `imem_data` is not yet a reprogrammable ASIC: the fabricated chip needs a
  host-visible write/load/run/status path and writable instruction storage.
- 2026-09-17: staged P&R instead of leaving all physical design until January.
  The first PE-10 run happens as soon as the loader, writable memory and minimal
  core compose; final firmware and verification results trigger a later re-run.
  This follows the announcement's instruction to synthesize and route early.
- 2026-09-17: made UART, SPI and I2C an explicit P0 runtime-loaded gate and
  demoted PE-13 to P2. The fixed-UART comparison can strengthen the write-up,
  but it is internal platform evidence and cannot replace a mandatory protocol
  or post-fabrication programmability.
- 2026-09-17: the submission narrative now leads with the chip. atomiX's
  generated artifacts, shared oracles and cross-target experiment machinery are
  verification evidence supporting it; they are not a second deliverable that
  can make an incomplete chip competitive. This supersedes the earlier
  "chip and platform" ordering below while preserving its useful experiment.
- 2026-09-17: do not claim firmware self-calibration until the architecture can
  actually apply a measured period to later timing. The current ISA can measure
  a peer but cannot rewrite an instruction delay or load a delay register.

- 2026-09-17: open this board and give it the project's work-in-progress limit
  until 2027-01-18. M0 delivery work is paused rather than run alongside — the
  deadline is externally fixed and the board policy allows one Active slice.
- 2026-09-17: the instruction store is a gate, not an implementation detail.
  Published Tiny Tapeout density figures put a naive 256×32 flip-flop program
  memory at more flip-flops than the entire 6×4 budget holds, so PE-02 blocks
  PE-03 deliberately.
- 2026-09-17: hardware scope is the Tang Primer 25K Dock and nothing else. The
  toolchain is complete in oss-cad-suite, so PE-09 is not tool-blocked; what it
  needs is a `.cst` exposing a PMOD header, since the board currently constrains
  only `clk_50mhz`, `button_s1`, `uart_rx` and `uart_tx`.
- 2026-09-17: protocol peer hardware ordered, which resolves the deferred I2C
  question and gives every mandatory protocol a hardware peer: a Pi Pico 2 with
  breadboard and jumpers, a CP2102 USB-UART, a 24 MS/s 8-channel logic
  analyzer, and an AT24C256 I2C EEPROM. All 3.3 V, so no level shifting.
  Three consequences to design for, before PE-09 is pulled:
  - **The analyzer cannot resolve cycles at the board clock.** 24 MS/s is
    41.7 ns per sample against a 20 ns period. It decodes protocol rates with
    room to spare (208 samples per UART bit at 115200, 240 per I2C bit at
    100 kHz, 24 per SPI bit at 1 MHz) but cannot witness the `max(D,1)` rule.
    Captured-waveform evidence and cycle-exact timing stay separate claims.
  - **A capture clock makes it cycle-exact.** Running `axpe` from a divided
    clock at about 1 MHz gives roughly 24 samples per `axpe` cycle, and the
    rule is relative to `axpe`'s own clock, so edge placement can then be
    checked in cycles against the workload oracle on real hardware. The FPGA
    wrapper should carry a capture-clock divider from the start; it is the only
    route we have to physical evidence for the headline property.
  - **I2C needs pull-ups, and open-drain is why.** `axpe` never drives an
    open-drain pin high, so without pull-ups SDA and SCL float and I2C fails
    silently. Confirm the EEPROM module carries them before debugging firmware.
    The AT24C256 also uses two-byte word addressing, unlike the AT24C02
    originally considered, so a transaction costs more instructions against
    `imem_words`.
- 2026-09-17: no removable storage is needed, and microSD is not an option on
  this board. Only `board.ulx3s_45f` and `board.ulx3s_85f` declare `micro-sd`;
  `board.tangprimer25k` declares none, so `block.spi-sd` is not a peer we can
  reach here. An SD card would also be a poor first SPI target -- the CMD0 /
  CMD8 / ACMD41 init may not fit 256 instructions, and a peer that can be told
  to misbehave is worth more during bring-up than an independent one. USB mass
  storage is not reachable at all: it needs a full host stack, and the
  low-speed USB stretch goal means 1.5 Mbps signalling, for which the peer
  would be an old keyboard or mouse rather than a drive.
- 2026-09-17: no protocol peer hardware is owned, and buying one is deferred to
  December rather than assumed. UART therefore earns board evidence for free
  against the host's USB-serial stack -- an independent implementation by any
  reasonable reading. SPI and I2C stay at model and RTL evidence unless a peer
  appears, which the evidence levels already express without special pleading.
  The highest-value purchase when it is reconsidered is a single microcontroller
  board, which can be a UART, SPI and I2C peer at once.
- 2026-09-17: settled the clocked cell. It splits at its half point, data at
  the cell start (or the leading edge when `cpha=1`), clock leading edge at
  `D/2`, `cpol`/`cpha` giving SPI modes 0-3. An odd or zero clocked period and
  a clock aliased onto either data pin are refused before issue; `din == dout`
  is allowed because I2C's SDA needs it. None of these can be assembler errors,
  since `SHCFG` is loaded from a register and the configuration is invisible at
  assembly time -- the machine is the only place that knows it.
- 2026-09-17: retimed the ISA to `max(D,1)` after the host model failed the
  platform waveform oracle. A `1 + D` rule makes a bit cell `BAUD+1` cycles, so
  no firmware could land an edge on a multiple of the bit period -- the offset
  was in the instruction set, not the firmware. The draft model recorded the
  mismatch instead of tuning its expectation to match, which is the only reason
  it was found before RTL existed. A second, independent defect surfaced with
  it: `autobaud.s` had a branch between its two `WAITE`s, spending a cycle the
  measurement could not see. Interval measurement now requires adjacent waits,
  and that is normative.
- Earlier 2026-09-17 decision, superseded by the chip-first ordering above: the
  submission is the chip *and* the platform. The competition's
  premise -- protocols in firmware rather than fixed logic -- is a co-design
  tradeoff, which is the shape of question this project exists to answer, so
  PE-13 tests it against the fixed-function UART already in the tree instead of
  asserting it. See [§6](../protocol-emulator.md). This is the reason to enter
  through atomiX rather than a standalone repository, and it should shape how
  the write-up is ordered.
- 2026-09-17: corrected the novelty claim before building on it. A delay field
  in every instruction is RP2040 PIO's design, not ours, so it is the
  foundation rather than the pitch. The two bets that carry the submission are
  `WAITE` returning measured time, which makes the chip able to characterise an
  unknown peer, and generating every derived artifact from one ISA description.
  Both are recorded in [§3.1](../protocol-emulator.md).
- 2026-09-17: that gate is half closed, and in the favourable direction. Measured
  IHP-Open-PDK LEF footprints put a 256×32 single-port SRAM macro at 6.9% of the
  6×4 die and a 512×32 at 11.1% — see [§2.1](../protocol-emulator.md). Program
  size was never the constraint; the storage primitive was. PE-02 stays Active
  because area affordability is not flow acceptance: the macro has to go through
  the Tiny Tapeout 6×4 flow before PE-03 may assume it.
