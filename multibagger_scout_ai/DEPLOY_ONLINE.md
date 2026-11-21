# Putting Multibagger Scout AI online (free)

I could not deploy this for you: it needs your own GitHub and hosting accounts. These are the steps, and the honest limits first.

## Limits you must know (checked November 2026; free-tier terms change, so confirm)
- **Streamlit Community Cloud** is free but has about 1 GB of memory, a disk that is wiped on restart, apps that go to sleep when nobody visits, and no uptime guarantee.
  So the SQLite file will not last: use a free hosted Postgres database (for example Neon or Supabase) and put its address in `DATABASE_URL`.
- **A sleeping app cannot run its own daily schedule.** The daily job must run elsewhere: the included GitHub Actions workflow
  (`.github/workflows/daily_pipeline.yml`). GitHub may delay or drop scheduled runs, and switches them off after 60 days with no repository activity in public repositories.
  Use a private repository and press "Run workflow" now and then.
- **Yahoo Finance often rate-limits or blocks shared cloud addresses** (Streamlit Cloud and GitHub runners included). The app then shows "Data provider failed" and estimates nothing.
  If this happens a lot, the reliable free option is to run on your own PC (home internet address) with `run_app.bat` and Task Scheduler + `run_pipeline.bat`.
- Postgres was not tested against a live server in development (table creation commands were checked for the Postgres dialect only). Test with a throwaway database first.

## Steps
1. Create a **private** GitHub repository and upload this folder. `.gitignore` already keeps `.env`, databases and logs out. Never upload secrets.
2. Create a free Postgres database. Copy its connection string (it starts with `postgresql://`).
3. Streamlit Community Cloud: New app, pick the repository, main file `app.py`. In Advanced settings choose Python 3.12 and paste into Secrets:
   ```
   DATABASE_URL = "postgresql://user:password@host/dbname"
   APP_PASSWORD = "a-long-password-only-you-know"
   ```
   `APP_PASSWORD` shows a password screen before anything else. Set it: otherwise anyone with the link can run scans, change settings and place simulated orders.
4. GitHub repository, Settings, Secrets and variables, Actions: add the same `DATABASE_URL`. Open the Actions tab and run "Daily research pipeline" once by hand to test it.
5. Open the app, go to Floor 00 and check: last run, data-source health, coverage. Then Floor 01: download or upload the NSE list.
6. Keep the repository active (any small commit every couple of months) so GitHub does not disable the schedule.

If you want, ask me to push the project to your GitHub through the GitHub connector once you have made the repository.

## Getting the daily result on your phone (optional, free)
The workflow runs the automation agent. To receive its digest, add one of these as a GitHub Actions secret (and as a Streamlit secret if you want the Floor 00 test button):
- `NTFY_TOPIC`: pick a long random name, install the free ntfy app, subscribe to the same name. Anyone who learns the name can read the messages, so do not reuse a guessable one.
- `TELEGRAM_BOT_TOKEN` and `TELEGRAM_CHAT_ID`: create a bot with @BotFather, send it a message, then find your chat id.
- `SMTP_HOST`, `SMTP_PORT`, `SMTP_USER`, `SMTP_PASSWORD`, `SMTP_FROM`, `SMTP_TO` for e-mail, or `WEBHOOK_URL` (https only).
If the data provider is down, or the run fails, the workflow ends with an error, and GitHub also e-mails the repository owner about a failed run.
The notification senders have not been tried against the real services: press "Send test notification" on Floor 00 first.
