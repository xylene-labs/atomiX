# Draft axpe host model

`axpe_model.c` executes assembled words using the generated ISA opcode and
timing tables. `axpe_step` retires one instruction and emits one observation
per elapsed cycle. The caller supplies physical input levels by cycle number,
the program store, and a call stack; no firmware is baked into the model.
Memory length and stack capacity are runtime bounds, exercised at multiple
values. Register and pin widths currently implement the default ISA only;
PE-08 profile integration remains open.

This is a **partial reference model**, not a settled cycle-level RTL contract.
These conventions make the missing specification observable and reviewable:

- Reset clears registers, flags, output latches, direction, configuration and
  counters. PC starts at zero. Program words remain caller-owned.
- Fixed instructions apply their effects at issue, then occupy `max(D,1)` cycles.
  PC and retired count change after the final observation. HALT consumes its
  full delay; subsequent steps do nothing.
- WAITE samples at entry and after each waiting cycle. Edge modes require a
  change after entry; level-high may finish immediately. It occupies exactly
  the cycles it waited, with a one-cycle floor, so the value it returns and the
  time it costs are the same number. An edge exactly at the effective timeout
  still sets T; a level already satisfied at entry does not, because that is
  not a timeout. Two waits measure a true interval only when adjacent.
- Unclocked shifts emit/sample at each cell's first edge and hold for `max(D,1)`
  cycles, with no setup cycle, so n bits occupy exactly `n*max(D,1)`. They use
  the low n bits, in the requested order. SHOUT preserves its source; SHIN/SHIO replace the register with the
  zero-extended received word. Flags are preserved.
- Zero-distance ALU shifts preserve carry. Other ALU flag changes follow the
  JSON description; subtraction carry means borrow.
- Fetch bounds, invalid opcodes/operands, and stack faults stop before issue
  without consuming cycles. They are model diagnostics, not hardware traps.
- Clocked shifts split their cell at the half point: data at the cell start
  (or on the leading edge when `cpha=1`), clock leading edge at `D/2`, back to
  `cpol` at `D`, sampling on the edge `cpha` selects. All four SPI modes are
  covered by tests. `AXPE_UNSUPPORTED` before issue, consuming no cycle, for an
  odd or zero clocked period, a clock aliased onto either data pin, a clock on
  an input-only pin, or an input-only data-out pin. `din == dout` is allowed,
  because I2C needs it. Unclocked shifts accept any `D`, `0` meaning one cycle
  per bit.

Open-drain output enable is `direction & ~(drain & output_latch)`. The input
callback supplies resolved pad levels, including pull-ups or external drivers;
reading a pad never silently substitutes the output latch. Observations expose
both the latch and enable mask so a later RTL bench can compare both.

The tests run the UART and autobaud firmware against the platform oracle in
`research/personalities/workloads/uart-tx-8n1.json`, and both now **conform
exactly** for all five cases.

That was not true of the first draft, and the discrepancy it recorded is what
fixed the ISA. Under the earlier `1+D` rule this model measured a constant
two-cycle lag on every UART edge after the first, and an autobaud minimum two
cycles short. The lag was not a firmware defect: a `1+D` bit cell is `BAUD+1`
cycles, so no firmware could place an edge on a multiple of the bit period. The
rule became `max(D,1)`, and one of the two autobaud cycles turned out to be a
real firmware bug -- a branch sitting between the two waits, spending a cycle
the measurement could not see. Recording the mismatch rather than tuning the
expectation to match is what made both visible.

Clocked shifts are now specified and modelled. SPI and I2C firmware, their
platform oracles, randomized RTL comparison, the formal proof, and all hardware
evidence remain open.
