@echo off
cd /d "%~dp0"
".venv\Scripts\python.exe" manage.py runserver 127.0.0.1:8000 --noreload
