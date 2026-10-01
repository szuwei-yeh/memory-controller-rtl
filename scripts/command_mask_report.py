#!/usr/bin/env python3
"""Collect direct command-selection mask experiments and apply their adoption screen."""
import csv
import json
from pathlib import Path
import re
import shutil

from dc_sweep_report import parse_run
from storage_timing_report import read, sha, publish_reports, internal_setup_count

ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT/'results/command_mask'
EXPERIMENTS = {'direct_mask': 'command_mask_opt', 'folded_default': 'command_mask_folded',
               'mask_and_storage': 'command_mask_storage'}
CHANGED = ['rtl/mc_top.sv', 'rtl/mc_scheduler_frfcfs.sv']
REPORTS = ['area.rpt', 'timing.rpt', 'hold.rpt', 'qor.rpt', 'check_design.rpt', 'check_timing.rpt']


def main():
    previous = read(ROOT/'results/candidate_mask/summary.json')
    baseline = previous['current_rtl_sha256']
    files = (ROOT/'synth/rtl_files.f').read_text().split()
    current = {p: sha(ROOT/p) for p in files}
    rows, variants, verification, lint = [], {}, {}, {}
    for period in [3, 4]:
        row = dict(next(r for r in previous['runs']
                        if (r['variant'], r['clock_ns']) == ('compact_mask', period)))
        row.update(variant='compact_baseline', baseline_reused=True)
        rows.append(row)
    for variant, name in EXPERIMENTS.items():
        folder = ROOT/'build'/name
        changed = CHANGED + (['rtl/mc_transaction_table.sv'] if variant == 'mask_and_storage' else [])
        hashes = read(folder/'trial_hashes.json')
        assert read(folder/'baseline.json')['source_sha256'] == baseline
        assert read(folder/'lab_session.json')['library_sha256'] == previous['library_sha256']
        for p in files:
            assert sha(folder/'trial'/p) == hashes[p]
            if p not in changed:
                assert hashes[p] == baseline[p], 'Unexpected RTL change'
        eq = read(folder/'equiv_summary.json')
        assert eq['status'] == 'PASS' and eq['source_sha256'] == hashes
        assert {(r['queue_depth'], r['policy']) for r in eq['results']} == {
            (1, 'aging'), (3, 'strict'), (3, 'frfcfs'), (3, 'aging'), (16, 'aging')}
        assert all(r['status'] == 'PASS' and r['unproven_cells'] == 0 for r in eq['results'])
        variants[variant], verification[variant] = hashes, eq
        lint[variant] = read(folder/'lint.json')
        assert lint[variant]['status'] == 'PASS' and lint[variant]['source_sha256'] == hashes
        for p in changed:
            dest = OUT/'variants'/variant/p
            dest.parent.mkdir(parents=True, exist_ok=True)
            shutil.copyfile(folder/'trial'/p, dest)
        for period in [3, 4]:
            directory = folder/'dc'/f'q16_{period}ns'
            row = parse_run(directory)
            assert row['metadata']['rtl_sha256'] == hashes
            assert (row['queue_depth'], row['clock_ns'], row['policy']) == (16, period, 'frfcfs_aging')
            for key in ['lab_config_sha256', 'flow_sha256']:
                assert row['metadata'][key] == rows[0]['metadata'][key]
            environment = (directory/'environment.rpt').read_text()
            assert all(s in environment for s in ['nom_process: 1.000000', 'nom_voltage: 1.100000',
                       'nom_temperature: 27.000000', 'Time unit ns: 1.0; capacitance unit fF: 1000.0'])
            assert 'R-2020.09-SP4' in (directory/'tool.log').read_text()
            row['metadata'].pop('hostname', None)
            row.update(variant=variant, baseline_reused=False)
            row['sequential_cells'] = int(re.search(r'Number of sequential cells:\s+(\d+)',
                                                    (directory/'area.rpt').read_text())[1])
            assert row['sequential_cells'] == 1974
            dest = OUT/'reports'/variant/directory.name
            publish_reports(directory, dest, REPORTS)
            row['report_path'] = str(dest.relative_to(ROOT))
            rows.append(row)
    for row in rows:
        row['internal_setup_violation_count'] = internal_setup_count(row)
    def point(variant, period):
        return next(r for r in rows if (r['variant'], r['clock_ns']) == (variant, period))
    checks = {}
    for variant in EXPERIMENTS:
        r3, r4 = point(variant, 3), point(variant, 4)
        b3, b4 = point('compact_baseline', 3), point('compact_baseline', 4)
        checks[variant] = {
            'three_ns_worst_setup_improves': r3['setup_worst_slack_ns'] > b3['setup_worst_slack_ns'],
            'three_ns_internal_setup_count_not_worse': internal_setup_count(r3) <= internal_setup_count(b3),
            'three_ns_setup_tns_not_worse': r3['setup_tns_ns'] >= b3['setup_tns_ns'],
            'four_ns_setup_pass': r4['setup_pass'],
            'four_ns_area_at_most_five_percent_more': r4['area_um2'] <= 1.05*b4['area_um2'],
            'hold_worst_slack_not_worse_at_both_points': all(point(variant, p)['worst_hold_slack_ns'] >=
                point('compact_baseline', p)['worst_hold_slack_ns'] for p in [3, 4]),
            'hold_count_not_worse_at_both_points': all(point(variant, p)['hold_violation_count'] <=
                point('compact_baseline', p)['hold_violation_count'] for p in [3, 4]),
        }
    qualified = [v for v in EXPERIMENTS if all(checks[v].values())]
    recommended = max(qualified, key=lambda v: point(v, 3)['setup_worst_slack_ns']) if qualified else None
    selected = next((v for v, h in variants.items() if h == current), None)
    if selected:
        assert selected == recommended
    else:
        assert current == baseline
    mutation = read(ROOT/'build/command_mask_opt/mutation.json')
    assert mutation['status'] == 'REJECTED' and mutation['unproven_cells'] > 0
    assert mutation['source_sha256'] == variants['direct_mask']
    summary = dict(status='MEASUREMENTS_COMPLETE' if qualified else 'EXPERIMENT_COMPLETE', baseline_label='compact_mask',
        baseline_evidence='results/candidate_mask/summary.json', baseline_rtl_sha256=baseline,
        library_sha256=previous['library_sha256'], fresh_baseline_rerun=False,
        variants=variants, current_rtl_sha256=current, selected_variant=selected,
        recommended_variant=recommended, qualifying_variants=qualified, adoption_checks=checks,
        runs=rows, experimental_equivalence=verification, experimental_lint=lint, negative_control=mutation,
        limits='Typical-corner Q16 pre-layout DC only. Hold and zero-limit capacitance violations remain. No waiver or signoff claim.')
    if selected:
        eq = read(ROOT/'build/command_mask_equiv/summary.json')
        trace = read(ROOT/'build/command_mask_trace_compare/summary.json')
        assert eq['status'] == trace['status'] == 'PASS'
        assert eq['source_sha256'] == current and eq['baseline_sha256'] == baseline
        assert {(r['queue_depth'], r['policy']) for r in eq['results']} == {
            (q, p) for q in [1, 3, 16] for p in ['strict', 'frfcfs', 'aging']}
        assert all(r['status'] == 'PASS' for r in eq['results'])
        assert trace['pairs'] == len(trace['results']) == 120
        for label, build in trace['builds'].items():
            expected = baseline if label.startswith('before/') else current
            assert all(build['source_sha256'][p] == h for p, h in expected.items())
        suites = {name: read(ROOT/'build'/name) for name in ['test_summary.json', 'regress_summary.json']}
        assert len(suites['test_summary.json']['results']) == 42
        assert len(suites['regress_summary.json']['results']) == 300
        for suite in suites.values():
            for result in suite['results']:
                meta = read(ROOT/result['path']/'run.json')['build']['source_sha256']
                assert all(meta[p] == h for p, h in current.items())
        formal = read(ROOT/'build/formal/summary.json')
        assert len(formal) == 5 and all(task['status'] == 'PASS' for task in formal)
        for task in formal:
            for p in (ROOT/'build/formal'/task['task']/'src').glob('mc_*.sv'):
                assert sha(p) == current['rtl/'+p.name]
        selected_mutation = read(ROOT/'build'/EXPERIMENTS[selected]/'mutation.json')
        assert selected_mutation['status'] == 'REJECTED' and selected_mutation['source_sha256'] == current
        summary.update(status='EXPERIMENT_COMPLETE', equivalence=eq, controller_formal=formal,
            trace_pairs=trace['pairs'], trace_simulations=2*trace['pairs'],
            trace_accepted_total=2*sum(r['accepted_per_revision'] for r in trace['results']),
            trace_summary_sha256=sha(ROOT/'build/command_mask_trace_compare/summary.json'),
            regression_runs=len(suites['regress_summary.json']['results']),
            regression_accepted=sum(r['accepted'] for r in suites['regress_summary.json']['results']),
            directed_corner_runs=len(suites['test_summary.json']['results']),
            selected_negative_control=selected_mutation,
            verification_source_sha256={p: sha(ROOT/p) for p in ['scripts/command_mask_equiv.py',
                'scripts/candidate_mask_equiv.py', 'scripts/scheduler_trace_compare.py', 'tb/tb_scheduler.sv']})
    (OUT/'summary.json').write_text(json.dumps(summary, indent=2)+'\n')
    keys = ['variant', 'clock_ns', 'area_um2', 'setup_worst_slack_ns', 'setup_tns_ns',
            'setup_violation_count', 'internal_setup_violation_count', 'worst_hold_slack_ns', 'hold_violation_count']
    with (OUT/'summary.csv').open('w', newline='') as stream:
        writer = csv.DictWriter(stream, fieldnames=keys, extrasaction='ignore', lineterminator='\n')
        writer.writeheader(); writer.writerows(rows)
    table = [
        '| Variant | Target (ns) | Area (µm²) | Setup slack (ns) | Setup TNS (ns) | Setup endpoints | Internal setup endpoints | Hold slack (ns) | Hold endpoints |',
        '|---|---:|---:|---:|---:|---:|---:|---:|---:|',
    ]
    for r in rows:
        table.append(f"| {r['variant']} | {r['clock_ns']} | {r['area_um2']:,.2f} | "
                     f"{r['setup_worst_slack_ns']:+.6f} | {r['setup_tns_ns']:.6f} | {r['setup_violation_count']} | "
                     f"{r['internal_setup_violation_count']} | {r['worst_hold_slack_ns']:+.6f} | {r['hold_violation_count']} |")
    doc = ROOT/'docs/command-mask-optimization.md'
    text = doc.read_text()
    start, end = '<!-- measured-table -->', '<!-- /measured-table -->'
    assert text.count(start) == text.count(end) == 1
    prefix, rest = text.split(start); _, suffix = rest.split(end)
    doc.write_text(prefix+start+'\n\n'+'\n'.join(table)+'\n\n'+end+suffix)
    print(json.dumps(dict(qualified=qualified, recommended=recommended, selected=selected, checks=checks), indent=2))


if __name__ == '__main__':
    main()
