@echo off
setlocal
powershell.exe -NoProfile -ExecutionPolicy Bypass -File "%~dp0build_desktop_exe.ps1" %*
exit /b %ERRORLEVEL%
