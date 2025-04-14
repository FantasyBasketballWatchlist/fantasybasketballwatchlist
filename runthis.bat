@echo off
cd /d %~dp0
start cmd /k python app.py
python -m http.server 8000
pause