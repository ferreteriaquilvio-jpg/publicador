@echo off
REM Crea Publicador.exe en la carpeta "dist". Requiere Python 3 instalado desde python.org
REM (marca "Add python.exe to PATH" al instalarlo).
cd /d "%~dp0"
python -m pip install --upgrade requests pyinstaller
python -m PyInstaller --onefile --windowed --name Publicador publicar.py
echo.
echo Listo. Tu programa esta en: %~dp0dist\Publicador.exe
pause
