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

Current guidance includes the [organizer follow-up recorded 2026-10-10](notes/jane-street-follow-up-2026-10-10.md).
The complete email and the requirement-to-card mapping live there. Its sent
date was not supplied; expected releases in that message are not recorded as
completed releases. PE-12 submission compliance now precedes further PE-08 work.

The maintainer's October 12 [physical test plan](notes/axpe-hardware-test-plan-2026-10-12.md)
schedules PE-09 on the available Tang Primer Dock before further PE-08 repairs.
Adapter simulations and routed-image preflight now exist; physical loader
execution, independent peers, real EEPROM transactions, capture-clock timing
and power-cycle recovery remain. [AT24C256 runtime tools](../sw/pemu/firmware/eeprom/README.md)
now fit the 64-word store and pass independent digital peers; no physical
EEPROM access has been performed. Dates are targets;
no physical axpe result is claimed.

| | |
|---|---|
| Deadline | 2027-01-18 |
| Process | IHP 130nm CMOS5L, through Tiny Tapeout |
| Area | 6×4 tiles. The announcement's nominal estimate is 200µm × 150µm per tile, or about 0.7 mm²; the pinned CMOS5L support tools define the actual 6×4 hardening rectangle as 1289.28µm × 710.64µm = 0.916 mm². The follow-up plans an 8×4 maximum but directs entrants to stay at 6×4 until that template is released; 8×4 is an optional upgrade |
| Logic budget | ~1K logic cells per tile → ~24K cells. This is the competition announcement's estimate, not a measurement; PE-02 replaces it with one |
| Pins | Tiny Tapeout harness: 8 input, 8 output, 8 bidirectional, plus `clk`, `rst_n`, `ena` |
| Project baseline protocols | UART, SPI, I2C; the follow-up says to start here and sets no fixed speed requirement |
| Stretch | Low-speed USB, 10Mbit Ethernet. Also named as interesting: JTAG, SWD, PS/2, CAN |
| Licence / submission | Open source; public repository at submission, with RTL/tests, architecture/ISA, toolchain/examples, verification and AI-use write-up, passing Tiny Tapeout GDS/precheck |
| Judged on | Flexibility to support new protocols is the main criterion; no fixed weights. Protocol demonstrations, unique functionality and design/verification methodology also count |
| Clock / I/O | No mandated clock: select one that closes P&R and meets the protocols. Demo-board I/O is digital, 3.3 V; external parts belong on documented Pmods. CMOS5L pads are not yet characterized in the supplied update |
| Lifecycle | Use `rst_n` to establish state. Deselection powers down the design and loses state: select/reset/reload before running again |

### 1.1 Official template baseline

The original competition baseline links Tiny Tapeout's `cmos5l` Verilog-template
branch with `tiles: "6x4"`. The follow-up retains 6×4 until the planned 8×4
template is released. PE-01 pins that branch at
`b86a2a781484bcab7ba522dc5de540086695a430` (tree
`5d72d5b9e04c0732d32c7f7d0f72cf950508e551`) and imports it byte-for-byte under
[`asic/tt-axpe/`](../asic/tt-axpe).  Its top-level contract is a unique
`tt_um_*` module with eight dedicated inputs, eight dedicated outputs, eight
bidirectional input/output/enable paths, `ena`, `clk`, and active-low `rst_n`.

The template's `info.yaml` comment is older than the flow it invokes: it lists
only `*x2` shapes.  The `ihp-sg13cmos5l` support-tools revision
`d66cf179e7bc4d296362ab7e2e3b344dc3c4f665` explicitly carries `6x4` with the
rectangle `0 0 1289.28 710.64`, so the selected baseline is accepted by the
named technology data. That revision also knows `8x4`; the follow-up now
clarifies that 8×4 is the planned maximum. We still require the announced
template release and a separately pinned, verified profile before adopting it.

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
`ihp-sg13g2/libs.ref/sg13g2_sram`. That was the reason the original PE-02
experiment chose inferred storage; it is a finding about that installation,
not a competition-wide SRAM prohibition. The organizer follow-up explicitly
permits IHP macros and points to an integration walkthrough covering RTL,
LibreLane, Metal4 power and sign-off. That route is now an optional research
path. Pin its views, integration and power/physical checks, preserve the store
contract and pass Tiny Tapeout precheck before making a macro claim. The
selected candidate continues to use the measured 64-word inferred store.

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
| Instruction store | `axpe_imem.sv` requires one synchronous-read/write address and no promised read-during-write value; it has no reset or initial contents | The host must reload after reset or power loss. The original pinned CMOS5L library installation lacked SRAM views, so this candidate maps 64×32 to standard cells; any later macro or streamed window must preserve this contract and rerun the two-program chip suite |
| Clock and reset | One external `clk`; active-low asynchronous reset for state; `ena` and the loader's `running` state hold the core reset while leaving the host alive | The Tiny Tapeout wrapper connects these ports directly. No clock conversion is inferred; STA owns the external input/output assumptions |
| Loader clock-domain boundary | Host SCLK, MOSI and CS are asynchronous pads sampled by `clk`; SCLK is synchronized and contractually limited to `clk/4` | `docs/pemu-host-protocol.md` is the adapter contract; wrapper simulation exercises it, while CDC signoff beyond the explicit synchronizer remains open |
| Protocol I/O | `ui_in`, `uo_out` and `uio_*` are generic logic; open-drain behavior is expressed through `uio_oe`, not a device primitive | The `tt_um_*` wrapper is the only technology harness adapter. Independent protocol peers test behavior; post-route STA tests the declared pad-delay budget |
| Configuration and ISA include | Component parameters become generated Verilog defines; `axpe_isa.svh` is generated from the normative ISA JSON | `tools/tt_axpe.py check` resolves a non-default 64-word profile, hashes every exported source and rejects template drift or nondeterministic output |

The audit therefore proceeds with the standard-cell store for this bounded
experiment. The organizer-permitted IHP macro route is a separate optional
experiment requiring pinned LEF, GDS, Liberty and simulation views, appropriate
power integration and passing physical/precheck evidence. No memory macro is
part of the selected candidate. No FPGA-specific replacement is required.

The same figures constrain the datapath. With a whole-chip ceiling near 7,680
flip-flops and logic still to pay for, a wide register file is not affordable: a
32-bit × 8-entry file alone is 256 flip-flops. The working assumption is a
narrow datapath and few registers, revisited in PE-03.

### 2.3 First CMOS5L physical result

The pinned 64×32 standard-cell candidate synthesized to 12,026 cells and
227,279 µm², including 2,497 flip-flops. In the official 6×4 rectangle,
post-route standard cells occupy 287,809 µm² of a 902,417 µm² core (31.9%).
Global routing had zero overflow; detailed OpenROAD routing DRC, the final
antenna check, and the critical disconnected-pin check all reported zero.

The 20 ns timing criterion **fails** after RC extraction. The slow
`1.08 V / 125 °C` corner has one setup violation, with −0.903 ns worst slack
and total negative slack. Its path starts at `uio_in[4]` and ends at the
instruction store's registered read data; register-to-register setup has
+14.466 ns worst slack. All three corners have zero hold violations; the
fast and typical corners have zero setup violations. The slow corner also has
9 max-slew violations, and each corner reports 164 max-fanout violations.
These are violations to resolve, not clean signoff.

The result refutes the declared 20 ns target, not the store's capacity or
routability. PE-02 proceeds with the inferred store and hands PE-10 a new,
separately locked timing experiment starting at 25 ns, with an explicit I/O
delay contract and electrical-violation repair. A 25 ns pass is only an
inference from the current slack until that run is measured. This run stopped
after post-route STA; full GDS, Magic DRC, LVS, gate-level firmware replay,
power with an activity model, and silicon behavior remain unproved. The exact
inputs, commands, hashes, metrics, and the interrupted earlier attempt are in
[`axpe-cmos5l-feasibility.json`](../research/benchmarks/axpe-cmos5l-feasibility.json).

PE-10's separate 25 ns candidate is now measured, not inferred. With a
provisional 4 ns input/output delay, its post-route slow-corner setup slack is
+4.091 ns; every setup and hold check passes. OpenROAD routing DRC and final
antenna checks are clear. Standard cells use 287,869 µm² of the same core.
This is not electrical closure: the slow corner has 14 max-slew violations,
and all corners have 162 max-fanout violations; 160 are CTS leaf clock buffers.
The separate GDS continuation has now completed with zero Magic DRC errors,
uniquely matching LVS circuits and a passing antenna check. A CTS cluster-size-8
trial reaches +4.846 ns slow-corner setup slack and reduces fanout and
slow-corner slew violations to six each. Its GDS/DRC/LVS stage is not yet run,
and the remaining fanout and slew violations require repair. These are flow
results at a provisional I/O delay, not a validated external pad contract or
silicon behavior. Exact inputs and reports are in
[`axpe-cmos5l-25ns.json`](../research/benchmarks/axpe-cmos5l-25ns.json).

Two locked negative trials narrow the repair route. Reducing CTS clusters to
four worsened the comparable pre-route fanout count from two to 13. Tightening
the global fanout target to six made eight upstream clock buffers exceed it at
fanout 16, for 14 pre-route violations. Both trials were stopped during
detailed routing; neither has a post-route or GDS result. The six remaining
violations in the completed size-eight run call for selective data-path repair,
not a tighter whole-design fanout target.

Five later locked trials have reached a nominal-corner pre-route checkpoint.
The 25 ns closure settings (CTS clusters of eight, fanout limit eight and a
2 ns transition target) leave three fanout violations there. Adding ABC
buffering with area or delay synthesis makes that count 42 or 51 respectively.
The ABC area variant has now completed post-route STA: setup and hold pass and
routing DRC is zero, but fanout violations reach 111 at every corner and
slow-corner slew violations reach 273. Of the 111 fanout-violating drivers,
110 are `sg13cmos5l_buf_1` cells in the final mapped netlist. The ABC delay
variant also completes post-route STA with passing setup, hold, route DRC and
antenna checks, but reaches 102 fanout and 829 slow-corner slew violations;
101 of its fanout violators are `buf_1` cells. Neither ABC variant proceeded to
GDS. Resuming the
closure design with antenna jumpers only clears the nominal pre-route fanout
count, while a zero antenna-repair margin on the CTS-size-eight design leaves
two. The closure, jumper and zero-margin runs each ended with an unexpected
OpenROAD detailed-routing error during pin access. Their pre-route counts
cannot establish electrical closure.
The two-thread retry of jumper-only repair reached its antenna check and found
27 violating nets and 35 violating pins. That rejects this antenna strategy
regardless of its nominal pre-route fanout count; the retry was stopped there.
The pinned inputs, report hashes and failure boundaries are in
[`axpe-cmos5l-25ns.json`](../research/benchmarks/axpe-cmos5l-25ns.json).

A bounded resizer probe on the completed CTS-size-eight database reproduces
its six slow-corner slew and six fanout violations from extracted parasitics.
With placement estimates, OpenROAD inserts seven buffers across the six
fanout nets. The placement estimate loses the routed slew violations even
before repair, so this probe identifies a possible fanout mechanism only; it
does not establish routed electrical closure. The runnable Tcl and its hashed
log are in the same evidence record.

The next locked experiment enables LibreLane's built-in post-global-route
design repair on the CTS-size-eight candidate and reruns global routing from
that checkpoint.
Its `asic_post_grt_design_repair` profile setting is validated against the flow
lock and exercised at `true`. The step runs but inserts no buffers and resizes
no cells. Its output netlist is identical to the parent, antenna checks pass,
and the nominal pre-route check still has three fanout violations. The trial
was stopped before detailed routing; no post-route improvement is claimed.

Resuming that locked repair step from its completed post-antenna state does
insert buffers. Five successive repair/antenna passes insert 5, 2, 3, 1 and 3
buffers; antenna checks pass each time. The nominal pre-route fanout count is
2, 2, 1, 1 and 2: new violations appear after antenna work, so the repeated
sequence does not converge. The last three passes stop at the STA checkpoint
using a bounded flow command. A CTS-size-eight GDS continuation and two older
detailed-route retries were stopped when this more focused checkpoint was
available; none contributes post-route or signoff evidence.

A further locked variant disables global-route antenna repair after one more
design-repair step. It reaches zero nominal pre-route fanout, slew and cap
violations but leaves 15 antenna-violating nets. Detailed routing repairs
those antennas and completes with zero OpenROAD route DRC and zero final
antenna violations. All-corner setup and hold pass; slow-corner setup slack is
+3.099 ns. The routed design still has one fanout violation at every corner
and 19 slow-corner slew violations, so PE-10 electrical closure remains open.
The variant has not run GDS/DRC/LVS. An in-memory repair probe inserts three
buffers and resizes two cells, but OpenROAD uses wire-load estimates after
changing the design; its after-report is not routed timing evidence. The
provisional 4 ns I/O delay also still needs an external pad contract.

The next bounded repair trials isolate two global-route controls. Raising the
post-GRT slew margin from its pinned default of 10% to 35% finds three slew
targets but produces a byte-identical repaired netlist and nominal STA report.
Five of the seven routed violating gate outputs are `a221oi_1` cells, for
which the pinned library has no higher drive variant; simply asking the
resizer for more margin does not change them. A separate 400 µm maximum-wire
trial inserts 272 buffers across 211 nets, including a chain on a connection
whose endpoints are separated by at least 746 µm horizontally. Nominal
pre-route electrical checks remain clear, though global-route parasitic
estimation emits missing-route-to-pin warnings. The first detailed-route
attempt was interrupted; a supervised retry completed with zero route DRC and
antenna errors, zero all-corner setup, hold, fanout and cap violations, and
six slow-corner slew violations. Slow-corner setup slack is +7.100 ns, but
fast-corner hold margin is only +0.007 ns. The six slew pins are on two nets
driven by `nor4_1` cells. This is routed improvement, not electrical closure;
the variant has no GDS/DRC/LVS result, and the 4 ns I/O delay remains
provisional without an external pad contract.

A separately locked 200 µm cap inserts buffers after both of those `nor4_1`
drivers and completes a detailed route with zero DRC and antenna errors.
Extracted STA clears all-corner setup, hold, slew and cap checks, but one
max-fanout violation remains at every corner. The input buffer `input4/X`
drives four functional sinks and five antenna diodes, producing fanout nine
against the library limit of eight. Fast-corner hold slack is only +0.012 ns.
The zero-margin antenna reroute completes with byte-identical netlist, metrics
and slow-corner checks: it still adds five diodes and fails fanout. That control
does not repair this candidate.

A bounded physical ECO now inserts one `buf_1` between `net4` and its two
adjacent mux loads. The recipe checks the parent ODB, netlist and constraints
by hash, verifies every cell and connection against the expected one-buffer,
two-load delta, and clears stale timing and physical views from its checkpoint.
Placement and global routing complete; nominal estimated-parasitic STA clears
setup, hold, fanout, slew and cap. Global-route antenna estimation still finds
four violating nets. The supervised detailed route now clears route DRC,
antenna and setup/hold/slew/fanout/cap at all three extracted corners. Only
three antenna diodes are added, on other nets; net4/child fanout stays 3/2.
Fast hold slack is +0.025081 ns. Full Magic DRC and Netgen LVS now pass with
zero errors. The final signoff netlist is byte-identical to the routed netlist
that passes the shared protocol suite at three seeds. KLayout DRC/XOR and
Yosys EQY are skipped; the 4 ns external I/O budget remains provisional and
the maintainer owes commit-pinned review.

The [mapped functional replay](../research/benchmarks/axpe-netlist.json) now
checks both the completed 200 µm zero-margin route and the prepared one-buffer
ECO. `make pemu-netlist-check` runs the existing chip suite, C oracle, firmware
and independent UART/SPI/I2C peers on each unchanged netlist at three randomized
startup seeds. Yosys derives the cell logic from the pinned Liberty files;
all three corners generate identical models. Missing models and disconnected
inputs fail before compilation. The PDK's timing-check delayed signals are not
driven by Verilator when it ignores the timing constructs, so that direct-model
path was rejected and recorded. This is two-state, zero-delay functional
evidence, with no SDF or extracted timing claim. The completed ECO route also
passes all shared cases at three seeds. Final signoff must retain the replayed
netlist hash before this can cover the final submission candidate.

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

`make tt-export` now bundles the same chip cases, C model, independent peers,
assembler and firmware with the Tiny Tapeout source tree. The exported
[demo](../asic/axpe/demo/README.md) needs no atomiX checkout and runs the
runtime-loaded UART/SPI/I2C and autobaud tests at three startup seeds.
`make pemu-asic-check` runs this standalone path. A fresh export relocated
outside the repository also passes, with unchanged hardware source hashes.
The manifest hashes verification inputs separately from hardware, and the
evidence index records historical inputs, levels and unresolved work. This
prepares PE-12; it does not supply final-candidate signoff or a silicon result.

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

The [isolated timer proof](../formal/pemu/README.md) now establishes
`max(D,1)` occupancy and `last` by induction at the component default delay
width and half-width. The independent reference counts elapsed cycles upward,
using a duration expression generated from the ISA. Real load/completion covers
and two broken-timer counterexamples check that the property is not vacuous.
[Recorded evidence](../research/benchmarks/axpe-timing.json) is limited to binary
sampled-edge behavior of the timer; this isolated result alone does not establish
core retirement, shift or `WAITE` behavior. Asynchronous reset recovery and
physical timing are outside it.

The [isolated shift proof](../research/benchmarks/axpe-shift-timing.json) now
establishes cell duration, bit count and final-cycle `done` for arbitrary
effective delay under the legal/stable caller contract. It decomposes the
normative product into independent cell age and bit index; non-vacuity covers
include all four SPI modes and back-to-back completion, and two mutated engines
must fail. This isolated result alone does not establish core operand holding,
register-period selection or instruction handoff. Two normative
wording issues found in this review are now clarified: BR uses `max(D,1)`,
and immediate level-high wait returns zero but occupies one cycle. Generated
C/SV headers stay byte-identical, and model tests and both isolated proofs
pass again; no hardware source identity changes.

The [core wait proof](../research/benchmarks/axpe-wait-timing.json) now covers
legal `DELAY`/`WAITE` streams at the selected profile. A downward reference
budget proves the upward count and effective timeout, held operands across
changing words, final-sample T and following-instruction issue without a bubble.
Eleven reachable witnesses and two mutant counterexamples check the domain and
properties. The word source is abstract; fetch, other instruction classes and
the immediate-level zero register value remain outside this formal claim.

The [complete legal-stream proof](../research/benchmarks/axpe-core-timing.json)
now establishes occupancy and handoff for all 31 defined opcodes at the selected
profile: fixed duration, encoded/register-selected shift cells, held operands,
wait bounds and full HALT occupancy. The reference counts cell age upward,
bit index forward and wait budget downward, and checks architectural timing
controls against their source operand. No DUT ready/done/reject is assumed.
All 31 opcode completions and 15 additional boundaries have witnesses; five
broken core copies must yield base-case counterexamples. Legal operands,
balanced stack and in-range branch/call targets define the domain; program
memory/fetch data, arithmetic/data/pin effects, invalid-program fault policy,
non-default architecture and physical reset recovery remain outside it.
The core RTL and generated ISA headers are unchanged, preserving the routed
candidate's source identity. PE-06 awaits maintainer commit-pinned review.

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

PE-12 now exports explicit [submission/clock](../asic/axpe/docs/submission-compliance.md),
[AI-use](../asic/axpe/docs/ai-use.md) and [wiring/reload](../asic/axpe/docs/demo-wiring.md)
drafts. The shipped firmware's 50 MHz constants imply different absolute rates
at the selected 40 MHz target, and its logical pins need adapters for the
recommended Pmod mappings; neither discrepancy is hidden by a simulation pass.
`make pemu-precheck` records unchanged Tiny Tapeout checks against exact
GDS/LEF/netlist bytes. All nine pinned checks pass on the selected GDS; the
[precheck receipt](../research/benchmarks/axpe-precheck.json) retains tool/report
hashes and the initial setup failure.
Candidate packages can include a completed precheck via `--precheck`; the
packager and portable validator bind it to the selected GDS and signoff state.
Logical reset/selection/full-reload now passes on exported RTL and the selected
routed netlist at three startup seeds; see
[lifecycle evidence](../research/benchmarks/axpe-lifecycle.json).
Three supplied 40 MHz runtime profiles now have waveform/rate checks; the I2C
timing audit rejected earlier decoded-but-too-short SCL low intervals and
corrected runtime handoffs and the fast cell. Physical power-loss/carrier
validation and maintainer review remain open; the staged ECO continuation
now passes with byte-identical routed inputs/metrics and matching GDS
non-timestamp bytes. Maintainer review/publication remain owed. Earlier local
archives remain historical.

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
planned experiment sweeps them. The first PE-08 slice now resolves all six
into the RTL build and a capacity harness through `make pemu-profile-check`.
A 64-word, seven-register, four-pin, two-stack-entry profile passes boundary
probes; register and delay widths remain 16. The all-non-default tiny profile
is a failing experiment: its width/index assumptions still prevent strict
elaboration. Four registers and a one-entry stack also fail elaboration when
probed independently. These are functional capacity measurements, not an area
sweep or full non-default ISA conformance. See
[`axpe-profiles.json`](../research/benchmarks/axpe-profiles.json).

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
that selected capacities have executable boundary checks; and that the premise
of the competition itself was tested rather than assumed. Parameter selection
by a complete area/timing sweep remains future work and is not a submission
claim.

## 7. Open questions

- PE-10: establish an external I/O pad contract and obtain maintainer review
  of the accepted one-buffer ECO. Its completed extracted STA, GDS/DRC/LVS
  and mapped replay pass; fast hold margin remains only 25 ps. The 64×32
  inferred store routes in 6×4; changing memory capacity is not indicated by
  these results.
- PE-03: instruction width, register count and datapath width, under §2's ceiling.
- Target clock frequency, and therefore the fastest protocol bit rate reachable.
- When the planned 8×4 template is released, and whether it or the permitted
  IHP SRAM route improves flexibility enough to justify a new candidate.
- Stretch protocols, evaluated in PE-07 and dropped without ceremony if the
  budget or the clock says no.
- Submission closure: bind Tiny Tapeout precheck to the selected GDS, audit
  the staged ECO against that flow, document actual-clock protocol rates and
  select/reset/reload behavior, external hardware and AI use. The board owns
  these PE-12 tasks and the maintainer review/publication gates. Solo or team
  entry is permitted; team size is unlimited, with one entry per team.
