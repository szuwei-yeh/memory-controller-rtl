# Project instructions

Follow the frozen v1 contracts in docs/architecture.md and docs/protocol-and-timing.md.
Use the names Strict Request FCFS or Strict-FCFS (HOL baseline), never imply this
baseline is the only FCFS interpretation.

After each meaningful architecture change, implementation step, debugging session,
regression, formal run, performance experiment, or synthesis run, append a dated
Traditional Chinese entry to local_notes/實驗日誌.md. Include 本次目標、完成事項、
修改檔案、執行指令、測試／實驗結果、發現的問題、設計決策與原因、下一步.
Preserve previous entries. Record failures and interruptions honestly. Use actual
local timestamps with timezone offsets. scripts/log_experiment.py provides an
append-only helper. Redact secrets from recorded commands.

local_notes/ is private, local-only, and must never be tracked, force-added,
uploaded, copied to the lab, or included in generated public documentation or
artifacts. Transfer only explicit allowlisted files. Check exclusions before export.
Remote CI must not create the private notebook; the append helper skips CI=true.
Lab runs use --lab and record ordinary per-run metadata; import retrieved results
locally with scripts/import_lab_results.py to append the corresponding notebook entries.

ASIC synthesis must use synth/rtl_files.f and mc_top only. Exclude simulation,
formal harnesses, workloads, notebooks, and verification infrastructure. Final ASIC
evidence comes from UCSB Design Compiler; optional local Yosys is only a sanity
check. Never invent lab results. Keep tool/environment limitations explicit.
