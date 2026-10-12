# CI failure investigation — 2026-10-12

The [push CI run](https://github.com/xylene-labs/atomiX/actions/runs/38239693617)
tests commit `386ff3c0d456195dc1cf972d3e17b6f3b63f592f`. Its quick job fails
in `pemu-cosim`, specifically the new profile probe's elaboration. Unit and
integration jobs pass. The [nightly run](https://github.com/xylene-labs/atomiX/actions/runs/38238712118)
uses the earlier `e82bdafe543809c6d876ef05d310cb4e059b873c` and fails its
integrated job in `pemu-cosim` and `pemu-chip`; 35 stages pass. The randomized,
ISA and three-platform jobs pass. This failure predates the latest commit.

Both jobs report the distro-provided Verilator 4.038. axpe's RTL and generated
ISA headers use `UNUSEDPARAM` and `UNUSEDSIGNAL` lint directives; the older
frontend rejects these before simulation. The local accepted runs used a
different frontend. The [upstream release notes](https://github.com/verilator/verilator-announce/issues/57)
record the split warning names. Tool support, tested history and the immutable
CI release/version pin are single-sourced in `tools/requirements.json`.

## Reproduction and local repair

Selecting `/usr/bin/verilator` through PATH reproduces the same eight lint
directive errors in the profile probe. The failing receipt is
`build/pemu/profiles/ci-old-verilator-2026-10-12/evidence.json`. A second failed
attempt verifies that the repaired runner prints the compiler diagnostics;
its receipt is `build/pemu/profiles/ci-old-verilator-diagnostics-2026-10-12/evidence.json`.
These are recorded failures, not accepted profile results.

The shared setup action now reads the pin, verifies its supported range,
builds the pinned source revision on a cache miss, restores the cached install
on subsequent runs and verifies the selected executable's version. It no
longer relies on the runner's apt Verilator. The generated dependency table
rejects the known-incompatible frontend while retaining historical baseline
evidence. Profile failures print the last 40 diagnostic lines and their raw
logs/receipts are included in quick and integrated-nightly artifacts.

A local `ci-quick` replay exposed an additional source-scope problem:
`diagram-check` traversed downloaded Nix documentation below `build/` and
reported four unrelated diagrams. The checker now enumerates tracked and
visible untracked Markdown through Git, excluding ignored generated trees.
A temporary-repository probe confirms that ignored vendor diagrams are skipped
and malformed source diagrams still fail. This local failure was not the cause
of the hosted runs above.

## Validation and limits

The repaired local `ci-quick` suite passes all 14 stages. Focused
`pemu-cosim-check`/`pemu-chip-check` and all 14 smoke stages pass. Workflow YAML,
embedded shell syntax, the actual pin-output step, support classification and
negative compiler diagnostics also check successfully. The selected-profile
export's ten hardware source hashes match the frozen submission candidate;
neither RTL nor GDS changed.

The compact receipt is `research/benchmarks/axpe-ci-toolchain.json`. The local
initial quick failure and final passing quick/smoke reports are retained under
`build/verification/ci-repair-2026-10-12` and
`build/verification/ci-repair-final-2026-10-12`. Generated logs and downloaded
workflow archives are not source artifacts.

The source-build/cache path has been syntax-checked; it has not yet run on a
fresh GitHub worker. Unit/integration results above belong to the original
hosted run, not a new run with the repaired setup action. The maintainer has
authorized committing this fix; the commit recording this note is the review
target. Hosted confirmation requires publication of that commit and a new run;
rerunning the old commit would use the old setup again. Publication and
commit-pinned maintainer approval remain separate actions.
