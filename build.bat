@echo off
echo ============================================
echo   FKFTP Build - Generating Windows Executable
echo ============================================
echo.

pip install pyinstaller pyftpdlib flask pywin32 >nul 2>&1

pyinstaller --onefile ^
  --add-data "templates;templates" ^
  --icon "static\icon.ico" ^
  --name fkftp ^
  --hidden-import pyasyncore ^
  --hidden-import pyasynchat ^
  --hidden-import pyftpdlib.handlers ^
  --hidden-import pyftpdlib.filesystems ^
  --hidden-import pyftpdlib.authorizers ^
  --hidden-import win32serviceutil ^
  --hidden-import win32service ^
  --hidden-import win32event ^
  --hidden-import servicemanager ^
  --hidden-import win32api ^
  --console ^
  app.py

echo.
if exist dist\fkftp.exe (
  echo Build successful!
  echo Output: dist\fkftp.exe
  echo.
  echo Copy fkftp.exe and config.json to your desired location.
  copy config.json dist\config.json >nul 2>&1
  echo config.json has been copied to dist\ folder.
) else (
  echo Build failed. Check the output above for errors.
)
echo.
pause
