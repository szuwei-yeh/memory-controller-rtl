#!/usr/bin/env python3
"""Collect candidate-mask experiments without claiming complete timing closure."""
import csv
import hashlib
import json
from pathlib import Path
import re
import shutil

from candidate_mask_equiv import BASELINE_COMMIT, baseline_sources
from dc_sweep_report import parse_run

ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT/'results/candidate_mask'
EXPERIMENTS = {'bank_mask': ROOT/'build/candidate_mask_opt',
               'compact_mask': ROOT/'build/candidate_mask_compact'}
REPORTS = ['area.rpt','timing.rpt','hold.rpt','qor.rpt','check_design.rpt','check_timing.rpt']


def read(path):
    return json.loads(path.read_text())


def sha(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def main():
    original = read(ROOT/'results/address_sharing/summary.json')
    baseline = original['current_rtl_sha256']
    files = (ROOT/'synth/rtl_files.f').read_text().split()
    current = {p:sha(ROOT/p) for p in files}
    assert {**current, **{p:hashlib.sha256(s.encode()).hexdigest() for p,s in baseline_sources().items()}} == baseline
    rows = []
    for period in [3,4]:
        row = dict(next(r for r in original['runs'] if (r['variant'],r['queue_depth'],r['clock_ns']) == ('shared_address',16,period)))
        row.update(variant='baseline',baseline_reused=True)
        rows.append(row)
    verification = {}
    for variant,folder in EXPERIMENTS.items():
        hashes = read(folder/'trial_hashes.json')
        assert read(folder/'baseline.json')['source_sha256'] == baseline
        eq = read(folder/'equiv_summary.json')
        assert eq['status'] == 'PASS' and eq['source_sha256'] == hashes
        assert read(folder/'lab_session.json')['library_sha256'] == original['library_sha256']
        verification[variant] = eq
        for p in files:
            assert sha(folder/'trial'/p) == hashes[p]
            if p not in baseline_sources():
                assert hashes[p] == baseline[p], 'Unplanned RTL change'
        for name in baseline_sources():
            target = OUT/'variants'/variant/name
            target.parent.mkdir(parents=True,exist_ok=True)
            shutil.copyfile(folder/'trial'/name,target)
        for period in [3,4]:
            directory = folder/'dc'/f'q16_{period}ns'
            row = parse_run(directory)
            assert row['metadata']['rtl_sha256'] == hashes
            assert (row['queue_depth'],row['clock_ns'],row['policy']) == (16,period,'frfcfs_aging')
            assert row['metadata']['lab_config_sha256'] == rows[0]['metadata']['lab_config_sha256']
            assert row['metadata']['flow_sha256'] == rows[0]['metadata']['flow_sha256']
            environment = (directory/'environment.rpt').read_text()
            for setting in ['nom_process: 1.000000','nom_voltage: 1.100000','nom_temperature: 27.000000',
                            'Time unit ns: 1.0; capacitance unit fF: 1000.0',
                            f'Clock target ns: {period}; Q: 16; policy: 1; aging: 1']:
                assert setting in environment
            assert 'R-2020.09-SP4' in (directory/'tool.log').read_text()
            row['metadata'].pop('hostname',None)
            row.update(variant=variant,baseline_reused=False)
            cells = int(re.search(r'Number of sequential cells:\s+(\d+)',(directory/'area.rpt').read_text())[1])
            assert cells == 1974
            row['sequential_cells'] = cells
            public = OUT/'reports'/variant/directory.name
            public.mkdir(parents=True,exist_ok=True)
            raw_hashes,public_hashes = {},{}
            for name in REPORTS:
                text = (directory/name).read_text()
                text = re.sub(r'/[^\s()]*?/gscl45nm\.db','${TECH_LIBRARY_DIR}/gscl45nm.db',text)
                text = '\n'.join(line.rstrip() for line in text.splitlines())+'\n'
                assert not re.search(r'/Users/|/fs/|/tmp/|szu-wei',text)
                (public/name).write_text(text)
                raw_hashes[name],public_hashes[name] = sha(directory/name),sha(public/name)
            (public/'hashes.json').write_text(json.dumps(dict(raw=raw_hashes,public=public_hashes),indent=2)+'\n')
            row['report_path'] = str(public.relative_to(ROOT))
            rows.append(row)
    def point(variant,period):
        return next(r for r in rows if (r['variant'],r['clock_ns']) == (variant,period))
    qualified = [v for v in EXPERIMENTS if point(v,3)['setup_worst_slack_ns'] > point('baseline',3)['setup_worst_slack_ns']
                 and point(v,4)['setup_pass'] and point(v,4)['area_um2'] <= 1.05*point('baseline',4)['area_um2']]
    assert qualified, 'Neither hypothesis met the predeclared setup/area screen'
    selected = 'compact_mask'
    assert selected in qualified
    assert point(selected,3)['hold_violation_count'] < point('bank_mask',3)['hold_violation_count']
    assert point(selected,3)['setup_violation_count'] < point('bank_mask',3)['setup_violation_count']
    assert point(selected,3)['area_um2'] < point('bank_mask',3)['area_um2']
    selected_folder = EXPERIMENTS[selected]
    assert read(selected_folder/'trial_hashes.json') == current, 'Working RTL is not the selected measured variant'
    for name,h in rows[0]['metadata']['flow_sha256'].items():
        assert sha(ROOT/name) == h
    eq = read(ROOT/'build/candidate_mask_equiv/summary.json')
    trace = read(ROOT/'build/candidate_mask_trace_compare/summary.json')
    assert eq['status'] == trace['status'] == 'PASS'
    assert eq['source_sha256'] == current and eq['baseline_sha256'] == baseline
    assert {(r['queue_depth'],r['policy']) for r in eq['results']} == {(q,p) for q in [1,3,16] for p in ['strict','frfcfs','aging']}
    assert all(r['status'] == 'PASS' for r in eq['results'])
    for label,build in trace['builds'].items():
        expected = baseline if label.startswith('before/') else current
        assert all(build['source_sha256'][p] == h for p,h in expected.items())
    suites = {name:read(ROOT/'build'/name) for name in ['test_summary.json','regress_summary.json']}
    for suite in suites.values():
        for result in suite['results']:
            meta = read(ROOT/result['path']/'run.json')['build']['source_sha256']
            assert all(meta[p] == h for p,h in current.items())
    formal = read(ROOT/'build/formal/summary.json')
    assert all(task['status'] == 'PASS' for task in formal)
    for task in formal:
        for p in (ROOT/'build/formal'/task['task']/'src').glob('mc_*.sv'):
            assert sha(p) == current['rtl/'+p.name]
    mutation = read(selected_folder/'mutation.json')
    assert mutation['status'] == 'REJECTED'
    summary = dict(status='EXPERIMENT_COMPLETE',baseline_commit=BASELINE_COMMIT,
        selected_variant=selected,adoption_scope='Setup-oriented research variant; timing closure remains incomplete.',
        selection_screen=dict(three_ns_slack_improves=True,four_ns_setup_passes=True,max_four_ns_area_increase_percent=5),
        selection_rule='Both candidates pass the predeclared setup/area screen. Compact mask is selected after full STA review for fewer 3 ns internal setup/hold violations and lower 3 ns area, accepting weaker 3 ns WNS and more 4 ns hold violations than bank mask. Neither variant dominates all metrics; no violations are waived.',
        baseline_reused_from='results/address_sharing/summary.json: shared_address Q16/3 ns and Q16/4 ns',
        fresh_baseline_rerun=False,library_sha256=original['library_sha256'],
        baseline_rtl_sha256=baseline,current_rtl_sha256=current,runs=rows,
        verification_per_experimental_variant=verification,equivalence=eq,controller_formal=formal,
        trace_pairs=trace['pairs'],trace_simulations=2*trace['pairs'],
        trace_accepted_total=2*sum(r['accepted_per_revision'] for r in trace['results']),
        trace_summary_sha256=sha(ROOT/'build/candidate_mask_trace_compare/summary.json'),
        regression_runs=len(suites['regress_summary.json']['results']),
        regression_accepted=sum(r['accepted'] for r in suites['regress_summary.json']['results']),
        directed_corner_runs=len(suites['test_summary.json']['results']),negative_control=mutation,
        verification_source_sha256={p:sha(ROOT/p) for p in ['scripts/candidate_mask_equiv.py','scripts/scheduler_trace_compare.py','tb/tb_scheduler.sv']},
        limits='Q16 mapped data only. Typical-corner pre-layout medium-effort DC. Setup and hold remain violated at 3 ns; hold regresses at 4 ns. Zero-limit max-cap violations remain. No new frequency, power, Q32 PPA, physical timing, or signoff claim.')
    (OUT/'summary.json').write_text(json.dumps(summary,indent=2)+'\n')
    fields=['variant','clock_ns','area_um2','setup_worst_slack_ns','setup_tns_ns','setup_violation_count',
            'worst_hold_slack_ns','hold_violation_count','max_capacitance_violation_count']
    with (OUT/'summary.csv').open('w',newline='') as stream:
        writer=csv.DictWriter(stream,fieldnames=fields,extrasaction='ignore',lineterminator='\n')
        writer.writeheader();writer.writerows(rows)
    table=['| Variant | Target (ns) | Area (µm²) | Setup slack (ns) | Setup TNS (ns) | Setup endpoints | Hold slack (ns) | Hold endpoints |',
           '|---|---:|---:|---:|---:|---:|---:|---:|']
    for r in rows:
        table.append(f"| {r['variant']} | {r['clock_ns']} | {r['area_um2']:,.2f} | {r['setup_worst_slack_ns']:+.6f} | {r['setup_tns_ns']:.6f} | {r['setup_violation_count']} | {r['worst_hold_slack_ns']:+.6f} | {r['hold_violation_count']} |")
    doc=ROOT/'docs/experiments/candidate-mask-optimization.md'
    text=doc.read_text();start,end='<!-- measured-table -->','<!-- /measured-table -->'
    assert text.count(start)==text.count(end)==1
    prefix,rest=text.split(start);_,suffix=rest.split(end)
    doc.write_text(prefix+start+'\n\n'+'\n'.join(table)+'\n\n'+end+suffix)
    print('Selected:',selected,'; verified four new DC runs, two reused baselines and matching verification evidence.')


if __name__ == '__main__':
    main()
