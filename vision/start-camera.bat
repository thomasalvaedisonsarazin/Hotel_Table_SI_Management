@echo off
rem Starts the DineOps SI camera demo. The first run sets everything up, which takes a few minutes.
cd /d "%~dp0"
if not exist .venv\Scripts\python.exe (
    echo Setting up for the first time...
    python -m venv .venv || goto :failed
    .venv\Scripts\python -m pip install --quiet -r requirements.txt || goto :failed
)
.venv\Scripts\python -m dineops_vision
pause
exit /b

:failed
echo.
echo Setup failed. Check that Python is installed and that you're online, then try again.
pause
