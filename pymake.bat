@echo off
setlocal
set /p ENV_PATH=<"%~dp0.env_path"
set ENV_PATH=%ENV_PATH: =%

where mamba >nul 2>nul
if %ERRORLEVEL% equ 0 (
    call mamba run -p "%ENV_PATH%" python "%~dp0pymakefile.py" %*
) else (
    call conda run -p "%ENV_PATH%" python "%~dp0pymakefile.py" %*
)
endlocal
