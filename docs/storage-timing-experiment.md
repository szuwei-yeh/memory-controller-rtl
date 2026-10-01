# Storage timing and free-slot availability experiment

This is the standalone storage study. The subsequent
[command-mask experiment](command-mask-optimization.md) freshly measures and
selects a combination with fixed-slot storage; the standalone outcomes below
remain unchanged.

**Neither alternative is adopted; production RTL retains the compact mask.**
Fixed-slot writes eliminate all 34 internal 3 ns setup failures and reduce hold
failures from 17 to 2, but worsen the overall setup slack from −0.116465 to
−0.157969 ns. Separating free-slot availability also worsens overall setup and
introduces more internal failures. Both candidates fail the predeclared screen.

This experiment follows the [compact candidate-mask revision](candidate-mask-optimization.md).
It investigates the new internal setup failures at Q16/3 ns and the reset hold
regression at Q16/4 ns. Baseline source hashes identify the exact compact RTL;
the two reused mapped points are not fresh baseline compiles.

## Diagnosis on the existing mapped design

Read-only queries reopen the original compact-mask DDCs without compiling,
reapplying constraints, or changing the technology library. Area and worst hold
slack match the original reports. The query script, DDC, RTL, configuration, and
SDC hashes are retained with the published evidence.

The worst internal 3 ns setup path is **`occupied[0] → req_ready → done[13]`**.
It stays inside the transaction table; this is a free-slot allocation control
path, rather than a path from the returning read-data input.

| Point | Arrival / requirement (ns) |
|---|---:|
| Occupancy register clock-to-Q | 0.145385 |
| `table_i/req_ready` arrival | 1.844668 |
| `done[13]/D` arrival | 2.852526 |
| Setup required time | 2.841594 |
| Setup slack | −0.010932 |

The path spends 1.844668 ns reaching availability, followed by 1.007858 ns in
the accepted-request and completion-update logic. The related read-data path
ends at bit 417 (slot 13, bit 1), with arrival 2.832423 ns and setup slack
−0.000036 ns. All 34 internal setup-violating endpoints in the original 3 ns
mapping belong to read-data (32) or completion (2) registers.

At 4 ns, the worst hold path is **`rst → NOR3X1 → banks_i/wr_reg[0][0]/D`**.
The arrival is 0.041259 ns, required hold time 0.091935 ns, and slack
−0.050676 ns. Reset remains a constrained synchronous input: minimum input delay
is zero and clock uncertainty is 0.1 ns. Faster setup logic cannot by itself
solve a path that is too short. This experiment keeps those constraints and all
reset semantics intact.

## Two independent RTL hypotheses

Only `mc_transaction_table.sv` changes relative to the compact baseline. No
pipeline, state, storage capacity, or cycle latency is added.

- **`fixed_slot`:** replace dynamic-index writes to `read_data` and `done` with
  comparisons and constant slices at each slot. Preserve update priority:
  retirement, allocation, write issue, then read return (highest priority).
  Keep the original free-slot search and all other state updates.
- **`free_valid`:** calculate availability as `~(&occupied)` independently of
  the slot encoder. A reverse index loop retains lowest-numbered-free-slot
  priority, including a zero output when all slots are occupied. Keep the
  original dynamic-index state updates. This isolates the availability cone
  from the fixed-slot experiment.

Before running either experiment, the adoption screen required functional
equivalence, no worse 3 ns worst setup slack, fewer 3 ns internal setup failures,
a 4 ns setup pass, no worse hold slack **or count at either point**, and at most
5% additional 4 ns area. A failed screen means retaining the compact baseline;
improving one favorable metric is insufficient.

## Matched measurements

All points use Q=16, FR-FCFS+aging, DC R-2020.09-SP4, GSCL45nm typical at
1.1 V/27°C, identical SDC and cycle timing parameters, and
`compile -map_effort medium`. Four new isolated runs measure the two alternatives
at 3/4 ns. Exact source/flow/configuration hashes accompany every point. Targets
are separate mappings, not clock sweeps of one fixed netlist.

<!-- measured-table -->

| Variant | Target (ns) | Area (µm²) | Setup slack (ns) | Setup endpoints | Internal setup endpoints | Hold slack (ns) | Hold endpoints |
|---|---:|---:|---:|---:|---:|---:|---:|
| compact_baseline | 3 | 73,105.21 | -0.116465 | 84 | 34 | -0.002538 | 17 |
| compact_baseline | 4 | 67,729.84 | +0.000518 | 0 | 0 | -0.050676 | 39 |
| fixed_slot | 3 | 72,872.90 | -0.157969 | 50 | 0 | -0.000659 | 2 |
| fixed_slot | 4 | 67,494.26 | +0.000827 | 0 | 0 | -0.050676 | 29 |
| free_valid | 3 | 73,426.68 | -0.129980 | 110 | 60 | -0.002538 | 9 |
| free_valid | 4 | 67,969.66 | +0.000852 | 0 | 0 | -0.050676 | 29 |

<!-- /measured-table -->

<!-- decision -->

`fixed_slot` removes all 32 read-data and two completion setup failures, leaving
50 command-output setup failures. At 3 ns its area falls 0.32%, hold slack
improves to −0.000659 ns, and only two hold endpoints fail. However, worst setup
slack regresses by 0.041504 ns and setup TNS worsens from −5.655077 to −7.753271 ns.
The 4 ns area falls 0.35%; setup passes and hold count falls from 39 to 29, but
worst hold remains −0.050676 ns. The worst-setup criterion fails despite these
internal-path and hold improvements, so this version remains an experimental
snapshot rather than the production implementation.

`free_valid` leaves 110 setup failures at 3 ns: 50 command outputs plus 48
write-data and 12 tag bits. The original read-data/completion failures disappear,
but the internal count rises from 34 to 60. Worst setup is −0.129980 ns and TNS
is −6.608304 ns, both worse than the compact baseline. Its 3 ns hold count falls
to nine with unchanged worst hold slack; 4 ns has 29 hold failures and unchanged
worst hold slack. Area increases 0.44% at 3 ns and 0.35% at 4 ns. It fails both
the worst-setup and internal-setup-count criteria.

All four new runs retain 1,974 sequential cells. Neither hypothesis is a
uniform timing improvement. Changing the RTL also changes the global mapped
implementation, so the local simplification does not guarantee a shorter
controller critical path. The next experiment should target the command-output
selection chain while continuing to measure the internal allocation paths and
hold. Fixed-slot storage remains a possible component of a later combined trial;
its benefit cannot be assumed to add linearly to another optimization.

No production RTL is changed by this study. Each trial has five passing
integration-equivalence configurations; neither underwent the full simulation
release regression because neither passed the timing adoption screen. The
compact baseline retains its separately recorded regression evidence.

<!-- /decision -->

## Validation and reproduction

Each isolated candidate passes whole-controller matched-node SAT equivalence
against the compact baseline at Q1/aging, Q3/all three policies, and Q16/aging.
The proof uses flattening, memory mapping, identical-cell merging, and
`equiv_simple -undef -short`; every equivalence cell must be proved. Corresponding
state shares synchronous reset. This is implementation equivalence, not an
independent proof of arbitrary functionality or all parameter combinations.

The frozen seven-file baseline hashes are in the summary. Reconstruct that
baseline from commit `12db399` plus the three files in
`results/candidate_mask/variants/compact_mask/rtl/`. Reconstruct either
trial by substituting its published transaction-table file into that baseline;
the other six RTL files must remain identical. The proof-script generator is
`proof_script()` in `scripts/candidate_mask_equiv.py`. Use the two isolated source
directories, the seven-file `synth/rtl_files.f` manifest, and the five Q/policy
combinations above. For example, after preparing `build/storage_repro/before/rtl`
and `build/storage_repro/after/rtl` with those exact sources, generate and run the
Q3 FR-FCFS proof:

```sh
python3 - <<'PY'
from pathlib import Path
import subprocess
import sys
sys.path.insert(0, 'scripts')
from candidate_mask_equiv import proof_script
root = Path('build/storage_repro').resolve()
files = Path('synth/rtl_files.f').read_text().split()
script = root/'proof.ys'
script.write_text(proof_script(root/'before', root/'after', files, 3, 'frfcfs'))
subprocess.run(['yosys', '-Q', '-T', '-s', str(script)], check=True)
PY
```

Repeat for the other Q/policy combinations listed above. On the authorized lab
environment, run each trial with:

```sh
python3 scripts/synth.py dc --lab --policy frfcfs_aging --point 16 3
python3 scripts/synth.py dc --lab --policy frfcfs_aging --point 16 4
```

The read-only `synth/dc/analyze_storage_paths.tcl` requires `MC_LAB_CONFIG`,
`MC_MAPPED_DDC`, `MC_ANALYSIS_TOP`, and `MC_ANALYSIS_OUT`. It reports focused
read-data/completion setup and hold paths. Focused reports can include multiple
paths to the same endpoint; violation counts come from the complete constraint
reports, not the number of printed path alternatives.

`python3 scripts/storage_timing_report.py` collects the retained local experiment
directories `build/storage_opt/` and `build/free_valid_opt/`, validates provenance,
and applies the predeclared screen. Raw logs, mapped netlists, site configuration,
and licensed library files remain private. Public reports redact the technology
library path and retain both raw and public report hashes.

- [Metrics CSV](../results/storage_timing/summary.csv)
- [Source hashes, adoption checks, proof scope, and complete metrics](../results/storage_timing/summary.json)
- [Focused baseline path queries](../results/storage_timing/analysis/)
- [Both trial RTL files](../results/storage_timing/variants/)
- [Mapped trial reports](../results/storage_timing/reports/)

All results remain typical-corner pre-layout measurements with ideal clocks and
no extracted interconnect. Hold and inherited zero-limit max-capacitance
violations are not waived. This study does not establish power, exact Fmax,
Q32 mapped performance, post-route timing, or signoff.
