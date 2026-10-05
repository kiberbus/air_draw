@echo off
chcp 65001 > nul
echo ========================================================
echo   Air Draw - one-click Windows EXE build
echo ========================================================
echo.

where python >nul 2>nul
if %errorlevel% neq 0 (
    echo [ERROR] Python is required to build the EXE.
    echo Install Python 3.10 - 3.12 from python.org and tick
    echo "Add python.exe to PATH" during installation.
    echo.
    pause
    exit /b 1
)

echo [1/3] Installing dependencies...
python -m pip install --upgrade pip
python -m pip install -r requirements.txt
python -m pip install pyinstaller

echo.
echo [2/3] Building a single-file AirDraw.exe...
pyinstaller air_draw.spec --clean --noconfirm

echo.
echo [3/3] Checking the result...
if exist "dist\AirDraw.exe" (
    echo.
    echo ========================================================
    echo   SUCCESS! Built:
    echo   dist\AirDraw.exe
    echo.
    echo   This single file runs on any Windows PC without
    echo   Python or an internet connection.
    echo ========================================================
) else (
    echo.
    echo [WARNING] Build failed - check the messages above.
)

echo.
pause
