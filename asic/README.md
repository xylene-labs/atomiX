# ASIC sources

`tt-axpe/` is a pristine import of the official Tiny Tapeout CMOS5L Verilog
template linked by the Jane Street protocol-emulator competition.  Keeping the
baseline untouched makes upstream drift visible before axpe is bound into it.

| Item | Pinned value |
|---|---|
| Repository | `https://github.com/TinyTapeout/ttihp-verilog-template.git` |
| Branch named by the competition link | `cmos5l` |
| Commit | `b86a2a781484bcab7ba522dc5de540086695a430` |
| Commit date | 2026-06-24 |
| Git tree | `5d72d5b9e04c0732d32c7f7d0f72cf950508e551` |
| Imported | 2026-09-25 |

The competition page currently requires `tiles: "6x4"`.  The imported
`info.yaml` still comments that only `*x2` shapes are valid, but that comment is
stale: Tiny Tapeout's `ihp-sg13cmos5l` support-tools branch at
`d66cf179e7bc4d296362ab7e2e3b344dc3c4f665` defines `6x4` as the rectangle
`0 0 1289.28 710.64` micrometres.  That is the shape PE-02 must harden against.
The same support-tools revision contains `8x4`, but Jane Street's current rules
still cap the entry at `6x4`, so axpe does not assume the larger allocation.

Two other upstream facts are deliberately not repaired in this baseline.  The
template's GDS workflow selects `ihp-sg13cmos5l`, while its devcontainer still
sets `PDK=ihp-sg13g2` and clones the support tools' `main` branch.  The workflow
also names moving action branches rather than commit identities.  PE-02 must
pin the actual flow inputs and prove the local command before producing area or
timing evidence.  Importing this tree is therefore not synthesis, place-and-
route, gate-level, FPGA, or silicon evidence.

`axpe/` is the maintained project overlay and [`flow-lock.json`](axpe/flow-lock.json)
pins the GDS action, support tools, PDK commit and LibreLane version used by the
first feasibility run. `make tt-export` verifies a canonical hash of the
pristine template, resolves `configs/tt-axpe-6x4.json`, and writes their merged,
standalone Tiny Tapeout repository to `build/asic/tt-axpe-export/`. The output
marker records every exported RTL and generated-ISA-include hash; the exporter
refuses to replace an unmarked directory or any export containing a flow
`runs/` tree.

The PDK commit installed by the pinned official action contains no SRAM macro
views under `ihp-sg13cmos5l/libs.ref`. The similarly named 256×32 macro exists
only in the SG13G2 library, so it is not silently treated as CMOS5L-compatible.
The first hardening candidate instead uses a 64×32 inferred synchronous array:
all four mandatory firmware images fit (largest: 55 words), and the physical
flow must now determine whether those cells fit the 6×4 rectangle.

To compare the baseline with upstream, clone the pinned commit elsewhere and
run `diff -ru --exclude=.git <clone> asic/tt-axpe`.  An empty diff, plus the
executable mode on `.devcontainer/copy_tt_support_tools.sh`, reproduces the
import check.
