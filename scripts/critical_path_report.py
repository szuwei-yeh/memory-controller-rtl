#!/usr/bin/env python3
"""Break down the Q16/3 ns timing paths and read-only queries on the existing mapped DDC."""
import csv
from collections import Counter
import hashlib
import json
from pathlib import Path
import re

ROOT = Path(__file__).resolve().parents[1]
SOURCE_COMMIT = '12db3996def42219deb0d0d589ec2ac0c472f0cf'
EVIDENCE = ROOT/'results/address_sharing/summary.json'
OUT = ROOT/'results/critical_path_3ns'
STAGES = ['clock_to_q', 'address_preprocessing', 'bank_candidates', 'scheduler', 'output_selection']
LABELS = ['Launch clock-to-Q', 'Shared address comparison / buffering',
          'Dependency filtering + bank candidate selection / encoding',
          'FR-FCFS / aging arbitration + slot encoding', 'Slot decode + command output selection / buffering']
NUMBER = r'-?\d+\.\d+'
ARC = re.compile(r'^\s*(\S+) \(([^)]+)\)\s+('+NUMBER+r')\s+('+NUMBER+r')\s+('+NUMBER+r')\s+([rf])\s*$')
NET = re.compile(r'^\s*(\S+) \(net\)\s+(?:(\d+)\s+)?('+NUMBER+r')\s+('+NUMBER+r')\s+('+NUMBER+r')\s+([rf])\s*$')


def sha(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def parse_path(block, rank):
    start = block.splitlines()[0].strip()
    endpoint = re.search(r'Endpoint:\s+(\S+)', block)[1]
    arrival = float(re.search(r'data arrival time\s+('+NUMBER+r')', block)[1])
    required = float(re.search(r'data required time\s+('+NUMBER+r')', block)[1])
    slack = float(re.search(r'slack \((?:MET|VIOLATED)\)\s+('+NUMBER+r')', block)[1])
    assert abs(required-arrival-slack) < 0.000002
    phase = 'address_preprocessing'
    arcs, nets = [], []
    for line in block.split('  data arrival time')[0].splitlines():
        match = ARC.match(line)
        if match and float(match[4]) > 0:
            pin, cell, transition, delay, path, edge = match.groups()
            if cell.startswith('DFF'):
                stage = 'clock_to_q'
            elif pin.startswith('candidates_i/'):
                stage = phase = 'bank_candidates'
            elif pin.startswith('frfcfs.scheduler_i/'):
                stage = phase = 'scheduler'
            elif pin.startswith('U') and pin.count('/') == 1:
                if phase == 'scheduler':
                    phase = 'output_selection'
                stage = phase
            else:
                raise RuntimeError(f'Unexpected positive-delay point: {line}')
            arcs.append(dict(stage=stage, pin=pin, cell=cell, transition_ns=float(transition),
                             increment_ns=float(delay), arrival_ns=float(path), edge=edge))
        match = NET.match(line)
        if match:
            net, fanout, cap, delay, path, edge = match.groups()
            # Hierarchical aliases can repeat a net's capacitance, but fanout is
            # only counted on rows that explicitly report it. Never sum aliases.
            assert float(delay) == 0, 'This decomposition expects recorded zero net delay'
            if fanout is not None:
                assert arcs, 'A reported load must follow a driving cell'
                nets.append(dict(net=net, driver=arcs[-1]['pin'], stage=arcs[-1]['stage'],
                    fanout=int(fanout), capacitance_ff=round(float(cap)*1000, 6),
                    net_delay_ns=float(delay), arrival_ns=float(path), edge=edge))
    assert len(nets) == len(arcs), 'Unexpected pin/net correspondence'
    assert abs(sum(a['increment_ns'] for a in arcs)-arrival) < len(arcs)*0.000001
    assert abs(arcs[-1]['arrival_ns']-arrival) < 0.000002
    observed = [a['stage'] for i,a in enumerate(arcs) if i == 0 or arcs[i-1]['stage'] != a['stage']]
    assert observed == STAGES, 'Unexpected path topology'
    stages, previous = [], 0.0
    for key, label in zip(STAGES, LABELS):
        if key == 'address_preprocessing' and 'candidates_i/same_address[' not in block:
            label = 'Address distribution / buffering (no shared comparator on this path)'
        group = [a for a in arcs if a['stage'] == key]
        end = group[-1]['arrival_ns']
        stage_nets = [n for n in nets if n['stage'] == key]
        stages.append(dict(stage=key, description=label, cells_on_path=len(group),
            start_ns=previous, end_ns=end, delay_ns=round(end-previous, 6),
            percent_of_arrival=100*(end-previous)/arrival,
            first_pin=group[0]['pin'], last_pin=group[-1]['pin'],
            max_reported_fanout=max(n['fanout'] for n in stage_nets),
            max_reported_capacitance_ff=max(n['capacitance_ff'] for n in stage_nets)))
        previous = end
    return dict(rank=rank, startpoint=start, endpoint=endpoint, arrival_ns=arrival,
        required_ns=required, slack_ns=slack, cell_arcs=len(arcs),
        combinational_cell_arcs=len(arcs)-1, stages=stages, arcs=arcs, nets=nets)


def write_csv(name, rows):
    with (OUT/name).open('w', newline='') as stream:
        writer = csv.DictWriter(stream, fieldnames=list(rows[0]), lineterminator='\n')
        writer.writeheader(); writer.writerows(rows)


def supplementary_queries(evidence, original, original_folder):
    from dc_sweep_report import paths as parse_timing
    folder = OUT/'reports'
    hashes = json.loads((folder/'hashes.json').read_text())
    provenance = json.loads((folder/'provenance.json').read_text())
    assert all(sha(folder/name) == h for name,h in hashes['public'].items())
    assert provenance['rtl_sha256'] == evidence['current_rtl_sha256']
    assert provenance['library_sha256'] == evidence['library_sha256']
    assert provenance['config_sha256'] == original['metadata']['lab_config_sha256']
    assert provenance['sdc_sha256'] == sha(ROOT/'synth/constraints/controller.sdc')
    assert provenance['script_sha256'] == sha(ROOT/'synth/dc/analyze_paths.tcl')
    area = float(re.search(r'Total cell area:\s+([\d.]+)',(folder/'area.rpt').read_text())[1])
    assert area == original['area_um2']
    marker = 'Information: Checking generated_clocks...'
    # Updating-design/high-fanout notices occur when the timing engine is first
    # initialized; compare every actual check, not that incidental preamble.
    assert (folder/'check_timing.rpt').read_text().split(marker,1)[1] == (original_folder/'check_timing.rpt').read_text().split(marker,1)[1]
    clocks = (folder/'clocks.rpt').read_text()
    assert re.search(r'^core_clk\s+3\.00\s+\{0 1\.5\}',clocks,re.M)
    # The saved DDC was written after change_names. Normalize only the known
    # scheduler hierarchy alias for the description; keep raw register names.
    expanded_text = (folder/'timing.rpt').read_text()
    expanded = parse_timing(expanded_text.replace('frfcfs_scheduler_i/','frfcfs.scheduler_i/'))
    assert len(expanded) == len({p['endpoint'] for p in expanded}) == 100
    failed = {p['endpoint']:p for p in expanded if p['slack_ns'] < 0}
    assert set(failed) == {p['endpoint'] for p in original['setup_violations']}
    for violation in original['setup_violations']:
        assert abs(failed[violation['endpoint']]['slack_ns']-violation['slack']) < 0.000002
    for block in expanded_text.split('  Startpoint:')[1:]:
        endpoint = re.search(r'Endpoint:\s+(\S+)',block)[1]
        if endpoint in failed:
            assert 'candidates_i/' in block and 'frfcfs_scheduler_i/' in block
    assert all(p['classification'] == 'register-to-output' for p in failed.values())
    assert min(p['slack_ns'] for p in expanded) == original['setup_worst_slack_ns']
    classes = []
    for kind,name in [('register-to-output','timing.rpt'),
                      ('register-to-register','register_to_register.rpt'),
                      ('input-to-register','input_to_register.rpt'),
                      ('input-to-output','input_to_output.rpt')]:
        text = (folder/name).read_text()
        rows = parse_timing(text)
        if kind == 'register-to-output':
            rows = [p for p in rows if p['classification'] == kind]
        worst = min(rows,key=lambda p:p['slack_ns'])
        classes.append(dict(path_class=kind,reported_paths=len(rows),unique_endpoints=len({p['endpoint'] for p in rows}),
            worst_slack_ns=worst['slack_ns'],startpoint=worst['startpoint'],endpoint=worst['endpoint'],
            report=str((folder/name).relative_to(ROOT))))
    return dict(read_only_ddc=True,constraints_reapplied=False,rtl_modified=False,
        identical_area_um2=area,identical_worst_setup_slack_ns=original['setup_worst_slack_ns'],
        all_51_setup_endpoints_reproduced=True,all_failed_paths_cross_candidates_and_scheduler=True,
        failed_startpoint_counts=dict(Counter(p['startpoint'] for p in failed.values())),
        expanded_paths=expanded,path_classes=classes,provenance=provenance,
        report_hashes=hashes['public'],
        scope='Overall report has 100 distinct endpoints. Focused class reports may contain alternatives to the same endpoint. These are constrained static paths, not claims of simultaneous functional sensitization.')


def main():
    evidence = json.loads(EVIDENCE.read_text())
    row = next(r for r in evidence['runs'] if (r['variant'],r['queue_depth'],r['clock_ns']) ==
               ('shared_address',16,3))
    baseline = next(r for r in evidence['runs'] if (r['variant'],r['queue_depth'],r['clock_ns']) ==
                    ('baseline',16,3))
    for name, digest in evidence['current_rtl_sha256'].items():
        assert sha(ROOT/name) == digest, 'RTL no longer matches the analyzed implementation'
    sdc = ROOT/'synth/constraints/controller.sdc'
    assert sha(sdc) == row['metadata']['flow_sha256']['synth/constraints/controller.sdc']
    folder = ROOT/row['report_path']
    recorded = json.loads((folder/'hashes.json').read_text())
    assert sha(folder/'timing.rpt') == recorded['public']['timing.rpt']
    paths = [parse_path(b,i) for i,b in enumerate((folder/'timing.rpt').read_text().split('  Startpoint:')[1:],1)]
    assert len(paths) == 10
    assert min(p['slack_ns'] for p in paths) == row['setup_worst_slack_ns']
    assert all(p['required_ns'] == 1.9 for p in paths)
    groups = []
    for name in ['cmd_wdata','cmd_row','cmd_col','cmd_bank','cmd_op','cmd_valid']:
        violations = [p for p in row['setup_violations'] if p['endpoint'].split('[')[0] == name]
        groups.append(dict(port=name, violating_endpoints=len(violations),
            worst_slack_ns=min(p['slack'] for p in violations),
            best_violating_slack_ns=max(p['slack'] for p in violations)))
    assert sum(g['violating_endpoints'] for g in groups) == row['setup_violation_count'] == 51
    assert abs(sum(v['slack'] for v in row['setup_violations'])-row['setup_tns_ns']) < 0.000002
    worst = paths[0]
    shared_prefix = 0
    for index,arc in enumerate(worst['arcs']):
        if not all(len(p['arcs']) > index and p['arcs'][index]['pin'] == arc['pin'] for p in paths):
            break
        shared_prefix += 1
    cohorts = []
    for startpoint in dict.fromkeys(p['startpoint'] for p in paths):
        cohort = [p for p in paths if p['startpoint'] == startpoint]
        prefix = 0
        for i,arc in enumerate(cohort[0]['arcs']):
            if not all(len(p['arcs']) > i and p['arcs'][i]['pin'] == arc['pin'] for p in cohort):
                break
            prefix += 1
        cohorts.append(dict(startpoint=startpoint,paths=len(cohort),common_prefix_cell_arcs=prefix,
            common_prefix_last_pin=cohort[0]['arcs'][prefix-1]['pin'] if prefix else None))
    queries = supplementary_queries(evidence, row, folder)
    report = dict(status='COMPLETE',source_commit=SOURCE_COMMIT,new_sta_run=True,new_synthesis_run=False,
        supplementary_sta=queries,
        source_sha256={str(p.relative_to(ROOT)):sha(p) for p in [EVIDENCE,folder/'timing.rpt',sdc]},
        rtl_sha256=evidence['current_rtl_sha256'],
        tool=evidence['tool'],library_sha256=evidence['library_sha256'],
        corner='GSCL45nm typical, 1.1 V, 27 C',queue_depth=16,policy='frfcfs_aging',
        budget=dict(clock_ns=3.0,uncertainty_ns=0.1,output_delay_ns=1.0,
                    required_ns=1.9,arrival_ns=worst['arrival_ns'],slack_ns=worst['slack_ns']),
        prior_round_worst_setup_slack_ns=baseline['setup_worst_slack_ns'],
        setup_tns_ns=row['setup_tns_ns'],violating_endpoints=groups,
        reported_path_count=len(paths),common_prefix_cell_arcs=shared_prefix,
        common_prefix_last_pin=worst['arcs'][shared_prefix-1]['pin'] if shared_prefix else None,
        startpoint_counts=dict(Counter(p['startpoint'] for p in paths)),startpoint_cohorts=cohorts,
        paths=[{k:v for k,v in p.items() if k not in ['arcs','nets']} for p in paths],
        highest_fanout_nets=sorted(worst['nets'],key=lambda n:(n['fanout'],n['capacitance_ff']),reverse=True)[:8],
        largest_combinational_arcs=sorted(worst['arcs'][1:],key=lambda a:a['increment_ns'],reverse=True)[:8],
        methodology='Stages use consecutive mapped hierarchy boundaries and cumulative arrival differences. Cell counts include inverters/buffers, not RTL operator depth. Increment sums are checked within printed rounding precision. Capacitance converts pF to fF; alias rows are not summed.',
        limits='Original top-10 paths plus 100 mapped-DDC paths and focused class queries; all 51 setup violations covered. Not an exhaustive path/sensitization analysis. No new synthesis, physical extraction, power, or signoff. Zero net delay in these reports does not imply zero physical wire delay. Hold and library max-cap violations remain.')
    report['analysis_script_sha256'] = sha(Path(__file__))
    report['source_sha256']['synth/dc/analyze_paths.tcl'] = sha(ROOT/'synth/dc/analyze_paths.tcl')
    OUT.mkdir(parents=True,exist_ok=True)
    (OUT/'summary.json').write_text(json.dumps(report,indent=2)+'\n')
    write_csv('worst_stages.csv',worst['stages'])
    write_csv('worst_arcs.csv',worst['arcs'])
    write_csv('worst_nets.csv',worst['nets'])
    write_csv('violating_endpoints.csv',groups)
    write_csv('expanded_paths.csv',queries['expanded_paths'])
    write_csv('path_classes.csv',queries['path_classes'])
    write_csv('top_paths.csv',[{k:p[k] for k in ['rank','startpoint','endpoint','arrival_ns','required_ns','slack_ns','cell_arcs','combinational_cell_arcs']} for p in paths])
    table = ['| Stage | Delay (ns) | Arrival (ns) | Share of arrival | Cells on path |',
             '|---|---:|---:|---:|---:|']
    for stage in worst['stages']:
        table.append(f"| {stage['description']} | {stage['delay_ns']:.6f} | {stage['end_ns']:.6f} | {stage['percent_of_arrival']:.2f}% | {stage['cells_on_path']} |")
    document = ROOT/'docs/experiments/critical-path-3ns.md'
    text = document.read_text()
    start,end = '<!-- stage-table -->','<!-- /stage-table -->'
    assert text.count(start) == text.count(end) == 1
    prefix,rest = text.split(start); _,suffix = rest.split(end)
    document.write_text(prefix+start+'\n\n'+'\n'.join(table)+'\n\n'+end+suffix)
    print(f"Verified {len(paths)} paths, {len(worst['arcs'])} worst-path cell arcs and 51 setup violations.")
    print('Worst stages:',[(s['stage'],s['delay_ns']) for s in worst['stages']])
    print('Shared top-10 prefix:',shared_prefix,report['common_prefix_last_pin'])


if __name__ == '__main__':
    main()
