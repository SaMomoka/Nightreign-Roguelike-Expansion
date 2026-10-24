@echo off
cd /d "%~dp0"
python tools\combined_package.py build
pause
