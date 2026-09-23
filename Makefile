PYTHON ?= python3
SEEDS ?= 100
N ?= 10000
JOBS ?= 4
PLOT_PYTHON ?= $(if $(wildcard .tools/venv/bin/python),.tools/venv/bin/python,$(PYTHON))
LAB_CONFIG ?= synth/lab_config.tcl
DC_RUN ?= build/synth/dc/frfcfs_aging_q16_5ns
.PHONY: lint test smoke regress perf formal report synth-local-sanity synth-dc sta-pt lab-bundle
lint:
	$(PYTHON) scripts/run.py lint
test:
	$(PYTHON) scripts/run.py test
smoke:
	$(PYTHON) scripts/run.py smoke
regress:
	$(PYTHON) scripts/run.py regress --seeds $(SEEDS) --n $(N) --jobs $(JOBS)
perf:
	$(PYTHON) scripts/run.py perf
formal:
	$(PYTHON) scripts/formal.py
report:
	$(PLOT_PYTHON) scripts/report.py
synth-local-sanity:
	$(PYTHON) scripts/synth.py local
synth-dc:
	$(PYTHON) scripts/synth.py dc --lab --config "$(LAB_CONFIG)"
sta-pt:
	$(PYTHON) scripts/synth.py pt --lab --config "$(LAB_CONFIG)" --run "$(DC_RUN)"
lab-bundle:
	$(PYTHON) scripts/lab_bundle.py
