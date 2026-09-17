# axpe — the atomiX protocol emulator

A protocol emulator is a small chip whose instruction set is built for
bit-banging: it reads pins, writes pins, counts cycles, and holds precise
timing, so that UART, SPI and I2C are *firmware* rather than fixed logic. `axpe`
is atomiX's entry to the Jane Street open-source CMOS5L ASIC competition, and it
is the project's execution of [RX-08](research-checklist.md#rx-08) and
[RX-09](research-checklist.md#rx-09). Work is tracked on the
[protocol emulator board](boards/protocol-emulator.md).

This document is maintained. It states what has been decided and measured, and
it marks what is still open. Nothing here is a silicon claim.

## 1. Fixed external constraints

| | |
|---|---|
| Deadline | 2027-01-18 |
| Process | IHP 130nm CMOS5L, through Tiny Tapeout |
| Area | 6×4 tiles; tile = 200µm × 150µm, so 1200µm × 600µm ≈ 0.72 mm². An 8×4 option (~30% more) was under discussion and is not assumed |
| Logic budget | ~1K logic cells per tile → ~24K cells. This is the competition announcement's estimate, not a measurement; PE-02 replaces it with one |
| Pins | Tiny Tapeout harness: 8 input, 8 output, 8 bidirectional, plus `clk`, `rst_n`, `ena` |
| Mandatory protocols | UART, SPI, I2C |
| Stretch | Low-speed USB, 10Mbit Ethernet. Also named as interesting: JTAG, SWD, PS/2, CAN |
| Licence | Open source, required |
| Judged on | Unique functionality, and novel design and verification methodology |

## 2. The memory finding, and why it is a gate

Tiny Tapeout publishes density figures that decide the architecture before any
encoding is chosen. Per the [Tiny Tapeout memory specs](https://tinytapeout.com/specs/memory/):

| Storage approach | Density | 6×4 whole-chip ceiling |
|---|---|---|
| Flip-flops | ~320 DFFs per tile | ~7,680 DFFs |
| Latch-based memory | ~512 bits per tile | ~12,288 bits |
| DFF RAM compiler (`RAM32`) | 128 bytes in 3×2 tiles | — |
| IHP SG13G2 SRAM macro | pre-generated, single-port 256×8 up to 1024×32 | — |

A 256-instruction, 32-bit-wide program memory is 8,192 bits. In flip-flops that
is **more storage than the entire 6×4 budget holds**, before a single gate of
CPU exists. In latches it is two-thirds of the chip. The obvious shape for this
design is therefore not affordable in the obvious way — which is what PE-02
exists to settle, and §2.1 now settles it.

### 2.1 Measured macro footprints

Measured 2026-09-17 from the `SIZE` records in the IHP-Open-PDK `main` branch
LEF files under `ihp-sg13g2/libs.ref/sg13g2_sram/lef/`, against a 6×4 die of
1200µm × 600µm = 720,000 µm²:

| Macro | Footprint (µm) | Area (µm²) | Share of 6×4 |
|---|---|---|---|
| `RM_IHPSG13_1P_64x16_c2` | 236.80 × 64.36 | 15,240 | 2.1% |
| `RM_IHPSG13_1P_256x8_c3_bm_bist` | 236.80 × 74.10 | 17,547 | 2.4% |
| `RM_IHPSG13_1P_256x16_c2_bm_bist` | 236.80 × 118.78 | 28,127 | 3.9% |
| `RM_IHPSG13_1P_256x32_c2_bm_bist` | 416.64 × 118.78 | 49,488 | 6.9% |
| `RM_IHPSG13_1P_512x16_c2_bm_bist` | 236.80 × 191.34 | 45,309 | 6.3% |
| `RM_IHPSG13_1P_512x32_c2_bm_bist` | 416.64 × 191.34 | 79,720 | 11.1% |

**This inverts the assumption the gate was opened on.** A 256-instruction,
32-bit program memory is impossible in flip-flops — more storage than the whole
die holds — and costs **6.9% of the die** as a macro. The constraint on program
size was never area; it was the choice of storage primitive, and one route is
roughly fifteen times denser than the other.

**But 256 words is a ceiling the ISA imposes, not a budget choice.** `BR` and
`CALL` targets are eight bits, so nothing past word 255 can be jumped to
however large the store is. The 512x32 macro at 11.1% buys addressable nothing.
Raising the ceiling is an ISA change — a wider target field, or paging — and it
would cost encoding bits that are already spent. RTL elaboration at
`IMEM_WORDS=512` is what surfaced this; the parameter sweep the project's own
knob rule requires is what ran it.

So the instruction store is an SRAM macro, and the remaining risk is
*integration*, not budget: Tiny Tapeout's own documentation says integrating the
IHP macro "is not trivial," and whether their 6×4 flow accepts a macro at all is
still unconfirmed. Aspect ratio is comfortable — 416.64 × 118.78 µm is about a
third of the die width and a fifth of its height, so placement has room.

PE-02 is not closed until a macro has been through the flow. Two fallbacks stay
live until it is, and both are affordable precisely because the knobs below keep
them reachable:

1. **Small latch-based program memory.** 64 instructions × 16 bits is 1,024
   bits, roughly two tiles at published latch density. Low risk, but it
   constrains firmware hard and pushes complexity into the encoding.
2. **Streamed program.** Hold a small instruction window on-chip and load it
   over a serial port, in the same spirit as the FPGA loader this project
   already runs. Cheapest in area, costs a pin and a load protocol.

**The architecture must not bet on which one wins.** The program store depth and
instruction width are declared as component `parameters` with defaults and docs,
bounded in `tools/configure.py`, and exercised at a non-default value by
`configs/sim-axpe-tiny.json` — the same four-step rule the rest of the project
applies to every knob. PE-02 then picks the value with measured numbers rather
than the ISA being written around a guess.

The same figures constrain the datapath. With a whole-chip ceiling near 7,680
flip-flops and logic still to pay for, a wide register file is not affordable: a
32-bit × 8-entry file alone is 256 flip-flops. The working assumption is a
narrow datapath and few registers, revisited in PE-03.

## 3. Architecture direction

A single timed-ISA micro-CPU. Cycle timing is part of the instruction encoding
rather than something firmware accumulates by counting NOPs:

```
 31            16 15   12 11        0
+----------------+-------+----------+
|    operand     | delay |  opcode  |
+----------------+-------+----------+

WAITE  pin, edge, timeout   ; block until edge, bounded
SHOUT  reg, n, lsb|msb      ; clock out n bits
SHIN   reg, n               ; sample n bits
PINW   mask, val            ; drive pins, hold for delay
DELAY  n                    ; exactly n cycles
```

Widths above are illustrative and are PE-03's to fix; §2 may well narrow them.
The full instruction set is in [`sw/pemu/isa/axpe-isa.md`](../sw/pemu/isa/axpe-isa.md).

### 3.1 What is actually novel here, and what is not

**A delay field in every instruction is not novel.** RP2040's PIO does exactly
this, with a 5-bit delay in each instruction word. An entry that leads with it
is showing a judge a wider PIO. It remains the right foundation — it is what
makes the timing proof a one-line property — but it is table stakes, not a
differentiator, and the submission must not claim otherwise.

Two bets carry the novelty instead.

**Bet 1 — measured time is a first-class ISA value.** `WAITE` returns the number
of cycles it actually waited (§4.1 of the ISA document). The counter already
exists to enforce the timing discipline, and the `a` field was unused by `WAITE`,
so the feature costs one 16-bit read path and nothing in the encoding. It
converts the chip from one that emits known protocols into one that can measure
an unknown peer: autobaud in eight instructions, pulse-width capture,
self-calibration against hardware whose clock was never documented.

This follows from the competition's own framing. The announcement names hardware
debugging and reverse engineering as the purpose, and a reverse engineer is
rarely speaking a protocol whose timing they already know — they are trying to
discover it. An emulator that can only transmit has solved the easier half.
`sw/pemu/firmware/autobaud.s` is the demonstration.

**Bet 2 — the instruction set is written exactly once.**
[`sw/pemu/isa/axpe-isa.json`](../sw/pemu/isa/axpe-isa.json) is the single source;
`tools/axpe_isa.py` generates the SystemVerilog decoder constants, the C model's
opcode and timing tables, and the instruction tables inside the ISA document,
while the assembler loads it directly and holds no second copy. An ISA
transcribed into an assembler, a model, a decoder, a proof and a document is
written five times, and five copies drift — silently, and usually in the field
nobody re-reads, which for this design is a cycle count. `make` fails on drift,
in the same shape as the existing `requirements-check` gate. Consistency stops
being discipline anyone can slip on and becomes a build step.

## 4. The verification claim

PE-04 has an executable [host model](../sw/pemu/model/README.md), checked by
`make pemu-model-check`. UART now matches the platform waveform oracle,
autobaud measures known pulses exactly, and clocked shifts cover all four SPI
modes; the development failures that led to those corrections remain in the
[host evidence](../research/benchmarks/axpe-model.json).

PE-05's first [RTL differential checkpoint](../research/benchmarks/axpe-cosim.json)
compares Verilated pin/output traces and elapsed cycles with that model. The
scalar/control path passes 64 deterministic randomized programs. Directed
`WAITE` and shift cases retain one explicit XFAIL: the RTL inserts an undeclared
cycle when handing control back to the issue state. Until that bubble is
removed, this is defect evidence rather than a cycle-for-cycle conformance
claim, and PE-06 remains blocked.

The competition's second judging axis is methodology, and it is where this
project has the most to offer. The headline claim is a property of the ISA
itself:

> Every instruction retires in exactly the cycle count its encoding declares.

`WAITE` is the single deliberate exception, because waiting on an external edge
is data-dependent by nature. It is bounded by an explicit timeout, and the proof
uses that worst case.

The claim matters beyond elegance: if it holds, protocol firmware timing is
*statically* analysable. The cycle cost of a bit-bang loop can be computed from
the listing rather than measured, which is what makes firmware-defined protocol
timing trustworthy on a chip with no PLL and one clock.

Evidence layers, in the order they are built:

0. The ISA description generating every derived artifact, with drift failing the build
1. RTL against the golden model, cycle for cycle, on randomised programs
2. Formal proof of the declared-versus-actual cycle counts
3. Protocol conformance against *independent* reference implementations
4. A non-default knob run, proving the profile parameters are real
5. FPGA-in-the-loop on the Tang Primer against physical devices
6. Gate-level simulation of the same firmware after place-and-route

Simulation, P&R, and physical evidence stay separate in every record, as
elsewhere in this project. A submission that states its own gaps is worth more
on the judged axis than one that hides them.

## 5. Where the code lives

```
components/pemu/axpe/       RTL and manifest
components/pemu/none/       opt-out arm
configs/sim-axpe.json       Verilator profile
configs/sim-axpe-tiny.json  every knob at a non-default value
configs/tangprimer25k-axpe.json   FPGA bring-up, loader-based
configs/tt-axpe-6x4.json    ASIC area and timing budget
sw/pemu/isa/axpe-isa.md     normative specification
sw/pemu/as/axpe_as.py       assembler
sw/pemu/model/axpe_model.c  golden model
sw/pemu/firmware/           uart.s, spi.s, i2c.s
sim/pemu/                   cosimulation and conformance benches
formal/pemu/                timing-determinism proof
tools/axpe_area.py          cell-budget tracker
asic/tt-axpe/               Tiny Tapeout CMOS5L wrapper and flow config
```

The Tiny Tapeout submission repository is generated from this tree by
`make tt-export`, so there is one source of truth and the competition entry
cannot drift from the verified design.

## 6. The integration is the point

A protocol emulator submitted as a standalone repository is a chip. Submitted
through atomiX it is a chip **and the platform that produced it**, and the
second half is the part no other entrant can reproduce, because it is years of
work that happens to be exactly what this competition needs.

### The competition's premise is a co-design question

The announcement's founding claim is that protocols belong in firmware rather
than fixed logic. That is not a slogan — it is a hardware/software tradeoff with
an answer that depends on what you measure. atomiX exists to answer exactly that
shape of question, so instead of asserting the premise, the submission tests it:

[`research/experiments/protocol-firmware-vs-fixed-logic.json`](../research/experiments/protocol-firmware-vs-fixed-logic.json)
runs one UART frame through two unrelated machines — `pemu.axpe` running seven
instructions of firmware, and `uart.mmio16550`, the fixed-function UART this
project already had — and judges both against the same oracle. The result is a
Pareto table over cycles, cell area, firmware bytes and protocols expressible.
Fixed logic is expected to win on area and lose on the last axis outright: a
16550 cannot be taught I2C, and it certainly cannot measure a peer it has never
seen.

Nobody else entering can run that comparison, because running it requires
already owning a fixed-function UART, a component system that can select between
them, and a contract for comparing across targets without inventing a composite
score. This repository owned all three before the competition existed.

### One workload, one oracle, four execution targets

[`research/personalities/workloads/uart-tx-8n1.json`](../research/personalities/workloads/uart-tx-8n1.json)
defines the workload as **the waveform**, not as any machine's behaviour: a start
bit low, eight data bits least-significant first, a stop bit high, recorded as
transitions so a run of equal bits produces no edge. Its oracle is registered in
`tools/personality_contract.py` beside SAXPY and GEMM — the emulator's notion of
correctness is now platform infrastructure, not a private testbench.

That one definition then validates the C golden model, the RTL under Verilator,
the FPGA image, and the CMOS5L netlist. A firmware bit-banger and a hard UART
must agree on it without sharing a register map, a clock domain, or an ISA. The
platform's rule that **evidence levels never collapse** does the rest: a
place-and-route area is not an FPGA number and neither is a silicon claim, and
the schema refuses to let a report pretend otherwise.

### The tapeout decision becomes a measurement

`components/pemu/axpe/component.json` declares `imem_words`, `reg_count`,
`reg_width`, `delay_bits`, `uio_pins` and `call_depth` as profile knobs, each
with a default and a doc, following the project's own rule that a knob is only
real once it is wired, bounded, and exercised at a non-default value. The
experiment sweeps them.

So the question PE-02 opened — how big should the program memory be — stops
being a judgement call and becomes a row in a table: three instruction-store
depths and two register widths, each with its measured area and its answer to
whether the firmware still fits. That is the design-space exploration this
platform was built for, applied to a decision that will be etched into silicon.

`tools/axpe_isa.py` keeps the manifest and the ISA description from drifting
apart: the manifest's defaults for register count, register width and delay
width must equal what `axpe-isa.json` says, or the build fails. A profile may
still override them — that is what a knob is — but a profile and an architecture
cannot silently disagree about how wide a register is.

### What the submission can therefore say

That the design is correct against an executable oracle shared with the rest of
a platform; that its timing is proved rather than measured; that its instruction
set exists in exactly one place and every derived artifact is generated from it;
that its parameters were chosen by sweeping them; and that the premise of the
competition itself was tested rather than assumed.

## 7. Open questions

- PE-02: whether the Tiny Tapeout 6×4 flow accepts an IHP SRAM macro, and what
  the real cells-per-tile figure is. Macro footprints are measured (§2.1); these
  two are not. The depth question is settled at 256 by the eight-bit branch
  target, so `RM_IHPSG13_1P_256x32_c2_bm_bist` at 6.9% is the candidate unless
  the ISA gains a wider target.
- PE-03: instruction width, register count and datapath width, under §2's ceiling.
- Target clock frequency, and therefore the fastest protocol bit rate reachable.
- Whether the 8×4 tile option becomes available, and what it would buy.
- Stretch protocols, evaluated in PE-07 and dropped without ceremony if the
  budget or the clock says no.
- Team or solo entry. The competition strongly recommends teams; this changes
  how much of PE-07 and PE-11 can be carried.
