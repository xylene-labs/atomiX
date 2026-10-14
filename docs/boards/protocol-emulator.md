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
fabrication; start with UART, SPI and I2C; keep the official CMOS5L 6×4
baseline until the planned 8×4 template is released; and use the Tiny Tapeout
flow with a passing GDS/precheck. The [organizer follow-up recorded 2026-10-10](../notes/jane-street-follow-up-2026-10-10.md)
clarifies that **flexibility is the main judging criterion**, with no fixed
weights. Protocol demonstrations, unique functionality and verification support
that claim. The tiers below are our delivery policy, not official judging weights.

**PE-12 local compliance work is complete; maintainer review and publication
remain owed.** The exact selected GDS passes all nine Tiny Tapeout checks.
Three supplied-clock runtime profiles pass waveform/rate checks, including the
corrected I2C timing and period-derived case budgets. Fresh ECO continuation
and full Magic/Netgen signoff reproduce the routed ODB/DEF/netlist and all
metrics exactly; GDS non-timestamp bytes match. The final source/review
archives are local deliverables. The maintainer requested a physical hardware
timeline on October 12 and confirmed the Dock, USB–UART, Pico 2, EEPROM and
logic analyzer are available. The EEPROM is AT24C256 and analyzer is marked
24M 8CH; module pull-ups/straps and exact electrical limits still need checks.
PE-09 is Active with a [hardware test plan](../notes/axpe-hardware-test-plan-2026-10-12.md)
targeting first physical readback October 21–23 and a repeatable report November
13. PE-08 remains Ready behind this hardware work and the submission review
gate, with its known width/model gaps retained. Physical axpe operation is untested.


## What winning means here

Three tiers, in strict order. A card's tier says what it is *for*; a card that
serves no tier does not belong on this board.

| Tier | Meaning | Contents |
|---|---|---|
| **T1 — Valid entry** | Without every one of these we are not competing at all, however good the rest is | Official CMOS5L template (6×4 baseline); programmable after fabrication; UART/SPI/I2C as our baseline; public repository with toolchain/examples, verification and AI-use write-up; passing Tiny Tapeout GDS/precheck |
| **T2 — Competitive** | What distinguishes a complete chip from other complete chips | Flexibility to support new protocols; measured time firmware can use; timing proof; generated artifacts and shared oracles |
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
3. UART, SPI and I2C each pass an independent reference peer. Name the supplied
   clock and firmware-derived rates. Common baud rates, SPI modes 0–3 and I2C
   100/400 kHz are recommended targets; there is no organizer-imposed speed minimum.
4. The exact selected GDS has passing **Tiny Tapeout flow and precheck** evidence,
   with versions, commands and hashes. Magic DRC/LVS and all-corner STA remain
   necessary local evidence, but do not establish that Tiny Tapeout precheck ran.
   Document/reproduce the staged ECO within the required flow, locally if needed.
5. The public submission repository contains RTL, tests, architecture/ISA,
   assembler/toolchain, runtime loader instructions, example programs and the
   verification write-up, including limits and how AI tools were used.
6. Document board/Pmod wiring and external parts, 3.3 V digital I/O, host timing,
   and select/reset/load/readback/run after power loss or deselection. Verify
   fresh-state loading without assuming retained program memory.
7. Maintainer commit-pinned reviews remain required. Prepare the repository/link
   and submit via the announced form by 2027-01-18; publishing and submission
   require explicit maintainer authorization. The internal target stays 2027-01-14.

The organizer confirms that CMOS5L pad characterization is unavailable. Retain
and label the provisional I/O budget while tracking updates; neither surrogate
SG13G2 data nor the absence of silicon turns that assumption into a guarantee.
FPGA lab evidence and a video remain optional. Registration is confirmed by
receipt of the email; it is not a completed submission.

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
| PE-01: competition entry and official template baseline | T1 | P0 | Review | Baseline imported 2026-09-25; maintainer review owed | Done: registration is recorded; the linked `cmos5l` template is pinned at `b86a2a7` and imported unchanged under [`asic/tt-axpe/`](../../asic/tt-axpe); the selected 6×4 baseline is reconciled with support-tools rectangle `1289.28 × 710.64µm`, and stale upstream comments remain visible rather than silently repaired |
| PE-14: post-fabrication programming and host contract | T1 | P0 | Review | Maintainer review owed | Done: [`docs/pemu-host-protocol.md`](../pemu-host-protocol.md) freezes the pins and framing; `make pemu-chip-check` loads two unrelated programs into one elaborated design and runs both cycle-exact; PE-02 also binds it behind the pinned template's unique `tt_um_*` top |
| PE-02: instruction-memory and early-flow feasibility gate | T1 | P0 | Review | Measured 20 ns refutation; maintainer review owed | The pinned 64×32 inferred-store candidate passes wrapper simulation, fits 6×4 at 31.9% core utilization and routes with zero OpenROAD DRC/antenna errors. Post-route slow-corner STA has one −0.903 ns setup violation; electrical violations remain. The result and interrupted earlier attempt are recorded in [`axpe-cmos5l-feasibility.json`](../../research/benchmarks/axpe-cmos5l-feasibility.json). Decision: retain this store; PE-10 tests a separately locked 25 ns target and I/O contract |
| PE-03: `axpe` ISA specification | T1 | P0 | Review | PE-02 budget | Done: `axpe-isa.json` is the single source, `axpe-isa.md` is generated from it, and `WAITE` returns its elapsed cycle count |
| PE-04: golden model and assembler | T1 | P0 | Review | PE-03 timing decisions | Model, assembler, UART/autobaud and four-mode clocked shifts pass via `make pemu-model-check`; close only after effect/reset/fault conventions receive commit-pinned review |
| PE-05: RTL and cycle-for-cycle cosimulation | T1 | P0 | Review | PE-04 | Done: `make pemu-cosim-check` compares every cycle with no tolerated deviation across 112 randomized programs and seventeen directed cases, and the handoff gap is closed. Close only after commit-pinned review of the retirement and forwarding path |
| PE-07: baseline UART, SPI and I2C firmware | T1 | P0 | Review | PE-05, PE-14 both done | Done in simulation: all three load into one unchanged chip image and pass peers written from each protocol, with I2C covering ACK/NACK, repeated start, STOP and bus release. The default and all three 40 MHz runtime profiles now pass waveform/rate checks on RTL and the mapped netlist; the I2C low-time failures and corrected runtime handoffs are recorded. Remaining: maintainer review. Physical peers are optional PE-09 evidence, not a prerequisite for submission |
| PE-10: staged CMOS5L synthesis and place-and-route | T1 | P0 | Review | Selected-GDS precheck passes; fresh ECO continuation passes; maintainer review owed; I/O budget provisional | The 25 ns baseline passes setup/hold at all corners, Magic DRC, LVS and antenna checks. Its provisional 4 ns I/O delay is not a pad contract. CTS clusters of eight reduce post-route fanout/slew violations to six each. ABC buffering worsens both classes; jumper-only repair leaves antenna violations. Five bounded repair/antenna passes do not converge. A locked post-antenna route has one fanout and 19 slow-corner slew violations; a 400 µm wire cap clears fanout but leaves six slow slews. A 200 µm cap clears slew, route DRC and antenna, but leaves one fanout violation from five antenna diodes and only 12 ps fast-corner hold margin. The zero-antenna-margin reroute is identical and does not repair fanout. A pinned one-buffer ECO now clears route DRC, antenna and all-corner setup/hold/slew/fanout/cap, with +25 ps fast hold margin. Its final GDS/Magic DRC/Netgen LVS pass, and the final netlist hash matches its passing three-seed functional replay. Earlier variants still fail electrical checks. The maintainer owes commit-pinned review; the external I/O budget remains provisional. See [`axpe-cmos5l-25ns.json`](../../research/benchmarks/axpe-cmos5l-25ns.json) |
| PE-15: a measured period firmware can use | T2 | P0 | Review | PE-03, PE-05 both satisfied | Done in simulation: `SHPER` (opcode `0E`) writes a period register and one bit of the shift shape's unused `b` field selects it, so `SHOUT`/`SHIN`/`SHIO` take their bit period from architectural state. `autobaud-demo.s` measures an unconfigured peer and answers at its rate, checked at two different rates through one unchanged chip image. Close only after commit-pinned review of the exact-but-not-static timing split and the reserved-bit rule |
| PE-06: timing-determinism proof | T2 | P0 | Review | Maintainer commit-pinned review owed | Complete legal instruction-stream occupancy and handoff induct for all 31 opcodes, including register-period selection, held operands, bounded waits and HALT. All 46 witnesses and five mutation counterexamples pass. The word source is abstract; memory/data correctness, invalid-program faults and non-default architecture remain outside the timing claim |
| PE-08: profile knobs exercised | T2 | P1 | Ready | After PE-12 email compliance work; PE-05; width repair and assembler/model profile integration remain | `make pemu-profile-check` wires all six resolved parameters into a fresh Verilator build and its capacity probes. The capacity profile exercises a 64-word store, seven registers, four pins and two stack entries. `configs/sim-axpe-tiny.json` is an explicit failing experiment, not a supported profile: narrower register/delay widths still fail strict elaboration. No RTL repair or full non-default ISA conformance is claimed |
| PE-09: Tang Primer bring-up | T3 | P1 | Active | Kit available October 12; adapter/constraints, bridge and EEPROM runtime tools implemented; physical execution and remaining peers/capture tools remain | Follow the [physical timeline and pass matrix](../notes/axpe-hardware-test-plan-2026-10-12.md): preflight by October 20, first SRAM load/readback October 21–23, UART/SPI/I2C peers and capture/recovery by November 6, repeatable report by November 13. Normal/capture adapter simulations and routed image preflight pass; Pico capture clock is external on J6.10. Use runtime programs on one unchanged image and matched EEPROM addressing/write-cycle behavior. No physical axpe pass yet |
| PE-11: gate-level firmware simulation | T3 | P1 | Review | Maintainer review owed; PE-10 candidate bound by hash | All mandatory protocols, two runtime-loaded programs and two autobaud rates pass the unchanged routed netlist at three startup seeds. Final signoff retains that netlist hash. A relocated standalone package repeats these cases with Liberty-derived cell functions. Two-state, zero-delay evidence; no SDF claim |
| PE-13: firmware-vs-fixed-logic experiment | T3 | P2 | Descoped | Cut 2026-09-25 when PE-01 missed its 2026-09-22 phase date | The comparison remains a useful future platform experiment, but it is outside the competition lane; its time now belongs to PE-02 and the first PE-10 hardening run |
| PE-12: submission package | T1 | P0 | Review | All local compliance gates pass; maintainer commit-pinned review, publication and submission owed | `make tt-export` now includes the shared standalone RTL protocol demo and a hash/level evidence index. Fresh relocation outside atomiX passes all chip cases at three seeds. The routed ECO now passes signoff and replay. A hash-bound package includes its GDS, reports, cell functions and standalone mapped demo; relocated RTL/mapped protocol suites pass at three seeds and five rejection checks pass. The complete legal-stream timing proof also passes. The relocated package repeats induction, all 46 witnesses and five mutation counterexamples. Its exact pre-ECO checkpoint restores into a fresh location with pinned input hashes. Preserve that archive as historical evidence. Current: all nine selected-GDS Tiny Tapeout prechecks pass; all three 40 MHz profiles pass nominal waveform/rate checks, with two earlier I2C timing failures retained and corrected; logical reload, pinned ETR reference mapping and AI-use disclosure are included. The updated candidate passes 24 RTL/mapped suites after fresh relocation and deeper XML/rate-asset refusal probes. Fresh ECO preparation/routing/full signoff pass and match the selected routed assets and all metrics exactly; GDS differs only in timestamps. Remaining: maintainer commit-pinned reviews, public-repository publication and submission. External I/O assumptions and maintainer review remain explicit |

## Schedule

### PE-12 compliance tooling and drafts — 2026-10-11 (historical checkpoint)

`make pemu-precheck` now runs unchanged pinned Tiny Tapeout checks against the
exact selected GDS, LEF and powered netlist in a fresh directory. Input hashes,
versions, commands, raw reports and individual failures are retained. Exported
CI also pins the precheck's support-tools revision. The selected GDS
`a5877dd7626f05d7462ce6e629e84e1b507a606f7c6a75e083e22c09af772134`
has entered that check: pin-label overlap passes, while full CMOS5L DRC is
still extracting connectivity. All remaining outcomes are unknown. The
[progress snapshot](../../research/benchmarks/axpe-precheck.json) explicitly
does not claim a precheck pass. Read its named final runtime receipt when the
existing process exits before starting another run or updating this status.

Candidate packaging accepts `--precheck` only for a completed passing receipt
bound to the selected GDS/state/lock/tools, and includes raw reports for the
portable validator. Six report refusal cases and nine package binding refusal
cases pass; the latter use synthetic host metadata, not a physical result.
The existing no-precheck package path also passes its portable validator.
An initial runner setup failure mistook tracked `reports/.gitignore` for a
stale report; its failed receipt remains recorded, and copying only tracked
upstream inputs fixes that mistake. No GDS check ran in that first attempt.

Exports now include [AI-use](../../asic/axpe/docs/ai-use.md),
[compliance/clock](../../asic/axpe/docs/submission-compliance.md) and
[wiring/reload](../../asic/axpe/docs/demo-wiring.md) drafts. The clock audit
states the unchanged payloads' rates at 40 MHz: about 92,166 baud UART,
800 kHz SPI and 80 kHz I2C. The wiring draft identifies the SPI CS/SCK and
I2C SDA/SCL adapters needed for recommended Pmod mappings, and does not claim
plug-in or EEPROM compatibility. Retimed common-rate payload checks,
selection/cold-reload coverage, final connector/electrical validation, the
ECO flow audit and maintainer reviews remain open. No RTL, ISA encoding,
selected GDS or existing historical archive changed.

Validation: report/binding refusals, `make verification-check`, registry and
all 14 smoke stages pass. The full Tiny Tapeout physical precheck remains
in progress, so PE-12 stays Ready and RX-09 remains open.

### PE-12 logical reload verification — 2026-10-11

Every shared-suite program is now read back in full before RUN; a refusal or
mismatch aborts loading. The Tiny Tapeout binding creates a fresh instance,
runs UART, deselects a driven TX pin, checks quiet outputs, resets/reselects
and fully reloads UART. Warm external reset followed by full reload is covered
too. The host's running latch survives `ena=0`; the documented reset step is
required before reselecting. Exported RTL and the unchanged selected routed
netlist pass the expanded suite at seeds 1, 17 and 91. See
[`axpe-lifecycle.json`](../../research/benchmarks/axpe-lifecycle.json).

This clears the logical lifecycle gap in the earlier checkpoint. It does not
model actual power removal, four-state startup or the carrier's isolation.
Physical reload, actual-clock payload retiming, full precheck completion,
staged ECO flow reproduction and maintainer review remain open. No RTL, ISA,
GDS, netlist or firmware changed; historical archives are preserved. PE-12
stays Ready and RX-09 stays open.

Validation: `make pemu-chip-check`, the exact routed-netlist replay and all 14
smoke stages pass. Registry and the 130-command verification coverage map pass.
The fresh `build/asic/axpe-submission-lifecycle-verified-2026-10-11` package
passes its portable validator and relocated RTL/mapped suites at all three
seeds. Hardware, GDS, netlist and firmware identities match the historical
candidate, whose original review archive checksum is unchanged. Its manifest
has no precheck pass: the separate full-layout run remains in progress.

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

Superseded by the checkpoint below, which closes that gap. It stays here because
what a defect looked like before it was understood is part of the record.

### PE-07 checkpoint — 2026-09-18

All three mandatory protocols now load as runtime programs into one unchanged
`axpe_chip` and pass a peer written from the protocol's own rules rather than
from axpe's ISA, model or firmware. `i2c.s` is new and carries the whole
transaction the board asks for: START, address + W, a data byte, repeated
START, address + R, a byte read back, the master's NACK and STOP. The peers
resolve the bus the way a wire does, with pull-ups and pull-downs, so the
open-drain path I2C cannot be expressed without is exercised rather than
assumed.

The peers earned their keep immediately. Both `uart.s` and `spi.s` enabled
their pad drivers while `pin_latch` still read zero, so the line was driven low
until something raised it: the UART receiver reported a start bit that was not
low at its centre, and the SPI target reported chip select rising after nine
bits, having clocked in a bit no master sent. `i2c.s` had the same defect and
this peer cannot see it, because SDA and SCL move together so no START or STOP
is synthesised — so the rule is now stated in the `PDIR` description in
`axpe-isa.json`, and a static check in `check_axpe_as.py` holds all three
firmwares to it. Reverting any of the three fails something.

The firmware the peers judge is assembled from `sw/pemu/firmware` by the build
rather than transcribed into the testbench, and `.include` (new, with its own
tests, including a duplicate-symbol error that did not exist before) lets one
copy of each routine serve the model tests, the chip test and the submission
demo.

Evidence is host simulation, in
[`axpe-protocols.json`](../../research/benchmarks/axpe-protocols.json). The
peers are independent of the firmware and of the golden model, not of the
author, and no hardware has seen any of it — rise times, pull-up values, clock
tolerance and bus capacitance are what PE-09 exists to find, and the board keeps
those at different evidence levels on purpose. I2C clock stretching is not
supported and not claimed.

### PE-14 checkpoint — 2026-09-18

`axpe` is now a chip rather than a core with its instructions handed to it.
`axpe_chip` composes the core with a writable single-port instruction store and
a fixed-logic SPI host port, in the Tiny Tapeout pin shape. `make
pemu-chip-check` elaborates it once, loads one program over four host pins, runs
it, then loads an unrelated program into that same design and runs that —
checking both against the golden model cycle for cycle, so the claim is not
"it loaded" but "it executes what was loaded, exactly". It also reads a written
word back, and proves that a write attempted while the core runs is refused,
reported in status, and absent from the store afterwards.

The bench does not assume how long after a RUN frame the core starts. It
requires exactly one alignment of the model trace in the collected window, a
quiet reset state before it and a frozen state after it, so the alignment is
proved rather than calibrated. Inventing a debug pin for a testbench's benefit
would have been the testbench designing the chip.

Closing PE-14 exposed and closed a defect in PE-05's core. `imem_addr` was the
registered program counter, so the store had to answer in the same cycle — an
asynchronous read no block RAM or SRAM macro provides, while the file's own
header claimed synchronous fetch. It is now the address of the *next* fetch,
driven from the same expression that advances the program counter so the two
cannot disagree. The differential harness models a true synchronous store, and
all 112 randomized programs and twelve directed cases pass with unchanged cycle
counts; restoring the old address fails the first case immediately.

The host contract is frozen in
[`docs/pemu-host-protocol.md`](../pemu-host-protocol.md) and every decision in
it is recorded with its cost, including the two that were refused: arbitrating
writes against fetches, which would work in simulation and fail on a single-port
macro, and a register-file read port for result readback, which `POUT` and one
status byte already do for less area. Evidence is host simulation only, in
[`axpe-chip.json`](../../research/benchmarks/axpe-chip.json): no independent
protocol peer, no synthesis, P&R, FPGA or silicon claim, and the store is still
a behavioural model rather than the macro. PE-02 is Ready, and what it needs
from PE-01 is the official wrapper name and template revision.

### PE-15 checkpoint — 2026-09-18

The measured-time feature is a whole feature. `SHPER` takes one of the two
reserved opcodes and writes a 16-bit period register; one bit of the `b` field,
which the shift shape never used, lets `SHOUT`, `SHIN` and `SHIO` take their
cell duration from it. The select is per instruction rather than a mode, so two
transfers with nothing between them can run at different rates — a fixed
protocol and a measured peer in the same routine.

`autobaud-demo.s` is the claim end to end: it measures a peer, loads what it
counted, and answers at that rate, with no host involved and no rate written
anywhere in the program. The chip bench runs it against peers at **37 and 53**
cycles per bit through one unchanged elaborated design, and the peer's own
receiver decodes the reply. Two rates rather than one on purpose — a single
rate could be a constant that happened to be right, and replacing the firmware's
`SHOUT R0, 10, P` with a hardcoded `D=37` does pass the first peer and fail the
second, decoding `0xEF`.

**The honest cost is a distinction the ISA now has to carry.** A selected shift
is still *exact* — it retires in `n*max(P,1)`, a function of machine state at
issue and of nothing external, so PE-06 carries `P` as a symbol and not as a
bound. It is no longer *static*, so `axpe_as.py --listing` prints `10xP` where
it prints `4340` for the fixed-rate routine, and a program containing one has no
duration readable from its text. Conflating those two words is how "the listing
prints the cycle count" would have quietly become false; the generator now
refuses a timing class that claims to be static without being exact.

Two consequences fell out rather than being designed. Only the shift engine
reads the period register, so the measured-rate UART frame goes out as one
ten-cell `SHOUT` — start bit included — because a start bit built from `PINCLR`
would still be held for an immediate `D`, and that is the cell a receiver uses
to find every other one. And including `autobaud.s` and `uart.s` into one
program for the first time hit the assembler's duplicate-symbol rule: both
independently defined `RX_PIN` for the same wire. They agreed, but nothing made
them agree, so autobaud's constants are prefixed and `check_axpe_as.py` now
compares the pin each file's `WAITE` actually encodes.

Validation: `make pemu-model-check` (19 model groups and the assembler
self-check), `make pemu-cosim-check` (112 randomized programs and seventeen
directed cases, cycle for cycle with no tolerated deviation, half the engine
programs now drawing their period from the register), `make pemu-chip-check`,
`make verification-check` and `make registry-check` all pass. An RTL that
ignores the select bit fails the first directed case, so the gate is known to
have teeth rather than assumed to. Evidence is host RTL/model simulation only,
in [`axpe-period.json`](../../research/benchmarks/axpe-period.json): no hardware
peer, and no synthesis, P&R, FPGA or silicon claim. The added state is one
16-bit register counted from its declaration, not a mapped area. No
commit-pinned approval or completed card is claimed.

Not taken, and named rather than left implicit: nothing outside the shift engine
can read the period register. A `DELAY` that could would let firmware hold a
line for a measured interval, which clock stretching and inter-frame gaps would
both use. It is listed in the ISA's open questions instead, because the
mandatory protocols do not need it and the card's claim is narrower without it.

### Preparing the ASIC rows — 2026-09-18

Three small pieces of groundwork, done now because each is cheap before the
flow exists and awkward after it.

**The verification ladder now has the rows an ASIC entry needs**, in
[`docs/verification.md`](../verification.md): ASIC synthesis, place-and-route
with STA, gate-level, and physical silicon — all empty, listed rather than
omitted, because an absent row is the easiest kind of claim to make by
accident. Every axpe result to date is RTL equivalence and RTL integration. The
note under the table now also says what was previously only implied: Verilator
is two-state, so no run of it can see a flop that comes up unknown or a path
that misses timing.

**The chip bench is split so PE-11 is a binding rather than a bench.**
`sim/pemu/axpe_device.h` holds a `Device` interface and the host-port driver;
`axpe_cases.h` holds every check that decides pass or fail; `axpe_chip_tb.cpp`
is now six methods and a `main`. The peers never knew what simulated the part.
A netlist judged by a different list of cases than the RTL was would not be
evidence about the same chip, and this is what stops that happening by
convenience in December. Behaviour is unchanged: the same cycle counts, the
same alignments, the same peers.

**A part is now required to be silent before anyone talks to it.** With nothing
loaded and nothing running, no protocol pin may be driven, `uo_out` must be
zero, the status word must read `0000`, and a host frame must not disturb any
of it. Nothing pinned this before — the reset state was only ever observed as
the quiet prefix `compare_run` demanded of a run that then went on to do
something else, which is true but incidental, and says nothing about what
happens mid-frame. It is the first thing observable about a returned die and
the first thing a bring-up engineer needs. The host's CS synchronisers already
reset to deselected, deliberately, so this locks in a property the design
already had rather than reporting a defect; making the core come up with
`pin_dir` all ones fails it at cycle 0, naming the pins.

### PE-08 finding — 2026-09-18, ahead of the card

Found while checking that PE-15's period register follows `delay_bits` rather
than a literal 16. It does. What does not is the rest of the core: `axpe` only
elaborates at `reg_width = delay_bits = 16`, and the manifest declares both as
knobs with no such limit. This is exactly the failure `AGENTS.md` names — a
knob that is declared but never exercised reads as configurable and is not,
which is worse than an honest constant.

Verified pre-existing, not introduced by PE-15: linting `components/pemu/axpe/`
at HEAD and with this change gives identical diagnostic counts at every setting
tried.

| Setting | Result |
|---|---|
| `DELAY_BITS=12`, `REG_W=16` | 5 width warnings, no clean elaboration. `axpe_timing`'s `delay` port takes the decoder's fixed 16-bit field |
| `DELAY_BITS=16`, `REG_W=12` | **hard error**: `{{(REG_W-DELAY_BITS){1'b0}}, wait_elapsed}` on `axpe.sv:164` replicates a negative count. Plus `shcfg <= src_a[14:0]` selecting 15 bits out of 12 |
| `DELAY_BITS=8`, `REG_W=8` | 24 warnings, most of them `axpe_shift`'s bit-position arithmetic assuming a 4-bit index |

Three things this decides for PE-08, before it is pulled:

- The card is larger than "run the knobs at a non-default value". It is "make
  two of them work", and the estimate should say so.
- `reg_width < delay_bits` is arguably not a configuration worth supporting at
  all — `WAITE` returns a `delay_bits` count into a `reg_width` register, so
  the combination is incoherent rather than merely unimplemented. If that is
  the answer, the constraint belongs in the manifest and in `axpe_isa.py`'s
  manifest check, not in a replication that happens to fail.
- Nothing here changes any current claim. Every result on this board is at the
  default, and the defaults are what the submission hardens.

### PE-05 checkpoint — 2026-09-18

The retirement handoff is closed and the gate no longer tolerates a deviation.
`make pemu-cosim-check` now compares the RTL against the golden model cycle for
cycle across 112 randomized programs and twelve directed cases, including two
transfers back to back, a trailing clock edge sharing an edge with a pin
instruction, a received value read by the instruction issuing on the retirement
cycle, `T` tested by the branch immediately after its `WAITE`, and adjacent
waits measuring a known five-cycle pulse as exactly five.

The defect was one rule, not five cases. A long instruction kept its word in
`imem_data` until it finished, so the next instruction could not be fetched in
time to issue on the cycle it should, and every `WAITE` and shift cost one cycle
the ISA does not declare. That is the `1 + D` shape this board already rejected
once, one cycle past the bit period per transfer and accumulating across a
frame. Every instruction now advances the PC at issue; a running instruction
reads latched operands rather than the instruction word; it retires on its final
cycle with the next instruction issuing into that same edge; and the retiring
register result and `T` are forwarded to it. 43 flip-flops at default
parameters, counted from the declarations, not synthesized.

The pre-fix RTL was rebuilt against the new harness and fails at the first shift
case, naming the extra cycle, so the gate is known to have teeth rather than
assumed to. Validation: `make pemu-cosim-check`, `make verification-check`,
`make registry-check` and all 13 smoke stages pass. Evidence is host
RTL/model cosimulation only, in
[`axpe-cosim.json`](../../research/benchmarks/axpe-cosim.json); no protocol
conformance against an independent peer, and no synthesis, P&R, FPGA or silicon
claim. PE-06 is unblocked. No commit-pinned approval or completed card is
claimed.

### PE-01 checkpoint — 2026-09-25

The entry now has an exact official source baseline. The competition page's
CMOS5L link resolves to Tiny Tapeout's `cmos5l` template branch; commit
`b86a2a781484bcab7ba522dc5de540086695a430`, tree
`5d72d5b9e04c0732d32c7f7d0f72cf950508e551`, is imported unchanged under
[`asic/tt-axpe/`](../../asic/tt-axpe). The imported top fixes the wrapper
contract PE-14 was waiting for: a unique `tt_um_*` module with the standard
eight input, eight output, eight bidirectional, `ena`, `clk` and `rst_n` ports.

The apparent tile conflict is upstream documentation drift, not an unresolved
choice. Jane Street's current rule says `tiles: "6x4"`; the template's
`info.yaml` comment still lists only `*x2` shapes; and the
`ihp-sg13cmos5l` support-tools branch at
`d66cf179e7bc4d296362ab7e2e3b344dc3c4f665` accepts `6x4` with the hardening
rectangle `0 0 1289.28 710.64`. The same tool revision contains `8x4`, but the
competition page still caps entries at 6×4, so tool capability does not expand
the allocation. The exact rectangle also corrects the macro-area denominator:
the 256×32 candidate occupies 5.4%, not the 6.9% derived from the announcement's
nominal 1200µm × 600µm estimate.

The baseline preserves defects as well as files. Its CI workflow selects
CMOS5L, while its devcontainer still names SG13G2, and the actions name moving
branches. PE-02 must pin those executable inputs, bind `axpe_chip` behind the
wrapper, and run the flow. This checkpoint is source/interface evidence only:
no synthesis, P&R, gate-level, FPGA or silicon result is claimed. PE-01 is in
Review because the maintainer still owes the commit-pinned review.

Phase 0 landed three days after its 2026-09-22 date. Per the board's pre-written
descope order, PE-13 is cut from the competition lane now; the slip is not taken
from PE-02 or the first PE-10 run and is not hidden by spending submission
buffer.

### PE-02 checkpoint — 2026-09-27

The documented pinned CMOS5L feasibility run reached post-route RC extraction and STA.
The inferred 64×32 store fits the 6×4 core and OpenROAD reports zero final
routing DRC, antenna and critical disconnected-pin errors. The 20 ns criterion
fails by 0.903 ns on one slow-corner input-to-instruction-read-register path;
all hold checks pass, while slew and fanout violations remain. The result is a
bounded refutation of the clock target, with the exact inputs, commands,
metrics and automation failure in
[`axpe-cmos5l-feasibility.json`](../../research/benchmarks/axpe-cmos5l-feasibility.json).
PE-02 awaits maintainer review. PE-10 now owns the separately locked 25 ns
experiment and full GDS/DRC/LVS closure; no signoff or silicon result is claimed.

### PE-10 post-route checkpoint — 2026-09-27

The new 25 ns profile keeps a provisional 4 ns input/output delay. Its pinned
CMOS5L run reaches RC-extracted post-route STA with zero OpenROAD routing DRC
and antenna errors. All setup and hold checks pass; the slow-corner worst setup
slack is +4.091 ns. Standard cells occupy 287,869 µm² of a 902,417 µm² core.
Electrical closure is still open: 14 slow-corner max-slew violations and 162
max-fanout violations, 160 of them clock-tree leaf buffers. The separate
GDS continuation has completed: Magic DRC reports zero errors, LVS matches
uniquely and the antenna check passes. These do not clear the electrical
violations. A separately locked CTS cluster-size-8 trial reached post-route STA:
slow-corner setup slack improved to +4.846 ns, fanout violations fell to six
at every corner and slow-corner slew violations fell to six. The remaining
fanout drivers are data-path nets, so clock clustering alone cannot close the
card. This variant still needs GDS/DRC/LVS. Inputs, hashes and exact commands are in
[`axpe-cmos5l-25ns.json`](../../research/benchmarks/axpe-cmos5l-25ns.json).
Two further locked trials were stopped during detailed routing after the
comparable pre-route checks worsened: cluster size four left 13 fanout
violations against size eight's two; a global fanout target of six created 14
violations, eight on upstream CTS buffers at fanout 16. Neither stopped trial
has post-route or GDS evidence. The remaining repair needs a selective
data-path strategy without constraining the whole clock tree.

A later locked post-antenna repair trial disables global-route antenna
insertion after repair. Its nominal pre-route fanout, slew and cap checks are
clear, but a separate antenna check finds 15 violating nets. Detailed routing
repairs those antennas and completes with zero route DRC, zero final antenna
violations and passing setup/hold at every corner. It still has one fanout
violation at every corner and 19 slow-corner slew violations. The variant has
no GDS/DRC/LVS result and does not close PE-10. A direct in-memory repair probe
uses wire-load estimates after changing the design, so it does not replace a
rerouted, RC-extracted check. The trial's inputs, hashes and exact commands are
in [`axpe-cmos5l-25ns.json`](../../research/benchmarks/axpe-cmos5l-25ns.json).

A separate locked 400 µm post-global-route wire cap inserts 272 buffers in
211 nets. After an interrupted first route, its supervised detailed-route
retry completes with zero route DRC and antenna errors. Extracted STA passes
all-corner setup/hold/fanout/cap checks; slow-corner slew still fails on six
pins across two `nor4_1`-driven nets. The fast hold margin is only +0.007099 ns.
This is the best routed electrical result, but it has no GDS/DRC/LVS result,
no external pad timing contract, and does not close PE-10.

A tighter locked 200 µm wire cap clears all six slow-slew violations in a
completed detailed route. Route DRC, antenna, setup, hold and cap checks pass,
but `input4/X` reaches fanout nine against eight after five antenna diodes are
inserted on `net4`. Fast-corner hold slack is only +0.012071 ns. A separate
zero-margin antenna-repair reroute completes with identical netlist, metrics
and slow-corner checks, retaining fanout nine. The 200 µm variants have no final
GDS/DRC/LVS result and do not close PE-10.

### PE-10 single-buffer fanout experiment — 2026-10-09

The zero-margin result rules out that repair control. The next bounded trial
inserts one `buf_1` for the two adjacent mux loads on `net4`, reducing the input
buffer's functional fanout from four to three and leaving room for antenna
diodes. The [recipe](../../asic/axpe/experiments/wire200-fanout-eco.py) pins the
parent inputs, checks every cell and connection for exactly one buffer and two
load moves, refuses overwrite, and drops stale timing/physical views and metrics.

The prepared ECO passes placement and global routing. Nominal estimated-parasitic
STA has zero setup, hold, fanout, slew and cap violations. Global-route antenna
estimation finds four violating nets and pins. Two preparation attempts failed
closed while establishing OpenROAD's suffixed buffer/net naming. A separate
bounded continuation executes another design-repair pass and adds 380 buffers;
it is recorded but not selected for routing, which keeps the isolated one-buffer
change. Commands, source/output hashes and failures are in
[`axpe-cmos5l-25ns.json`](../../research/benchmarks/axpe-cmos5l-25ns.json).

The supervised detailed route now completes with zero route DRC and antenna
errors. Setup, hold, slew, fanout and cap checks pass at all three extracted
corners. Only three antenna diodes are added, on other nets; `net4` has three
functional loads and its child two, with no diode on either. Fast hold slack
is +0.025081 ns, still narrow. The full GDS/DRC/LVS continuation is supervised
by `axpe-wire200-fanout-eco-signoff.service` and finishes successfully. Magic
full DRC and Netgen LVS report zero errors; the final signoff netlist hash
matches the routed replay that passes all shared chip cases at three startup
seeds. KLayout DRC/XOR and Yosys EQY were skipped by the locked flow; unset
supply locations prevent a package-level IR-drop claim. PE-10 moves to Review
with maintainer commit-pinned review owed and the 4 ns I/O delay provisional.

Validation: the input/overwrite and pre-route summary guards, verification
contract, registry checks and all 14 smoke stages pass. Changes await maintainer
review; no commit or completed card is claimed.

The same slice now has mapped functional verification through
`make pemu-netlist-check`. Both the completed zero-margin routed netlist and
the prepared single-buffer ECO pass all shared chip cases at three randomized
startup seeds, including runtime reprogramming, UART/SPI/I2C and two autobaud
rates. Cell models are generated from the pinned Liberty files and identical
across the three corners. The direct PDK Verilog-model attempt was rejected
because ignored timing constructs leave a delayed reset signal undriven.
Commands, hashes, failures and limitations are in
[`axpe-netlist.json`](../../research/benchmarks/axpe-netlist.json).
The binding rejection checks run through the existing `pemu-chip` CI stage.
This prepares PE-11 without closing it: the evidence is two-state, zero-delay
simulation. The completed ECO route passes these same cases at three seeds;
final signoff retains the replayed netlist hash, as checked in the signoff receipt.

The isolated timer now has an [inductive proof](../../formal/pemu/README.md)
at the manifest default and half-width. Its upward elapsed-cycle reference is
generated from the normative ISA formula, covers establish actual loads and
completions for D=0/1/7, and two changed timer copies must produce counterexamples.
[`axpe-timing.json`](../../research/benchmarks/axpe-timing.json) records the
commands, hashes and initial harness failures. This is preparatory evidence for
PE-06, which remains Ready: core retirement, core-level shift occupancy and `WAITE` timeout
are still unproved. It changes neither the RTL nor the active physical candidate.

The isolated shift engine now also proves occupancy under its caller contract:
independent cell age and bit index establish exactly the declared number of
cells and `done` on the final cycle. Eight covers reach zero-delay completion,
maximum count, maximum period at load, back-to-back completion and all four SPI
modes; two changed engine copies produce counterexamples. See
[`axpe-shift-timing.json`](../../research/benchmarks/axpe-shift-timing.json).
Core enforcement of those assumptions and instruction handoff remain unproved.
The same review found old BR `1+D` wording and incorrect equality of immediate
level-high wait return and occupancy. Both are clarified in the normative ISA
and derived document; generated C/SV headers stay byte-identical. Model tests
and both isolated proofs pass again. No RTL change or second Active card is introduced.

The original core now also inducts for an abstract stream of legal `DELAY` and
`WAITE` words at the selected 64-word profile. A downward reference budget
checks the upward wait count, sampled event and timeout, held operands despite
changing prefetched fields, final-sample T and same-edge issue of the following
instruction. Eleven covers and two changed core copies pass their expected
outcomes; see [`axpe-wait-timing.json`](../../research/benchmarks/axpe-wait-timing.json).
This subset excludes other instruction classes and program memory/fetch; PE-06
remains Ready for the complete retirement proof.

The standalone export now bundles that same protocol suite and its source
inputs. `make pemu-asic-check` runs it from the export, and a fresh export
relocated outside atomiX passes at three seeds with identical hardware hashes.
The manifest separates verification inputs from hardware; the evidence index
retains failures, levels and unresolved work. See
[`axpe-package.json`](../../research/benchmarks/axpe-package.json). PE-12 remains
Next while final-candidate signoff and maintainer reviews are outstanding.

| Phase | Cards | By |
|---|---|---|
| 0 — official entry and template | PE-01 | 2026-09-22 (reviewable slice landed 2026-09-25; PE-13 cut) |
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

- 2026-09-25: PE-01 pins the official CMOS5L template at `b86a2a7` and the
  current 6×4 technology rectangle at 1289.28µm × 710.64µm. The stale `*x2`
  comment and SG13G2 devcontainer setting stay visible in the pristine import;
  PE-02 owns the executable, commit-pinned flow. Because phase 0 missed its date
  by three days, PE-13 is the first scope removed under the descope order. No
  ASIC flow evidence exists yet.
- 2026-09-18: registration is done, and the mandatory-email step this board
  listed as a PE-01 blocker was not a requirement. PE-01 stays open for what it
  is actually for: the official template revision, its tile-shape metadata
  against the 6x4 allocation, and the `tt_um_*` wrapper name the chip top does
  not yet use.
- 2026-09-18: a protocol's peer is written from the protocol, never from the
  emulator. An oracle derived from the thing it checks agrees with it by
  construction, and the first run of these three found two real firmware
  defects that every model-level test had passed over. Where a peer structurally
  cannot see a defect, the rule goes into the ISA description and a static check
  instead of being left to a reviewer's memory.
- 2026-09-18: the loader is fixed logic and the store is single-port, decided
  together. Firmware cannot load itself, so the host port cannot be firmware;
  and the IHP macro PE-02 is aiming at has one address port, so there is no
  cycle in which a fetch and a write can both happen. Rather than arbitrate,
  the chip refuses writes while the core runs and says so in a status bit. An
  arbiter would have passed this bench and failed in silicon, which is the
  failure mode this project exists to avoid.
- 2026-09-18: the lane is single-agent from here. Codex is unavailable for an
  extended period, so the coordination board is retired for this work and
  `AGENTS.md` records the rule. The consequence is not cosmetic: PE-03, PE-04
  and PE-05 sit in **Review** waiting on a commit-pinned review that named an
  agent reviewer who is gone, so **the maintainer owes those three reviews**.
  They stay in Review until then. A card does not become closed because the
  only party who could have objected stopped being available — that is how a
  submission ends up asserting what nobody checked, on the one axis the
  competition says it is judging.
- 2026-09-18: PE-05's retirement handoff closed, so the declared-cycle property
  is now true of the RTL and not only of the ISA document. PE-06 is Ready: the
  proof it has to carry is exactly the claim the cosimulation now demonstrates
  on 112 programs, which is the difference between evidence and a proof.
- 2026-09-17: added a three-tier win condition, a submission definition of done
  and a written descope order, so every card answers to an outcome rather than
  to its own completion. The descope order is decided now on purpose: the worst
  time to choose what to cut is the week it must be cut.
- 2026-09-18: `reg_width` and `delay_bits` are knobs in name only — the core
  does not elaborate away from 16, and at `reg_width < delay_bits` it fails
  with a hard error rather than a warning. Recorded under PE-08 above with the
  diagnostics rather than fixed here, because it is a second RTL change and
  this lane takes one at a time. It is pre-existing and does not touch any
  claim on this board, all of which are at the defaults. Naming it now is the
  point: the alternative is PE-08 discovering in December that its first
  reviewable slice is a rewrite.
- 2026-09-18: PE-15 landed, so the unique-functionality claim is "it can
  measure an unknown peer and then talk to it" rather than measurement only.
  The walk-back below is superseded by the work it asked for, and the two
  reserved opcodes are now one. What the card also forced is a vocabulary: this
  ISA now distinguishes an *exact* cost from a *statically known* one, because
  a register-period shift is the first instruction that is the former and not
  the latter. That distinction belongs to PE-06 as much as to the listing.
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
  **Superseded 2026-09-18 by PE-15**, which added the delay register this
  entry said was missing. The entry stays because a claim that was walked back
  and then earned is worth more than one that was always asserted.

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
  IHP-Open-PDK LEF footprints originally put a 256×32 single-port SRAM macro at
  6.9% of the announcement's nominal 1200µm × 600µm area and a 512×32 at 11.1%.
  PE-01 later pinned the actual hardening rectangle and corrected those shares
  to 5.4% and 8.7% — see [§2.1](../protocol-emulator.md). Program
  size was never the constraint; the storage primitive was. PE-02 stays Ready
  because area affordability is not flow acceptance: the macro has to go through
  the Tiny Tapeout 6×4 flow before PE-03 may assume it.


### PE-12 candidate package checkpoint — 2026-10-09

`make pemu-package` creates a fresh local review artifact from the completed
signoff and accepted mapped replay. It verifies the selected state and GDS,
zero physical/all-corner electrical errors, source-profile/lock identity,
unchanged functional inputs, cell bindings and the final netlist/replay hash
match. Its standalone export includes the final GDS, mapped netlist and cell
functions, compact reports/receipts, exact ECO recipe and runtime payloads.
Firmware hashes remain separate from hardware identity.

A fresh relocation outside atomiX passes both the RTL and mapped protocol
suites at seeds 1, 17 and 91. The package checker also compares freshly
assembled payload hashes to the accepted replay. Five checks reject an
existing output, incomplete signoff, changed GDS, mismatched netlist binding
and changed payload. The selected 25 ns profile/lock are exercised through
`make pemu-asic-check`, with `TT_AXPE_FLOW_LOCK` reaching export and check.
See [`axpe-package.json`](../../research/benchmarks/axpe-package.json).

The package documents the expensive staged regeneration procedure and its
pinned parent requirements; its source GDS workflow alone does not reproduce
the ECO. Fresh physical regeneration was not repeated for this packaging
check. PE-12 stays Active: the complete instruction-retirement proof, external
I/O contract and maintainer reviews remain open. No commit, publication or
external challenge submission is made.


### PE-06 full-stream proof — 2026-10-10

PE-12's validated local package is Ready while the sole Active slice moves to
its remaining PE-06 dependency. The full legal instruction-stream timing
reference now inducts against unchanged core RTL, including scalar occupancy,
shift cells, period selection, held operands, waits, instruction handoff and
HALT. The final gate passes all 31 opcode completions, 15 additional witnesses
and five broken-core counterexamples. The register-period witness compares P
with the encoded delay of that same instruction, not only its next word. PE-06
moves to Review; the maintainer owes commit-pinned review. PE-12 resumes as the
sole Active slice to finish the portable proof and archive. Branch/call
targets are in range, stack operations are balanced, and the instruction word
source is abstract. Program-memory data correctness, arithmetic/data effects,
non-default architecture and physical reset recovery remain outside this proof.


### Local submission deliverables ready for review — 2026-10-10

The candidate package now carries the complete accepted legal-stream timing
proof. From a fresh location outside atomiX, all 52 SAT jobs pass their expected
outcomes: induction, 46 witnesses and five mutation counterexamples. Both the
RTL and mapped protocol suites pass at three startup seeds, and all 14 smoke
stages pass. Changed proof harnesses and mismatched formal/profile parameters
are rejected before a package can be accepted.

The exact pre-ECO ODB, netlist, constraints and interface headers are bundled.
Their restoration helper preserves the pinned input hashes, writes local paths
with empty inherited metrics, and refuses an existing checkpoint without
changing it. This supplies the actual input to the documented staged ECO
reproduction, rather than depending on the original workstation's build tree.
It is checkpoint restoration evidence, not a new physical-flow run.

PE-06, PE-11 and PE-12 are in Review. The maintainer owes the required
commit-pinned reviews; no card is silently closed. The 4 ns external I/O budget
and 25 ps fast hold margin remain explicit limits, and no physical-operation,
commit, publication or external submission claim is made. The remaining
PE-08 knob sweep and PE-09 lab work remain optional future board work; their
known gaps are preserved. Evidence is in `axpe-core-timing.json` and
`axpe-package.json` under `research/benchmarks/`.


### PE-08 capacity verification — 2026-10-10

PE-08 is the sole Active slice following the local submission package.
`make pemu-profile-check` now resolves every declared component parameter into
both Verilator's top-module arguments and independent capacity expectations.
The existing cosimulation stage runs it in smoke, quick CI and nightly. Each
attempt has fresh output, exact commands, input/log hashes and a status receipt;
invalid profiles fail before compiling and existing output cannot be replaced.

The default architecture and `configs/sim-axpe-capacity.json` pass. The latter
uses 64 instruction addresses, seven registers, four bidirectional pins and two
stack entries. Probes exercise the highest register/address, register wrap,
pad mask/open-drain release, maximum delay/wait, full stack unwind, overflow,
underflow and an out-of-range branch where its encoding exists. The synchronous
word-source stand-in does not establish instruction-memory or loader behavior
at these settings. This is capacity evidence, not full non-default model
conformance or physical implementation.

The all-non-default `configs/sim-axpe-tiny.json` is now present as a reproducible
**failing** experiment. Isolated probes retain the 12-bit delay warnings, the
register-width/SHCFG errors, and the coupled 12-bit failures. They additionally
expose four-register index-width warnings and a one-entry stack's invalid index
width. Warnings remain fatal; these attempts are recorded as failures.

No RTL, ISA, component defaults or frozen submission artifact changes in this
slice. Width/index repairs, profile-aware assembler/model conformance and the
physical area sweep remain PE-08 work. See
[`axpe-profiles.json`](../../research/benchmarks/axpe-profiles.json).

Validation: all 14 smoke stages pass with the capacity gate included. Removing
each of the four non-default RTL parameter arguments causes the intended
probe failure; malformed profiles stop before compilation, and overwriting an
existing receipt is rejected. The registry and 129-command verification map
pass. The frozen review archive still matches its original SHA-256.


### Organizer follow-up alignment — recorded 2026-10-10

The [complete supplied email and decision map](../notes/jane-street-follow-up-2026-10-10.md)
are stored in the repository; its sent date was not provided. This checkpoint
supersedes earlier statements that 8×4 was outside the planned rules, that an
IHP SRAM integration was categorically unavailable, and that the local archive
alone satisfied submission readiness. Historical measurements remain valid
only for their named inputs.

PE-12 returns to Ready and is the next pull. PE-08 returns to Ready behind it;
its passing capacity probes and recorded failures are retained. No card is
closed and no maintainer review is waived. Keep 6×4 and the inferred store as
the selected candidate; evaluate 8×4/SRAM only as optional, separately verified
upgrades. Do not change pinned flow versions just because a newer action exists.
The email's lack of characterized pads explains the unresolved external I/O
contract and does not supply a replacement number. Further protocols, dual
roles and concurrency must earn their schedule after the submission baseline.

Validation: the stored email body matches the supplied text after CRLF-to-LF
normalization, its original checksum is recorded, and local reference links
resolve. `make verification-check` and all 14 `make verify-smoke` stages pass.
No implementation, flow lock or frozen review archive changed in this alignment.


### PE-12 completed local audit — 2026-10-11

All nine selected-GDS Tiny Tapeout checks pass. The unchanged selected netlist
passes the default and standard/fast/slow 40 MHz profiles at three seeds
(12 suite invocations); a fresh relocation repeats all 24 RTL/mapped runs.
All 14 final smoke stages pass. The I2C audit retains its two previously
decoded low-time violations and corrected runtime cell/handoff words. Valid
slow profiles retain their earlier fixed-timeout failures; case budgets now
scale with periods. Legacy assembly rejects a 16-word limit and accepts the
selected 64-word limit with byte-identical words. Deeper portable XML/rate-asset
refusal probes pass.

Fresh pinned ECO preparation, global route, nominal STA, detailed route and
full Magic/Netgen signoff pass. Routed ODB/DEF/netlist and every final metric
match the selected candidate exactly. All GDS bytes outside library/structure
timestamps match; this is neither a new geometric XOR nor a new precheck on
the timestamp variant. The original selected GDS remains the packaged image.
The transient three-net antenna finding and configured repair remain recorded.

The final source and review archives, ETR reference wiring, AI-use disclosure
and [maintainer review note](../notes/axpe-submission-review-2026-10-11.md) are
prepared locally. PE-12 is in Review, with the maintainer owing commit-pinned
approval and publication/submission. No card closes itself. The 4 ns I/O
budget, 25 ps fast hold margin, checkpoint-only reproduction boundary and
unmeasured physical operation remain explicit. PE-08 repairs and PE-09 lab
work remain future work; no existing record or frozen archive is invalidated.


### PE-09 adapter and loader preflight — 2026-10-12

The CI/toolchain repair and physical test plan are signed off in `922094a`.
PE-09 is the sole Active slice; PE-08 width/model repairs remain Ready behind
it. The new board component wraps unchanged axpe RTL, exposes J4 protocol and
J6 host/reset/clock signals, and omits all runtime firmware initialization.
Normal mode uses dedicated divide-by-two clocking at nominal 25 MHz; capture
mode uses the Pico's external nominal 1 MHz PWM clock. The image-specific
clock constraints and reset parameters reach the build and simulation.

The simulation suite passes at three startup seeds per mode, plus a separate
2.5 MHz capture/23-cycle reset profile. Eleven transport-fake checks cover raw
word order/readback, mismatch/refusal without RUN, HALT/fault/deadline handling,
stale replies, CS cleanup and non-default GPIO/timing settings. An optional
Icarus check covers only the four-state pad boundary. Full-core Icarus
elaboration failed on pre-existing declaration order and remains excluded.

The open Gowin flow produces normal/capture images with timing checks enabled.
Initial BRAM hold failures, fabric-divider hold failure, DCS clock-packing
assertion and cascaded-divider routing failure are retained. The FPGA-only
store mapping uses flip-flops and the capture profile uses an external clock;
the selected ASIC RTL/GDS are untouched. The bridge is a MicroPython prototype,
not a physically tested Pico program. Pin continuity, actual clocks/voltages,
physical readback, independent protocol peers, EEPROM payloads, capture analysis
and repetition/power-loss runs remain open. See the
[adapter instructions](../../components/board/tangprimer25k-axpe/README.md) and
`research/benchmarks/axpe-primer-preflight.json`.


### PE-09 AT24C256 runtime slice — 2026-10-12

The confirmed module now has separate 54-word byte-write, 46-word ACK-poll
and 60-word tagged random-read programs. Each ACK is checked; failure sends
STOP and releases the open-drain lines. Tagged low/high nibbles keep all 256
data values distinct from NACK in the existing eight-bit host result. A host
runner defaults to reads, persists the original scratch byte before requested
writes, verifies test writes and restores/reads the original. Deadlines and
repetition counts are EEPROM-owned settings; the readiness deadline includes
host loading/USB overhead and is not a tWR measurement.

Both Primer simulations pass independent EEPROM peers at three startup seeds
with default/non-default addressing/data and first/last memory locations. Busy
NACK/deferred commit, every write/read address ACK, repeated START, final NACK,
STOP/release and WP are exercised. Two firmware mutants fail at the intended
peer oracle. The first simulation receipt was rejected because a parameter
file changed during the run; it remains a failed attempt. See
[EEPROM reproduction/limits](../../sw/pemu/firmware/eeprom/README.md) and
`research/benchmarks/axpe-eeprom.json`.

These are runtime payload and host/digital tests. No FPGA rebuild, core/ISA
change, physical EEPROM write or board pass is implied. PE-09 stays Active:
Pico execution, independent UART/SPI peers, waveform/cycle capture and physical
acceptance/recovery remain. Device suffix/straps/WP/pull-ups still need matched
physical inspection. The original generic I2C demo remains a synthetic-peer
example.
