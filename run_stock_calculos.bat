@echo off
setlocal
cd /d %~dp0

if not exist ".venv\Scripts\python.exe" (
	echo ERRO: Python da venv nao encontrado em ".venv\Scripts\python.exe".
	echo Rode primeiro o arquivo setup._env.bat para criar o ambiente.
	pause
	exit /b 1
)

set "PY_EXE=.venv\Scripts\python.exe"

echo Usando ambiente virtual: %PY_EXE%
echo.

"%PY_EXE%" "app\Boxer\main.py"
if errorlevel 1 goto :erro

"%PY_EXE%" "app\BoxerV2\maindf.py"
if errorlevel 1 goto :erro

"%PY_EXE%" "app\Meia\main.py"
if errorlevel 1 goto :erro

echo.
echo Execucao concluida com sucesso.
pause
exit /b 0

:erro
echo.
echo ERRO: Falha durante a execucao dos scripts.
pause
exit /b 1
