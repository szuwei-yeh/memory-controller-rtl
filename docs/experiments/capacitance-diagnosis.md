# Diagnose the inherited zero-limit capacitance violations

**Finding:** all **5,504 / 5,334** capacitance violations at Q16/3 ns and 4 ns
come from five cell types with **explicit `max_capacitance : 0` in the supplied
Liberty source**. The loaded DB and constraint reports agree. Every affected net
has positive receiver-pin capacitance and zero modeled wire capacitance;
most have just one receiver. This identifies the rule's origin and load sources,
but does **not** establish the library author's intended corrected limits.

This is a read-only diagnosis of the latest
[setup-margin mappings](setup-margin-experiment.md). No library limit, load,
SDC, RTL or mapping was changed, and no capacitance repair is claimed.
The [summary](../../results/capacitance_diagnosis/summary.json),
[numeric library metadata](../../results/capacitance_diagnosis/library_metadata.json),
[3 ns load accounting](../../results/capacitance_diagnosis/reports/q16_3ns/load_accounting.csv)
and [4 ns load accounting](../../results/capacitance_diagnosis/reports/q16_4ns/load_accounting.csv)
retain source identity and account for every violating net.

## Source definition, DB interpretation and units

The associated `gscl45nm.lib` contains 31 cells and 33 output pins. All 33
output limits agree with the loaded `gscl45nm.db` within the DB query's
six-decimal precision. Seven output limits are explicitly zero:

| Output pin | 3 ns violating drivers | 4 ns violating drivers |
|---|---:|---:|
| AOI21X1/Y | 328 | 337 |
| AOI22X1/Y | 1,553 | 2,049 |
| NAND2X1/Y | 1,330 | 1,145 |
| NAND3X1/Y | 1,745 | 1,753 |
| NOR2X1/Y | 548 | 50 |
| DFFSR/Q | 0; unused | 0; unused |
| TBUFX1/Y | 0; unused | 0; unused |
| **Total** | **5,504** | **5,334** |

The source declares `capacitive_load_unit (1,pf)` and `time_unit : "1ns"`.
DC reports a capacitance unit of **1,000 fF** and a time unit of **ns**, matching
the retained lab configuration. Thus 0.010104 library units is 10.104 fF,
not 0.010104 fF. Multiplying by a unit conversion cannot turn the zero limit
into a positive allowance. There is no `set_max_capacitance` command in the
unchanged exported SDC, and no dynamic `max_cap` group overrides these limits.

The [Synopsys Liberty reference](https://people.eecs.berkeley.edu/~alanmi/publications/other/liberty13_03.pdf)
(§2.4.5 and §4.4.1) defines the capacitance unit and the output pin's maximum
total capacitive load as separate attributes. An output pin's own
`capacitance : 0` is also separate from its `max_capacitance : 0` drive limit.
Here the latter is present in the source and DC actually applies zero as the
allowed load; this is not a missing value inferred from the report alone.

## Actual load accounting

The [query script](../../synth/dc/diagnose_capacitance.tcl) loads each exact
retained post-optimization DDC independently. It finds all zero-limit output
references, queries the highest connected net segment to resolve hierarchical
port aliases, and obtains flattened driver/receiver connections with
`report_net -connections -verbose -nosplit`.

| Observation | 3 ns mapping | 4 ns mapping |
|---|---:|---:|
| Violating nets with exactly one receiver | 5,184 / 5,504 | 5,214 / 5,334 |
| Maximum receiver count | 4 | 2 |
| Summed nominal receiver-pin load (fF) | 1.53896–10.10350 | 1.53896–5.05869 |
| Violating nets with nonzero modeled wire capacitance | 0 | 0 |
| Violating nets with external output-port load | 0 | 0 |

Every reported receiver pin's capacitance matches the associated Liberty value.
The complete constraint-report actual load matches the sum of nominal receiver
capacitances to 0.00051 fF, allowing for six decimal places in pF. There are no
unaccounted loads in this set. The design report specifies no wire-load model;
the connection reports explicitly show zero wire capacitance. Those zeros
describe the pre-layout model, not physical wires after routing.

At 3 ns, the worst net `candidates_i/n1034` is a NAND2X1 output driving a
single INVX8/A input with **10.1035 fF** nominal capacitance. The required load
is zero, so even this single receiver violates the rule. At the low end, a
single BUFX2/A input still adds 1.53896 fF. Adding a buffer after a zero-limit
driver leaves a positive input capacitance on that driver's output.

There are two related report quantities. In these mappings,
`report_constraint` uses the summed nominal input capacitances, while verbose
`report_net` reports the minimum/maximum of the separately summed rise/fall
input capacitances. These can differ for mixed receiver types. At 3 ns,
`table_i/n2813` has a nominal sum of 5.63036 fF and a rise/fall maximum of
5.57074 fF. The collector checks both definitions independently instead of
calling their difference missing wire load. Native examples are retained for
[3 ns](../../results/capacitance_diagnosis/reports/q16_3ns/examples.rpt) and
[4 ns](../../results/capacitance_diagnosis/reports/q16_4ns/examples.rpt).

## Additional characterization concern

For all five affected logic cell types, the associated Liberty source's
`cell_rise` / `cell_fall` load-axis grid spans **0.1–5 pF (100–5,000 fF)**.
Every affected net's measured load is below that source grid. This raises a
model-extrapolation concern in addition to the zero drive limits. The largest
table load is a lookup-table coordinate, not an authoritative replacement
for the electrical limit.

The recorded DC setup/hold values remain reproducible supplied-library results.
This diagnosis does not certify characterization at the actual low loads.
Loaded DB output limits and used receiver-pin capacitances were directly checked;
the exact compiled DB delay-table arrays were not exported because the current
Library Compiler setup could not service `report_lib`. The source-grid finding
therefore concerns the associated Liberty source; a complete timing-model audit
needs the library's build provenance or a working table-inspection flow.

## Available views and repair decision

The [bounded installed-view inventory](../../results/capacitance_diagnosis/available_views.json)
found an older SignalStorm Liberty view at the same nominal 1.1 V / 27°C corner.
It retains all five problematic limits and includes an additional zero-limit
OAI22X1, so it does not supply a fix or another corner. A file named
`gscl45nm_final.lib` is compressed native Cadabra layout data, not Liberty timing
text; its suffix alone is insufficient to select it as a replacement.

The installed GSCL45nm LEF has 33 macros, covering all 31 current timing-library
cell names, and ten routing layers with resistance declarations. It has no
layer `CAPACITANCE` declarations. This is useful starting data but does not
establish a complete RC/extraction or physical-signoff setup. The current remote
shell finds DC on PATH; ICC/ICC2, PrimeTime, Library Compiler and OpenROAD were
not found on that PATH. This is a bounded readiness check, not an assertion that
other installations or licenses do not exist.

The next repair should follow one of two evidence-based routes:

1. Obtain documented corrected or recharacterized timing data for matching
   physical cells, including the actual low-load region and relevant corners.
   Rebuild/reload the DB and rerun **both baseline and candidate** with those
   same models. Do not compare new-library PPA directly with old-library PPA
   as if the library were unchanged.
2. As a constrained experiment with the existing library, exclude all zero-limit
   output references and remap their existing uses into allowed positive-limit
   cells. This requires actual logic replacement, not just buffering. Assess
   setup margin, zero setup/hold/capacitance failures, transition limits, area
   and full mapped functional equivalence together. Even a clean electrical
   report under this library would not resolve the source-grid/physical concerns.

No limits are deleted, increased to guessed values, or replaced with table maxima.
Physical work requires a verified timing-library/cell-geometry match, RC setup,
tool flow and available corners. OpenROAD's primary documentation describes
[wire RC setup](https://openroad.readthedocs.io/en/latest/main/src/est/README.html)
and [electrical repair with estimated parasitics](https://openroad.readthedocs.io/en/latest/main/src/rsz/README.html);
neither is a physical result for this project.

## Retained timing and reproduction

The read-only queries reproduce the latest area, setup, hold, cell counts,
violation counts and constrained-endpoint status exactly. Exported SDC commands
also match. At 3/4 ns, setup remains **+0.050054 / +0.055773 ns**, hold remains
**+0.008031 ns**, and area remains **70,925.776764 / 65,735.788116 µm²**.
The prior mapped functional proofs still refer to the same exact DDC/netlist
identities; no new remapping or new equivalence result is claimed here.

`make check-evidence` checks the native report hashes, library metadata, per-net
load arithmetic, counts and baseline identity without licensed inputs. The
[collector](../../scripts/capacitance_report.py) can regenerate the diagnosis
from retained raw query runs and the matching private Liberty file.

```sh
# On the lab server, from the repository root; example for the retained 3 ns DDC.
export MC_LAB_CONFIG=/path/to/matching/lab_config.tcl
export MC_MAPPED_DDC=/path/to/setup_margin/after.ddc
export MC_ANALYSIS_TOP=mc_top_Q_DEPTH16_SCHED_POLICY1_AGING_ENABLE1
export MC_ANALYSIS_OUT=/path/to/new/capacitance_query
dc_shell -f synth/dc/diagnose_capacitance.tcl
```

Use a new output directory and repeat independently for the retained 4 ns DDC.
The collector's default source is `build/capacitance_diagnosis/canonical/`,
including query provenance. Its public destination must also be new.
Full raw connection reports, library/LEF files and mapped DDCs remain private;
numeric metadata, load accounting, selected native examples and hashes are public.
