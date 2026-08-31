# Development Setup

This project is primarily used on **Windows** — the PowerShell bootstrap
path below is the primary one. Linux/macOS instructions follow it.

## Windows (primary)

From a PowerShell prompt, at the repository root:

```powershell
.\scripts\bootstrap_dev.ps1
```

If PowerShell blocks script execution (`... cannot be loaded because
running scripts is disabled on this system`), run once as the current
user (not administrator):

```powershell
Set-ExecutionPolicy -Scope CurrentUser RemoteSigned
```

then re-run `bootstrap_dev.ps1`. The script:

1. Creates a virtual environment at `.venv` (override with `$env:VENV_DIR`).
2. Activates it.
3. Upgrades `pip`.
4. Installs the project and its dev dependencies (`pip install -e ".[dev]"`).
5. Runs `pae system doctor` to verify every core dependency actually
   imports.
6. Runs `pae constitution verify` and a minimal `pytest` smoke test as a
   final health check.

To re-activate the environment in a new PowerShell session later:

```powershell
.\.venv\Scripts\Activate.ps1
```

## Linux / macOS

```bash
bash scripts/bootstrap_dev.sh
```

Same five steps as the Windows script, using the platform's native
`venv`/activation. Re-activate later with:

```bash
source .venv/bin/activate
```

## Manual setup (either platform)

If you'd rather not use the bootstrap script:

```bash
python3 -m venv .venv
source .venv/bin/activate        # .\.venv\Scripts\Activate.ps1 on Windows
pip install --upgrade pip
pip install -e ".[dev]"
pae system doctor
```

## Optional provider dependencies

`databento` and `requests` (GEXBOT's HTTP client) are **optional**
dependencies — nothing in the core research pipeline, the test suite, or
`pae research full-run` needs either. Install them only if you intend to
use a real provider:

```bash
pip install -e ".[databento]"   # real Databento historical/live adapters
pip install -e ".[gexbot]"      # real GEXBOT HTTP client
```

`pae system doctor` reports whether each is installed; their absence is
never silently swallowed — the adapters that need them raise a clear
`RuntimeError` naming exactly which package/extra to install if you call
a method that needs one you don't have.

`duckdb` and `pyarrow`, by contrast, are **core** (non-optional)
dependencies: the futures data lake's parquet/DuckDB round-trip
(`data/lake_query.py`, `data/loader.py`, `data/immutable_store.py`) is
part of the pipeline every `pae research *` command can reach, not a
provider-specific add-on.

## Environment variables / secrets

Copy `.env.example` to `.env` and fill in real values locally:

```bash
cp .env.example .env
```

```
GEXBOT_API_KEY=
DATABENTO_API_KEY=
```

`.env` is gitignored — never commit real API keys. Nothing in this
repository reads `.env` automatically (there's no `python-dotenv`
dependency); export the variables into your shell yourself, or use your
IDE's own `.env` support, before running a command that needs a real
provider (`pae options verify-provider`, `pae data ingest`, `pae data
record`).

## Running tests

```bash
pytest -q                              # everything
pytest -m "not network and not live" -q  # the deterministic offline suite
pytest -m "integration" -q             # cross-module integration tests only
pytest -m "provider" -q                # tests against a real (not mocked) provider client
pae system test                        # the same, grouped and summarized (UNIT/INTEGRATION/PROVIDER/NETWORK/LIVE)
```

As of this writing every test in this repository is offline and
deterministic — none carry the `network`/`provider`/`live` markers,
because none of them need real credentials to run (every provider
adapter accepts a dependency-injected client specifically so its tests
never touch the network). `pytest -m "not network and not live" -q` is
therefore currently identical to `pytest -q`; the marker infrastructure
exists so that changes so it stays true as new tests are added, not
because today's suite needs the filter to pass.

## Governance

Before running `pae research full-run`/`discover`/`gex-templates`, the
CLI verifies `config/research_constitution.yaml` against its lock file
(`pae constitution verify`) and refuses to run if it doesn't match. See
`docs/constitution_amendment_process.md` if you need to change the
Constitution itself.
