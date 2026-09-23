#!/usr/bin/env python3
"""Frozen v1.1 stability study; historical comparison is built only under build/."""
import concurrent.futures
import csv
import hashlib
import json
import math
from pathlib import Path
import random
import shutil
import statistics
import subprocess

import run
from log_experiment import append_entry

ROOT = Path(__file__).resolve().parents[1]
SEEDS = list(range(1, 20)) + [42]
METRICS = ['responses_per_cycle', 'mean_latency', 'p95', 'p99', 'maximum_latency']
OUT = ROOT / 'results/perf_stability'


def hashes():
    return {str(p.relative_to(ROOT)): hashlib.sha256(p.read_bytes()).hexdigest()
            for folder in ['rtl', 'tb'] for p in sorted((ROOT / folder).glob('*.sv'))}


def spread(values):
    return dict(mean=statistics.mean(values), stdev=statistics.stdev(values),
                median=statistics.median(values), minimum=min(values), maximum=max(values))


def paired_stats(values):
    rng = random.Random(20260922)
    samples = sorted(statistics.mean(rng.choices(values, k=len(values))) for _ in range(10000))
    positive = sum(x > 0 for x in values)
    negative = sum(x < 0 for x in values)
    n = positive + negative
    p = min(1.0, 2 * sum(math.comb(n, k) for k in range(min(positive, negative) + 1)) / 2**n) if n else 1.0
    return {**spread(values), 'positive': positive, 'zero': len(values)-n,
            'negative': negative, 'bootstrap_mean_95_ci': [samples[249], samples[9749]],
            'two_sided_sign_test_p': p}


def summarize(rows):
    groups = []
    for policy in run.POLICIES:
        for workload in ['random', 'hot_cold', 'hol']:
            for ready in [100, 50, 20]:
                chosen = [r for r in rows if (r['revision'], r['policy'], r['workload'], r['ready_percent']) ==
                          ('v1.1', policy, workload, ready)]
                assert len(chosen) == len(SEEDS)
                groups.append(dict(policy=policy, workload=workload, ready_percent=ready,
                                   metrics={m: spread([r[m] for r in chosen]) for m in METRICS}))
    paired = []
    for policy in run.POLICIES:
        def index(revision):
            return {r['seed']: r for r in rows if (r['revision'], r['policy'], r['workload'], r['ready_percent']) ==
                    (revision, policy, 'random', 50)}
        old, new = index('v1.0'), index('v1.1')
        assert set(old) == set(new) == set(SEEDS)
        paired.append(dict(policy=policy,
            before={m: spread([old[s][m] for s in SEEDS]) for m in METRICS},
            after={m: spread([new[s][m] for s in SEEDS]) for m in METRICS},
            delta={m: paired_stats([new[s][m]-old[s][m] for s in SEEDS]) for m in METRICS},
            per_seed=[dict(seed=s, **{m: new[s][m]-old[s][m] for m in METRICS}) for s in SEEDS]))
    return groups, paired


def main():
    frozen = hashes()
    OUT.mkdir(parents=True, exist_ok=True)
    (OUT / 'frozen_sources.json').write_text(json.dumps(frozen, indent=2)+'\n')
    append_entry('v1.1 多種子效能穩定性研究：固定實驗設計',
        '凍結控制器與測試平台，評估三種工作負載、三種就緒比例及三種排程策略。',
        '預先固定種子 1–19 與 42；每次暖身 200 筆、量測 2000 筆；規劃 540 次 v1.1 與 60 次舊版 random/50% 配對比較。',
        'scripts/perf_stability.py；results/perf_stability/；RTL 與測試平台無修改。',
        'python3 scripts/perf_stability.py', '研究開始；尚未宣告結果。',
        'hot_cold 與 hol 的地址及讀寫序列不隨種子改變，只有資料內容改變；就緒訊號為週期性阻塞而非獨立隨機事件。',
        '沿用既有刺激避免增加功能；舊版僅於 build/ 隔離建置，以相同種子比較 p99 差值；不得修改工作目錄 RTL。',
        '完成自我檢查模擬、逐種子統計與配對分析。')
    rows = []
    try:
        binaries = {('v1.1', p): run.build(p) for p in run.POLICIES}
        # Reconstruct the historical response module with the published reverse patch.
        historical = ROOT / 'build/perf_stability/baseline'
        files = (ROOT / 'synth/rtl_files.f').read_text().split() + ['synth/rtl_files.f', 'tb/dram_model.sv', 'tb/tb_top.sv']
        for name in files:
            target = historical / name
            target.parent.mkdir(parents=True, exist_ok=True)
            shutil.copyfile(ROOT / name, target)
        subprocess.run(['patch', '-R', '-p1', '-i', str(ROOT/'results/response_refill.patch')],
                       cwd=historical, check=True, capture_output=True, text=True)
        expected = json.loads((ROOT/'results/response_refill_before.json').read_text())['synthesis_run']['rtl_sha256']
        assert all(hashlib.sha256((historical/name).read_bytes()).hexdigest() == digest for name, digest in expected.items())
        try:
            run.ROOT = historical
            for p in run.POLICIES:
                binaries['v1.0', p] = run.build(p)
        finally:
            run.ROOT = ROOT
        tasks = [('v1.1', p, w, ready, seed) for p in run.POLICIES for w in [3, 4, 5]
                 for ready in [100, 50, 20] for seed in SEEDS]
        tasks += [('v1.0', p, 3, 50, seed) for p in run.POLICIES for seed in SEEDS]

        def measure(task):
            revision, policy, workload, ready, seed = task
            result = run.simulate(binaries[revision, policy], policy, seed, 2000, workload=workload,
                ready=ready, warmup=200, trace=True,
                label=f'stability_{revision}_{policy}_w{workload}_r{ready}_s{seed}')
            m = result['metrics']; lat = m['latency']['end_to_end']
            return dict(revision=revision, policy=policy, workload=run.WORKLOADS[workload],
                ready_percent=ready, seed=seed, responses_per_cycle=m['responses_per_cycle'],
                mean_latency=lat['mean'], p95=lat['p95'], p99=lat['p99'], maximum_latency=lat['max'],
                accepted=result['accepted'], measured=m['requests'], measurement_cycles=m['measurement_cycles'],
                path=result['path'])

        with concurrent.futures.ThreadPoolExecutor(max_workers=4) as pool:
            for row in pool.map(measure, tasks):
                rows.append(row)
                if len(rows) % 30 == 0:
                    print(f'PASS {len(rows)}/{len(tasks)}', flush=True)
        assert hashes() == frozen, 'Frozen RTL/testbench changed during study'
        with (OUT/'per_seed.csv').open('w', newline='') as f:
            writer = csv.DictWriter(f, fieldnames=list(rows[0]))
            writer.writeheader(); writer.writerows(rows)
        groups, paired = summarize(rows)
        report = dict(status='PASS', seeds=SEEDS, warmup=200, measured_per_run=2000,
            final_runs=540, historical_random_ready50_runs=60,
            accepted_total=sum(r['accepted'] for r in rows), frozen_sources_verified=True,
            baseline_rtl_sha256=expected,
            builds={f'{rev}/{p}': json.loads((b.parent/'build_config.json').read_text()) for (rev,p), b in binaries.items()},
            methodology={'latency':'response consumption minus request acceptance, in cycles',
                'throughput':'2000 measured responses / (last consumption - first acceptance + 1)',
                'percentile':'sorted per-request sample at floor(q*(n-1)); no pooling across seeds',
                'ready':'cycle modulo 100 < ready_percent; forced ready during final drain',
                'traffic':'25% writes; interval 1; load 100%; fixed 10-request directed prelude',
                'geometry':'simulation ROWS=8 COLS=8, four banks, Q_DEPTH=16; default timing tCCD=2',
                'uncertainty':'10000 paired-seed bootstrap resamples, RNG seed 20260922; descriptive 95% intervals, no multiplicity correction',
                'limitation':'hot_cold and hol seeds change payloads only, not address/operation sequences'},
            distributions=groups, paired_random_ready50=paired, per_seed=rows)
        (OUT/'summary.json').write_text(json.dumps(report, indent=2)+'\n')
        (ROOT/'build/perf_stability/commands.json').write_text(json.dumps(run.COMMANDS, indent=2)+'\n')
        details = '\n'.join(f"- {p['policy']}：p99 平均差 {p['delta']['p99']['mean']:.2f} 週期，增加／持平／減少種子數 {p['delta']['p99']['positive']}/{p['delta']['p99']['zero']}/{p['delta']['p99']['negative']}，配對重抽樣平均差 95% 區間 {p['delta']['p99']['bootstrap_mean_95_ci']}。" for p in paired)
        append_entry('v1.1 多種子效能穩定性研究：模擬與配對統計完成',
            '完成凍結設計的效能穩定性研究及舊版配對比較。',
            '600 次自我檢查模擬全部通過，包含 540 次 v1.1 與 60 次舊版；確認 RTL 與測試平台雜湊未變。',
            'results/perf_stability/per_seed.csv、summary.json、frozen_sources.json；build/ 下逐次記錄與隔離舊版建置。',
            'python3 scripts/perf_stability.py；詳細實際建置與模擬指令位於 build/perf_stability/commands.json。',
            f"共接受 {report['accepted_total']} 筆交易；量測 1200000 筆，全部完成回應。\n"+details,
            'hot_cold 與 hol 的多種子結果只驗證資料變化，不代表多種隨機地址樣本；收尾時就緒訊號強制為一。',
            '以同種子新舊差值判斷 p99 變化，避免將不同刺激誤認為微架構效果；所有分位數先逐次計算再摘要。',
            '整理公開研究報告與限制，向使用者回報後停止；不修改 RTL。')
        print(json.dumps(paired, indent=2), flush=True)
    except BaseException as exc:
        append_entry('v1.1 穩定性研究未完成', '執行固定研究。', f'已收集 {len(rows)} 次結果。',
            'scripts/perf_stability.py；build/；results/perf_stability/。', 'python3 scripts/perf_stability.py',
            '失敗或中斷，尚不可宣告研究完成。', str(exc), '保留實際狀態，不修改 RTL。', '排查實驗流程問題。')
        raise


if __name__ == '__main__':
    main()
