# Multibagger Scout AI

A research tool for NSE and BSE stocks. It reads public data, runs eight analysis agents, scores each stock, and writes reports.
It is research only. It never places real orders and has no broker connection. Floor 04 is a simulation.
A "multibagger" label is a research hypothesis, never a promise of returns. This is not investment advice.

## Install on Windows 11 (4 GB RAM is enough)
1. Install Python 3.11 or newer from python.org. Tick "Add python.exe to PATH".
2. Double-click `setup.bat`. It creates a private Python folder, installs everything, creates the database and runs the tests.
3. Double-click `run_app.bat`. Your browser opens the app. (`run_dashboard.bat` does the same.)

Other files: `run_backend.bat` (API on 127.0.0.1 only), `run_pipeline.bat` (one daily run), `backup_database.bat` (copies the database to the `backups` folder).

## The eight floors (left panel, or click a card on the Building overview)
| Floor | What it does |
|---|---|
| 00 Central Command | Last and next run, coverage, settings, task queue, database health, data-source health, logs |
| 01 Market Scanner | Imports the NSE/BSE lists, scans in resumable batches, keeps your watchlist |
| 02 AI Analyst | Runs the eight agents on one stock; charts, financials, valuation, news, scores, reports |
| 03 Risk Manager | Risk class with evidence, sizing and risk/reward (illustration only) |
| 04 Paper Executor | SIMULATED orders, stops and targets, history |
| 05 Monitor and Alerts | Alerts, price rules (checked on end-of-day data) |
| 06 Portfolio Manager | Simulated holdings, profit and loss, exposure |
| 07 Final Decision Engine | Ranks stocks and gives APPROVE / WATCHLIST / REJECT with reasons |

## How the daily research works
The pipeline scans the stock list in batches, deep-researches the best candidates, updates scores and ranking, saves reports,
raises alerts and retries failures. It runs at the time set on Floor 00 (default 18:30 IST, Monday to Friday) **only while this app is running
and the computer is on**. It is batch research on end-of-day data, not continuous monitoring. Market holidays are not modelled.
For unattended runs on Windows, point Task Scheduler at `run_pipeline.bat`. For an online website, read `DEPLOY_ONLINE.md`.

## How scores work
Fundamental, technical, data confidence (each /100) and risk (/100, higher = riskier). Every sub-score is shown with its evidence.
Missing data earns 0 points and is listed as missing, so scores are deliberately conservative: with the free data used here the
fundamental score can reach at most 75 and data confidence about 81. Long-term = 70% fundamental + 30% technical. Short-term = 30% fundamental + 70% technical.
Balanced = 50% long-term + 50% short-term. A critical risk is always shown, whatever the score.

## Data and its limits
- Prices and financials: Yahoo Finance through `yfinance`. Unofficial, end-of-day or delayed, no guarantee. Yahoo can slow or block requests, especially from cloud servers.
- News: public RSS headlines. They are unverified and labelled so.
- NSE list: downloaded from the NSE archive address in `config/settings.py` (it may change). If the download fails, upload the CSV yourself on Floor 01. BSE: upload a CSV.
- Not built yet: official NSE/BSE announcement feeds, promoter holding and pledge, industry and peer valuation, PDF reports, 4-hour and 1-hour charts, bank-specific metrics, login for several users, schema migrations beyond version 1.
- Financial line-item names from Yahoo were never checked against live data in development. If a metric shows "n/a" for a company you know has it, tell the developer.

## Troubleshooting
- "Python was not found": reinstall Python and tick "Add python.exe to PATH".
- A stock shows "Data provider failed": Yahoo refused or the symbol is wrong. Wait and retry. Nothing is estimated.
- Port already in use: close other copies of the app, or run `streamlit run app.py --server.port 8502`.
- Tests fail during `setup.bat`: send the text shown to the developer. Do not ignore a failed test.

## Automation agent (Floor 00)
One supervised cycle, run by the scheduler, by `run_pipeline.bat`, by the GitHub workflow, or by the button on Floor 00:
1. Skips if another pipeline run is already in progress.
2. Tests that the data provider answers (retries). If it does not, the pipeline is NOT run and you are told. Nothing is estimated.
3. Runs the daily pipeline; if the whole run fails it runs once more.
4. Checks that the newest stored price date is not stale.
5. Writes a short digest (coverage, new APPROVE names, critical risks, new alerts, problems), backs up a local SQLite database, and sends the digest to any channel you configured.
It is rule-based, with no AI language model. Notifications are optional: set one of NTFY_TOPIC, TELEGRAM_*, SMTP_* or WEBHOOK_URL (see `.env.example`).
The notification senders were tested with simulated network calls only, never against the real services.
