# Experiments

This folder is for Memorycore research branches that are not part of the MVP.

Experiments can be useful, but they should not be treated as production architecture until tested.

## Current experiment tracks

### `glyph-memory/`

Theoretical symbolic compression track.

Core idea:

- 7x7 ASCII-style grid
- 2x2 quads encode concepts through a codebook
- row 7 acts as a detail or metadata anchor
- stored beside readable memory, never instead of it

Status: theoretical prototype only. Not validated. Not part of the MVP.

### `swarm-blackboard-memory/`

Experimental multi-agent memory coordination track.

Core idea:

- planner/manager
- scouts/foragers
- specialist workers/nanoagents
- verifier/critic
- shared memory/blackboard
- final output

Main rule: decentralized sensing and reasoning, centralized state, memory, permissions, and audit.

Status: experimental. Not part of the MVP.

### `agent-lineage-simulation/`

Simulation-only branch for studying bounded agent lineage, evaluation history, mutation records, failures, and containment-policy memory.

This branch is for toy models, simulations, formal threat modeling, and defensive governance design. It should not include operational self-replication, persistence, evasion, or unauthorized spreading.

Status: simulation/research only.

### `lisp-mojo-memory-language/`

Research branch for a possible hybrid language concept where Lisp-style symbolic control defines memory rules and Mojo-style performance handles ranking, scoring, deduplication, vector operations, and compression benchmarks.

Status: language concept only. Not required for the MVP.

## Graduation rule

An experiment can move toward core only after it has:

1. a clear problem it solves,
2. a small working prototype,
3. evaluation results,
4. failure cases documented,
5. no dependency on unverifiable or lossy memory reconstruction,
6. no replacement of readable canonical memory text.
