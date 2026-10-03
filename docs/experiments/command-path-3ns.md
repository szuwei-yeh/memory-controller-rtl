# Remaining 3 ns command-output paths

This analysis describes checkpoint `9d40e16`. The proposed experiment has since
been [implemented and measured](parallel-arbitration-experiment.md); its results
are kept separately rather than changing this pre-experiment diagnosis.

The selected command-mask plus storage implementation still misses 3 ns setup
by **68.773 ps**. Read-only queries on its saved mapped DDC reproduce all **50
setup and eight hold violations**. Two almost equally critical path families
make a mask-fanout-only change insufficient: the next proposed experiment is
parallel column/preparation arbitration in the scheduler. **That RTL change has
not been implemented or measured by this analysis.**

The source checkpoint is `9d40e165e8b071bbe20c01e16d8a12e20b6a8bbc`.
Its RTL hashes match the selected `mask_and_storage` mapping from the
[command-mask experiment](command-mask-optimization.md). The mapping was made
before the checkpoint commit; this is not a fresh synthesis run. The earlier
[critical-path study](critical-path-3ns.md) describes a different implementation.

## Scope and checks

DC R-2020.09-SP4 reads the existing Q16/FR-FCFS+aging/3 ns DDC and links the same
GSCL45nm typical library (1.1 V, 27°C). There is no compile, RTL change, SDC reload,
or timing exception. Area remains 71,720.770984 µm² with 1,974 sequential cells.
Library, configuration, SDC, query script, DDC, and RTL hashes are retained in
the [analysis summary](../../results/command_path_3ns/summary.json).

The query reports 60 distinct setup endpoints, including every one of the 50
failing command outputs. Original and reloaded `report_constraint` setup/hold
endpoint slacks match exactly. Two `report_timing` endpoint slacks differ from
`report_constraint` by the final printed digit (0.000001 ns); the collector
records these differences and permits no larger discrepancy. Setup TNS remains
−3.396384 ns using constraint-report endpoint slacks. No unconstrained endpoints
are reported. Hold and inherited zero-limit max-capacitance violations remain.

## Two representative paths

The output budget is **1.900000 ns**: 3 ns period minus 1 ns output delay and
0.1 ns clock uncertainty. Both paths start at transaction-table address flops,
pass through address comparison/distribution, bank candidates, and scheduler,
then drive a command payload output.

| Stage (ns) | Worst: address bit 146 → `cmd_op[0]` | Near-worst: address bit 7 → `cmd_col[1]` |
|---|---:|---:|
| Clock to Q | 0.101875 | 0.113515 |
| Address comparison/distribution | 0.237142 | 0.229443 |
| Bank candidates | 0.756054 | 0.777048 |
| Scheduler | 0.636239 | 0.686411 |
| Command mux/output | 0.237463 | 0.162352 |
| Arrival | **1.968773** | **1.968769** |
| Slack | **−0.068773** | **−0.068769** |
| Cell arcs, including clock to Q | 71 | 66 |
| Mask at scheduler boundary | `select_mask[5]` | `select_mask[4]` |
| Boundary arrival (ns) | 1.731310 | 1.806417 |
| Boundary fanout | 1 | 50 |
| Reported boundary capacitance (fF) | 5.092 | 130.563 |

The bank-candidate and scheduler stages account for **70.72%** and **74.33%**
of these total arrival times. Stage boundaries follow explicit mapped hierarchy;
they do not attribute every optimized gate to one RTL expression. The first
combinational group includes top-level shared address logic and distribution.
Stage times are differences between reported boundary arrivals, retaining
signed increments. For example, the worst path includes a reported
−0.002192 ns increment at `candidates_i/U563/Y`; dropping negative increments
would misstate the total. This is a report value, not a claim of physical
negative propagation time.

The top 20 endpoint paths contain 19 launches from address bit 7 through mask 4
and one from address bit 146 through mask 5. Their slacks span only 0.014 ps;
such tiny ordering differences should not be treated as physically meaningful.
All 50 failures launch from those same two address bits (38 and 12 paths).
Their mask distribution is 39 through mask 4, four through mask 5, three through
mask 8, two through mask 1, and one each through masks 3 and 11.

The net connection report independently confirms mask 4's 50 loads and
128.420–130.563 fF pin capacitance. Mask 5 has one load, a top-level inverter,
and 5.080–5.092 fF pin capacitance. Both have zero reported wire capacitance.
Therefore improving mask 4 fanout alone would leave the mask 5 path violating.
The top 20 paths share **20 driver pins**: nine in candidates and 11 in the
scheduler. This is a set intersection, not a claim that all 20 cells form one
contiguous common path. Pin lists and all 50 detailed paths are published.

## Other paths that must stay within budget

| Query | Worst path | Slack (ns) |
|---|---|---:|
| Register → register | `occupied_reg_0_` → `ages_reg_48_` in table | **+0.002394** |
| Input → register | `rst` → table `ages_reg_48_` | +0.429083 |
| Input → output | `rst` → `req_ready` | +0.574358 |
| Hold | bank `ras_reg_2__2_` feedback | **−0.000661** |

The internal setup margin is only **2.394 ps**. A command-path improvement that
reintroduces age-update failures is not acceptable. All eight remaining hold
failures are bank timer feedback endpoints; a separate hold experiment must
retain the original constraints. This read-only analysis does not establish
whether an RTL change or implementation-level hold repair is preferable.

## Next experiment: parallel command-class arbitration

The current scheduler computes eligible `choices`, forms column choices,
replaces `choices` with columns when any exist, and only then performs oldest
selection. The proposed trial moves class selection after oldest arbitration:

```text
Current: eligible choices → column-presence selection → oldest winners → mask

Trial:   eligible columns ───→ oldest column winners ──┐
         eligible PRE/ACT ──→ oldest PRE/ACT winners ─┴→ class selection → mask
```

The hypothesis is that removing column-presence selection from the input of
the pairwise older-rejection logic shortens the shared arbitration dependency.
It may duplicate arbitration logic and increase area. The path evidence
motivates targeting the shared cone; it does not prove which mapped gate
implements the column-presence test or guarantee a timing improvement.

Behavioral requirements for the trial:

- Choose the column class using **`columns != 0`**, not whether column winners
  exist. If an arbitrary ordering matrix has a cycle, columns may exist with
  no winner; falling through to PRE/ACT would change reference behavior.
- Preserve highest-slot priority for incomparable winners, default slot-zero
  payload when no winner exists, and the distinction between mask and validity.
- Preserve aging qualification, owner-service override, encoded slot updates,
  and cycle timing. No additional register stage is proposed.

Compare against the selected checkpoint, not the older compact-mask baseline.
Before adoption require whole-controller equivalence for Q=1/3/16 and all three
policies, paired cycle traces, and the existing regression/formal checks. Use
the same synthesis flow and two independently mapped Q16 target points:

| Metric | Acceptance condition |
|---|---|
| 3 ns setup WNS | Strictly better than −0.068773 ns |
| 3 ns setup TNS | At least −3.396384 ns |
| 3 ns internal setup | Zero failing endpoints; report remaining margin |
| 4 ns setup | Pass |
| 3 ns hold | Slack at least −0.000661 ns; at most eight failures |
| 4 ns hold | Slack at least −0.000659 ns; at most two failures |
| 4 ns area | At most 5% above 65,996.718912 µm² |

## Reproduction and artifacts

On a licensed DC host, set `MC_LAB_CONFIG` to the matching library configuration,
`MC_MAPPED_DDC` to the selected 3 ns `mapped.ddc`, `MC_ANALYSIS_TOP` to
`mc_top_Q_DEPTH16_SCHED_POLICY1_AGING_ENABLE1`, and `MC_ANALYSIS_OUT` to a new
directory, then run:

```sh
dc_shell -f synth/dc/analyze_command_paths.tcl
```

The saved DDC and licensed library are not redistributed. The local raw query
folder also contains a `provenance.json` captured against that DDC before the
query. To audit and publish those raw reports:

```sh
python3 scripts/command_path_report.py --source build/command_path_3ns
```

- [Top 20 endpoint paths and stage times](../../results/command_path_3ns/top20.csv)
- [Detailed arcs for all 50 failing paths](../../results/command_path_3ns/failing_path_details.json)
- [Summary, provenance, class margins, shared pins and net loads](../../results/command_path_3ns/summary.json)
- [Raw/public report hashes](../../results/command_path_3ns/reports/hashes.json)
- [Timing report](../../results/command_path_3ns/reports/timing.rpt) and
  [mask connections](../../results/command_path_3ns/reports/command_mask_nets.rpt)

These are typical-corner pre-layout measurements with an ideal clock. They do
not establish routed timing, exact Fmax, power, or signoff closure.
