# Execution targets and toolchains board

[All boards](README.md) · [Execution-target design](../execution-targets.md) ·
[Roadmap](../roadmap.md)

This board owns the work that makes atomiX useful across software execution,
architecture models, programmable hardware, and eventual silicon. All owners
are unassigned. AX-10 is part of M0 and comes after delivery card AX-01; the
generic ASIC dependency audit can start without a physical board. Its selected
competition execution now uses the official CMOS5L template because wrapper,
pin, memory-write and full-flow assumptions are part of the question being
audited.

| Card / outcome | Priority | State | Depends on | First reviewable slice |
|---|---|---|---|---|
| [AX-10: native CPU and RTL execution adapters](../design-checklist.md#ax-10) | P0 | Done | AX-01 | Define the adapter contract and implement one native integer workload against the shared oracle, without invoking FPGA or RISC-V tools |
| [AX-12: ISS and emulator adapters](../design-checklist.md#ax-12) | P1 | Done | AX-10 | Separate aXsim/QEMU adapters run one exact ELF fixture; QEMU-required conformance covers refusals, bounds, and failed replay |
| [AX-11: compiler/runtime and hardware co-design experiments](../design-checklist.md#ax-11) | P1 | Done | AX-10, AX-02, AX-03 | GCC `-O0`/`-O2` and a complete SIMT-algorithm/lane-count control passed exact oracles with replayable identities |
| [RX-08: ASIC portability dependency audit](../research-checklist.md#rx-08) | P0 | Active | Existing RTL and manifests; official competition template | Executed by [PE-01, PE-14 and PE-02](protocol-emulator.md): pin the official wrapper, post-fabrication programming path, writable memory semantics and technology dependencies, then run the smallest integrated design through the 6x4 flow |
| [AX-13: external accelerator backend](../design-checklist.md#ax-13) | P2 | Next | AX-10, AX-03; a supported device/runtime for execution | Inventory available compute devices and choose one workload/adapter only when an actual target is accessible |
| [RX-09: technology-mapped implementation feasibility](../research-checklist.md#rx-09) | P0 | Next | RX-08; IHP-Open-PDK and the Tiny Tapeout CMOS5L flow | Executed by staged [PE-10](protocol-emulator.md): early full-flow P&R when loader, writable memory and core first compose, then final P&R with actual area and timing after the mandatory protocols close |

## What keeps this work focused

AX-10 proves portability early using the native host already needed for
development. AX-12 makes existing functional platforms available through the
same experiment path. AX-11 lets the platform explore both software and
hardware choices, while keeping which variables changed visible in the result.

AX-13 can select a GPU or another accessible accelerator through its own
backend; it does not mandate CUDA, a specific vendor, an NPU purchase, or a
remote service. If access is absent when its execution slice is pulled, mark
that slice Blocked. CPU fallbacks can be separately identified candidates.

RX-08 and RX-09 earn an ASIC feasibility decision. Existing Primer limits stay
local to those profiles; they do not size host experiments or future technology
targets.

As of 2026-09-17 both cards have a concrete vehicle: `axpe`, on the
[protocol emulator board](protocol-emulator.md). The Jane Street CMOS5L
competition supplies what these cards previously lacked — a selected block, an
accessible PDK and flow, a fixed area and timing budget, and a deadline. That
changes how the work is executed, not what it may claim. A place-and-route
result remains a place-and-route result; foundry selection and any fabrication
decision keep their own prerequisites, and submitting a design to a shuttle is
not a silicon claim. Nothing taped out exists until it returns measured.

Current commands remain in [workflow.md](../workflow.md). New adapters must
add focused conformance checks and appropriate suite coverage before closure;
the existing simulator or FPGA suite cannot certify an unimplemented backend.

## Priority decisions

- 2026-09-17: promoted RX-08 to P0 for the competition lane and expanded its
  dependency map to include the runtime loader and writable instruction store.
  An instruction-memory footprint without an after-fabrication write path does
  not answer the competition's portability question.
- 2026-09-17: split RX-09 execution into an early integrated hardening run and
  final closure rather than waiting for finished firmware to discover wrapper,
  macro, clock-tree or routing failures.

- 2026-09-10: broadened the product to hardware/software co-design. Added a
  native CPU adapter to the first milestone so FPGA independence is exercised.
- 2026-09-10: opened ASIC feasibility as staged research and retained physical
  implementation, sign-off, and manufactured-device evidence as distinct gates.
- 2026-09-10: closed AX-10 with three adapters -- native host, RTL role, and
  RTL SoC -- behind one boundary in `tools/execution/`. AX-12 becomes a matter
  of adding aXsim and QEMU to that map rather than of designing an interface.
- 2026-09-12: closed AX-12 with separate aXsim retired-instruction and QEMU
  guest-counter domains. One ELF and exact checksum prove functional agreement;
  no QEMU counter is ranked as an ISS or RTL cycle, and missing QEMU never falls
  back to aXsim.
- 2026-09-12: closed AX-11 with a six-candidate SAXPY experiment. Compiler
  settings are separate executable identities, and the complete algorithm by
  lane-count control records a negative strength-reduction result without
  mixing native elapsed time with deterministic RTL cycles.
