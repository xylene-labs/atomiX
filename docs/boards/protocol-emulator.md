# Protocol emulator board

[All boards](README.md) · [Design document](../protocol-emulator.md) ·
[Execution targets](targets.md)

`axpe` is a timed-ISA protocol emulator built for the Jane Street open-source
CMOS5L ASIC competition. It is this project's execution of
[RX-08](../research-checklist.md#rx-08) and [RX-09](../research-checklist.md#rx-09):
the competition supplies the specific block, the accessible PDK and flow, a fixed
area budget, and an external deadline those two cards were missing.

The deadline is **2027-01-18** and is not ours to move. Cards are ordered by that
date rather than by priority alone; a card that slips takes scope out of a later
card instead of taking time from the submission. All owners are unassigned.

| Card / outcome | Priority | State | Depends on / blocker | First reviewable slice |
|---|---|---|---|---|
| PE-01: competition entry and template baseline | P0 | Ready | Sign-up form and asic-competition@janestreet.com | Register, record the confirmed rules and any template updates, and pull the CMOS5L Verilog template into `asic/tt-axpe/` unmodified |
| PE-02: area and memory feasibility gate | P0 | Active | PE-01 template for the macro trial | Macro footprints measured 2026-09-17; remaining slice is confirming the Tiny Tapeout 6×4 flow accepts an SRAM macro, and measuring real cells per tile |
| PE-03: `axpe` ISA specification | P0 | Review | PE-02 budget | Done: `axpe-isa.json` is the single source, `axpe-isa.md` is generated from it, and `WAITE` returns its elapsed cycle count |
| PE-04: golden model and assembler | P0 | Active | PE-03 timing decisions | Draft C model, assembler and host checks run via `make pemu-model-check`; settle shift/effect timing and correct the reproduced UART/autobaud gaps before closing |
| PE-05: RTL and cycle-for-cycle cosimulation | P0 | Next | PE-04 | `components/pemu/axpe/` passes `make pemu-check` against the golden model on randomised programs |
| PE-06: timing-determinism proof | P0 | Next | PE-05 | Every instruction proved to retire in its declared cycle count, `WAITE` bounded by its timeout |
| PE-07: UART, SPI and I2C firmware | P0 | Active | PE-05 for RTL | UART conforms to the platform oracle and SPI mode 0 runs full duplex against a modelled peer; I2C and independent reference cross-checks remain |
| PE-08: profile knobs exercised | P1 | Next | PE-05 | `configs/sim-axpe-tiny.json` runs every declared knob at a non-default value with limits derived from the build's own defines |
| PE-13: firmware-vs-fixed-logic experiment | P0 | Active | PE-05, PE-07 for full results | Plan and workload validate today; the comparison against `uart.mmio16550` under one oracle is what makes the premise measured rather than asserted |
| PE-09: Tang Primer bring-up | P1 | Next | PE-05; Dock access; a `.cst` exposing a PMOD header | UART against the host's own USB-serial stack, which is an independent implementation and needs no purchase. SPI and I2C peers are deferred |
| PE-10: CMOS5L synthesis and place-and-route | P0 | Next | PE-07, PE-02 | Actual area and timing at the chosen clock, violations recorded as found |
| PE-11: gate-level firmware simulation | P1 | Next | PE-10 | The same three firmware images pass post-P&R netlist simulation |
| PE-12: submission package | P0 | Next | PE-06, PE-07, PE-10 | `make tt-export` produces the Tiny Tapeout repository from this tree, with the write-up and evidence index |

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

| Phase | Cards | By |
|---|---|---|
| 0 — feasibility gate | PE-01, PE-02 | 2026-10-01 |
| 1 — spec and model first | PE-03, PE-04 | 2026-10-22 |
| 2 — RTL and proof | PE-05, PE-06, PE-08 | 2026-11-12 |
| 3 — protocol firmware | PE-07 | 2026-12-03 |
| 4 — FPGA bring-up | PE-09 | 2026-12-17 |
| 5 — ASIC flow | PE-10, PE-11 | 2027-01-07 |
| 6 — submission | PE-12 | 2027-01-14 |

Four days of buffer remain before the deadline. They are buffer, not a phase.

## What closes a card here

The competition is judged on unique functionality **and** on novel design and
verification methodology. The second axis is the one this project is unusually
placed to win, so evidence discipline is part of the deliverable rather than
overhead on it.

Every card keeps simulation, synthesis/P&R, and physical evidence explicitly
separate, exactly as the rest of the project does. A CMOS5L P&R result is not an
FPGA result and neither is a silicon claim; nothing taped out exists until it
comes back from the shuttle. Record failures, timing violations, and unresolved
verification alongside passes — a submission that states its own gaps is worth
more on the judged axis than one that hides them.

Firmware is never part of a bitstream's identity. On the Primer the emulator's
program loads at runtime over the existing loader; adding or changing a protocol
firmware must never re-open a board claim or trigger re-synthesis.

## Priority decisions

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
- 2026-09-17: the submission is the chip *and* the platform. The competition's
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
