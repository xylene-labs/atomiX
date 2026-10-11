# axpe timing proof

`make pemu-timing-check` checks the original `axpe_timing.sv` with Yosys's SAT
engine. It proves the isolated cell timer, not the core retirement schedule,
shift-engine total occupancy or `WAITE` timeout.

The reference duration is generated from the `fixed` timing formula in
`sw/pemu/isa/axpe-isa.json`. An independent counter measures elapsed cycles
upward while the DUT counts remaining cycles downward. The invariant relates
those counters and proves `last` exactly at the declared final cycle, including
zero-delay clamping and the ready state after completion. Delay, load and reset
are arbitrary binary inputs; the first sampled edge is in reset, and a new
load or reset interrupts the previous cell.

The proof runs at the component manifest's default delay width and at half
that width. This is an isolated timer parameter check; it does not establish
that the non-default width composes through the entire core (PE-08 remains
open). Induction covers every representable delay, rather than enumerating a
bounded selection. Witnesses for D=0, D=1 and D=7 establish non-vacuity. Two
deliberately changed copies must produce counterexamples: decrementing by two,
and adding a load cycle. Those copies and all generated jobs/logs stay under
`build/formal/pemu/`.

Yosys resolves the timer parameter, then exposes its existing `remaining`
register as an observation-only output before reading the harness. No RTL
source or data path changes. `async2sync` makes reset behavior suitable for
sampled-edge checking; it does not prove reset recovery timing. SAT steps
represent rising clock edges, so the witness's free clock input is not a clock
waveform. The proof does not cover glitches, analog behavior or physical timing.

The compact `evidence.json` records input, harness, script and log hashes and
the proof/counterexample results. An explicit `--output` must name a new child
of `build/formal/pemu/`; the default creates a fresh directory for each run.

## Shift occupancy

`make pemu-shift-timing-check` proves the isolated shift engine's occupancy at
the manifest's default architecture. The per-bit duration and SHCFG field
positions come from the normative ISA. The proof counts elapsed cycles upward
within each bit and advances an independent bit index; the original RTL's
phase, index and timer remaining register are observed without modification.
Each cell occupies `max(D,1)` cycles, exactly the declared number of cells
executes, and `done` is true exactly on the final cell's final cycle. This
establishes `n*max(D,1)` by composition without a nonlinear SAT multiplier.
The register-period formula must be the same expression after substituting P
for D; the effective delay input remains symbolic across its entire width.

Caller assumptions are explicit: legal bit count and pins, an even nonzero
clocked period, stable SHCFG during a transfer, and stable effective delay
except on the final cycle when a new transfer may start. Start is allowed only
while idle or on the reference's expected final cycle. Reset interrupts a
transfer. Covers reach a zero-delay unclocked completion, maximum bit count,
maximum encoded delay at load, a back-to-back completion and all four SPI
modes. Mutated copies add a first-cell cycle or finish a bit early; both must
produce actual counterexamples.

This proves timing under those assumptions, not that the core enforces them,
chooses the correct register period or retires without a handoff cycle. It
also does not prove shifted data, pin waveforms or asynchronous reset recovery.
The non-default whole-core knob failure remains open. Each SAT job has a
bounded wall-clock timeout; inputs, scripts, logs and failure status are recorded
under a new `build/formal/pemu/` directory.

## Core DELAY/WAITE stream

`make pemu-wait-timing-check` checks the original core at the selected profile
parameters (the default is the exported 64-word profile). A symbolic word
source supplies only legal `DELAY` and `WAITE` words, with arbitrary delay,
register, edge mode and pin inputs; word fields may change while a wait runs.
Their opcodes, fields and duration/bound expressions come from the ISA. The
profile parameters reach the core through Yosys `chparam` before observations
are exposed. Non-default register/delay/pin composition remains unsupported.

An independent downward wait budget is compared with the RTL upward count.
Induction establishes the effective timeout, sampled edge/level detection,
return count on a completed active wait, final-sample timeout flag, and the
same-edge issue gate for the following instruction. A separate upward cell
age establishes `DELAY` occupancy. Immediate level-high completion has its
one-cycle floor and clears T; the zero register return remains a separate
model/RTL test, not a claim of this proof.

Eleven witnesses cover all edge/level modes, no-event timeout, zero-encoded
timeout, an event on the final sample, maximum bound at load, changed
prefetched fields, immediate-level completion and back-to-back waits. Mutated
copies delay the timeout by one cycle or use the live next word's delay instead
of the latched operand; both must produce counterexamples.

The first sampled edge resets, and subsequent resets interrupt occupancy.
This is a restricted core-stream proof, not a proof of other instruction
classes, program memory/fetch behavior, asynchronous reset recovery or physical
timing. It closes that subset of the timing argument without closing PE-06.

## Complete legal instruction-stream timing

`make pemu-core-timing-check` composes the reference counters around the
original core. All 31 defined opcodes participate in one arbitrary stream:
scalar operations occupy the ISA's `max(D,1)` cycles; shifts execute the
specified number of cells at encoded D or architectural P; waits complete on
the selected sample or effective timeout; HALT stops after its full occupancy.
The following instruction issues on the retiring instruction's final edge.

The reference independently counts cell age upward, bit index forward and
wait budget downward. It tracks the stack depth, shift configuration, period,
wait flag and held operands. SHCFG/SHPER effects are checked against the
observed forwarded register operand at issue; this proves their timing-control
updates and selection, not the arithmetic that produced the operand. The
proof asserts the core's issue gate, shift start/done, held-delay stability,
wait completion, timer state, stop state and same-edge handoff. It never
assumes a DUT ready, done or reject signal.

The legal-program assumptions are explicit: known opcode and legal operands
at reference issue, balanced stack operations, in-range branch/call targets,
and legal shift pins and effective period. The instruction word can change
while an instruction runs. The first sampled edge resets; later reset
interrupts occupancy. Invalid-program fault policy, program-memory/fetch data,
arithmetic/data/pin effects, non-default register/delay/pin composition and
physical reset recovery are outside this claim.

Completion witnesses cover every opcode. Fifteen additional witnesses cover
mixed wait/shift and same-kind handoffs, register P differing from that shift's
encoded D, changed prefetched delay, maximum encoded delay at load, maximum
bit-count completion, timeout/final-sample event, immediate level-high entry
and all four SPI modes. Five changed copies must produce base-case
counterexamples: lost shift handoff, live-word shift delay, wrong period
selection, early HALT and late wait timeout. The unchanged core must induct;
a bounded trace alone does not pass the gate.

A candidate package can carry the accepted harnesses and SAT scripts. Its
portable timing runner replays the original induction, all witnesses and
expected mutation failures, checks package hashes before and after, and
records each attempt in a fresh directory. Generator/template snapshots are
included for audit; regeneration for a different ISA/profile uses the
maintained atomiX runner.
