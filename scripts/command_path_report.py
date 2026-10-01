#!/usr/bin/env python3
"""Audit and publish read-only path queries for the selected command-mask DDC."""
import argparse
from collections import Counter
import csv
import hashlib
import json
from pathlib import Path
import re
import subprocess

from dc_sweep_report import constraint_rows, paths
from storage_timing_report import publish_reports, read, sha

ROOT = Path(__file__).resolve().parents[1]
NUMBER = r'-?\d+\.\d+'
ARC = re.compile(r'^\s*(\S+) \(([^)]+)\)\s+(?:<-\s+)?(' + NUMBER +
                 r')\s+(' + NUMBER + r')\s+(' + NUMBER + r')\s+([rf])\s*$')
NET = re.compile(r'^\s*(\S+) \(net\)\s+(?:(\d+)\s+)?(' + NUMBER +
                 r')\s+(' + NUMBER + r')\s+(' + NUMBER + r')\s+([rf])\s*$')
STAGES = ['clock_to_q', 'address_comparison_distribution', 'bank_candidates',
          'scheduler', 'command_mux']
REPORTS = ['area.rpt', 'check_timing.rpt', 'clocks.rpt', 'constraints.rpt',
           'timing.rpt', 'register_to_output.rpt', 'register_to_register.rpt',
           'input_to_register.rpt', 'input_to_output.rpt', 'hold.rpt',
           'command_mask_nets.rpt']


def detail(block):
    """Partition this register-to-command path; retain signed cell increments.

    A net row with explicit fanout identifies the preceding driver arc. Alias
    net rows have no fanout and must not double-count a hierarchical boundary.
    This parser deliberately rejects nonzero net delay: it describes this
    pre-layout, zero-wire-capacitance analysis, not an arbitrary routed report.
    """
    start = block.splitlines()[0].strip()
    end = re.search(r'Endpoint:\s+(\S+)', block)[1]
    arrival = float(re.search(r'data arrival time\s+(' + NUMBER + ')', block)[1])
    required = float(re.search(r'data required time\s+(' + NUMBER + ')', block)[1])
    slack = float(re.search(r'slack \((?:MET|VIOLATED)\)\s+(' + NUMBER + ')', block)[1])
    assert abs(required - arrival - slack) < 2e-6
    arcs, last, phase = [], None, STAGES[1]
    for line in block.split('  data arrival time')[0].splitlines():
        match = ARC.match(line)
        if match and '/' in match[1]:
            last = match.groups()
        net_match = NET.match(line)
        if not net_match or net_match[2] is None:
            continue
        assert last is not None, line
        pin, cell, transition, delay, path, edge = last
        net, fanout, cap, net_delay, net_path, _ = net_match.groups()
        assert float(net_delay) == 0 and abs(float(net_path) - float(path)) < 2e-6
        if cell.startswith('DFF'):
            stage = STAGES[0]
        elif pin.startswith('table_i/') and phase == STAGES[1]:
            stage = phase
        elif pin.startswith('candidates_i/'):
            stage = phase = STAGES[2]
        elif pin.startswith(('frfcfs.scheduler_i/', 'frfcfs_scheduler_i/')):
            stage = phase = STAGES[3]
        elif pin.startswith('U'):
            if phase == STAGES[3]:
                phase = STAGES[4]
            stage = phase
        else:
            raise ValueError(f'Unclassified driver: {pin}')
        arcs.append(dict(pin=pin, cell=cell, stage=stage, increment_ns=float(delay),
                         arrival_ns=float(path), transition_ns=float(transition),
                         net=net, fanout=int(fanout), capacitance_ff=1000*float(cap), edge=edge))
        last = None
    assert arcs and arcs[0]['stage'] == STAGES[0]
    assert abs(sum(a['increment_ns'] for a in arcs) - arrival) < len(arcs)*1e-6
    stages, previous = [], 0
    for stage in STAGES:
        group = [a for a in arcs if a['stage'] == stage]
        assert group, stage
        boundary = group[-1]['arrival_ns']
        stages.append(dict(stage=stage, delay_ns=round(boundary-previous, 6),
                           end_ns=boundary, cells=len(group)))
        previous = boundary
    masks = [dict(a, net=a['net'].split('/')[-1]) for a in arcs
             if re.fullmatch(r'select_mask\[\d+\]', a['net'].split('/')[-1])]
    assert len(masks) == 1
    return dict(startpoint=start, endpoint=end, arrival_ns=arrival, required_ns=required,
                slack_ns=slack, mask=masks[0], arcs=arcs, stages=stages)


def normalized(name):
    return re.sub(r'\[(\d+)\]', r'_\1_', name)


def violation_map(rows):
    return {normalized(r['endpoint']): r['slack'] for r in rows}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--source', type=Path, default=ROOT/'build/command_path_3ns')
    args = parser.parse_args()
    source, out = args.source, ROOT/'results/command_path_3ns'
    previous = read(ROOT/'results/command_mask/summary.json')
    baseline = next(r for r in previous['runs']
                    if (r['variant'], r['clock_ns']) == ('mask_and_storage', 3))
    provenance = read(source/'provenance.json')
    assert (source/'SUCCESS').is_file()
    assert provenance['read_only'] and not provenance['constraints_reapplied']
    assert provenance['rtl_sha256'] == previous['current_rtl_sha256']
    # Check the historical checkpoint, so this collector remains usable after
    # later RTL experiments. The original mapping predates the checkpoint commit.
    for path, digest in provenance['rtl_sha256'].items():
        data = subprocess.check_output(['git', 'show', f"{provenance['source_commit']}:{path}"], cwd=ROOT)
        assert hashlib.sha256(data).hexdigest() == digest, path
    assert re.fullmatch(r'[0-9a-f]{64}', provenance['ddc_sha256'])
    assert provenance['config_sha256'] == baseline['metadata']['lab_config_sha256']
    assert provenance['library_sha256'] == previous['library_sha256']
    assert provenance['sdc_sha256'] == baseline['metadata']['flow_sha256']['synth/constraints/controller.sdc']
    assert provenance['script_sha256'] == sha(ROOT/'synth/dc/analyze_command_paths.tcl')
    report = lambda name: (source/name).read_text()
    assert not any(re.search(r'^Error:', report(name), re.M) for name in REPORTS)
    assert float(re.search(r'Total cell area:\s+([\d.]+)', report('area.rpt'))[1]) == baseline['area_um2']
    assert re.search(r'core_clk\s+3\.00\s+\{0 1\.5\}', report('clocks.rpt'))
    assert int(re.search(r'Number of sequential cells:\s+(\d+)', report('area.rpt'))[1]) == 1974
    checks = report('check_timing.rpt')
    assert 'Checking unconstrained_endpoints...' in checks
    assert checks.split('Checking unconstrained_endpoints...', 1)[1].split('Information:', 1)[0].strip() in ['', '1']
    constraints = constraint_rows(report('constraints.rpt'))
    for section, key in [('max_delay/setup', 'setup_violations'), ('min_delay/hold', 'hold_violations')]:
        assert violation_map(constraints[section]) == violation_map(baseline[key])
    assert len(constraints['max_delay/setup']) == 50
    assert len(constraints['min_delay/hold']) == 8
    assert len(constraints['max_capacitance']) == baseline['max_capacitance_violation_count']
    queries = {name[:-4]: paths(report(name).replace('frfcfs_scheduler_i/', 'frfcfs.scheduler_i/'))
               for name in REPORTS if name.endswith('.rpt') and name not in REPORTS[:4] + ['command_mask_nets.rpt']}
    for path in queries['input_to_output']:
        path['classification'] = 'input-to-output'
    all_paths = queries['timing']
    assert len(all_paths) == len({p['endpoint'] for p in all_paths}) == 60
    failing = [p for p in all_paths if p['slack_ns'] < 0]
    assert len(failing) == 50 and all(p['endpoint'].startswith('cmd_') for p in failing)
    endpoint_slacks = {p['endpoint']: p['slack'] for p in constraints['max_delay/setup']}
    assert {p['endpoint'] for p in failing} == set(endpoint_slacks)
    # Two report_timing slacks differ from report_constraint by its last
    # printed digit (0.000001 ns); original/query constraint rows match exactly.
    rounding_differences = {p['endpoint']: round(p['slack_ns']-endpoint_slacks[p['endpoint']], 6)
                            for p in failing if p['slack_ns'] != endpoint_slacks[p['endpoint']]}
    assert all(abs(delta) <= 1e-6 for delta in rounding_differences.values())
    details = [detail(block) for block in report('timing.rpt').split('  Startpoint:')[1:50+1]]
    assert [(p['endpoint'], p['slack_ns']) for p in details] == [(p['endpoint'], p['slack_ns']) for p in failing]
    assert min(p['slack_ns'] for p in queries['hold']) == baseline['worst_hold_slack_ns']
    top = details[:20]
    shared = set.intersection(*[{a['pin'] for a in p['arcs']} for p in top])
    nets = {}
    for block in re.split(r"(?m)^net '", report('command_mask_nets.rpt'))[1:]:
        name = block.split("':", 1)[0]
        cap = re.search(r'total capacitance:\s+min:([\d.]+)\s+max:([\d.]+)', block)
        nets[name] = dict(loads=int(re.search(r'number of loads:\s+(\d+)', block)[1]),
                          min_capacitance_ff=1000*float(cap[1]), max_capacitance_ff=1000*float(cap[2]))
    for path in details:
        mask = path['mask']
        assert mask['fanout'] == nets[mask['net']]['loads']
        load = nets[mask['net']]
        assert min(abs(mask['capacitance_ff']-load[key]) for key in
                   ['min_capacitance_ff', 'max_capacitance_ff']) <= 0.001
    summary = dict(status='READ_ONLY_ANALYSIS_COMPLETE', provenance=provenance,
        baseline_evidence='results/command_mask/summary.json', baseline_variant='mask_and_storage',
        area_um2=baseline['area_um2'], sequential_cells=1974, clock_ns=3,
        setup_worst_slack_ns=baseline['setup_worst_slack_ns'], setup_tns_ns=baseline['setup_tns_ns'],
        setup_endpoint_count=50, hold_endpoint_count=8, hold_worst_slack_ns=baseline['worst_hold_slack_ns'],
        unconstrained_endpoint_count=0, max_capacitance_violation_count=len(constraints['max_capacitance']),
        all_constraint_violation_slacks_match_original=True,
        timing_vs_constraint_rounding_differences_ns=rounding_differences, queries=queries,
        worst_by_query={name: min(rows, key=lambda p: p['slack_ns']) for name, rows in queries.items()},
        top20_startpoints=dict(Counter(p['startpoint'] for p in top)),
        top20_masks=dict(Counter(p['mask']['net'] for p in top)),
        failing_startpoints=dict(Counter(p['startpoint'] for p in details)),
        failing_masks=dict(Counter(p['mask']['net'] for p in details)),
        top20_shared_driver_pins=sorted(shared), command_mask_nets=nets,
        representative_paths=details[:2],
        limits='Saved typical-corner pre-layout DDC with ideal clock; no compile, new PPA result, routing or signoff. Signed reported cell increments retained.')
    out.mkdir(parents=True, exist_ok=True)
    summary['report_hashes'] = publish_reports(source, out/'reports', REPORTS)
    (out/'summary.json').write_text(json.dumps(summary, indent=2)+'\n')
    (out/'failing_path_details.json').write_text(json.dumps(details, indent=2)+'\n')
    rows = []
    for rank, p in enumerate(top, 1):
        row = {k: p[k] for k in ['startpoint', 'endpoint', 'arrival_ns', 'required_ns', 'slack_ns']}
        row.update(rank=rank, select_mask=p['mask']['net'], mask_fanout=p['mask']['fanout'],
                   mask_capacitance_ff=p['mask']['capacitance_ff'], cell_arcs=len(p['arcs']))
        row.update({s['stage']+'_ns': s['delay_ns'] for s in p['stages']})
        rows.append(row)
    with (out/'top20.csv').open('w', newline='') as f:
        writer = csv.DictWriter(f, fieldnames=list(rows[0]), lineterminator='\n')
        writer.writeheader()
        writer.writerows(rows)
    print(f'PASS: 60 unique endpoints; all 50 setup and 8 hold violations match; {len(shared)} shared top-20 drivers.')


if __name__ == '__main__':
    main()
