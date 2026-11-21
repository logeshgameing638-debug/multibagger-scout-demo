@echo off
REM Runs the daily research pipeline once. Point Windows Task Scheduler at this file for unattended runs (computer must be on).
call .venv\Scripts\activate.bat
python scripts\run_pipeline.py
