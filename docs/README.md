# Documentation guide

Start with [the five-minute review](portfolio-review.md), then use
[the reproduction guide](reproduce.md) to inspect or run the current snapshot.

## Design and verification

| Document | Purpose |
|---|---|
| [Architecture](architecture.md) | Module responsibilities, scheduling and design decisions |
| [Protocol and timing](protocol-and-timing.md) | Interface, ordering, reset and timing contract |
| [Verification plan](verification-plan.md) | Test coverage, formal scope and limitations |
| [Annotated traces](traces.md) | Examples of command scheduling and aging |

## Published results

These documents describe their recorded revisions. Use each document's source
identity and limitations when comparing it with current RTL.

| Document | Purpose |
|---|---|
| [Local results](results.md) | Frozen v1.1 simulation and response-path measurements |
| [Performance stability](performance-stability.md) | Multi-seed distributions and backpressure tradeoffs |
| [ASIC results](asic-results.md) | Frozen v1.1 mapped area/timing sweep and synthesis setup |
| [Optimization experiments](experiments/README.md) | Later implementation changes, measurements and rejected alternatives |

The current implementation's experiment is
[parallel command-class arbitration](experiments/parallel-arbitration-experiment.md),
followed by [mapped hold repair](experiments/hold-repair-experiment.md) and
[setup-margin improvement](experiments/setup-margin-experiment.md).
Machine-readable summaries, reports and source snapshots live in
[`results/`](../results/README.md). Command-line tools are listed in
[`scripts/`](../scripts/README.md).

## Where new documents belong

- Keep design contracts, reproduction instructions and published overview documents here.
- Put optimization hypotheses, timing diagnoses and paired experiments in `experiments/`.
- Put editable SVG diagrams used by the README and guides in `figures/`.
- Keep local interview notes and experiment journals in ignored `local_notes/`.
- Put generated traces and working reports in ignored `build/`; publish selected evidence in `results/`.

The two short experiment pages at this level preserve older address-sharing and
parallel-arbitration references. Edit their documents in `experiments/`.
