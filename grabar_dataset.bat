@echo off
rem Graba el dataset de la Fase 0. Uso: grabar_dataset.bat [--only error^|pair^|free]
chcp 65001 >nul
cd /d "%~dp0"
uv run --group spikes python spikes\record_dataset.py %*
pause
