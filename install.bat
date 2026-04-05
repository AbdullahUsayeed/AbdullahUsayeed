@echo off
REM ─────────────────────────────────────────────────────────────────────────────
REM System Link — One-Command Installer (Windows)
REM ─────────────────────────────────────────────────────────────────────────────
REM Usage:  Double-click install.bat  (or run from Command Prompt / PowerShell)
REM ─────────────────────────────────────────────────────────────────────────────

title System Link Installer

echo.
echo  ╔═══════════════════════════════════╗
echo  ║       System Link Installer       ║
echo  ║   Proudly built by Usayeed        ║
echo  ║   usayeed.com                     ║
echo  ╚═══════════════════════════════════╝
echo.

REM ── Check Docker ──────────────────────────────────────────────────────────
docker --version >nul 2>&1
if errorlevel 1 (
    echo [ERROR] Docker not found.
    echo         Install Docker Desktop: https://www.docker.com/products/docker-desktop/
    echo         Then re-run this installer.
    pause
    exit /b 1
)
echo [OK] Docker found.

REM ── Create .env if missing ─────────────────────────────────────────────────
if not exist ".env" (
    echo.
    echo [INFO] Creating .env from .env.example...
    copy /Y ".env.example" ".env" >nul

    echo.
    echo  Action required:
    echo  1. Open ".env" in Notepad or VS Code
    echo  2. Set OPENAI_API_KEY to your OpenAI API key
    echo     (or OPENAI_BASE_URL for a local LLM)
    echo.
    echo  Pro users: set CLOUD_OPENAI_API_KEY and GUMROAD_PRODUCT_PERMALINK
    echo             on your cloud server only.
    echo.
    pause
) else (
    echo [OK] .env already exists.
)

REM ── Build + start ─────────────────────────────────────────────────────────
echo.
echo [INFO] Building System Link (this may take a few minutes the first time)...
docker compose build --quiet
if errorlevel 1 (
    echo [ERROR] Build failed. Check the error above and try again.
    pause
    exit /b 1
)

echo.
echo [INFO] Starting services...
docker compose up -d
if errorlevel 1 (
    echo [ERROR] Failed to start services.
    pause
    exit /b 1
)

echo.
echo  ╔═══════════════════════════════════════════════╗
echo  ║  System Link is running!                      ║
echo  ║                                               ║
echo  ║  Open:  http://localhost:3000                 ║
echo  ║  Stop:  docker compose down                   ║
echo  ║  Logs:  docker compose logs -f                ║
echo  ╚═══════════════════════════════════════════════╝
echo.

REM Open browser
start "" "http://localhost:3000"

pause
