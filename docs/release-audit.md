# v1.1 portfolio release audit

This release freezes the accepted controller and architecture. M8 changes only
public documentation and documentation-generation wording. RTL, testbench, formal
harnesses, scheduler behavior, SDC, and accepted measured results are unchanged.

## Evidence and claims

- Local summary: 300 randomized runs, 3,003,000 accepted transactions, 42
  directed/workload/reset/corner runs, plus separate model/scheduler/response checks.
- Formal: three depth-12 integrated BMC tasks; focused bank and reduced two-slot
  progress tasks use unbounded PDR. These do not prove every parameterization or
  the full-width data path unboundedly.
- Stability: 540 final-design and 60 historical paired experiments, 20 seeds.
  Random/50%-ready p99 increased consistently, while throughput and mean latency
  improved. Hot/cold and HOL address/operation patterns are deterministic across
  seeds; ready percentages are duty cycles, not independent random probabilities.
- ASIC: 30 distinct DC runs, 25 setup passes, zero reported unconstrained endpoints.
  At Q=16 the fastest tested setup-passing targets are 3 ns for Strict-FCFS and
  4 ns for both FR-FCFS policies. All tested depths pass setup at 5 ns.
- Figures and annotated traces derive from the same accepted seed-42 performance
  cohort; the separate stability report summarizes multiple seeds. ASIC CSV/JSON
  hashes matched their accepted verification manifest before publication redaction. Historical response-refill
  files describe the before/after experiment, not another current RTL revision.

## Reproduction boundaries

Run the README commands in order after installing the pinned dependencies in
[toolchain.md](toolchain.md). `make report` requires the preceding run summaries
and performance event traces; it rewrites derived public reports. Use a disposable
checkout to reproduce them while preserving accepted release artifacts.

The local release check uses an isolated Git snapshot and a fresh clone, with no
build cache copied in. The ignored `.tools` dependency paths point to the already
installed pinned SymbiYosys checkout and Python environment. This tests a clean
source/build checkout, not a fresh operating-system installation.

ASIC commands require UCSB credentials, the verified library/tool installation,
and a local lab configuration. The historical sweep orchestrator additionally
uses the authenticated SSH master and retained baseline configuration described
in the lab guide. They are not standalone local commands. Rebuilding ASIC reports
requires retained raw `build/dc_sweep/runs/` outputs, including full constraint
reports and transcripts; these are not all in the curated public report set.
PrimeTime is optional and was not executed. M8 does not rerun the accepted ASIC
sweep or change its constraints.

Historical response-refill reproduction requires the before-run snapshots and
comparison inputs described in that report. Current capacity tests can be run
independently. The multi-seed study regenerates its own simulation traces before
its reporting step. Archived measured data are retained unchanged in this release.

## Release validation results

The isolated checkout passed `make lint smoke test regress formal perf
synth-local-sanity report lab-bundle` with the default full regression settings:
300 runs and 3,003,000 accepted transactions, 42 directed/corner simulations,
all separate unit checks, all five formal tasks, and 48 performance experiments.
The generic Yosys check passed without changing RTL.

The complete 600-run stability reproduction also passed. Its per-seed CSV,
distribution CSV, summary JSON, verification JSON, and public report match the
accepted files byte for byte. The local summary JSON, performance PNG, and
annotated traces likewise reproduce exactly. With the retained raw DC run outputs
restored separately, ASIC summary CSV/JSON, the area/timing PNG, and the public
ASIC report also reproduce byte for byte. PDF containers may include fresh
creation timestamps; they are not used as byte-identity evidence.

All six current response-capacity metric sets reproduce exactly, including 5,000
consecutive handshakes at tCCD=1 for each policy. The response-refill comparison
reproduces its performance metrics, generic cell counts, and logic depth. Its
clean-checkout instructions now create the report-log directory explicitly; only
documentation and generated instruction text changed.

One audit setup attempt used an incorrect relative source path when restoring DC
reports and failed before copying; the absolute source path corrected it. No
verification, synthesis, or measurement change was needed.

## Git and privacy

At the end of the original M8 audit, the working repository had no tracked files
or commits. The subsequent publication step stages the audited public inventory,
creates the initial release commit and annotated v1.1 tag, and requires authenticated
GitHub access before any upload. See [publication privacy audit](publication-audit.md).
The release file inventory and checksums are recorded in the local audit artifacts.
The isolated reproduction snapshot commits only the explicit public inventory.

`local_notes/` is ignored and untracked. Public and lab archives use explicit file
allowlists; private notes, local tool installations, build caches, credentials,
and `synth/lab_config.tcl` are excluded. Notebook contents are never inputs to
report generation. All generated archive member lists are checked against their
allowlists before release. Public logging instructions mention the private path
but do not contain its entries.

## Limitations

The command protocol omits refresh, PHY/training, bursts, byte masks, ECC, and
many JEDEC constraints. Simulation responses/cycle are not physical DDR bandwidth.
Fixed-latency reads and finite synthetic workloads limit generalization. Aging
bounds command service under the stated reduced proof assumptions; consuming
responses requires eventual host readiness.

ASIC results use the inherited GSCL45nm typical library, ideal clocks, and no
extracted physical parasitics. Hold violations remain (14 at the accepted baseline;
6–259 across the sweep). All 186,081 reported sweep max-capacitance violations have
zero allowed load in the inherited library; this is documented, not waived.
Setup-only passes are not timing signoff. There is no post-layout or PrimeTime
claim and no exact maximum-frequency claim.

## Freeze disposition

**v1.1 is portfolio-frozen.** No optimization or new ASIC run is part of M8.
At M8 completion, all 394 pre-existing frozen source/specification/constraint/measurement
files matched the pre-audit SHA-256 snapshot. Publication subsequently redacts only
private provenance strings from reports; measured values and RTL remain unchanged. The public archive, exact file inventory,
file hashes, empty tracked-file list, Git status, and machine-readable audit are
local release artifacts under `build/release_audit/`. The pre-publication export was
`build/release_audit/memory-controller-rtl-v1.1.tar.gz`. It predates privacy redaction
and must not be uploaded. Publication uses the sanitized Git tree instead.
The archive's `release_manifest.json` lists every included public file and hash.
