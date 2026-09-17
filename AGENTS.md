# atomiX agent instructions

## Current focus — CMOS5L protocol emulator, until 2027-01-18

**This section is temporary and is removed once the competition closes.** It
narrows what to work on. It does not suspend any rule below it; the mission
constraints, evidence rules, and Git safety rules apply to this work unchanged.

The project's whole work-in-progress limit belongs to `axpe`, a timed-ISA
protocol emulator entered in the Jane Street open-source CMOS5L ASIC
competition. Read [`docs/protocol-emulator.md`](docs/protocol-emulator.md) for
the design and [`docs/boards/protocol-emulator.md`](docs/boards/protocol-emulator.md)
for the card queue; pull from that board unless asked otherwise.

- **M0 delivery work is paused, not abandoned.** No card is withdrawn and no
  evidence is invalidated. AX-04 stays pullable only because it needs two people
  who are not the implementer, so it costs this lane nothing.
- `axpe` executes [RX-08](docs/research-checklist.md#rx-08) and
  [RX-09](docs/research-checklist.md#rx-09). It does not create a parallel ASIC
  track, and it does not license a silicon claim: submitting to a shuttle is not
  fabrication, and nothing taped out exists until it returns measured.
- The competition is judged on unique functionality **and on verification
  methodology**. Evidence discipline is part of the deliverable here, not
  overhead on it. Record gaps, timing violations, and failures as found — a
  submission that states its own limits scores better than one that hides them.
- The deadline is external and fixed. When a card slips, take scope out of a
  later card rather than time out of the submission.

### Team

Three parties work this repository during the competition: the maintainer,
Claude, and Codex. More than one agent is therefore active by default, so
`gator-tools/skills/multi-agent-coordination/SKILL.md` applies to this work
rather than being reserved for exceptional cases. Claim before you edit, and
keep claims, reviews, and design questions in `.git/multi-agent-coordination/`.
Two agents silently editing the same RTL or the same ISA table is the failure
this lane can least afford.

## Mission and constraints

- Keep atomiX a replaceable, component/profile-driven hardware/software
  co-design platform. RISC-V is the reference machine; FPGA is one execution
  target. Keep native software, simulation/emulation, external accelerators,
  and future ASIC targets expressible through their own contracts and evidence.
  Do not hard-wire an ISA, vendor flow, board, accelerator, or evolution policy
  into a generic interface when a manifest/profile boundary can express it.
- Preserve the immutable management shell, UART loader, isolation, watchdog,
  oracle, provenance, and rollback boundaries for Live FPGA work.
- The only physically available board is the Tang Primer 25K Dock. Never turn
  simulation or synthesis results for another board into a physical claim.
- Tang Primer main RAM is 32 KiB. Keep `kernel-evolve-small`, `-mid`, and
  `-large` independently selectable and enforce their existing fit gates.
- A capacity, limit, or name that a build could reasonably want to change is a
  profile knob, not a literal. Put it where its owner is: a component's own
  `parameters` in its manifest (with a default and a `doc`) if a component owns
  it, a profile `setting` if the kernel does. Then make it *reach* the build,
  check its bounds where they are known, and test at a non-default value --
  `make -C sw/kernel check-abi-torture-small` is the pattern. A knob that is
  declared but not wired, or wired but never exercised, reads as configurable
  and is not; that is worse than an honest constant, because it fails silently.
  See `skills/atomix-development/SKILL.md`.
- Never make software part of a bitstream's identity. Adding an example, game,
  or kernel must not require re-synthesis or re-open a board claim: synthesize
  the loader bitstream once and ship programs as runtime payloads over it. The
  baked `RAM_INIT_FILE` path is for first bring-up only. See
  `skills/atomix-development/SKILL.md`.

## Start here

- Use `docs/workflow.md` as the command authority.
- Use `docs/design-checklist.md` and `docs/research-checklist.md` to select and
  update work. Adaptive reconfiguration details live in `docs/live-fpga.md`.
- Use `docs/tangprimer25k-bringup.md` for the lab procedure and
  `docs/achievements/tangprimer25k.md` for physical results.
- For normal implementation/research work, read and follow
  `skills/atomix-development/SKILL.md`. For physical Tang Primer work, also read
  `skills/tang-primer-lab/SKILL.md`.
- When more than one agent works this repository at the same time, read
  `gator-tools/skills/multi-agent-coordination/SKILL.md` and coordinate through
  it. It is a submodule: `git submodule update --init --recursive` if that
  directory is empty. Claims, reviews, and design questions live in
  `.git/multi-agent-coordination/` here, not in the submodule. Do not use it for
  ordinary single-agent work.

- Tool version requirements are explicit and single-sourced in
  `tools/requirements.json`: which versions are *supported* (accepted without
  comment), which are *tested* (actually run, with the evidence named beside
  each), and which are known-bad and why. Never state a version requirement in
  prose, a `?=`, or a shell script instead -- those are what let "Verilator 5
  fails to elaborate role.loopback" survive years past the release it was true
  for. Widen `tested` only by running the evidence named beside the tool and
  recording the version; then `make requirements` regenerates the tables in
  `docs/dependencies.md`, and `make requirements-check` fails when host or docs
  drift from the file.

## Verification and evidence

- Run the narrowest relevant test first, then `make verify-smoke` before a
  completed change. `make nightly-integrated` is the broad scheduled suite.
- Keep simulator, synthesis/P&R, and physical-board evidence explicitly
  separate. Record failures as well as passes; never infer a hardware pass.
- Store reproducible inputs, commands, hashes, compact JSON evidence, and
  benchmark summaries. Do not commit generated build trees, bitstreams, logs,
  or an `artifacts/` directory.
- Keep content-addressed Live FPGA records valid with `make registry-check`.

## Hardware and Git safety

- Program FPGA SRAM only. Never run `make flash` or `openFPGALoader -f` without
  explicit user approval in the current turn.
- Preserve user changes. Avoid destructive Git operations.
- Sign off every commit: `git commit -s`, which appends the `Signed-off-by:`
  line the DCO in `CONTRIBUTING.md` requires. It applies to project commits, not
  only to outside contributions -- a contribution rule the maintainer does not
  follow is a rule no contributor will follow either, and sign-off cannot be
  added to history after the fact. Keep the `Co-Authored-By:` trailer as well;
  they answer different questions (who certifies the right to submit, and who
  wrote it).
- Work directly on `main`. Never commit or push unless the user explicitly asks
  in the current turn; earlier authorization is one-time only. Do not open PRs
  or create feature branches unless the user changes this policy.
