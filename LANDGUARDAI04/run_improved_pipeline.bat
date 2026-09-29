@echo off
setlocal
call .venv\Scripts\activate
powershell -ExecutionPolicy Bypass -File run_improved_pipeline.ps1
endlocal
