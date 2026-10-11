# AI use and review

AI coding assistants have contributed to axpe. The project records work by
Claude and OpenAI Codex in its development notes and commit trailers. Their
use includes architecture and ISA discussion, implementation and debugging,
assembler/model/test development, formal harnesses, physical-flow experiments,
evidence collection and documentation. This is a project-level disclosure;
the repository does not provide a complete prompt archive or per-line model
attribution.

The maintainer sets the project scope, hardware constraints and submission
decisions. Assistants run tools and prepare changes and evidence for review.
AI-generated explanations are not verification results: the included receipts
identify actual commands, tool versions, reproducible inputs and hashes.
Failed experiments and excluded proof domains remain in those records.

The C model, protocol peers and RTL have shared author/tool provenance. The
peers are independent implementations of protocol rules, not independently
authored third-party certification. Differential agreement therefore has
shared-error risk. The ISA source, independent timing counters, reachable
formal witnesses, deliberate mutation counterexamples, extracted STA and
layout checks provide additional checks with distinct scopes; none establishes
measured hardware operation.

Commit-pinned maintainer reviews of the ISA, RTL, proof assumptions, ECO recipe
and submission candidate are still owed. This draft does not claim they have
occurred. The maintainer must review this disclosure for completeness before
publishing or submitting the entry. See [verification](verification.md) for
the methods, failures and remaining limits.
