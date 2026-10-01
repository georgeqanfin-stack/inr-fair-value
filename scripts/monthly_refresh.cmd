@echo off
rem Monthly refresh, as run by the Windows scheduled task (scripts\schedule_monthly_refresh.ps1).
rem Re-downloads every source, runs the pipeline and commits data/raw and reports/ locally.
rem It does not push; run "git push" yourself once GitHub is signed in.
setlocal
cd /d "%~dp0.."
if not exist outputs\refresh_logs mkdir outputs\refresh_logs
for /f %%i in ('powershell -NoProfile -Command "Get-Date -Format yyyyMMdd-HHmmss"') do set STAMP=%%i
set PYTHONIOENCODING=utf-8
if not defined INRFV_PYTHON set INRFV_PYTHON=python
"%INRFV_PYTHON%" -m inrfv.refresh --commit > "outputs\refresh_logs\%STAMP%.log" 2>&1
exit /b %ERRORLEVEL%
