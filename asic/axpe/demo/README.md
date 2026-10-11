# Reproduce the protocol demonstrations

From the exported repository, run `make -C demo check`. This needs Make,
Python, a C++ compiler and Verilator. Tool support is recorded in the bundled
`tools/requirements.json`. The export contains every source needed for this
command; no atomiX checkout, PDK or FPGA is needed.

The unchanged shared chip harness assembles the four firmware programs from
the normative ISA and loads them over the fixed SPI host port into one wrapper
simulation. It checks runtime reprogramming against the C model cycle by cycle,
refuses writes while running, and checks UART, mode-0 duplex SPI and I2C against
independent peers. I2C covers ACK/NACK, repeated START, reads, STOP and released
open-drain lines. Autobaud measures and uses two unknown input periods. The
suite runs at three randomized startup seeds.

Each loaded image is read back completely before RUN; a refusal or mismatch
aborts the load. At every seed, a fresh instance additionally runs UART,
deselects while TX is driven, checks quiet outputs, resets/reselects and fully
reloads. Warm reset and another full UART reload are also checked. The mapped
suite runs the same cases. These inputs do not model power removal or carrier
isolation; physical reload validation remains open.

The fixed-rate UART payload and its peer use 434 cycles per bit, based on a
nominal 50 MHz program clock. A 25 ns P&R target does not establish that
operating rate. Set the program's clock/bit-period constants for the actual
supplied clock before physical use; changing a runtime payload needs no
hardware rebuild. Autobaud instead measures and uses the peer's period in
cycles. These simulations establish cycle counts, not an absolute physical baud.

For the selected nominal 40 MHz target, run `make -C demo rate-check`.
It builds all three bundled runtime profiles without recompiling the hardware:
115200/57600 UART, 1/2 MHz mode-0 SPI and 100/400 kHz I2C. Each runs the full
protocol/readback/reload suite at three seeds. A candidate package also supports
`make -C demo mapped-rate-check`. Requested rates, exact integer periods,
listings and hashes are under `demo/build/fw-rates/`. See the
[clock audit](../docs/submission-compliance.md) for UART rounding and I2C gaps.

The simulator and assembled payloads go under `demo/build/`. None of the
firmware is a memory-initialization or synthesis input. Editing firmware changes
the demonstration inputs, not the hardware source hashes in
`.atomix-export.json`.

This command checks RTL behavior with two-state, zero-delay semantics. It
does not establish routed timing, analog behavior, FPGA operation or silicon
operation. `verification/evidence-index.json` hashes the included historical
receipts and names their evidence levels. Their limits and failures remain
in those receipts; bundling them does not establish signoff for this export.
The selected export profile and flow lock are recorded separately in
`.atomix-export.json`.
# Checking a hardened candidate

If the export includes `.atomix-candidate.json`, run
`python3 verification/check_package.py` followed by
`make -C demo mapped-check mapped-rate-check`.
The latter repeats the same suite over the bundled mapped netlist and cell
functions without a PDK checkout. See [physical candidate](../docs/physical-candidate.md)
for its exact provenance and limits. A normal source export has no hardened
assets and uses `make -C demo check`.

The fast I2C profile requests a 400 kHz ceiling and runs a 112-cycle symmetric
cell (about 357.143 kHz at 40 MHz) to satisfy nominal Fast-mode low/high timing
with a 100 ns guard. The bus checker also checks START/STOP, bus-free and data
setup timing. See the submission clock audit for the retained timing failures
and physical limitations.

`40mhz-slow` runs SPI and I2C at 10 kHz. Protocol-case timeouts scale with
the profile periods, so slower legal images are allowed to finish.
