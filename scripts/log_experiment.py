#!/usr/bin/env python3
"""Append a private engineering entry. Never export or consume this as public data."""
import argparse
import os
from datetime import datetime
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]

def append_entry(title, goal, completed, files, commands, results, problems, decisions, next_step):
    # Remote CI keeps ordinary test metadata; it must not create a private notebook.
    if os.environ.get('CI', '').lower() == 'true':
        return
    path = ROOT / 'local_notes' / '實驗日誌.md'
    path.parent.mkdir(exist_ok=True)
    sections = [('本次目標', goal), ('完成事項', completed), ('修改檔案', files),
                ('執行指令', commands), ('測試／實驗結果', results),
                ('發現的問題', problems), ('設計決策與原因', decisions), ('下一步', next_step)]
    with path.open('a', encoding='utf-8') as f:
        f.write(f'\n## {datetime.now().astimezone():%Y-%m-%d %H:%M:%S %z} — {title}\n')
        for heading, value in sections:
            f.write(f'\n### {heading}\n{value or "無"}\n')

if __name__ == '__main__':
    p = argparse.ArgumentParser(description=__doc__)
    for key in ['title', 'goal', 'completed', 'files', 'commands', 'results', 'problems', 'decisions', 'next_step']:
        p.add_argument('--' + key.replace('_', '-'), default='無')
    append_entry(**vars(p.parse_args()))
