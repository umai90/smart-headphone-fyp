@echo off
setlocal enabledelayedexpansion
cls

:: ═══════════════════════════════════════════════════════
::   Smart Headphone System — Production Deploy to Pi
::   Copies only runtime files (no git, no Flutter source,
::   no training scripts, no dev files)
:: ═══════════════════════════════════════════════════════

set PI_USER=pi
set PI_HOST=192.168.1.15
set SRC=D:\FYP_project
set PKG=%TEMP%\sh_deploy\FYP_project

echo.
echo  Smart Headphone System ^| Production Deploy
echo  Target: %PI_USER%@%PI_HOST%
echo  ────────────────────────────────────────────
echo.

:: ── STEP 1: Build clean package ─────────────────────────────────────────────
echo  [1/5] Building clean package...

if exist "%TEMP%\sh_deploy" rmdir /s /q "%TEMP%\sh_deploy"

mkdir "%PKG%\translate"
mkdir "%PKG%\lcd_ui\services"
mkdir "%PKG%\module-1\deepfake_detection\models"
mkdir "%PKG%\translate\recordings"

:: Flask backend — runtime files only
echo        translate\  (backend)
for %%f in (
    mode2_online_translation.py
    mode1_offline_translation.py
    run_flask.py
    deepfake_checker.py
    conversation_recorder.py
    cloud_backup.py
) do (
    if exist "%SRC%\translate\%%f" (
        copy /y "%SRC%\translate\%%f" "%PKG%\translate\" >nul
    ) else (
        echo        [WARN] Missing: translate\%%f
    )
)

:: LCD UI — only what runs on Pi (no lcd_controller.py, no install.sh)
echo        lcd_ui\     (touchscreen app)
for %%f in (app.py setup_pi.sh start_manual.sh) do (
    if exist "%SRC%\lcd_ui\%%f" (
        copy /y "%SRC%\lcd_ui\%%f" "%PKG%\lcd_ui\" >nul
    ) else (
        echo        [WARN] Missing: lcd_ui\%%f
    )
)
copy /y "%SRC%\lcd_ui\services\*.service" "%PKG%\lcd_ui\services\" >nul

:: Deepfake module — checker + feature extractor + trained models only
:: (no train scripts, no dataset, no test utilities)
echo        module-1\   (deepfake detection)
for %%f in (deepfake_checker.py preprocess.py) do (
    if exist "%SRC%\module-1\deepfake_detection\%%f" (
        copy /y "%SRC%\module-1\deepfake_detection\%%f" ^
               "%PKG%\module-1\deepfake_detection\" >nul
    ) else (
        echo        [WARN] Missing: module-1\deepfake_detection\%%f
    )
)
robocopy "%SRC%\module-1\deepfake_detection\models" ^
         "%PKG%\module-1\deepfake_detection\models" ^
         /E /NFL /NDL /NJH /NJS /NC /NS /NP >nul

echo        Package ready.
echo.

:: ── STEP 2: Show package size ────────────────────────────────────────────────
echo  [2/5] Package contents:
dir /s "%TEMP%\sh_deploy" | findstr "File(s)"
echo.

:: ── STEP 3: Upload to Pi ─────────────────────────────────────────────────────
echo  [3/5] Uploading to Pi (this may take a few minutes)...
echo        Enter Pi password when prompted.
echo.
scp -r "%TEMP%\sh_deploy\FYP_project" %PI_USER%@%PI_HOST%:/home/pi/
if errorlevel 1 (
    echo.
    echo  [ERROR] Upload failed. Check:
    echo    1. Pi is on and connected to same Wi-Fi
    echo    2. Pi IP is %PI_HOST%
    echo    3. SSH is enabled on Pi
    set DEPLOY_FAILED=1
    goto :cleanup
)
echo.
echo        Upload complete.
echo.

:: ── STEP 4: Run setup on Pi via SSH ─────────────────────────────────────────
echo  [4/5] Running setup on Pi (10-15 min, installing packages)...
echo        DO NOT close this window.
echo.
ssh %PI_USER%@%PI_HOST% "bash /home/pi/FYP_project/lcd_ui/setup_pi.sh"
echo.

:: ── STEP 5: Verify Flask starts ──────────────────────────────────────────────
echo  [5/5] Verifying Flask API starts correctly...
ssh %PI_USER%@%PI_HOST% "cd /home/pi/FYP_project/translate && python3 run_flask.py &>/tmp/flask_test.log & sleep 6 && curl -s http://127.0.0.1:5000/health && kill %%1 2>/dev/null; echo."
echo.

:cleanup
:: ── Cleanup temp files ───────────────────────────────────────────────────────
echo  Cleaning temp files...
rmdir /s /q "%TEMP%\sh_deploy" 2>nul

if defined DEPLOY_FAILED (
    echo.
    echo  ════════════════════════════════════════════
    echo   Deploy did NOT complete — see [ERROR] above.
    echo  ════════════════════════════════════════════
    echo.
    pause
    endlocal
    exit /b 1
)

echo.
echo  ════════════════════════════════════════════
echo   Deploy complete!
echo.
echo   Next steps:
echo   1. Reboot Pi:  ssh %PI_USER%@%PI_HOST% "sudo reboot"
echo   2. Flutter app:  Settings ^> http://%PI_HOST%:5000
echo   3. To start manually without reboot:
echo      ssh %PI_USER%@%PI_HOST% "bash /home/pi/FYP_project/lcd_ui/start_manual.sh"
echo  ════════════════════════════════════════════
echo.
pause
endlocal
