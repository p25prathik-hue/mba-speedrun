@echo off
rem MBA Speedrun - double-click this file to start (Windows).
rem First run: makes a private Python environment in .venv and installs the
rem requirements (needs internet, about 1-3 minutes). Later runs start at once.
setlocal
cd /d "%~dp0"
title MBA Speedrun

where python >nul 2>nul
if errorlevel 1 goto nopython
python -c "import sys; sys.exit(0 if sys.version_info >= (3, 9) else 1)" >nul 2>nul
if errorlevel 1 goto nopython

if exist ".venv\speedrun_ready.txt" goto run

echo.
echo  First run: setting up MBA Speedrun. This takes 1-3 minutes and needs internet.
echo.
if not exist ".venv\Scripts\python.exe" python -m venv .venv
if errorlevel 1 goto setupfail
".venv\Scripts\python.exe" -m pip install --disable-pip-version-check -q -r requirements.txt
if errorlevel 1 goto setupfail
echo  Installing numba to make the solver faster - optional, skipped if it fails...
".venv\Scripts\python.exe" -m pip install --disable-pip-version-check -q numba >nul 2>nul
if errorlevel 1 echo  numba could not be installed. That is fine: the tool uses its numpy solver instead.
echo ready> ".venv\speedrun_ready.txt"
echo  Setup finished.

:run
".venv\Scripts\python.exe" start.py %*
echo.
pause
exit /b 0

:nopython
echo.
echo  Python 3.9 or newer was not found.
echo  1. Install it from https://www.python.org/downloads/
echo     and tick "Add python.exe to PATH" during the install.
echo  2. Then double-click this file again.
echo.
echo  To use the roadmap planner without Python, open docs\index.html in your browser.
echo.
pause
exit /b 1

:setupfail
echo.
echo  Setup failed. Check your internet connection and double-click this file again.
echo  If it keeps failing, delete the .venv folder and try once more.
echo.
pause
exit /b 1
