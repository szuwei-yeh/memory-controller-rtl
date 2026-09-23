# Toolchain used for local evidence

- Verilator 5.046 (2026-02-28).
- Yosys 0.68+post, git c12172fbae8af5e20f6fb52e3d4e92d56ed587b6.
- SymbiYosys source commit b1a1e98cba941ec8433f8dc27f416cd7bb7f14be.
- ABC supplied with Yosys; BMC3 and PDR engines.
- Python 3.13; Click 8.5.0 for the local SymbiYosys checkout.
- Matplotlib 3.11.2 and NumPy 2.5.3 for standalone figures.

Example isolated formal setup from the project root:

```sh
mkdir -p .tools
git clone https://github.com/YosysHQ/sby.git .tools/sby
git -C .tools/sby checkout b1a1e98cba941ec8433f8dc27f416cd7bb7f14be
python3 -m venv .tools/venv
.tools/venv/bin/pip install click==8.5.0
make formal
```

For figures, install into the same isolated environment and use the report target:

```sh
.tools/venv/bin/pip install -r scripts/requirements-plot.txt
make report
```

The isolated environment also avoids mixing host Python binary architectures.

Yosys and its ABC executable must be on PATH. The runner prefers an installed
`sby`, otherwise it uses the ignored local checkout and virtual environment.
Z3 was available but the integrated symbolic-data run timed out with it; final
tasks use ABC and do not require Z3. The local checkout is a dependency, not
vendored project source. The CI smoke job uses the distribution's Verilator;
run metadata identifies the actual simulator version used for each result.
