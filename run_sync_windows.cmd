@echo off
setlocal
"C:\Users\Abhi\AppData\Local\Programs\Python\Python314\python.exe" "C:\Users\Abhi\Programming\GithubClonerAgent\clone_repos.py" --sync -o "C:\Users\Abhi\Programming"
set "EXITCODE=%ERRORLEVEL%"
powershell -NoProfile -ExecutionPolicy Bypass -Command "Add-Type -AssemblyName System.Windows.Forms; [System.Windows.Forms.Application]::SetSuspendState('Suspend', $false, $false)" >NUL 2>&1
exit /b %EXITCODE%
