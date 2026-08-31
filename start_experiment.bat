@echo off
rem LSCI Visual Mental Imagery Experiment - double-click launcher.
rem main.py finds a compatible Python (3.8-3.11) by itself, so any
rem installed Python works as the starting point.
setlocal
cd /d "%~dp0"

where py >nul 2>nul
if %errorlevel%==0 (
    py main.py %*
) else (
    python main.py %*
)

if errorlevel 1 (
    echo.
    echo The experiment failed to start. Read the message above.
    pause
)
endlocal
