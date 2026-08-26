# Generation 6 — Experience Becomes Memory

Status: **ACCEPTED**

## Thesis
Successful and failed Lab experience should compound automatically without becoming a second source of truth. Procedural memory is an evidence-backed index/hypothesis; immutable capabilities, workflows, graphs, evaluators, traces, and hashes remain authoritative.

## Designs considered
1. Merge procedural memory and regressions directly into the Capability Forge registry.
2. Keep a separate content-addressed experience layer and add only a narrow regression replay gate to Forge promotion.

Chosen: **#2**. It keeps authority boundaries explicit, makes memory replaceable/retirable, and preserves the 10-tool permanent MCP surface.

## Implemented
- `experience_memory.py`: sanitized episodes, Gen5 Forge episode import, held-out distillation, inspectable applicability retrieval, outcome tracking, ACTIVE/CANDIDATE/SUPERSEDED/RETIRED lifecycle.
- `regression_compiler.py`: immutable capability-I/O and command-exit regressions, best-effort structural minimization with explicit uncertainty, known-bad/known-good verification, promotion replay.
- `experience_loop.py`: memory-first planning, regression/anti-pattern retrieval, Forge reuse before Forge creation.
- Capability Forge r2: relevant ACTIVE regressions are a hard promotion gate.
- Benchmark + failure miner: quantitative retrieval/reuse/regression evidence and evidence-ranked Gen7 proposals.

## Benchmark target
Prove fewer external reasoning/authoring bytes, zero wrong-memory reuse on incompatible variants, avoided Forge creation, durable failure regressions, and unchanged containment/tool surface.
