# UCSB ASIC synthesis flow

The UCSB environment has been inspected; see [initial baseline evidence](ucsb-baseline.md)
for the exact prior-project provenance, setup, library, and measured run status.

## Transfer and setup

Locally run `make lab-bundle`. This creates `build/lab_bundle.tar.gz` from an
explicit allowlist: controller RTL, synthesis manifest, constraints, DC/PT scripts,
runner, and this guide. It does not upload anything. Simulation, formal harnesses,
workloads, local notes, and library files are excluded.

Copy that bundle to the authorized lab workspace, extract it, load the lab's
Synopsys environment, and create `synth/lab_config.tcl` from the example. Set
actual target `.db` paths, search paths, corner identity, and time/capacitance
unit conversion factors. Verify units against library reports before using the SDC.

```sh
python3 scripts/synth.py dc --lab --config synth/lab_config.tcl
python3 scripts/synth.py pt --lab --config synth/lab_config.tcl \
  --run build/synth/dc/frfcfs_aging_q16_5ns
```

For only the initial FR-FCFS with aging, Q=16, 5 ns point, add `--baseline`.
For one policy's ten-point sweep, use `--policy strict_fcfs`, `--policy frfcfs`,
or `--policy frfcfs_aging` without `--baseline`. The local
`scripts/dc_sweep.py` orchestrator runs these in three isolated server workspaces,
retrieves explicit per-run output lists, and appends each result to the private
notebook locally. It reuses the established SSH control connection and verified
baseline lab configuration; it never sends the notebook to the server.
The matrices share Q=16 at 5 ns, so the complete comparison has 30 distinct points.
Six-decimal setup/hold and constraint reports preserve small violations rather
than allowing display rounding to imply a pass. The SDC is unchanged.
On the inspected UCSB host use `/usr/bin/python3.11`; its default `python3` is 3.6.8.
The runner records the RTL, manifest, Tcl, SDC, configuration, and runner hashes.
DC's parameterized elaboration selects a specialized top name; retain that current
design rather than looking up the unspecialized `mc_top` name afterward.
The startup banner in `tool.log` records the DC version.

Optionally set `OPERATING_CONDITION` to an observed library corner and
`TARGET_LIBRARY_NAMES` to the internal library names. The flow explicitly selects
that condition and records loaded database units and nominal PVT attributes.
Do not copy another project's reset false-path exceptions: this controller's
synchronous reset is fully constrained.

`--lab` saves machine-readable experiment metadata without creating a private
notebook on the server. After retrieving the run outputs, append a Traditional
Chinese entry in the local notebook with actual commands, status, and results.
Do not upload the notebook to support this step.

After downloading the per-run result directories, use
`python3 scripts/import_lab_results.py build/lab_return` locally. This appends one
entry per actual DC/PT run and avoids duplicate imports. It does not turn tool
completion into timing closure or fabricate numeric results.

## Inputs and constraints

Only `synth/rtl_files.f` is analyzed, with mc_top as top and SYNTHESIS defined.
Every entry must be an immediate `rtl/*.sv` file. Each run records SHA-256 of all
RTL sources, configuration, command, elapsed time and result. Tool logs/environment
reports record DC version, library/corner and compile settings. Uncommitted RTL is
identified by hashes rather than pretending it corresponds to a committed revision.

One clock, 0.1 ns uncertainty, max/min input/output delay 1/0 ns, 0.1 ns input
transition, 10 fF output load. Synchronous reset remains constrained. There are no
false-path or multicycle exceptions. Convert ns/fF into library units explicitly.

Compile each point from RTL at fixed medium mapping effort. Three policies at Q=16
and periods 20/10/8/5/4/3/2 ns, plus Q=4/8/32 at 5 ns: 30 runs total. Policies,
library, corner, I/O assumptions, effort, and timing parameters must match across
comparisons. Mapped netlists/SDC, area, timing, QoR, references, constraints, and
design/timing checks are retained per run.

## Interpreting results

Tool completion is not timing closure. Inspect negative slack, constraint violations,
unconstrained endpoints, unresolved cells, sequential/combinational area, and the
ten longest paths. Explain dependency comparison, arbitration, response ordering,
and muxing contributions. Report area-versus-clock curves and the fastest **passing
tested** frequency. Do not estimate ASIC frequency from generic local Yosys cells.

PrimeTime is optional and consumes the mapped netlist/SDC with the same library.
Its reports include setup, hold, constraint violations, and analysis coverage.
Without placement/routing/extracted parasitics these are pre-layout estimates.
Changing controller clock period does not establish real DRAM timing compliance:
the illustrative cycle-valued memory timings need separate physical interpretation.
