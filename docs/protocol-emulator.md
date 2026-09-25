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
| Area | 6×4 tiles. The announcement's nominal estimate is 200µm × 150µm per tile, or about 0.7 mm²; the pinned CMOS5L support tools define the actual 6×4 hardening rectangle as 1289.28µm × 710.64µm = 0.916 mm². An 8×4 option remains outside the current rules and is not assumed |
| Logic budget | ~1K logic cells per tile → ~24K cells. This is the competition announcement's estimate, not a measurement; PE-02 replaces it with one |
| Pins | Tiny Tapeout harness: 8 input, 8 output, 8 bidirectional, plus `clk`, `rst_n`, `ena` |
| Mandatory protocols | UART, SPI, I2C |
| Stretch | Low-speed USB, 10Mbit Ethernet. Also named as interesting: JTAG, SWD, PS/2, CAN |
| Licence | Open source, required |
| Judged on | Unique functionality, and novel design and verification methodology |

### 1.1 Official template baseline

The competition page links Tiny Tapeout's `cmos5l` Verilog-template branch and
requires `tiles: "6x4"`.  PE-01 pins that branch at
`b86a2a781484bcab7ba522dc5de540086695a430` (tree
`5d72d5b9e04c0732d32c7f7d0f72cf950508e551`) and imports it byte-for-byte under
[`asic/tt-axpe/`](../asic/tt-axpe).  Its top-level contract is a unique
`tt_um_*` module with eight dedicated inputs, eight dedicated outputs, eight
bidirectional input/output/enable paths, `ena`, `clk`, and active-low `rst_n`.

The template's `info.yaml` comment is older than the flow it invokes: it lists
only `*x2` shapes.  The `ihp-sg13cmos5l` support-tools revision
`d66cf179e7bc4d296362ab7e2e3b344dc3c4f665` explicitly carries `6x4` with the
rectangle `0 0 1289.28 710.64`, so the competition rule is both unambiguous and
accepted by the named technology data.  That revision also knows `8x4`, but
tool support is not permission: Jane Street's current page still says 6×4 is
the maximum and that a larger allocation would be announced separately.

The baseline is intentionally not customised yet.  In particular, its CI GDS
workflow selects CMOS5L while the devcontainer still names SG13G2, and its
actions follow moving branch names.  PE-02 owns pinning the executable flow,
binding axpe and running it.  PE-01 is source provenance and interface evidence,
not a synthesis or physical-design result; the exact upstream record and the
known drift are in [`asic/README.md`](../asic/README.md).

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
exists to settle. The first pinned-PDK inspection and flow candidate are below;
only place-and-route can settle whether the fallback actually fits.

### 2.1 Macro lead rejected; bounded inferred-store trial

Measured 2026-09-17 from the `SIZE` records in the IHP-Open-PDK `main` branch
LEF files under `ihp-sg13g2/libs.ref/sg13g2_sram/lef/`. The shares below are
recomputed against the pinned CMOS5L support tools' 6×4 hardening rectangle,
1289.28µm × 710.64µm = 916,214 µm²:

| Macro | Footprint (µm) | Area (µm²) | Share of 6×4 |
|---|---|---|---|
| `RM_IHPSG13_1P_64x16_c2` | 236.80 × 64.36 | 15,240 | 1.7% |
| `RM_IHPSG13_1P_256x8_c3_bm_bist` | 236.80 × 74.10 | 17,547 | 1.9% |
| `RM_IHPSG13_1P_256x16_c2_bm_bist` | 236.80 × 118.78 | 28,127 | 3.1% |
| `RM_IHPSG13_1P_256x32_c2_bm_bist` | 416.64 × 118.78 | 49,488 | 5.4% |
| `RM_IHPSG13_1P_512x16_c2_bm_bist` | 236.80 × 191.34 | 45,309 | 4.9% |
| `RM_IHPSG13_1P_512x32_c2_bm_bist` | 416.64 × 191.34 | 79,720 | 8.7% |

These are real SG13G2 macro dimensions, but they are **not a CMOS5L
implementation result**. Inspection of the exact IHP-Open-PDK commit
`2bbec755dc67ca3db0261c3d6163e15735d66710` installed by the pinned official
GDS action found no SRAM LEF/GDS/liberty/Verilog views under
`ihp-sg13cmos5l/libs.ref`; the table's macros exist only under
`ihp-sg13g2/libs.ref/sg13g2_sram`. Importing one across technologies without an
explicitly supported library contract would turn a useful footprint estimate
into a false flow claim, so PE-02 rejects that candidate for now.

**But 256 words is a ceiling the ISA imposes, not a budget choice.** `BR` and
`CALL` targets are eight bits, so nothing past word 255 can be jumped to
however large the store is. The 512x32 macro at 8.7% buys addressable nothing.
Raising the ceiling is an ISA change — a wider target field, or paging — and it
would cost encoding bits that are already spent. RTL elaboration at
`IMEM_WORDS=512` is what surfaced this; the parameter sweep the project's own
knob rule requires is what ran it.

The bounded fallback is the existing 32-bit ISA with **64 inferred instruction
words**: 2,048 storage bits before synthesis overhead. The mandatory images are
UART 36 words, SPI 15, I2C 54 and autobaud 55, so 64 is the smallest
power-of-two profile that preserves every T1 program. It is selected by
[`configs/tt-axpe-6x4.json`](../configs/tt-axpe-6x4.json), while 256 remains the
component default; `imem_words` is bounded to powers of two from 16 through 256.
The exact Tiny Tapeout wrapper passes the same two-program and independent-peer
suite as the direct chip boundary at 64 words. That is functional simulation,
not evidence that 2,048 inferred bits place or route.

The executable flow inputs and success criteria are frozen before the run in
[`asic/axpe/flow-lock.json`](../asic/axpe/flow-lock.json): 6×4, 20 ns, no setup,
hold or routing violations, and no power claim. `make tt-export` verifies the
pristine template hash, resolves the component profile and emits a standalone
repository with source hashes and a commit-pinned GDS workflow. A smaller
latch implementation or streamed window remains a fallback if the first
physical run refutes the inferred array.

### 2.2 ASIC dependency map

RX-08's portability audit is deliberately at source and interface boundaries,
not at module names alone:

| Boundary | Classification and exact dependency | Replacement / verification route |
|---|---|---|
| Core, decode, timing, shift and pad logic | Portable synthesizable SystemVerilog in `axpe*.sv`; no FPGA primitive, PLL, generated clock, initial block or vendor arithmetic | Use the same sources unchanged; cycle-for-cycle cosimulation and independent UART/SPI/I2C peers remain the functional gates |
| Instruction store | `axpe_imem.sv` requires one synchronous-read/write address and no promised read-during-write value; it has no reset or initial contents | The host must load every program after reset. CMOS5L has no compatible SRAM views, so this run maps 64×32 to standard cells; any later macro or streamed window must preserve this contract and rerun the two-program chip suite |
| Clock and reset | One external `clk`; active-low asynchronous reset for state; `ena` and the loader's `running` state hold the core reset while leaving the host alive | The Tiny Tapeout wrapper connects these ports directly. No clock conversion is inferred; STA owns the external input/output assumptions |
| Loader clock-domain boundary | Host SCLK, MOSI and CS are asynchronous pads sampled by `clk`; SCLK is synchronized and contractually limited to `clk/4` | `docs/pemu-host-protocol.md` is the adapter contract; wrapper simulation exercises it, while CDC signoff beyond the explicit synchronizer remains open |
| Protocol I/O | `ui_in`, `uo_out` and `uio_*` are generic logic; open-drain behavior is expressed through `uio_oe`, not a device primitive | The `tt_um_*` wrapper is the only technology harness adapter. Independent protocol peers test behavior; post-route STA tests the declared pad-delay budget |
| Configuration and ISA include | Component parameters become generated Verilog defines; `axpe_isa.svh` is generated from the normative ISA JSON | `tools/tt_axpe.py check` resolves a non-default 64-word profile, hashes every exported source and rejects template drift or nondeterministic output |

The audit therefore proceeds with the standard-cell store for this bounded
experiment. It rejects the SG13G2 SRAM as a cross-technology substitution and
defers a memory-macro claim until CMOS5L supplies compatible LEF, GDS, liberty
and simulation views. It does not require an FPGA-specific replacement.

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
an unknown peer: autobaud in eight instructions, and pulse-width capture.

**Self-calibration now follows from it, and PE-15 is what closed the gap.**
`D` is an immediate in the instruction word, so for a while `autobaud.s` could
measure a bit period and then not transmit at it — the feature was half of
itself, and the board said so rather than rounding the claim up. `SHPER` writes
a 16-bit period register and one bit of the otherwise unused `b` field lets
`SHOUT`/`SHIN`/`SHIO` take their cell duration from it, which cost one of the
two reserved opcodes and no encoding space at all.
[`sw/pemu/firmware/autobaud-demo.s`](../sw/pemu/firmware/autobaud-demo.s) is
the whole loop: it measures an unconfigured peer and answers at that peer's
rate, with no host involved and no rate written anywhere in the program. The
chip bench runs it at two different peer rates through one unchanged elaborated
design, because one rate could be a constant that happened to be right.

The honest cost is in the listing, not the hardware. A selected shift is still
exact — it retires in `n*max(P,1)`, a function of machine state and of nothing
external — but it is no longer *static*, so `axpe_as.py` prints the formula
where it would print a number. Those are two different claims and this design
now needs both words. Evidence is in
[`axpe-period.json`](../research/benchmarks/axpe-period.json).

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

PE-05's [RTL differential gate](../research/benchmarks/axpe-cosim.json) compares
Verilated pin/output traces and elapsed cycles with that model, every cycle and
with no tolerated deviation: the scalar and control path, the shift engine and
`WAITE`, across 112 deterministic randomized programs and twelve directed cases.

The XFAIL that checkpoint recorded is closed. Returning from `WAITE` or a shift
to the issue state inserted a cycle the ISA does not declare, so a transfer cost
`n*max(D,1) + 1` — the same `1 + D` shape §3 rejects, one cycle past the bit
period on every transfer and accumulating across a frame. The cause was the
handoff itself: a long instruction kept its word in `imem_data` until it
finished, so the next instruction could not be fetched in time to issue on the
cycle it should. Every instruction now advances the PC at issue, a running
instruction reads latched operands instead of the instruction word, and it
retires *on* its final cycle with the next instruction issuing into that same
edge — which is why a retiring result is forwarded to the instruction that
reads it. At default parameters that is 43 added flip-flops counted from the
declarations — 25 in the core, 18 in the shift engine — against the whole-chip
ceiling near 7,680 in §2; no synthesis has run, so that is a count and not a
mapped area. It is what the declared-retirement claim means in hardware rather
than on paper, and PE-06 can now start.

PE-14's [chip gate](../research/benchmarks/axpe-chip.json) closes the other half
of that, and it is the half the entry is invalid without. `axpe_chip` composes
the core with a writable single-port store and a fixed-logic SPI host port; the
bench elaborates it once, loads one program, runs it, then loads an unrelated
program into that same design and runs that. Both are compared with the golden
model cycle for cycle, so the claim is not "it loaded" but "it executes what was
loaded, exactly". The contract those four pins answer to is frozen in
[`docs/pemu-host-protocol.md`](pemu-host-protocol.md).

The store is single port because the macro is, so the loader refuses writes
while the core runs and reports the refusal rather than dropping it. That is the
one place this design could have been made easier in simulation than in silicon,
and it was not.

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
1b. Two unrelated programs loaded over the host port into one unchanged design,
    each cycle-exact — the capability the entry is invalid without
2. Formal proof of the declared-versus-actual cycle counts
3. Protocol conformance against *independent* reference implementations --
   in simulation now, against hardware in PE-09
4. A non-default knob run, proving the profile parameters are real
5. FPGA-in-the-loop on the Tang Primer against physical devices
6. Gate-level simulation of the same firmware after place-and-route

Simulation, P&R, and physical evidence stay separate in every record, as
elsewhere in this project. A submission that states its own gaps is worth more
on the judged axis than one that hides them.

## 5. Where the code lives

```
components/pemu/axpe/       RTL and manifest
  axpe.sv                   the core: decode, timing, control
  axpe_shift.sv             the shift engine
  axpe_imem.sv              writable instruction store, single-port sync read
  axpe_host.sv              SPI host port: the loader that is not firmware
  axpe_chip.sv              the three composed, in Tiny Tapeout pin shape
docs/pemu-host-protocol.md  the frozen host contract
components/pemu/none/       opt-out arm
configs/tangprimer25k-axpe.json   FPGA bring-up, loader-based
configs/tt-axpe-6x4.json    ASIC area and timing budget
sw/pemu/isa/axpe-isa.md     normative specification
sw/pemu/as/axpe_as.py       assembler
sw/pemu/model/axpe_model.c  golden model
sw/pemu/firmware/           uart.s, spi.s, i2c.s and their loadable demos
sim/pemu/axpe_peers.h       independent UART, SPI and I2C peers
sim/pemu/                   cosimulation and conformance benches
formal/pemu/                timing-determinism proof
asic/tt-axpe/               pristine official CMOS5L template baseline
asic/axpe/                  wrapper, project metadata and pinned flow overlay
tools/tt_axpe.py            deterministic standalone-repository exporter
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

- PE-02: whether the 64×32 inferred store and the rest of axpe place and route
  in the official 6×4 CMOS5L flow at 20 ns. The exact pinned PDK has no
  compatible SRAM macro views; the SG13G2 footprint table in §2.1 is context,
  not a substitution license. If the inferred store fails, the next experiment
  is a smaller latch store or streamed instruction window, with the same
  single-port synchronous contract.
- PE-03: instruction width, register count and datapath width, under §2's ceiling.
- Target clock frequency, and therefore the fastest protocol bit rate reachable.
- Whether the 8×4 tile option becomes available, and what it would buy.
- Stretch protocols, evaluated in PE-07 and dropped without ceremony if the
  budget or the clock says no.
- Team or solo entry. The competition strongly recommends teams; this changes
  how much of PE-07 and PE-11 can be carried.
