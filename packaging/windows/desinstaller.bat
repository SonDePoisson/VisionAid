@echo off
rem Désinstalle la version portable de VisionAId : données (réglages, modèles…) puis ce dossier.
chcp 65001 >nul
echo Désinstaller VisionAId : l'application, ses réglages et les modèles téléchargés
echo (environ 3 Go) seront supprimés.
choice /C ON /M "Continuer (O = oui, N = non)"
if errorlevel 2 exit /b 0
taskkill /F /IM VisionAId.exe >nul 2>&1
"%~dp0VisionAId.exe" --uninstall
cd /d "%TEMP%"
rem le dossier est supprimé une fois ce script terminé
start "" /min cmd /c "timeout /t 2 /nobreak >nul & rmdir /s /q "%~dp0""
echo VisionAId a été désinstallé.
timeout /t 3 >nul
