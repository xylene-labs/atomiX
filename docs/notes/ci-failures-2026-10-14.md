# CI follow-up — 2026-10-14

The latest [nightly run](https://github.com/xylene-labs/atomiX/actions/runs/38537077473)
and [static-analysis run](https://github.com/xylene-labs/atomiX/actions/runs/38550610415)
both test `386ff3c0d456195dc1cf972d3e17b6f3b63f592f`. GitHub's `main` branch
still points there when checked on October 14. Local `922094a` contains the
Verilator setup repair; local `d29cd42` records the signed-off PE-09 adapter,
loader and EEPROM work. Neither is published by this investigation. Rerunning
an old run uses its old source/setup and cannot confirm the local fixes.

## Hosted failures

Nightly's integrated job passes 35 stages and fails `pemu-cosim` and
`pemu-chip`. The other three jobs pass. Its tool report names Verilator 4.038;
exported axpe sources reject eight `UNUSEDPARAM`/`UNUSEDSIGNAL` lint directives.
This is the same frontend mismatch reproduced in the
[October 12 investigation](ci-verilator-failure-2026-10-12.md). The existing
local repair selects the immutable pin from `tools/requirements.json` instead
of the apt frontend. Fresh hosted build/cache confirmation remains pending.

Static analysis has a different cause: Python lint reports two findings:

- `sw/pemu/firmware/build_demos.py:13`, E402: assembler import after deliberate
  repository-path setup.
- `sw/pemu/firmware/check_demos.py:6`, F401: unused `settings` import.

The other five analyzer stages, kernel clang/lld checks and all four parser
fuzz targets pass on that hosted run. The final workflow step intentionally
fails after preserving the findings. Deprecated-action runtime warnings are
not the failing condition. No issue/comment update was sent by this agent.

## Local correction and boundaries

Remove the unused import. Preserve `build_demos.py` byte-for-byte because the
frozen ASIC review archive and functional replay bind it; document only its
intentional E402 bootstrap exception in `ruff.toml`. The existing nextpnr
injected-global exemption also covers the new Primer clock script, without
editing that image-bound input.

The new PE-09 files added fifteen further local diagnostics, although they are
not yet present in the hosted run: four injected `ctx` references, intentional
path-bootstrap imports, unused imports/a binding, and two test callbacks using
loop variables. The callbacks now bind their values explicitly; dead imports
and the unused binding are removed. Required bootstrap imports carry narrow
annotations. No defect rule is disabled project-wide.

Both local Ruff and the exact hosted Ruff version produce zero findings after
these changes. Versions/evidence live only in `tools/requirements.json`; the
isolated matching package is under `build/`. Cppcheck/ShellCheck are also
extracted below `build/`, leaving system packages untouched. The initial strict
local replay could not run those two tools and is retained as incomplete.

The isolated cppcheck initially could not start without its shared library.
This exposed a reporting defect: `analyse_cpp` could turn a nonzero tool exit
with no parsed source diagnostic into a clean result. It now emits
`analysis-did-not-run` for that case. A negative probe confirms all affected
program groups are rejected. After supplying its dependency and relocating the bundled config assets,
the actual analyzers are rerun; an unusable-tool result is not accepted as C++ evidence.

The new local lint/reporting repair remains uncommitted after the requested
PE-09 commit. It changes no core/ISA, FPGA pin/clock inputs, selected GDS or
frozen review archive. Compact source/log/run identities and local verification
results are recorded in `research/benchmarks/axpe-ci-followup-2026-10-14.json`.
Hosted confirmation requires publishing the repaired source and running new
jobs. This investigation performs no push, dispatch, FPGA programming or
physical EEPROM operation.


## Capture-driver verification budget

The first local smoke replay passed 13 stages and timed out `pemu-chip` at its
180-second limit. Capture mode was evaluating every unused Dock oscillator
edge while running the external-clock design. The simulator driver now applies
only the external clock edges during functional cycles. It still explicitly
measures eight periods using oscillator ticks and the resolved frequency ratio.
Normal mode retains its oscillator/divider model. The clock mode is wired from
the board profile into the C++ driver; no RTL, clock constraint or stage timeout
is changed. Both adapters pass all shared/EEPROM cases at three seeds and
both firmware mutation checks after this change. The failed timing attempt
remains recorded; full smoke is rerun after the correction.

All six actual analyzers pass locally with the hosted Ruff version and working
Cppcheck/ShellCheck. The Python file-count note includes generated trees even
though Ruff excludes them; it is not treated as a source-coverage count. The
verdict is backed by Ruff's actual zero-finding output.


## Accepted local verification

All six static-analysis stages pass with no findings and no skips. All 14
smoke stages pass after the capture-driver correction; `pemu-chip` completes
in 35.175 seconds on this replay, within its unchanged 180-second budget. A
separate 2.5 MHz capture/23-cycle-reset profile also passes three startup seeds
and both firmware mutations. These are local observations, not a new hosted
run or a controlled cross-machine performance benchmark. Registry, workflow
coverage and generated tool requirements checks pass.
