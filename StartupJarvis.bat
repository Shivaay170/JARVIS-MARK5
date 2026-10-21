@echo off
cd /d "%~dp0"
echo ==============================================
echo           Starting JARVIS-MARK5
echo ==============================================
python main.py
if errorlevel 1 (
    echo.
    echo JARVIS exited with an error.
    pause
)
