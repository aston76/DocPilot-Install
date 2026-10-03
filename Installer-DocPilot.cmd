@echo off
powershell.exe -NoProfile -ExecutionPolicy Bypass -File "%~dp0Installer-DocPilot.ps1"
if errorlevel 1 echo Installation interrompue. Consultez le message ci-dessus.
pause
