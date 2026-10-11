# Local CMOS5L candidate

This document applies when `.atomix-candidate.json` is present. A normal
`make tt-export` creates a source repository and historical evidence index;
it does not select or reproduce the physical ECO by itself.

The candidate package contains the measured one-buffer ECO's final GDS,
unchanged routed netlist, Liberty-derived functional cell model, physical
summary and reports, accepted mapped-replay receipt and its runtime payloads.
The selected 25 ns profile and flow lock are included beside the receipts.
`.atomix-candidate.json` hashes every supplied file and binds the final
netlist to the passing protocol replay. Hardware source identity and runtime
payload hashes remain separate.

When `precheck` is present in the candidate manifest, the package additionally
contains the exact selected GDS's separate Tiny Tapeout precheck receipt and
raw reports under `verification/precheck/`. The validator binds that receipt
to this GDS and final signoff state. A package without that field has no
selected-GDS Tiny Tapeout precheck claim. Include an accepted directory with
`--precheck` in atomiX's `PEMU_PACKAGE_ARGS`; incomplete, failed or changed
checks and mismatched GDS/state/tool identities are refused before packaging.

Run from the package:

```sh
python3 verification/check_package.py
make -C demo mapped-check
make -C demo check
make -C demo rate-check mapped-rate-check
```

When `timing_proof` is present in the candidate manifest, run
`make -C demo formal-check` to repeat the core timing induction, all 46
completion/boundary witnesses and five expected mutation counterexamples.
This additionally needs Yosys from the formal tool tier in the bundled
requirements. Each attempt records its result in a fresh `demo/build/formal-*`
directory. The scope is all legal instruction occupancy over an abstract word
source; memory/data correctness and non-default architecture are excluded.

The mapped check needs Python, Make, a C/C++ compiler and Verilator; it needs
neither atomiX nor a PDK checkout. It recompiles the supplied mapped netlist
and cell functions against the same runtime-programming cases, C oracle and
independent protocol peers as the source demo. Three startup seeds and the
four assembled demo payloads are checked. It is two-state, zero-delay
simulation without SDF. Clock cycles do not establish absolute physical baud:
the fixed UART payload's 434-cycle bit assumes 50 MHz, and must be retimed as
a runtime payload for the supplied clock. The autobaud payload measures its
own period.
The bundled 40 MHz runtime profiles supply retimed common-rate demos and their
accepted mapped replay receipts; `mapped-rate-check` repeats their peer and
clock-cell checks. See [the clock audit](submission-compliance.md).

## Reproduce the physical candidate in atomiX

`verification/candidate/physical-evidence.json` retains the exact staged
commands, parent/output hashes, failed experiments and selected continuation.
`post_grt_max_wire_200_fanout_eco_trial` identifies the accepted recipe and
signoff. The included `eco.py` and `eco.tcl` are snapshots of
`asic/axpe/experiments/wire200-fanout-eco.*`; run the maintained originals
from atomiX using the pinned Nix environment, rather than from this package.
The recipe requires its named parent checkpoint and fails if the ODB,
netlist or SDC bytes differ. Its exact parent assets are bundled under
`verification/candidate/eco-parent`. From the package, run
`python3 verification/restore_eco_parent.py --atomix-root /path/to/atomiX`
to restore them into the recipe's required build location. The helper checks
the maintained recipe hash, refuses an existing checkpoint, relocates file
paths and clears inherited metrics. The original state is retained by hash;
the relocated state has a new provenance hash because its paths change.
The pinned PDK/Nix/flow environment must still be prepared in atomiX.

This replays from the recorded parent. Regenerating that parent from source
uses the earlier wire-200 stages in the evidence; it is not a new synthesis
from the package's default GDS workflow. A different parent must receive new placement, route, timing, physical
checks and replay evidence before it can replace this candidate.

The selected continuation performs global routing, then nominal STA, then
detailed routing through extracted STA. It skips the second post-global-route
design repair: starting at the antenna-check stage also ran that repair and
added 380 buffers in a separate, unselected experiment. Full signoff resumes
at the IR-drop stage and proceeds through Magic GDS/DRC, extraction and
Netgen LVS. No source RTL or ISA encoding changed for the ECO.

The fresh 2026-10-11 continuation reproduces the preparation, global route,
nominal STA, detailed route and full Magic/Netgen signoff. Routed ODB, DEF,
netlist and all final metrics match the selected candidate exactly. Comparing
all GDS record bytes after excluding only BGNLIB/BGNSTR timestamps also
matches. The compact `axpe-flow-reproduction.json` receipt contains commands,
hashes, the comparison algorithm and the transient three-net antenna finding
that the configured repair clears. This is a fresh checkpoint continuation;
it does not claim a fresh source-to-parent synthesis, a KLayout XOR run or
another selected-GDS precheck. The package retains the original selected GDS.

## Limits and review

Magic full DRC and Netgen LVS report zero errors. Route DRC and antenna checks
are clear, and setup, hold, slew, fanout and capacitance checks pass at all
three extracted corners for the declared 25 ns clock. Fast-corner hold margin
is only 25 ps. The 4 ns external I/O delay remains provisional because no
pad/carrier timing contract is available. The flow's KLayout DRC/XOR and Yosys
EQY were skipped; a supplied Tiny Tapeout precheck records its separate KLayout
checks. Unset supply locations prevent a package-level
IR-drop claim. The legal-stream timing proof excludes program-memory/data
correctness, invalid-program fault policy and non-default architecture.

The maintainer owes commit-pinned review of the candidate and its recipe.
These files are a local review package, with no external publication or
submission implied. No physical FPGA or returned, measured silicon evidence
is included.
