@echo off
call .venv\Scripts\activate.bat
python -c "from services.command import backup_database; print(\x27Backup written:\x27, backup_database())"
pause
