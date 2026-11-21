# Multibagger Scout AI - new custom-UI build (transfer package)

## What this is

A complete, locally verified build of Logeshwaran's Multibagger Scout AI as a NEW website with a custom-designed UI. The entire original archive backend (agents, engine, services, database, tests) runs unmodified underneath. The UI is a Streamlit custom component (vanilla JS) that talks to that backend through one RPC layer. Provenance: original archive came from his uploaded ZIP on 20 Nov 2026 (re-sent 21 Nov, verified byte-identical; the archive itself was never in his public repo's history); the custom UI + RPC layer were built 20-21 Nov.

## Layout

- `app.py` - Streamlit entry: secrets->env passthrough, optional APP_PASSWORD gate, per-session visitor id, component mount, native download tray (including base64 binary payloads such as workspace backups).
- `handler.py` - RPC layer mapping the UI's ~27 actions to the archive's own services/engine/database calls. Provider swap by env: `SCOUT_PROVIDER=synthetic` (default unset = Yahoo connector), `SCOUT_NEWS=synthetic` (default = RSS connector via `NEWS_FEED_TEMPLATE`). Visitor isolation by env: `SCOUT_ISOLATION=visitor`.
- `component/` - the custom UI: index.html + app1.js (core/charts) + app2.js + app3.js (screens) + bundled streamlit-component-lib. Static files, no build step.
- `.streamlit/config.toml` - dark theme, minimal toolbar.
- `multibagger_scout_ai/` - the original archive, code unmodified. Excluded from this copy as runtime/test artifacts: `scout.db`, `logs/app.log`, generated `exports/`, `visitors/`, `.pytest_cache`, `__pycache__`.
- `requirements.txt` - corrected pins. The archive's own requirements.txt listed 5 versions that do not exist (pandas 3.0.6, numpy 2.5.4, SQLAlchemy 2.1.9, fastapi 0.164.0, streamlit 1.67.0); these corrected pins were installed and verified by running the archive's full test suite.
- `tests-e2e/` - the puppeteer harnesses used to exercise every screen headlessly (test-a..d cover all screens; test-e covers two-visitor isolation). Not needed to run the app (they need node + Chrome).

## Visitor isolation (SCOUT_ISOLATION=visitor)

Built 21 Nov 2026 to satisfy the approved model: no password, separate workspaces per visitor.

- Each browser session gets a random visitor id (`secrets.token_hex(8)` in Streamlit session_state, sent with every RPC). Server side the id is sanitized to a bare alphanumeric token, so it can never be used as a path outside `visitors/`; a missing/empty id is REJECTED with "workspace session identity missing" and never falls back to shared state.
- Every visitor gets their OWN SQLite database at `<archive>/visitors/<vid>.db` (schema auto-initialized), their own export directory `<archive>/exports/<vid>/`, capped at 25 visitor DBs with LRU eviction of IDLE ones. A database with an in-flight request is never evicted; if too many workspaces are active at once the cap is exceeded rather than breaking a live visitor. An evicted idle visitor's next request recreates a fresh EMPTY workspace, never someone else's data.
- The background scheduler is OFF in isolation mode (multi-visitor scheduling would cross workspaces).
- Floor 00 hides the shared host application-log block, shows the visitor's OWN database size (never the shared host DB's), and shows a "private session workspace" banner; the building overview footer shows the same note. Log/backup functions are NOT removed: they are scoped to each visitor. "Back up database now" snapshots ONLY that visitor's DB (sqlite backup API) as a native download ("Download your workspace backup (.db)"). The automation cycle's built-in backup is disabled in isolation because the archive's backup targets the shared host path.
- Demo mode (`SCOUT_PROVIDER=synthetic`) contacts NO external source: provider and news are in-process fakes, no notification channels are configured, and the direct "Download NSE equity list" button returns a truthful unavailable notice instead of probing the exchange website.
- Unset `SCOUT_ISOLATION` (or set anything else) to restore the original single-shared-database behavior.

### Isolation qualification (21 Nov 2026)

- `tests-e2e/test-f-unit.py` (server-side, synthetic env): path-traversal vid (`../../etc/evil`) confined to `visitors/etcevil.db`; empty/missing vid rejected; 8 threads uploading distinct CSVs simultaneously each land only in their own DB; an in-flight visitor DB survives 8 churn visitors with the cap forced to 4; idle eviction stays bounded and a recreated workspace is empty, never foreign; report exports land strictly under `exports/<vid>/`.
- `tests-e2e/test-f.mjs` (headless Chrome, two browser contexts): CONCURRENT research runs (A on ALPHA, B on GAMMA at the same moment) each stay bound to their own session; afterwards A still shows its 2-row universe and B its empty one; the demo NSE-download notice renders; a null vid is rejected with the identity error; a fresh reload recovers cleanly. Zero page errors.

## Run

```
python -m venv venv && pip install -r requirements.txt
SCOUT_PROVIDER=synthetic SCOUT_NEWS=synthetic SCOUT_ISOLATION=visitor streamlit run app.py   # public-visitor demo mode, no network, clearly labelled synthetic data
streamlit run app.py                       # default: shared DB, Yahoo connector (see data-rights note)
```

Env/secrets (all optional unless noted): `DATABASE_URL` (default `sqlite:///scout.db`; per-visitor DBs replace it in isolation mode), `APP_PASSWORD` (access gate; unset = open), `SCOUT_ARCHIVE` (where app.py finds the archive; defaults to the bundled `./multibagger_scout_ai`), `SCOUT_ISOLATION=visitor`, `NEWS_FEED_TEMPLATE`, plus the notifier/SMTP/Telegram/webhook keys listed in app.py's passthrough.

## Verified state (21 Nov 2026, local)

- Archive: 35/35 tests pass offline on the corrected pins.
- UI: every screen and flow exercised in headless Chrome with zero page errors - overview, floors f00-f07, full research run (all 8 agents), candlestick+EMA chart, report generation + in-page viewer, risk assessment, simulated order placement, exits check, decision ranking, universe listing CSV upload, all three downloads (HTML/JSON/CSV content-verified), mobile 390px layout.
- Isolation E2E (test-e.mjs, two separate browser contexts = two visitors, synthetic mode): visitor A imported a 2-row universe CSV and ran research; visitor B simultaneously saw an empty universe with the "nothing is guessed" empty-state banner. Server proof: two separate visitor DB files with 2 and 0 universe rows respectively. Both saw the private-workspace banner, neither saw the host application log, both got their own native workspace-backup download. Zero page errors.
- Synthetic mode is prominently labelled in the UI, the report footer, and the download filenames. Paper trading is strictly simulated (paper_broker, no broker API anywhere in the archive).

## Open gates at packaging time

- Deployment remains PAUSED on market-data source rights for a public free app: research found NO verified permitted free server-side data source among the candidates checked (Stooq forbids redistribution without consent; Yahoo ToS restricts automated collection/reproduction; free API-key tiers verified personal/individual-use only, e.g. Alpha Vantage; NSE/BSE restrict automated access). TradingView embeddable widgets are a verified permitted client-side chart-display option (free with attribution kept) but cannot feed the server-side research pipeline.
- Free-host persistence: on Streamlit Community Cloud the local filesystem is ephemeral (verified from Streamlit's own forum), so per-visitor DBs are session scratchpads wiped on reboot/redeploy/sleep. The UI's workspace banner must keep disclosing this; the per-visitor backup download is the visitor's own recovery path.
- Import path: the archive has a designed provider seam (data/connectors/base.py MarketDataProvider + ProviderResult; tests/synthetic.py is a complete example). A provider keyed by each visitor's OWN data source (their own API key or uploaded files) fits this seam with no synthetic fill; without statements, the fundamental/business agents fail explicitly and scoring continues from available inputs (archive's own missing-data behavior).
- Note: synthetic mode imports the archive's `tests/synthetic.py`, whose header says "never import from application code"; `handler.py` does so deliberately and ONLY when `SCOUT_PROVIDER=synthetic`. Unset the env for real-provider runs.
