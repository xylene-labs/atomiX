# atomiX axpe Tiny Tapeout export

This repository is generated from the atomiX source tree by `make tt-export`.
It contains `axpe`, a runtime-programmable timed-ISA protocol emulator for the
Jane Street CMOS5L challenge.  Programs are loaded after reset over the fixed
SPI host port; UART, SPI, I2C and autobaud are firmware, not mask-fixed blocks.

The generated `.atomix-export.json` records the exact source hashes, component
profile, instruction-store capacity and flow lock used for this export. The
default source export uses the early-flow profile; a candidate package also
binds the selected hardened images through `.atomix-candidate.json`. Run
`make -C demo check` for runtime reprogramming, cycle-exact comparisons and
independent UART/SPI/I2C peers, including measured-period autobaud, from this
export alone. The compact cocotb test also checks loader read/write directly.
The [demo instructions](demo/README.md) explain the simulation limits.
The generated `axpe_isa.svh` include is exported and hashed beside the RTL but
is not listed as a compilation unit in `info.yaml`.

`.atomix-export.json` keeps hardware `sources` separate from
`verification_inputs`, so firmware is never part of a hardened design's
identity. `verification/evidence-index.json` links historical evidence with
its hashes and levels; it records failures and unresolved work and does not
assert signoff for this exported candidate.
The [verification draft](docs/verification.md) explains the methods and gaps.
The [AI-use disclosure](docs/ai-use.md) describes assistant contributions,
shared author provenance and the outstanding human review.
The [submission compliance audit](docs/submission-compliance.md) identifies
remaining entry requirements and the shipped payloads' actual clock assumptions.
The [wiring/reload draft](docs/demo-wiring.md) specifies host and peer connections,
including adapters for the payloads' differences from recommended Pmod pinouts.

Licensed under Apache-2.0.  See `LICENSE`.

Source publication and candidate delivery are distinct artifacts. Generated
demo builds, hardened images, raw candidate/precheck reports and accepted
formal jobs are excluded from source Git staging. The candidate archive carries
those assets and its manifest for review or an authorized release; it must be
validated after downloading or relocation. Publication of either artifact and
submission remain maintainer actions.
