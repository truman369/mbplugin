@echo OFF

where 7z >nul 2>&1
if NOT "%errorlevel%"=="0" (
echo Not found 7z
goto :EOF
)

where curl >nul 2>&1
if NOT "%errorlevel%"=="0" (
echo Not found curl
goto :EOF
)

%~d0 
cd "%~dp0\.."
call mbplugin\tcc\get_tcc.bat

cd "%~dp0\.."
SET PYTHONDONTWRITEBYTECODE=1
call mbplugin\python\get_python.bat

cd "%~dp0\.."
call mbplugin\standalone\mbp

cd "%~dp0\.."
call mbplugin\setup_and_check.bat

cd "%~dp0\.."
call mbp clear-browser-cache

cd "%~dp0\.."
call mbplugin\python\python mbplugin\python\remove__pycache__.py

cd "%~dp0\.."
call mbp web-server stop
timeout 5

cd "%~dp0\.."
del mbplugin\log\*.log
del mbplugin\log\*.png
del mbplugin\store\mbplugin.ini.bak.zip 

cd "%~dp0"
call git-restore-mtime

cd "%~dp0\.."
7z a -tzip mbplugin mbplugin
