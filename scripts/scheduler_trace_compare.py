#!/usr/bin/env python3
"""Compare complete event traces for v1.1 and the current controller."""
import concurrent.futures
import hashlib
import json
from pathlib import Path
import shutil

import run
from log_experiment import append_entry
from scheduler_equiv import baseline_source

ROOT = Path(__file__).resolve().parents[1]


def main(sources=None, label='scheduler'):
    if sources is None:
        sources = {'rtl/mc_scheduler_frfcfs.sv': baseline_source()}
    out = ROOT / 'build' / f'{label}_trace_compare'
    historical = out / 'baseline'
    files = (ROOT/'synth/rtl_files.f').read_text().split()+[
        'synth/rtl_files.f', 'tb/dram_model.sv', 'tb/tb_top.sv']
    for name in files:
        target = historical / name
        target.parent.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(ROOT/name, target)
    for name, source in sources.items():
        (historical/name).write_text(source)
    binaries = {}
    try:
        for revision, root in [('before', historical), ('after', ROOT)]:
            run.ROOT = root
            for policy in run.POLICIES:
                binaries[revision, policy] = run.build(policy)
    finally:
        run.ROOT = ROOT
    tasks = [(policy, w, seed, ready) for policy in run.POLICIES
             for w in range(len(run.WORKLOADS)) for seed in [1, 42] for ready in [100, 30]]
    results = []
    def compare(task):
        policy, workload, seed, ready = task
        pair = []
        for revision in ['before', 'after']:
            result = run.simulate(binaries[revision, policy], policy, seed, 500,
                workload=workload, ready=ready, trace=True,
                label=f'{label}_compare_{revision}_{policy}_w{workload}_s{seed}_r{ready}')
            pair.append(result)
        traces = [(ROOT / r['path'] / 'events.csv').read_bytes() for r in pair]
        if traces[0] != traces[1]:
            raise RuntimeError(f'Cycle trace mismatch: {task}')
        return dict(policy=policy, workload=run.WORKLOADS[workload], seed=seed,
                    ready=ready, accepted_per_revision=pair[0]['accepted'],
                    trace_sha256=hashlib.sha256(traces[0]).hexdigest(),
                    before_path=pair[0]['path'], after_path=pair[1]['path'])
    status = '未完成'
    try:
        with concurrent.futures.ThreadPoolExecutor(max_workers=4) as pool:
            for result in pool.map(compare, tasks):
                results.append(result)
                if len(results) % 20 == 0:
                    print(f'Identical traces: {len(results)}/{len(tasks)} pairs', flush=True)
        status = 'PASS'
    finally:
        report = dict(status=status, pairs=len(results), workload_requests=500,
            warmup=0, seeds=[1,42], ready_percent=[100,30], results=results,
            builds={f'{revision}/{policy}':json.loads((binary.parent/'build_config.json').read_text())
                    for (revision,policy),binary in binaries.items()})
        (out/'summary.json').write_text(json.dumps(report, indent=2)+'\n')
        append_entry(f'{label} 優化逐週期 trace 配對', '確認完整控制器的接受、命令、完成與回應事件不變。',
            f'完成 {len(results)}/{len(tasks)} 組新舊配對。', f'build/{label}_trace_compare/；build/runs/{label}_compare_*',
            'python3 scripts/scheduler_trace_compare.py' if label=='scheduler' else 'python3 scripts/address_equiv.py --trace', status,
            '有限刺激的逐位元組 CSV 比較，不能替代形式證明。',
            '三政策、十工作負載、兩 seeds、兩 ready 比例；使用相同 testbench 和相同請求序列。',
            '與 mapped synthesis、形式證明一起判斷修改。')


if __name__ == '__main__':
    main()
