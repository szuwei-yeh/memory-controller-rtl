# Reproduce the current portfolio snapshot

Use a fresh checkout from your repository remote, then run the commands below
from its root. No existing `build/`, private notes, remote-server account or
licensed library is needed for local RTL verification. The
[five-minute review](portfolio-review.md) explains the design and measured result.

## Inspect published evidence first

```sh
make check-evidence
```

This uses Python's standard library and Git. It checks current RTL hashes,
published report hashes, measured area/setup/hold numbers and verification
summaries. It reads committed evidence; **it does not rerun EDA tools**.
Expected output includes a final `PASS`, +0.000038 ns setup at 3 ns, and the
the original eight/two hold endpoints and zero endpoints after mapped hold repair
at 3/4 ns. A source edit should invalidate
the snapshot check until corresponding evidence is produced.

## Simulate and check equivalence

The tested workstation uses Python 3.13.0, Verilator 5.046, a C++ compiler/make,
and Yosys 0.68+post (`c12172fbae8af5e20f6fb52e3d4e92d56ed587b6`). Python 3.10+
and a Verilator supporting `--binary --timing --assert` are the code's stated
requirements; the audit below verifies the listed toolchain, not every version.
Keep `python3`, `verilator`, `yosys`, and the Yosys ABC executable on `PATH`.

Run these sequentially. Individual builds and regression manage their own
parallel jobs; separate concurrent make invocations can share build directories.

```sh
make lint
make smoke
make test
make regress SEEDS=5 N=1000 JOBS=2
make formal-parallel
make compare-parallel
```

| Command | What a successful run establishes |
|---|---|
| `lint` | Verilator lint completes without errors |
| `smoke` | One default run for each policy |
| `test` | 42 integrated workload/reset/corner cases plus model, scheduler and response unit checks |
| Short `regress` | 15 runs and 15,150 accepted requests, including directed preludes |
| `formal-parallel` | Nine Q=1/3/16 × policy equivalence configurations pass with no unproven cells |
| `compare-parallel` | 120 baseline/current complete event-trace pairs match |

Equivalence uses a committed, hash-checked reference scheduler and checks the
six unchanged modules. It needs Yosys but not SymbiYosys or Git history before
the current checkout. It is the matched-node proof described in the
[verification plan](verification-plan.md).

For the full published regression workload, run `make regress SEEDS=100 N=10000
JOBS=4`: 300 runs, 3,003,000 accepted requests. This replaces the local regression
summary. The fresh-checkout audit uses the shorter sample; the full workload's
source-matched evidence is retained in the final optimization report.

## Run the property checks

If `sby` is already installed, `make formal` uses it. The audited isolated
dependency setup is:

```sh
mkdir -p .tools
git clone https://github.com/YosysHQ/sby.git .tools/sby
git -C .tools/sby checkout b1a1e98cba941ec8433f8dc27f416cd7bb7f14be
python3 -m venv .tools/venv
.tools/venv/bin/pip install click==8.5.0
make formal
```

The runner falls back to this `.tools` checkout and Python environment if no
installed `sby` is found. ABC supplied with Yosys provides BMC3 and PDR; Z3 is
not required. Expected results are `PASS` for strict, frfcfs, aging, bank and
progress: three depth-12 BMC tasks and two reduced unbounded control proofs.
The tool clone and environment are ignored dependencies, not project source.

## Optional commands and historical reports

`make synth-local-sanity` performs generic Yosys synthesis. It is not mapped
ASIC area or frequency evidence. `make lab-bundle` creates an allowlisted local
archive for a lab flow; it uploads nothing and excludes notes and testbenches.
`make perf` runs the documented workload/ready-rate study and writes local
metrics; it does not establish physical DDR bandwidth.

**`make report` is a historical publishing command.** It rewrites
`docs/results.md`, `docs/traces.md` and public performance artifacts using local
test/regression/performance/formal outputs. It is not part of this snapshot's
review checklist. Use it only in a separate historical checkout with that
experiment's complete inputs; running it after a short regression can replace
the frozen report with a different sample. Plot dependencies are optional and
listed in `scripts/requirements-plot.txt`.

The earlier `formal-command-mask` / `compare-command-mask` targets use an older
compact-mask baseline. Their measured experiment is recorded at `9d40e16`.
Use the `*-parallel` targets for the current implementation. Historical DC
collectors may require ignored raw runs as well as their exact source snapshot;
their published reports can be inspected without rerunning those collectors.

## What local reproduction does not include

New mapped PPA requires licensed Synopsys DC and the matching GSCL45nm library
configuration. Neither the library nor mapped DDCs are redistributed. See
[ASIC setup](asic-results.md) and the
[RTL experiment](experiments/parallel-arbitration-experiment.md) and
[mapped hold repair](experiments/hold-repair-experiment.md) for flow, source hashes,
corner and constraint details. The local reproduction commands do not rerun DC,
PrimeTime or a physical-design flow. The repaired Q16/3 ns and 4 ns mappings pass
setup and hold; library capacitance violations remain, and the +0.038 ps 3 ns
setup margin is not robust signoff.

## Fresh-checkout audit

The audit starts from commit `0be62b7a30882165fc3e2bcef804db76e207468f` on the
same macOS workstation, using a fresh Git clone with no copied build cache,
repo-local tools or private notes. The pinned SymbiYosys dependency is freshly
cloned and its Python environment installed separately. System-installed
Python, Verilator, Yosys/ABC, compiler and make are reused; this is **not** a
fresh OS/container or an executed Linux CI run.

<!-- audit-results -->
**PASS.** The clean checkout completed the following checks. The machine-readable
[audit summary](../results/portfolio_audit/summary.json) records tool versions,
RTL and execution-input hashes, command exit codes, counts and raw-log hashes.

| Check | Result |
|---|---|
| `make lint` | PASS |
| `make smoke` | 3 runs; 3,030 accepted requests |
| `make test` | 42 integrated cases plus model/scheduler/response checks |
| `make regress SEEDS=5 N=1000 JOBS=2` | 15 runs; 15,150 accepted requests |
| `make formal-parallel` | All 9 configurations PASS |
| `make compare-parallel` | 120 identical pairs; 240 simulations |
| Pinned dependency setup + `make formal` | All 5 tasks PASS |
| `make synth-local-sanity` | PASS; no inferred latches |
| `make lab-bundle` | PASS; no private notes, testbenches or licensed library files |

The tracked checkout remained clean after execution. The closeout adds
documentation and `make check-evidence`; it does not change RTL or existing
validation implementations. That additional evidence checker also passes and
its source hash is recorded separately. The 300-run regression was not repeated
in this audit; its earlier source-matched result remains published.
<!-- /audit-results -->

Local simulation/build logs and run manifests remain under `build/`. In normal
use the tools append to ignored `local_notes/實驗日誌.md`; the audit sets `CI=true`
to suppress notebook creation inside its clean clone. Public results contain
sanitized summaries, not local absolute paths or licensed tool inputs.
