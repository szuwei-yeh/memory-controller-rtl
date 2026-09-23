#!/usr/bin/env python3
"""Parse executed DC reports, preserving timing violations and source provenance."""
import csv
import hashlib
import json
import re
from collections import Counter
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
POLICIES = ['strict_fcfs', 'frfcfs', 'frfcfs_aging']
PERIODS = [20, 10, 8, 5, 4, 3, 2]


def paths(text):
    result=[]
    for block in text.split('  Startpoint:')[1:]:
        start=block.splitlines()[0].split()[0]
        end=re.search(r'Endpoint:\s+(\S+)', block)[1]
        slack=float(re.search(r'slack \((?:MET|VIOLATED)\)\s+(-?[\d.]+)', block)[1])
        start_info=block.split('Endpoint:')[0]
        end_info=block.split('Endpoint:')[1].split('Path Group:')[0]
        sr='flip-flop' in start_info; er='flip-flop' in end_info
        kind=('register-to-register' if sr and er else 'input-to-register' if 'input port' in start_info and er
              else 'register-to-output' if sr and 'output port' in end_info else 'other')
        stages=[]
        # Infer architectural blocks only from explicit hierarchy in the reported path.
        labels={'table_i':'transaction-table registers/data logic', 'candidates_i':'dependency/row-hit and bank-candidate selection',
                'frfcfs.scheduler_i':'FR-FCFS arbitration', 'strict_fcfs.scheduler_i':'Strict Request FCFS selection',
                'response_i':'same-address response eligibility/arbitration', 'banks_i':'bank state/timing logic'}
        for line in block.splitlines():
            for name,label in labels.items():
                if name+'/' in line and label not in stages: stages.append(label)
        if end.startswith('cmd_wdata'): stages.append('command write-data mux/output')
        elif end.startswith('cmd_'): stages.append('command decode/output')
        elif end.startswith('rsp_'): stages.append('host response output')
        if start.startswith('table_i/occupied_reg') and end.startswith('table_i/addresses_reg'):
            stages=['occupancy/free-slot admission logic', 'allocation/address-register write-enable logic']
            if 'table_i/req_ready' in block: stages.insert(1,'request-ready/acceptance gating')
        if start=='rst':
            stages=(['reset output masking', 'host response-valid output'] if end=='rsp_valid'
                    else ['reset fanout and register/output gating'])
        result.append(dict(startpoint=start, endpoint=end, slack_ns=slack, classification=kind,
                           logic_description=' -> '.join(stages) or 'top-level port/register logic'))
    if not result: raise RuntimeError('Missing timing paths')
    return result


def constraint_rows(text):
    sections={}; section=None
    pattern=r'^\s*(\S+)\s+([+-]?[\d.]+)\s+([+-]?[\d.]+)(?:\s+[rf])?\s+([+-]?[\d.]+)\s+\(VIOLATED[^)]*\)'
    for block in re.split(r'(?m)^\s{3}(?=max_delay/setup|min_delay/hold|max_capacitance|max_transition)',text):
        name=next((key for key in ['max_delay/setup','min_delay/hold','max_capacitance','max_transition'] if block.startswith(key)),None)
        if name:
            sections[name]=[dict(endpoint=m[0], required=float(m[1]), actual=float(m[2]), slack=float(m[3]))
                            for m in re.findall(pattern,block,re.M)]
    return sections


def parse_run(folder):
    meta=json.loads((folder/'run.json').read_text())
    if meta['status']!='PASS': raise RuntimeError(f'Incomplete DC flow {folder}')
    text=lambda name:(folder/name).read_text()
    errors=[x for name in ['tool.log','check_timing.rpt','check_design.rpt','constraints.rpt']
            for x in text(name).splitlines() if x.startswith('Error:')]
    if errors: raise RuntimeError(str(errors))
    setup=paths(text('timing.rpt')); hold=paths(text('hold.rpt')); sections=constraint_rows(text('constraints.rpt'))
    sv=sections.get('max_delay/setup',[]); hv=sections.get('min_delay/hold',[]); cv=sections.get('max_capacitance',[])
    qor=text('qor.rpt')
    qcount=lambda label:int(float(re.search(re.escape(label)+r':\s+([\d.]+)',qor)[1]))
    assert len(sv)==qcount('No. of Violating Paths'), (folder,'setup counts',len(sv),qcount('No. of Violating Paths'))
    assert len(hv)==qcount('No. of Hold Violations'), (folder,'hold counts',len(hv),qcount('No. of Hold Violations'))
    assert len(cv)==qcount('Max Cap Violations')
    checks=text('check_timing.rpt')
    assert 'Checking unconstrained_endpoints...' in checks
    # Do not infer zero from a missing or unfamiliar diagnostic section.
    unc=checks.split('Checking unconstrained_endpoints...',1)[1].split('Information:',1)[0].strip()
    if unc not in ['', '1']: raise RuntimeError(f'Review unconstrained endpoint diagnostic: {unc}')
    area=text('area.rpt')
    value=lambda label:float(re.search(re.escape(label)+r':\s+([\d.]+)',area)[1])
    warning_counts={name:dict(Counter(re.findall(r'^Warning:.*?\(([A-Z]+-\d+)\)',text(name),re.M)))
                    for name in ['tool.log','check_design.rpt','check_timing.rpt']}
    worst=min(setup,key=lambda p:p['slack_ns'])
    row=dict(policy=meta['policy'],queue_depth=meta['queue_depth'],clock_ns=meta['clock_ns'],
        area_um2=value('Total cell area'),combinational_area_um2=value('Combinational area'),
        sequential_area_um2=value('Noncombinational area'),setup_worst_slack_ns=worst['slack_ns'],
        setup_wns_ns=min(0,worst['slack_ns']),setup_tns_ns=round(sum(p['slack'] for p in sv),6),
        setup_violation_count=len(sv),worst_hold_slack_ns=min(p['slack_ns'] for p in hold),hold_violation_count=len(hv),
        unconstrained_endpoint_count=0,critical_startpoint=worst['startpoint'],critical_endpoint=worst['endpoint'],
        critical_logic_description=worst['logic_description'],setup_pass=len(sv)==0 and worst['slack_ns']>=0,
        max_capacitance_violation_count=len(cv),zero_allowed_load_violation_count=sum(p['required']==0 for p in cv),
        warning_counts=warning_counts,setup_paths=setup,hold_paths=hold,
        setup_violations=sv,hold_violations=hv,metadata=meta)
    return row


def write_summaries(rows):
    out=ROOT/'results/dc_sweep'
    expected={(p,16,t) for p in POLICIES for t in PERIODS}|{(p,q,5) for p in POLICIES for q in [4,8,16,32]}
    actual={(r['policy'],r['queue_depth'],r['clock_ns']) for r in rows}
    assert actual==expected and len(rows)==30
    freeze=json.loads((out/'frozen_inputs.json').read_text())
    assert all(hashlib.sha256((ROOT/p).read_bytes()).hexdigest()==h for p,h in freeze.items())
    for r in rows:
        assert r['metadata']['rtl_sha256']=={p:h for p,h in freeze.items() if p.startswith('rtl/')}
        assert r['metadata']['flow_sha256']['synth/constraints/controller.sdc']==freeze['synth/constraints/controller.sdc']
    assert len({r['metadata']['lab_config_sha256'] for r in rows})==1
    assert len({json.dumps(r['metadata']['flow_sha256'],sort_keys=True) for r in rows})==1
    baseline=json.loads((ROOT/'results/dc_baseline/summary.json').read_text())
    baseline_meta=json.loads((ROOT/'results/dc_baseline/run.json').read_text())
    assert all(r['metadata']['lab_config_sha256']==baseline_meta['lab_config_sha256'] for r in rows)
    repeated=next(r for r in rows if (r['policy'],r['queue_depth'],r['clock_ns'])==('frfcfs_aging',16,5))
    assert repeated['area_um2']==baseline['area_um2']
    assert repeated['setup_worst_slack_ns']==baseline['setup_worst_slack_ns']
    assert repeated['worst_hold_slack_ns']==baseline['hold_worst_slack_ns']
    rows=sorted(rows,key=lambda r:(POLICIES.index(r['policy']),r['queue_depth'],-r['clock_ns']))
    fastest={}
    for p in POLICIES:
        passing=[r for r in rows if r['policy']==p and r['queue_depth']==16 and r['setup_pass']]
        best=min(passing,key=lambda r:r['clock_ns']) if passing else None
        fastest[p]=dict(clock_ns=best['clock_ns'],frequency_MHz=1000/best['clock_ns']) if best else None
    summary=dict(status='COMPLETE',runs=rows,fastest_tested_setup_passing_q16=fastest,
        accepted_baseline_area_setup_hold_reproduced=True,
        interpretation='Setup pass only; hold and inherited library capacitance violations are not waived. No exact maximum frequency claim.',
        setup_tns_definition='Sum of negative endpoint slacks printed to six decimal places in report_constraint; one reported worst slack per violating endpoint.',
        unconstrained_endpoint_definition='Count reported by check_timing unconstrained_endpoints diagnostic (verified empty in every run).')
    (out/'summary.json').write_text(json.dumps(summary,indent=2)+'\n')
    fields=[k for k,v in rows[0].items() if not isinstance(v,(dict,list))]+['synthesis_warnings']
    with (out/'summary.csv').open('w',newline='') as f:
        w=csv.DictWriter(f,fieldnames=fields);w.writeheader()
        for r in rows:
            w.writerow({**{k:r[k] for k in fields if k!='synthesis_warnings'},'synthesis_warnings':json.dumps(r['warning_counts'],sort_keys=True)})
    return summary


if __name__=='__main__':
    folders=sorted((ROOT/'build/dc_sweep/runs').iterdir())
    summary=write_summaries([parse_run(p) for p in folders if (p/'run.json').exists()])
    print(json.dumps(summary['fastest_tested_setup_passing_q16'],indent=2))
