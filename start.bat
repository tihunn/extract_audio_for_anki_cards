@echo off
cd /d "%~dp0"

echo Активация виртуального окружения...
call venv\Scripts\activate.bat

if errorlevel 1 (
    echo Ошибка: Не удалось активировать виртуальное окружение
    echo Убедитесь, что папка venv существует
    pause
    exit /b 1
)

echo Запуск src\main.py...
python src\main.py

if errorlevel 1 (
    echo Ошибка при выполнении main.py
    pause
    exit /b 1
)

echo Скрипт успешно выполнен
pause