# axpe submission verification draft

axpe loads protocol programs after reset over a fixed SPI host port. One
unchanged design runs UART, duplex SPI and open-drain I2C firmware. The
measured-period demo waits on an unconfigured input, captures its period and
uses that architectural value to transmit at the measured rate. Protocol
firmware is a runtime payload, never an ASIC mask or FPGA synthesis input.

This is a submission draft for maintainer review. The measured candidate and
its repeatable protocol/formal checks can be packaged locally; an external
pad/carrier I/O timing contract and maintainer reviews remain open. The
export's selected capacity, clock, parameters and hardware source hashes live
in `.atomix-export.json`. Included historical results apply only to the input
hashes they name; this export does not inherit signoff merely by including them.
The [AI-use disclosure](ai-use.md) records assistant contributions and shared
author provenance; maintainer approval is still owed.

## Reproduce the functional demonstration

Run `make -C demo check` from the exported repository. It assembles the
firmware, checks generated ISA tables, compiles the exported wrapper and runs
the shared chip suite at three randomized startup seeds. See the
[demo instructions](../demo/README.md) for inputs and dependencies.

The suite loads two unrelated programs through the actual host pins and checks
their outputs and elapsed cycles against the C golden model without rebuilding
the design. It also checks reset silence and refusal of writes while running.
Mandatory protocol firmware is checked against independent peers: an 8N1 UART
receiver, a mode-0 full-duplex SPI target, and an I2C target covering ACK/NACK,
repeated START, read, STOP and open-drain release. Autobaud uses two different
unknown periods and an independently timed receiver. The test cases, peers,
firmware and model are the same sources used by the atomiX chip bench.

Before RUN, every shared-suite payload is written and read back in full; a
refused write or mismatched word aborts the attempt. The Tiny Tapeout binding
also creates a fresh device instance, decodes UART after a full load, deselects
while TX is driven, checks quiet outputs, then resets/reselects and reloads.
A warm external reset followed by another full load is covered too. The same
binding runs over RTL and mapped cells. This tests logical selection/reset
inputs, not physical power removal, carrier isolation or four-state startup.

## What the evidence establishes

The [evidence index](../verification/evidence-index.json) binds each bundled
receipt by hash and names its level. Each receipt retains failures and limits.

| Level | Method and present result | Limit |
|---|---|---|
| Host C model | ISA-generated encodings/timing tables, assembler checks and protocol waveforms | Executable specification; no RTL or physical proof |
| Host RTL simulation | Cycle-exact differential checks plus runtime programming and independent peers | Tested inputs, two-state and zero-delay semantics |
| Host formal | All 31 legal opcodes' occupancy and handoff induct, with 46 witnesses and five broken-core counterexamples; separate timer and shift proofs remain available | Abstract instruction source and legal-program assumptions; excludes memory/data correctness, invalid-program fault policy, non-default architecture and physical reset recovery |
| Host mapped simulation | PDK Liberty-generated cell models, complete input/model binding checks and shared runtime protocol suite at three seeds, including the routed one-buffer ECO; final signoff netlist hash matches | Two-state, zero-delay; no SDF, four-state startup or whole-design equivalence proof |
| CMOS5L synthesis and P&R | Routed one-buffer ECO passes all-corner extracted STA, antenna, Magic full DRC and Netgen LVS; final netlist hash matches the functional replay | Only 25 ps fast-corner hold margin; provisional I/O timing is not a pad contract; KLayout DRC/XOR and Yosys EQY were skipped |
| Physical FPGA or silicon | No result included | No physical-operation claim |

## Why the checks use different references

The ISA JSON owns encodings and declared timing. Derived C/SV tables and
assembly listings are generated or checked from it, so a copied timing table
cannot silently drift. Differential checking covers actual retirement and
pin traces, but agreement with the model alone cannot establish protocol
correctness. The protocol peers use bus rules and their own receive clocks;
their first runs found firmware defects that model checks had passed.

The timer proof uses an independent upward elapsed-cycle counter against the
RTL downward remaining-cycle counter. Witnesses exclude a reset-only proof,
and changed timer copies must be rejected with actual counterexamples. It
proves the isolated block's declared duration, including zero-delay clamping;
it does not promote a block invariant into a whole-core proof. The shift proof
tracks cell age and bit index independently, proving the declared number of
cells and `done` on the final cycle under its documented caller assumptions.
Covers reach all four SPI modes and a back-to-back transfer. It does not prove
that the core enforces those assumptions or selects the correct period.

The restricted core-stream proof supplies legal DELAY and WAITE instructions
through an abstract word interface. Its independent downward wait budget
checks the RTL upward count, edge/level detection, final-sample timeout flag,
active-wait return count and following-instruction issue gate. Eleven covers
include changed prefetched words and back-to-back waits; two mutated copies
must fail. Immediate level-high completion occupies one cycle, while its zero
register return remains separately model/RTL tested. Other instructions,
program memory/fetch and non-default core composition are outside this proof.

The complete-stream proof composes independent cell age, bit index and wait
budget around the unchanged core. It establishes each legal scalar opcode's
duration, encoded/register-selected shift timing, held operands, mixed
handoffs and full HALT occupancy. Configuration/period updates are compared
with the observed forwarded source operand; arithmetic that produced that
operand is outside the timing claim. Legal operands, balanced stack operations
and in-range branch/call targets define the domain. No DUT ready/done/reject
signal is assumed. All 31 opcode completions have witnesses, with 15 more for
boundary and mixed-stream cases. Five mutations break shift handoff, held
delay, period selection, HALT duration and wait timeout; each must produce a
base-case counterexample. The packaged SAT jobs can be rerun with Yosys.

Mapped functional replay checks a selected unmodified netlist. Cell functions
come from the pinned Liberty files and must agree across all three corners.
Every actual cell and every input pin must have a binding. Direct PDK timing
models were rejected when ignored timing constructs left reset undriven;
silencing those warnings would have weakened the check. Zero-delay replay
and extracted timing therefore remain separate evidence.

Physical experiments keep failed and interrupted candidates. A clean route
does not establish electrical closure, and a simulation pass cannot repair a
fanout or hold violation. The routed one-buffer ECO passes extracted all-corner
setup, hold, slew, fanout and capacitance checks, route DRC and antenna checks.
Its functional replay passes at three startup seeds. Fast-corner hold margin
is only 25 ps. Magic full layout DRC and Netgen LVS also pass; the final signoff
netlist is byte-identical to the replayed routed netlist. This establishes the
local candidate binding. The package includes exact inputs and the reproduction
recipe; the external I/O contract and maintainer review remain open. KLayout DRC/XOR
and Yosys EQY were skipped by the locked flow; unset supply locations also
prevent a package-level IR-drop claim. Submission to a shuttle will not
constitute fabrication or measured silicon.

## Supplied-clock runtime checks

The runtime builder derives payload periods from firmware-owned clock/rate
profiles, independently of hardware identity. The same RTL and mapped suites
run default 50 MHz payloads and three 40 MHz profiles at three startup seeds.
UART checks exact 8N1 transition offsets as well as independent decoding; SPI
checks all eight cell spacings. I2C additionally checks resolved digital SCL
low/high, START/repeated-START/STOP, bus-free and data setup times against
[NXP UM10204 Rev. 7 Table 11](https://www.nxp.com/docs/en/user-guide/UM10204.pdf).
The 400 kHz request is a ceiling: the symmetric cell and 100 ns nominal guard
yield 112 cycles, approximately 357.143 kHz at 40 MHz.

The stronger oracle rejected two previously decoded payloads: the old fast
cell's 1.25 µs low time, and quarter-cell STOP/repeated-START handoffs in
the Standard-mode library. Both failures are retained in the clock evidence;
corrected runtime words use a longer fast cell and half-cell handoffs. UART
period errors of one cycle are also rejected. These are nominal digital
simulation results; analog rise/fall, pad thresholds, data hold, clock
stretching and measured physical operation are excluded.

The slow profile uses 4000-cycle SPI/I2C cells. Test budgets scale with the
profile periods; earlier fixed budgets rejected these valid transactions before
completion. The retained failures distinguish test-limit errors from protocol
or hardware failures.
