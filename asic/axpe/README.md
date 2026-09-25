# atomiX axpe Tiny Tapeout export

This repository is generated from the atomiX source tree by `make tt-export`.
It contains `axpe`, a runtime-programmable timed-ISA protocol emulator for the
Jane Street CMOS5L challenge.  Programs are loaded after reset over the fixed
SPI host port; UART, SPI, I2C and autobaud are firmware, not mask-fixed blocks.

The generated `.atomix-export.json` records the exact source hashes, component
profile and flow lock used for this export.  The 64-word inferred instruction
store is an early-flow candidate, not a final capacity claim.  Full model,
cycle-exact cosimulation and independent-protocol-peer tests live in the atomiX
repository; this export's compact test checks the loader boundary directly.
The generated `axpe_isa.svh` include is exported and hashed beside the RTL but
is not listed as a compilation unit in `info.yaml`.

Licensed under Apache-2.0.  See `LICENSE`.
