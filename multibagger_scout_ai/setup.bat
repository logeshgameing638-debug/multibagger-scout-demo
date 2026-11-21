@echo off
setlocal
where python >nul 2>nul
if errorlevel 1 (
  echo Python 3.11 or newer was not found. Install it from python.org and tick "Add python.exe to PATH".
  exit /b 1
)
if not exist .venv python -m venv .venv
call .venv\Scripts\activate.bat
python -m pip install --upgrade pip
pip install -r requirements.txt
if errorlevel 1 exit /b 1
if not exist .env copy .env.example .env
python -c "from database.connection import init_db; init_db(); print('Database initialised')"
if errorlevel 1 exit /b 1
python -m pytest -q
echo.
echo Setup finished. Start the dashboard with run_dashboard.bat and the API with run_backend.bat
