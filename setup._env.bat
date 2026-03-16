@echo off
cd /d %~dp0

echo ==========================================
echo Configurando Ambiente Virtual...
echo ==========================================

:: 1. Criar ambiente virtual se nao existir
if not exist ".venv" (
    echo Criando ambiente virtual...
    python -m venv .venv
) else (
    echo Ambiente virtual ja existe.
)

echo.

:: 2. Atualizar pip
echo Atualizando pip...
.\.venv\Scripts\python -m pip install --upgrade pip

echo.

:: 3. Instalar dependencias se existir requirements
if exist "requirements.txt" (
    echo Instalando dependencias...
    .\.venv\Scripts\python -m pip install -r requirements.txt
) else (
    echo WARNING: requirements.txt nao encontrado.
)

echo.
echo ==========================================
echo Ambiente configurado com sucesso!
echo ==========================================
pause
