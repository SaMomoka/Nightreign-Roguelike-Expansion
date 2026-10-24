@echo off
cd /d "%~dp0"
python tools\phase1_package.py launch --mode tiered_choices
pause
