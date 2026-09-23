#!/usr/bin/env python3
"""Publish frozen ASIC sweep evidence from explicit local report allowlists."""
import hashlib
import json
from pathlib import Path
import shutil

from dc_sweep_report import POLICIES, PERIODS, parse_run, write_summaries
from log_experiment import append_entry

ROOT=Path(__file__).resolve().parents[1]
OUT=ROOT/'results/dc_sweep'


def main():
    rows=[parse_run(p) for p in sorted((ROOT/'build/dc_sweep/runs').iterdir()) if (p/'run.json').exists()]
    summary=write_summaries(rows)
    rows=summary['runs']; index={(r['policy'],r['queue_depth'],r['clock_ns']):r for r in rows}
    baseline=json.loads((ROOT/'results/dc_baseline/summary.json').read_text())
    for r in rows:
        assert r['metadata']['rtl_sha256']==baseline['rtl_sha256']
        folder=ROOT/'build/dc_sweep/runs'/f"{r['policy']}_q{r['queue_depth']}_{r['clock_ns']}ns"
        environment=(folder/'environment.rpt').read_text()
        assert 'Target libraries: '+baseline['library_path'] in environment
        assert 'Link libraries: * '+baseline['library_path'] in environment
        assert 'nom_voltage: 1.100000' in environment and 'nom_temperature: 27.000000' in environment
        public=OUT/'reports'/folder.name;public.mkdir(parents=True,exist_ok=True)
        for name in ['run.json','area.rpt','timing.rpt','hold.rpt','qor.rpt','check_timing.rpt','check_design.rpt','environment.rpt','mapped.sdc']:
            shutil.copyfile(folder/name,public/name)
        warnings=[line for line in (folder/'tool.log').read_text().splitlines() if line.startswith('Warning:')]
        (public/'warnings.txt').write_text('\n'.join(warnings)+'\n')
        # Full high-volume constraint and mapped files remain local; published parsed
        # summaries retain every violating setup/hold endpoint and cap counts.
        (public/'report_hashes.json').write_text(json.dumps({name:hashlib.sha256((folder/name).read_bytes()).hexdigest()
            for name in ['tool.log','constraints.rpt','mapped.v','mapped.ddc']},indent=2)+'\n')
    fastest=summary['fastest_tested_setup_passing_q16']
    lines=['# Frozen v1.1 ASIC comparison sweep','',
        f"All **30 distinct Design Compiler runs** completed; **{sum(r['setup_pass'] for r in rows)}/30** meet their target setup constraint. RTL, architecture, library, and SDC were not changed. A setup pass does not waive hold or capacitance violations.",'',
        '## Diagnostics completed before the sweep','',
        '[All 14 baseline hold paths](../results/dc_sweep/baseline_hold_paths.csv) are register-to-register feedback paths: 12 transaction DONE bits and two bank timing counters. Input-to-register, register-to-output, and other classifications each have zero entries. Worst hold slack is −0.002538 ns.', '',
        'The baseline’s 5,556 max-capacitance violations all use zero allowed load. The inherited gscl45nm database and companion Liberty both specify NAND2X1/Y max_capacitance=0. No library, constraint, or RTL edits were used to suppress these violations.', '',
        '## Fixed experiment conditions','',
        '- DC R-2020.09-SP4; `compile -map_effort medium` in every run.',
        '- Target library: `${TECH_LIBRARY_DIR}/gscl45nm.db`; link library is `*` followed by that same database.',
        '- Typical corner, process factor 1, 1.1 V, 27°C; time 1 ns, capacitance 1 pF. Same configuration hash and database identity as the accepted baseline.',
        '- I/O maximum/minimum delays 1/0 ns; uncertainty 0.1 ns (unchanged for setup and hold); input transition 0.1 ns; output load 10 fF; no false or multicycle paths.',
        '- Seven-file controller-only manifest; rows=256, columns=64, data=32 bits, fixed DRAM cycle timings/read latency/aging threshold. Only the requested scheduler, queue depth, and clock target vary.',
        '- Three isolated policy workspaces, one sequential stream of ten fresh RTL compiles each. The shared Q16/5 ns points serve both matrices; no duplicate counting. No existing baseline result was substituted for a fresh run.',
        '- No wire-load model or extracted interconnect; ideal clocks. Cell area is not physical core area. No RTL optimization, retiming, hold repair, library substitution, or capacitance waiver was performed.', '',
        '## Fastest tested setup-passing target at Q=16','',
        '| Policy | Smallest passing tested period (ns) | Corresponding target (MHz) |', '|---|---:|---:|']
    for p in POLICIES:
        b=fastest[p];lines.append(f"| `{p}` | {b['clock_ns'] if b else 'none'} | {1000/b['clock_ns']:.2f} |" if b else f'| `{p}` | none | — |')
    lines += ['', '**These are tested setup-passing targets, not exact maximum frequencies or full timing/DRC signoff.** No untested interval between clock points is inferred.', '',
              '## A — Clock sweep at Q=16','',
              '| Policy | Clock ns | Area µm² | Worst setup ns | WNS ns | TNS ns | Setup violations | Worst hold ns | Hold count | Unconstrained | Setup passes |',
              '|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|---|']
    def table_row(r):
        return f"| `{r['policy']}` | {r['clock_ns']} | {r['area_um2']:.2f} | {r['setup_worst_slack_ns']:.6f} | {r['setup_wns_ns']:.6f} | {r['setup_tns_ns']:.6f} | {r['setup_violation_count']} | {r['worst_hold_slack_ns']:.6f} | {r['hold_violation_count']} | {r['unconstrained_endpoint_count']} | {'yes' if r['setup_pass'] else 'no'} |"
    lines += [table_row(index[p,16,t]) for p in POLICIES for t in PERIODS]
    lines += ['', '## B — Queue-depth comparison at 5 ns','',
        '| Policy | Q | Total area µm² | Combinational µm² | Sequential µm² | Worst setup ns | Setup passes |',
        '|---|---:|---:|---:|---:|---:|---|']
    for p in POLICIES:
        for q in [4,8,16,32]:
            r=index[p,q,5]
            lines.append(f"| `{p}` | {q} | {r['area_um2']:.2f} | {r['combinational_area_um2']:.2f} | {r['sequential_area_um2']:.2f} | {r['setup_worst_slack_ns']:.6f} | {'yes' if r['setup_pass'] else 'no'} |")
    lines += ['', 'All fields for both matrices—including warning classifications, setup WNS/TNS, hold counts, and unconstrained counts—are in the CSV/JSON below.', '',
              '## Architectural tradeoffs','', '<!-- INTERPRETATION -->', '',
              'Queue capacity expands transaction payload storage and the exact older-than matrix. Same-address dependency/response comparisons scale across pairs of slots; candidate and response arbitration plus payload selection add combinational work. This explains why deeper queues carry both storage and selection costs, rather than only a linear FIFO cost. Mapped area can vary nonmonotonically with target period because DC chooses and buffers gates differently; the architecture is unchanged.', '',
              '## Critical paths','', '| Policy / Q / ns | Startpoint | Endpoint | Path logic inferred from mapped hierarchy |', '|---|---|---|---|']
    for p in POLICIES:
        chosen=[index[p,16,fastest[p]['clock_ns']]] if fastest[p] else []
        chosen += [index[p,32,5]]
        for r in chosen:
            lines.append(f"| `{p}` / {r['queue_depth']} / {r['clock_ns']} | `{r['critical_startpoint']}` | `{r['critical_endpoint']}` | {r['critical_logic_description']} |")
    lines += ['', 'Every run’s ten reported setup paths, startpoints/endpoints, and hierarchy-based descriptions are retained in JSON; the worst path and description also appear in CSV. These descriptions identify the mapped blocks on the measured path, not a gate-level equivalence proof.', '',
        '## Remaining violations and warning accounting','',
        f"Across the matrix, hold-violating endpoint counts range from {min(r['hold_violation_count'] for r in rows)} to {max(r['hold_violation_count'] for r in rows)}. Max-capacitance counts range from {min(r['max_capacitance_violation_count'] for r in rows)} to {max(r['max_capacitance_violation_count'] for r in rows)}; {sum(r['zero_allowed_load_violation_count'] for r in rows)} of {sum(r['max_capacitance_violation_count'] for r in rows)} reported capacitance violations have a zero allowed-load limit. All runs report zero unconstrained endpoints.", '',
        'Warnings are recorded separately for synthesis, design checks, and timing checks to avoid treating repeated messages as distinct faults. Classes include signed/unsigned conversions (VER-318), unused logic/nets (LINT-1/LINT-2), unused hierarchical port bits (LINT-28), and high-fanout clocks (TIM-134). With aging disabled, LINT-52 reports protection_active tied to zero and VO-4 reports emitted assignment constructs; the mapped netlist contains `assign protection_active = 1\'b0;`. These are retained in the per-run warning files and JSON counts. No final flow Error lines were accepted.', '',
        'Setup WNS is min(0, worst setup slack). TNS sums the six-decimal negative endpoint slacks in report_constraint; violation counts are cross-checked against report_qor. Hold slack is reported even for runs without a hold violation. Unconstrained endpoint count is the checked report count, not an assumption based only on SDC presence.', '',
        '## Reproduction and evidence','',
        '```sh', 'python3 scripts/lab_bundle.py', '# Set LAB_SSH_TARGET and LAB_BASELINE_DIR privately; optionally LAB_SSH_CONTROL_PATH.\n# Uses the authenticated connection and the verified baseline lab_config.tcl:', 'python3 scripts/dc_sweep.py', '# Rebuild summaries without rerunning synthesis:', 'python3 scripts/dc_sweep_report.py', '.tools/venv/bin/python scripts/dc_sweep_publish.py', '```', '',
        '- [CSV: all 30 points](../results/dc_sweep/summary.csv)',
        '- [JSON: metrics, paths, violations, warnings and provenance](../results/dc_sweep/summary.json)',
        '- [Frozen RTL/SDC hashes](../results/dc_sweep/frozen_inputs.json)',
        '- [Baseline hold-path CSV](../results/dc_sweep/baseline_hold_paths.csv)',
        '- [Published per-run reports](../results/dc_sweep/reports/)',
        '- [Synthesis setup](#synthesis-setup)', '',
        'Raw transcripts, full constraint reports and mapped Verilog/DDC are retained locally in `build/dc_sweep/runs/`; remote session paths/commands are in `build/dc_sweep/session.json`.', '']
    interpretation=OUT/'interpretation.txt'
    if interpretation.exists(): lines=[interpretation.read_text().strip() if x=='<!-- INTERPRETATION -->' else x for x in lines]
    # Standalone plot artifacts use the same numeric rows as the report.
    import matplotlib
    matplotlib.use('Agg')
    import matplotlib.pyplot as plt
    fig,axes=plt.subplots(1,3,figsize=(15,4.4),layout='constrained')
    colors=['#536878','#1f77b4','#d97706']
    for p,color in zip(POLICIES,colors):
        clock_rows=[index[p,16,t] for t in PERIODS]
        axes[0].plot(PERIODS,[r['area_um2']/1000 for r in clock_rows],'-o',label=p,color=color)
        axes[1].plot(PERIODS,[r['setup_worst_slack_ns'] for r in clock_rows],'-o',color=color)
        for r in clock_rows:
            if not r['setup_pass']:
                axes[0].plot(r['clock_ns'],r['area_um2']/1000,'x',color='black',ms=8)
        axes[2].plot([4,8,16,32],[index[p,q,5]['area_um2']/1000 for q in [4,8,16,32]],'-o',color=color)
    for ax in axes: ax.grid(alpha=.25)
    for ax in axes[:2]: ax.set_xlabel('Clock target (ns), Q=16');ax.set_xticks(PERIODS);ax.invert_xaxis()
    axes[0].set_ylabel('Mapped cell area (1000 µm²)');axes[0].set_title('Area versus clock target; × = setup fails')
    axes[1].set_ylabel('Worst setup slack (ns)');axes[1].axhline(0,color='black',lw=.8);axes[1].set_title('Setup margin only')
    axes[2].set_xlabel('Queue depth, 5 ns target');axes[2].set_ylabel('Mapped cell area (1000 µm²)');axes[2].set_title('Queue capacity cost')
    axes[2].set_xticks([4,8,16,32])
    fig.legend(*axes[0].get_legend_handles_labels(),loc='outside lower center',ncols=3)
    fig.savefig(OUT/'area_timing.png',dpi=170);fig.savefig(OUT/'area_timing.pdf');plt.close(fig)
    lines.insert(lines.index('## Architectural tradeoffs'),'![Frozen ASIC area/timing comparison](../results/dc_sweep/area_timing.png)\n')
    document=ROOT/'docs/asic-results.md'
    marker='<!-- technical-reference -->'
    text='\n'.join(lines)
    if document.exists() and marker in document.read_text():
        text+='\n'+marker+document.read_text().split(marker,1)[1]
    document.write_text(text)
    append_entry('整理固定 ASIC 矩陣公開報告','以實際 30 次輸出呈現架構的面積／時序取捨。','逐點驗證 RTL/SDC、環境與流程雜湊一致，產生 CSV/JSON、原始報告白名單及獨立圖表。','docs/asic-results.md；results/dc_sweep/。','.tools/venv/bin/python scripts/dc_sweep_publish.py',
        f"30 次工具流程完成，setup 通過 {sum(r['setup_pass'] for r in rows)} 次；最快已測目標 {json.dumps(fastest)}。",'hold 與零上限 max-cap 違例仍保留；不能宣稱完整 signoff 或精確最高頻率。','僅比較既有架構，不依結果最佳化 RTL；所有解讀限定目前 typical pre-layout 假設。','完成最終解讀後回報並停止。')
    print(json.dumps(fastest,indent=2))


if __name__=='__main__': main()
