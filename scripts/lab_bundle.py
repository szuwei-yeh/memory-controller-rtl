#!/usr/bin/env python3
"""Create a controller-only allowlisted lab bundle. Never walk the repository."""
import hashlib
import io
import json
from pathlib import Path
import subprocess
import tarfile
from log_experiment import append_entry
from synth import manifest

ROOT=Path(__file__).resolve().parents[1]

def main():
    files=manifest()+['synth/rtl_files.f','synth/lab_config.example.tcl',
        'synth/constraints/controller.sdc','synth/dc/run.tcl','synth/pt/run.tcl',
        'scripts/synth.py','docs/lab-flow.md']
    tracked=subprocess.run(['git','ls-files','--','local_notes'],cwd=ROOT,text=True,capture_output=True,check=True)
    if tracked.stdout.strip(): raise RuntimeError('Private notes are tracked; refusing export')
    ignored=subprocess.run(['git','check-ignore','-q','local_notes/實驗日誌.md'],cwd=ROOT)
    if ignored.returncode: raise RuntimeError('Private notes must be ignored before export')
    dest=ROOT/'build/lab_bundle.tar.gz'; dest.parent.mkdir(exist_ok=True)
    hashes={}
    with tarfile.open(dest,'w:gz') as archive:
        for name in files:
            path=(ROOT/name)
            if path.is_symlink() or 'local_notes' in path.parts or path.resolve()!=ROOT/name:
                raise RuntimeError(f'Unsafe export path {name}')
            hashes[name]=hashlib.sha256(path.read_bytes()).hexdigest()
            archive.add(path,arcname=name,recursive=False)
        data=(json.dumps(hashes,indent=2)+'\n').encode()
        info=tarfile.TarInfo('source_hashes.json'); info.size=len(data)
        archive.addfile(info,io.BytesIO(data))
    with tarfile.open(dest) as archive:
        if set(archive.getnames())!=set(files+['source_hashes.json']): raise RuntimeError('Bundle membership mismatch')
    append_entry('建立實驗室傳輸封裝','僅封裝控制器與綜合流程。','驗證 Git 忽略規則與封裝白名單。',
                 '無（僅產生 build/lab_bundle.tar.gz）','python3 scripts/lab_bundle.py',
                 '通過；未包含本機筆記、模型、測試平台或工作負載。','無',
                 '明確白名單避免遞迴上傳私人內容。','取得實驗室設定後執行 Design Compiler。')
    print(dest)

if __name__=='__main__': main()
