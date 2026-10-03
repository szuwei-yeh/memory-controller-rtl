#!/usr/bin/env python3
"""Check current RTL against published PPA/verification evidence, without EDA tools."""
import hashlib
import json
from pathlib import Path
import re
import subprocess

from dc_sweep_report import constraint_rows, paths
from hold_repair_report import measured, sdc_commands

ROOT = Path(__file__).resolve().parents[1]


def read(path):
    return json.loads(path.read_text())


def check_hold_repair(previous):
    folder = ROOT/'results/hold_repair'
    summary = read(folder/'summary.json')
    assert summary['status'] == 'EXPERIMENT_COMPLETE'
    assert summary['current_rtl_sha256'] == previous['current_rtl_sha256']
    assert summary['library_sha256'] == previous['library_sha256']
    assert summary['repair_script_sha256'] == hashlib.sha256((ROOT/'synth/dc/repair_hold.tcl').read_bytes()).hexdigest()
    for manifest in folder.glob('**/hashes.json'):
        for name, digest in read(manifest)['public'].items():
            assert hashlib.sha256((manifest.parent/name).read_bytes()).hexdigest() == digest
    assert [r['clock_ns'] for r in summary['runs']] == [3, 4]
    for row in summary['runs']:
        period = row['clock_ns']
        reports = ROOT/row['report_path']
        before, after = [measured(reports, prefix) for prefix in ['before', 'after']]
        assert before == row['before'] and after == row['after']
        baseline = next(r for r in previous['runs'] if r['variant'] == 'parallel_classes' and r['clock_ns'] == period)
        for key in ['area_um2', 'setup_worst_slack_ns', 'worst_hold_slack_ns',
                    'setup_violation_count', 'hold_violation_count', 'max_capacitance_violation_count']:
            assert before[key] == baseline[key]
        assert after['setup_violation_count'] == after['hold_violation_count'] == 0
        assert after['setup_worst_slack_ns'] == before['setup_worst_slack_ns']
        assert after['worst_hold_slack_ns'] >= 0
        assert before['sequential_cells'] == after['sequential_cells'] == 1974
        assert sdc_commands(reports/'before.sdc') == sdc_commands(reports/'after.sdc')
        assert row['constraints_identical_excluding_comments']
        assert row['inserted_buffers'] == after['buffer_cells']-before['buffer_cells']
        for key in ['max_capacitance_violation_count', 'zero_allowed_load_violation_count', 'max_transition_violation_count']:
            assert after[key] == before[key]
        point = row['provenance']
        for key, digest in previous['analysis_provenance']['points'][str(period)].items():
            assert point[key] == digest
        proof = summary['mapped_equivalence'][str(period)]
        assert proof['status'] == proof['equivalence']['status'] == 'PASS'
        assert proof['checker_sha256'] == hashlib.sha256((ROOT/'scripts/hold_repair_check.py').read_bytes()).hexdigest()
        eq, control = proof['equivalence'], proof['negative_control']
        assert eq['unproven_cells'] == 0 and eq['proven_cells'] > 0
        assert eq['before_sha256'] == point['report_sha256']['before.v']
        assert eq['after_sha256'] == point['report_sha256']['after.v']
        assert control['status'] == 'REJECTED' and control['unproven_cells'] > 0
        for label in ['equivalence', 'negative_control']:
            text = (folder/'checks'/reports.name/f'{label}_status.rpt').read_text()
            counts = re.search(r'Of those cells (\d+) are proven and (\d+) are unproven', text)
            assert counts and [int(counts[i]) for i in [1, 2]] == [proof[label]['proven_cells'], proof[label]['unproven_cells']]
        print(f"After hold repair Q16/{period} ns: area={after['area_um2']:.6f} um^2, "
              f"setup={after['setup_worst_slack_ns']:+.6f} ns, hold={after['worst_hold_slack_ns']:+.6f} ns / 0 endpoints")
    return summary


def check_setup_margin(previous):
    folder = ROOT/'results/setup_margin'
    summary = read(folder/'summary.json')
    digest = lambda path: hashlib.sha256(path.read_bytes()).hexdigest()
    assert summary['status'] == 'EXPERIMENT_COMPLETE'
    assert summary['baseline_evidence'] == 'results/hold_repair/summary.json'
    assert summary['current_rtl_sha256'] == previous['current_rtl_sha256']
    assert summary['library_sha256'] == previous['library_sha256']
    assert summary['setup_script_sha256'] == digest(ROOT/'synth/dc/improve_setup_margin.tcl')
    assert summary['publisher_sha256'] == digest(ROOT/'scripts/setup_margin_report.py')
    assert summary['setup_mode'] == 'preserve_zero_caps' and summary['setup_guard_ns'] == 0.05
    criteria = summary['predeclared_criteria']
    assert criteria['three_ns_setup_slack_at_least_ns'] == 0.020
    assert criteria['area_increase_at_most_percent'] == 5
    assert all(value is True for key, value in criteria.items() if key not in
               ['three_ns_setup_slack_at_least_ns', 'area_increase_at_most_percent'])
    for manifest in folder.glob('**/hashes.json'):
        for name, value in read(manifest)['public'].items():
            assert digest(manifest.parent/name) == value
    assert [r['clock_ns'] for r in summary['runs']] == [3, 4]
    for row in summary['runs']:
        period = row['clock_ns']
        assert row['queue_depth'] == 16 and row['policy'] == 'frfcfs_aging'
        old = next(r for r in previous['runs'] if r['clock_ns'] == period)
        reports = ROOT/row['report_path']
        before, after = [measured(reports, prefix) for prefix in ['before', 'after']]
        assert before == row['before'] == old['after'] and after == row['after']
        assert before['sequential_cells'] == after['sequential_cells'] == 1974
        assert after['setup_violation_count'] == after['hold_violation_count'] == 0
        assert after['setup_worst_slack_ns'] >= (0.020 if period == 3 else before['setup_worst_slack_ns'])
        assert after['worst_hold_slack_ns'] >= 0 and after['unconstrained_endpoint_count'] == 0
        assert after['area_um2'] <= 1.05*before['area_um2']
        assert row['area_increase_percent'] == 100*(after['area_um2']/before['area_um2']-1)
        for key in ['max_capacitance_violation_count', 'zero_allowed_load_violation_count',
                    'max_transition_violation_count']:
            assert after[key] <= before[key]
        assert sdc_commands(reports/'before.sdc') == sdc_commands(reports/'after.sdc')
        assert row['constraints_identical_excluding_comments']
        target = (reports/'optimization_target.sdc').read_text()
        assert re.search(r'set_clock_uncertainty -setup 0\.15\s+\[get_clocks core_clk\]', target)
        assert re.search(r'set_clock_uncertainty -hold 0\.1\s+\[get_clocks core_clk\]', target)
        restricted = (reports/'restricted_cells.rpt').read_text()
        assert set(re.findall(r'gscl45nm/(\w+)/Y max_capacitance=0\.000000', restricted)) == {
            'AOI21X1', 'AOI22X1', 'NAND2X1', 'NAND3X1', 'NOR2X1'}
        for prefix in ['before', 'after']:
            path = paths((reports/f'{prefix}_internal_setup.rpt').read_text())[0]
            assert path == row['register_to_register_setup'][prefix]
            assert path['classification'] == 'register-to-register' and path['slack_ns'] >= 0
        point = row['provenance']
        assert point['exit_code'] == 0 and point['point_qualifies']
        assert point['ddc_sha256'] == old['provenance']['report_sha256']['after.ddc']
        for key in ['config_sha256', 'sdc_sha256', 'library_sha256']:
            assert point[key] == old['provenance'][key]
        assert read(reports/'hashes.json')['raw'].items() <= point['report_sha256'].items()
        proof = summary['mapped_equivalence'][str(period)]
        assert proof['status'] == proof['equivalence']['status'] == 'PASS'
        assert proof['checker_sha256'] == digest(ROOT/'scripts/setup_margin_check.py')
        assert proof['shared_checker_sha256'] == digest(ROOT/'scripts/hold_repair_check.py')
        assert proof['liberty_sha256'] == previous['mapped_equivalence'][str(period)]['liberty_sha256']
        assert len(proof['registers']) == len(set(proof['registers'])) == 1974
        assert proof['equivalence']['port_maps_identical'] and proof['negative_control']['port_maps_identical']
        ports = proof['models']['before']['original_ports']
        assert all(direction in ['input', 'output'] and width > 0 for direction, width in ports.values())
        checks = folder/'checks'/reports.name
        for label in ['before', 'after', 'mutated']:
            model = proof['models'][label]
            assert model['original_ports'] == ports and model['latch_count'] == 0
            assert model['input_bits'] == 1974 + sum(n for d, n in ports.values() if d == 'input')
            assert model['output_bits'] == 3948 + sum(n for d, n in ports.values() if d == 'output')
            assert digest(checks/f'{label}.map') == model['port_map_sha256']
            assert model['port_map_sha256'] == proof['models']['before']['port_map_sha256']
        for label in ['before', 'after']:
            assert proof['models'][label]['netlist_sha256'] == point['report_sha256'][f'{label}.v']
        assert proof['negative_control']['status'] == 'REJECTED'
        assert proof['equivalence']['exit_code'] == proof['negative_control']['exit_code'] == 0
        assert re.search(r'^Networks are equivalent(?:\.| after structural hashing\.)',
                         (checks/'equivalence.log').read_text(), re.M)
        assert digest(checks/'equivalence.log') == proof['equivalence']['log_sha256']
        assert 'Networks are NOT EQUIVALENT.' in (checks/'negative_control_status.rpt').read_text()
        assert all(summary['adoption_checks'][str(period)].values())
        print(f"After setup-margin mapping Q16/{period} ns: area={after['area_um2']:.6f} um^2, "
              f"setup={after['setup_worst_slack_ns']:+.6f} ns, hold={after['worst_hold_slack_ns']:+.6f} ns / 0 endpoints")
    return summary


def main():
    folder = ROOT/'results/parallel_arbitration'
    summary = read(folder/'summary.json')
    assert summary['status'] == 'EXPERIMENT_COMPLETE'
    assert summary['selected_variant'] == 'parallel_classes'
    assert summary['trial_qualifies'] and all(summary['adoption_checks'].values())
    sources = summary['current_rtl_sha256']
    assert sources == summary['trial_rtl_sha256']
    assert set(sources) == set((ROOT/'synth/rtl_files.f').read_text().split())
    for name, digest in sources.items():
        assert hashlib.sha256((ROOT/name).read_bytes()).hexdigest() == digest, name
    assert (ROOT/'rtl/mc_scheduler_frfcfs.sv').read_bytes() == (
        folder/'variant/rtl/mc_scheduler_frfcfs.sv').read_bytes()
    reference = ROOT/'formal/reference/parallel_arbitration/mc_scheduler_frfcfs.sv'
    assert hashlib.sha256(reference.read_bytes()).hexdigest() == summary['baseline_rtl_sha256']['rtl/mc_scheduler_frfcfs.sv']
    assert summary['lint']['status'] == 'PASS' and summary['lint']['source_sha256'] == sources
    assert summary['negative_control']['status'] == 'REJECTED'
    assert summary['negative_control']['unproven_cells'] > 0
    validation = read(folder/'validation_summary.json')
    assert validation == summary['validation']
    assert validation['status'] == 'PASS' and validation['source_sha256'] == sources
    for eq in [summary['equivalence'], validation['current_equivalence']]:
        assert eq['status'] == 'PASS' and eq['source_sha256'] == sources
        assert len(eq['results']) == 9
        assert {(r['queue_depth'], r['policy']) for r in eq['results']} == {
            (q, p) for q in [1, 3, 16] for p in ['strict', 'frfcfs', 'aging']}
        assert all(r['status'] == 'PASS' and r['unproven_cells'] == 0 for r in eq['results'])
    assert validation['counts']['test']['runs'] == 42
    assert validation['counts']['regress']['runs'] == 300
    assert validation['counts']['regress']['accepted'] == 3003000
    assert len(validation['controller_formal']) == 5
    assert all(r['status'] == 'PASS' for r in validation['controller_formal'])
    trace_file = folder/'trace_summary.json'
    assert hashlib.sha256(trace_file.read_bytes()).hexdigest() == summary['trace_summary_sha256']
    trace = read(trace_file)
    assert trace['status'] == 'PASS' and trace['pairs'] == len(trace['results']) == 120
    for label, build in trace['builds'].items():
        expected = summary['baseline_rtl_sha256'] if label.startswith('before/') else sources
        assert all(build['source_sha256'][p] == h for p, h in expected.items())
    for manifest in sorted(folder.glob('**/hashes.json')):
        for name, digest in read(manifest)['public'].items():
            assert hashlib.sha256((manifest.parent/name).read_bytes()).hexdigest() == digest, name
    for row in summary['runs']:
        if row['variant'] != 'parallel_classes':
            continue
        reports = ROOT/row['report_path']
        assert row['metadata']['rtl_sha256'] == sources
        area = float(re.search(r'Total cell area:\s+([\d.]+)', (reports/'area.rpt').read_text())[1])
        assert area == row['area_um2']
        assert min(p['slack_ns'] for p in paths((reports/'timing.rpt').read_text())) == row['setup_worst_slack_ns']
        assert min(p['slack_ns'] for p in paths((reports/'hold.rpt').read_text())) == row['worst_hold_slack_ns']
        constraints = constraint_rows((reports/'constraints.rpt').read_text())
        for section, key in [('max_delay/setup', 'setup_violation_count'),
                             ('min_delay/hold', 'hold_violation_count'),
                             ('max_capacitance', 'max_capacitance_violation_count')]:
            assert len(constraints.get(section, [])) == row[key]
        assert row['setup_pass'] and row['hold_violation_count'] > 0
        print(f"Before hold repair Q16/{row['clock_ns']} ns: area={area:.6f} um^2, setup={row['setup_worst_slack_ns']:+.6f} ns, "
              f"hold={row['worst_hold_slack_ns']:+.6f} ns / {row['hold_violation_count']} endpoints")
    from capacitance_report import check_published
    check_published(ROOT/'results/capacitance_diagnosis', check_setup_margin(check_hold_repair(summary)))
    tracked = subprocess.check_output(['git', 'ls-files', '-z'], cwd=ROOT).decode().split('\0')
    assert not any(p.startswith('local_notes/') for p in tracked)
    assert not any(p.endswith(('.db', '.ddc', '.lib')) for p in tracked if p)
    print('PASS: current source, published report hashes, timing/area numbers and verification summaries agree.')
    print('Evidence audit only: this does not rerun simulation, formal proofs or licensed synthesis.')


if __name__ == '__main__':
    main()
