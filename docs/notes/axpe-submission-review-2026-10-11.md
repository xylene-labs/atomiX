# axpe submission review — 2026-10-11

This note prepares the maintainer's review of the Jane Street CMOS5L entry.
It does not record approval, publication or submission. PE-12 has completed
local preparation and is in Review; PE-08 width/profile repairs remain behind it.

## Candidate and review scope

The selected candidate remains the locked 6×4, 64×32 inferred-store design
at a 25 ns clock target. Its GDS SHA-256 is
`a5877dd7626f05d7462ce6e629e84e1b507a606f7c6a75e083e22c09af772134`;
its routed netlist SHA-256 is
`959c159a7259e687f3ef3003d1522266b3dfd838b500b9cbeaedbd4be88c05e3`.
No runtime firmware is part of that hardware identity.

Review the generated ISA and effects/reset/fault conventions (PE-03/04),
retirement/forwarding and host programming (PE-05/14), legal-stream formal
assumptions (PE-06), runtime protocol peers and timing limits (PE-07/11/15),
and the ECO recipe, physical evidence and final submission contents
(PE-10/12). All affected cards retain maintainer review; none closes itself.
The commit to review must be chosen after the maintainer authorizes a signed-off
commit. There is currently no commit-pinned approval of these working changes.

## Verification and retained failures

The exact selected GDS passes all nine unchanged pinned Tiny Tapeout prechecks.
The separate receipt and raw XML/reports must be included and hash-bound in the
final candidate package. The complete legal-stream proof covers 31 opcodes,
46 witnesses and five mutation counterexamples; it abstracts the word source
and excludes memory/data correctness, invalid-program faults and non-default
architecture.

Supplied 40 MHz runtime profiles verify UART/SPI/I2C without resynthesis.
The independent I2C waveform audit found and retains two errors that byte
peers had decoded successfully: a 1.25 µs Fast-mode SCL low interval, and
quarter-cell low handoffs before STOP/repeated START in Standard mode.
Runtime words now use half-cell handoffs and a 112-cycle fast cell, about
357.143 kHz at 40 MHz, with a 400 kHz requested ceiling and 100 ns nominal guard.
UART checks exact transition offsets as well as independent byte decoding.
The clock receipt records accepted replays and deliberate failing payloads.
All 24 RTL/mapped default/standard/fast/slow suite invocations also pass from a fresh
location outside atomiX, including package/XML/payload hash validation.
The legacy assembly recipe and mapped replay now pass the resolved instruction
limit; a 16-word refusal and byte-identical
64-word acceptance verify that gate. The final mapped helper replay passes
all 12 default/profile suites; all 14 smoke stages pass with bounded assembly and period-derived case budgets.
The 10 kHz slow profile demonstrates that legal slow images finish; earlier
fixed SPI/I2C case-timeout failures remain recorded.

The ECO preparation reproduces ODB, DEF, netlist and tool-log bytes exactly.
The fresh staged route and full Magic/Netgen signoff pass with 26 zero-error
physical/electrical counts. Routed ODB/DEF/netlist and all final metrics match
the selected candidate; GDS non-timestamp bytes match too. See
`research/benchmarks/axpe-flow-reproduction.json` for commands and hashes.
This is reproduction from the pinned pre-ECO parent, not a fresh source-to-parent
synthesis. The default exported GDS workflow does not perform this ECO.

## Limits and remaining maintainer actions

The external I/O budget remains a provisional 4 ns; the selected fast hold
margin is 25 ps. No characterized CMOS5L pads, analog rise/fall, data-hold,
clock-stretching, carrier isolation, physical power-loss, FPGA or measured
silicon evidence is claimed. The ETR v3 Rev 3.2 connector mapping is a pinned
reference document; check the delivered board's revision before lab use.

The existing public parent repository is `https://github.com/xylene-labs/atomiX`.
That does not publish these uncommitted changes or the generated standalone
submission repository. The final archives and relocated checks are ready.
The maintainer must review the candidate, authorize the signed-off commit and
publication target, and submit through the organizer's announced form.
Registration is recorded; an external submission is not. The deadline remains
2027-01-18 and the internal target 2027-01-14. Generated GDS/logs/build trees
belong in reproducible local packages or authorized release assets, not source
commits. The AI-use disclosure also awaits maintainer review.

## Final local artifacts

- [Candidate review archive](../../build/asic/axpe-submission-final-2026-10-11.tar.gz) — SHA-256 `b0da965720ad3cac896cdb0b7a416ae1b55a2243e2ecafd5cb20d4a81a26e377`; 234 files, 6374151 bytes. Extracted consistency/portable validation passes.
- [Source-only publication archive](../../build/asic/axpe-public-source-final-2026-10-11.tar.gz) — SHA-256 `80e3874c9c17bfb0eaad389cbe7f5dc775b5bac9dd4357fa784978ea719feaf6`; 88 files, 173763 bytes. Extracted consistency/portable validation passes.

The final candidate keeps 226 supplied files byte-identical to the relocated
package that passed all 24 suites; the seven changed files contain documentation,
compact evidence and export metadata. Hardware, payloads, peers, formal jobs
and portable validation tools are unchanged. The original 2026-10-10 review
archive remains at its recorded SHA-256. See
[`axpe-package.json`](../../research/benchmarks/axpe-package.json) for artifact
manifests, test receipts, extraction checks and the requirement-by-requirement
local completion audit. These archives are local preparation, not published
submission repositories. No commit or push was made.

## Signed-off commit preparation — 2026-10-12

The maintainer has authorized a local DCO-signed-off commit of these changes.
The commit recording this checkpoint is the review target; authorization to
commit does not record approval of the Review cards. Publication and submission
remain pending. Generated archives and raw build outputs stay outside Git.
Explicit root ignore exceptions now retain the runtime manifest and all three
supplied clock profiles in a fresh source checkout.

All 14 smoke stages pass from the staged source snapshot, alongside focused
model checks and selected-profile export/check. Verification and registry
gates also pass. The initial temporary archive permission mismatch and its
correction are retained in the precommit receipt in `axpe-package.json`.
