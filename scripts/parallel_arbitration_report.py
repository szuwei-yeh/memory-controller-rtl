#!/usr/bin/env python3
"""Publish the parallel command-class experiment without hiding rejected results."""
import json
from pathlib import Path
import re
import shutil

from dc_sweep_report import parse_run, paths, constraint_rows
from storage_timing_report import read, sha, publish_reports, internal_setup_count

ROOT = Path(__file__).resolve().parents[1]
SOURCE = ROOT/'build/parallel_arbitration'
OUT = ROOT/'results/parallel_arbitration'


def main():
    previous = read(ROOT/'results/command_mask/summary.json')
    baseline = previous['current_rtl_sha256']
    trial = read(SOURCE/'trial_hashes.json')
    assert read(SOURCE/'baseline.json')['source_sha256'] == baseline
    assert read(SOURCE/'lab_session.json')['library_sha256'] == previous['library_sha256']
    for name, digest in trial.items():
        assert sha(SOURCE/'trial'/name) == digest
        if name != 'rtl/mc_scheduler_frfcfs.sv':
            assert digest == baseline[name]
    eq, lint = read(SOURCE/'equiv_summary.json'), read(SOURCE/'lint.json')
    assert eq['status'] == lint['status'] == 'PASS'
    assert eq['source_sha256'] == lint['source_sha256'] == trial
    assert eq['baseline_sha256'] == baseline
    assert {(r['queue_depth'], r['policy']) for r in eq['results']} == {
        (q, p) for q in [1, 3, 16] for p in ['strict', 'frfcfs', 'aging']}
    assert all(r['status'] == 'PASS' and r['unproven_cells'] == 0 for r in eq['results'])
    mutation = read(SOURCE/'mutation.json')
    assert mutation['status'] == 'REJECTED' and mutation['unproven_cells'] > 0
    trace = read(SOURCE/'trace_summary.json')
    assert trace['status'] == 'PASS' and trace['pairs'] == 120
    # Each trace binary carries source hashes; verify both sides, not just PASS.
    for label, build in trace['builds'].items():
        expected = baseline if label.startswith('before/') else trial
        assert all(build['source_sha256'][p] == h for p, h in expected.items())
    rows = []
    for period in [3, 4]:
        old = dict(next(r for r in previous['runs'] if
                       (r['variant'], r['clock_ns']) == ('mask_and_storage', period)))
        old.update(variant='selected_baseline', baseline_reused=True)
        rows.append(old)
        directory = SOURCE/'dc'/f'q16_{period}ns'
        new = parse_run(directory)
        assert new['metadata']['rtl_sha256'] == trial
        for key in ['flow_sha256', 'lab_config_sha256']:
            assert new['metadata'][key] == old['metadata'][key]
        assert (new['queue_depth'], new['clock_ns'], new['policy']) == (16, period, 'frfcfs_aging')
        environment = (directory/'environment.rpt').read_text()
        assert all(s in environment for s in ['nom_process: 1.000000', 'nom_voltage: 1.100000',
                   'nom_temperature: 27.000000', 'Time unit ns: 1.0; capacitance unit fF: 1000.0'])
        assert 'R-2020.09-SP4' in (directory/'tool.log').read_text()
        new['metadata'].pop('hostname', None)
        new.update(variant='parallel_classes', baseline_reused=False)
        new['sequential_cells'] = int(re.search(r'Number of sequential cells:\s+(\d+)', (directory/'area.rpt').read_text())[1])
        assert new['sequential_cells'] == 1974
        dest = OUT/'reports'/directory.name
        publish_reports(directory, dest, ['area.rpt', 'timing.rpt', 'hold.rpt', 'qor.rpt',
                        'check_design.rpt', 'check_timing.rpt', 'constraints.rpt'])
        new['report_path'] = str(dest.relative_to(ROOT))
        rows.append(new)
    for row in rows:
        row['internal_setup_violation_count'] = internal_setup_count(row)
    point = lambda v, t: next(r for r in rows if r['variant'] == v and r['clock_ns'] == t)
    b3, b4 = [point('selected_baseline', t) for t in [3, 4]]
    r3, r4 = [point('parallel_classes', t) for t in [3, 4]]
    checks = dict(three_ns_worst_setup_improves=r3['setup_worst_slack_ns'] > b3['setup_worst_slack_ns'],
        three_ns_tns_not_worse=r3['setup_tns_ns'] >= b3['setup_tns_ns'],
        three_ns_no_internal_setup_failures=internal_setup_count(r3) == 0,
        four_ns_setup_pass=r4['setup_pass'],
        four_ns_area_at_most_five_percent_more=r4['area_um2'] <= 1.05*b4['area_um2'],
        hold_slack_not_worse_at_both_points=all(r['worst_hold_slack_ns'] >= b['worst_hold_slack_ns'] for r,b in [(r3,b3),(r4,b4)]),
        hold_count_not_worse_at_both_points=all(r['hold_violation_count'] <= b['hold_violation_count'] for r,b in [(r3,b3),(r4,b4)]))
    current = {p: sha(ROOT/p) for p in baseline}
    selected = 'parallel_classes' if current == trial else 'selected_baseline'
    assert current in [trial, baseline]
    if selected == 'parallel_classes':
        assert all(checks.values()), 'Cannot adopt a trial that fails the screen'
        validation = read(SOURCE/'validation.json')
        assert validation['status'] == 'PASS' and validation['source_sha256'] == trial
        assert validation['counts']['test']['runs'] == 42
        assert validation['counts']['regress']['runs'] == 300
        assert validation['counts']['regress']['accepted'] == 3003000
        assert len(validation['controller_formal']) == 5
        assert all(r['status'] == 'PASS' for r in validation['controller_formal'])
        assert validation['current_equivalence']['status'] == 'PASS'
        assert validation['current_equivalence']['source_sha256'] == trial
        assert len(validation['current_equivalence']['results']) == 9
        assert validation['current_trace']['status'] == 'PASS'
        assert validation['current_trace']['pairs'] == 120
        assert sha(SOURCE/'current_trace_summary.json') == validation['current_trace']['summary_sha256']
        assert sha(SOURCE/'run_manifests.json') == validation['run_manifests_sha256']
        for kind in ['test', 'regress']:
            assert sha(SOURCE/f'{kind}_summary.json') == validation['counts'][kind]['summary_sha256']
        shutil.copyfile(SOURCE/'validation.json', OUT/'validation_summary.json')
    else:
        validation = None
    analysis = read(SOURCE/'analysis_provenance.json')
    assert analysis['source_sha256'] == trial and analysis['read_only']
    assert analysis['library_sha256'] == previous['library_sha256']
    assert analysis['script_sha256'] == sha(ROOT/'synth/dc/analyze_arbitration_paths.tcl')
    queries = {}
    normalize = lambda name: re.sub(r'\[(\d+)\]', r'_\1_', name)
    for period in [3, 4]:
        folder = SOURCE/f'analysis_{period}ns'
        assert (folder/'SUCCESS').is_file()
        row = point('parallel_classes', period)
        prov = analysis['points'][str(period)]
        assert prov['config_sha256'] == row['metadata']['lab_config_sha256']
        assert prov['sdc_sha256'] == row['metadata']['flow_sha256']['synth/constraints/controller.sdc']
        assert float(re.search(r'Total cell area:\s+([\d.]+)', (folder/'area.rpt').read_text())[1]) == row['area_um2']
        assert re.search(r'core_clk\s+'+str(period)+r'\.00', (folder/'clocks.rpt').read_text())
        constraints = constraint_rows((folder/'constraints.rpt').read_text())
        for section, key in [('max_delay/setup', 'setup_violations'), ('min_delay/hold', 'hold_violations')]:
            assert {normalize(r['endpoint']): r['slack'] for r in constraints.get(section, [])} == {
                normalize(r['endpoint']): r['slack'] for r in row[key]}
        queries[str(period)] = {name: paths((folder/(name+'.rpt')).read_text().replace(
                                   'frfcfs_scheduler_i/', 'frfcfs.scheduler_i/'))
                               for name in ['register_to_register', 'register_to_output']}
        assert all(p['slack_ns'] >= 0 for group in queries[str(period)].values() for p in group)
        publish_reports(folder, OUT/'analysis'/f'q16_{period}ns',
                        ['area.rpt', 'clocks.rpt', 'constraints.rpt', 'register_to_register.rpt', 'register_to_output.rpt'])
    dest = OUT/'variant/rtl/mc_scheduler_frfcfs.sv'
    dest.parent.mkdir(parents=True, exist_ok=True)
    shutil.copyfile(SOURCE/'trial/rtl/mc_scheduler_frfcfs.sv', dest)
    summary = dict(status='EXPERIMENT_COMPLETE', baseline_commit=eq['baseline_commit'],
        baseline_evidence='results/command_mask/summary.json', fresh_baseline_rerun=False,
        baseline_rtl_sha256=baseline, trial_rtl_sha256=trial, current_rtl_sha256=current,
        library_sha256=previous['library_sha256'], selected_variant=selected,
        trial_qualifies=all(checks.values()), adoption_checks=checks, runs=rows,
        equivalence=eq, lint=lint, negative_control=mutation, trace_pairs=trace['pairs'],
        trace_simulations=2*trace['pairs'], trace_accepted_total=2*sum(r['accepted_per_revision'] for r in trace['results']),
        trace_summary_sha256=sha(SOURCE/'trace_summary.json'),
        validation=validation, analysis_provenance=analysis, path_queries=queries,
        limits='Typical Q16 pre-layout DC, ideal clocks. Existing hold and zero-limit capacitance violations remain. No timing-closure or routed-Fmax claim.')
    (OUT/'summary.json').write_text(json.dumps(summary, indent=2)+'\n')
    shutil.copyfile(SOURCE/'trace_summary.json', OUT/'trace_summary.json')
    print(json.dumps(dict(selected=selected, trial_qualifies=all(checks.values()), checks=checks), indent=2))
    for r in rows:
        print(r['variant'], r['clock_ns'], r['area_um2'], r['setup_worst_slack_ns'],
              r['setup_tns_ns'], r['setup_violation_count'], r['internal_setup_violation_count'],
              r['worst_hold_slack_ns'], r['hold_violation_count'])


if __name__ == '__main__':
    main()
