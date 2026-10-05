@echo off
chcp 65001 > nul
echo ========================================================
echo   Air Draw — Автоматическая сборка Windows EXE (в 1 клик)
echo ========================================================
echo.

where python >nul 2>nul
if %errorlevel% neq 0 (
    echo [ОШИБКА] На этом компьютере для сборщика нужен Python.
    echo Скачайте и установите Python (3.10 - 3.12) с python.org,
    echo отметив галочку "Add python.exe to PATH".
    echo.
    pause
    exit /b 1
)

echo [1/3] Установка необходимых библиотек для сборщика...
python -m pip install --upgrade pip
python -m pip install -r requirements.txt
python -m pip install pyinstaller

echo.
echo [2/3] Компиляция всего проекта в ОДИН файл AirDraw.exe...
pyinstaller air_draw.spec --clean --noconfirm

echo.
echo [3/3] Проверка результата...
if exist "dist\AirDraw.exe" (
    echo.
    echo ========================================================
    echo   УСПЕШНО! Создан единственный готовый файл:
    echo   dist\AirDraw.exe
    echo.
    echo   Теперь этот ОДИН файл AirDraw.exe можно раздавать
    echo   любым людям — он запустится на ЛЮБОМ ПК с Windows
    echo   в 1 клик без Python, без консоли и без интернета!
    echo ========================================================
) else (
    echo.
    echo [ВНИМАНИЕ] Проверьте сообщения об ошибках выше.
)

echo.
pause
