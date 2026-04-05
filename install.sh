#!/usr/bin/env bash
# ─────────────────────────────────────────────────────────────────────────────
# System Link — One-Command Installer (Linux / macOS)
# ─────────────────────────────────────────────────────────────────────────────
# Usage:
#   chmod +x install.sh && ./install.sh
#
# What this script does:
#   1. Checks for Docker + Docker Compose
#   2. Creates .env from .env.example if not present
#   3. Pulls/builds all images
#   4. Starts all services
#   5. Opens http://localhost:3000 in the default browser
# ─────────────────────────────────────────────────────────────────────────────

set -euo pipefail

BOLD="\033[1m"
CYAN="\033[36m"
GREEN="\033[32m"
YELLOW="\033[33m"
RED="\033[31m"
RESET="\033[0m"

print_banner() {
  echo ""
  echo -e "${CYAN}${BOLD}  ╔═══════════════════════════════════╗${RESET}"
  echo -e "${CYAN}${BOLD}  ║       System Link Installer       ║${RESET}"
  echo -e "${CYAN}${BOLD}  ║   Proudly built by Usayeed        ║${RESET}"
  echo -e "${CYAN}${BOLD}  ║   usayeed.com                     ║${RESET}"
  echo -e "${CYAN}${BOLD}  ╚═══════════════════════════════════╝${RESET}"
  echo ""
}

check_dependency() {
  if ! command -v "$1" &>/dev/null; then
    echo -e "${RED}✗ '$1' not found.${RESET} Please install it and re-run this script."
    echo "  Docker: https://docs.docker.com/get-docker/"
    exit 1
  fi
  echo -e "${GREEN}✓${RESET} $1 found."
}

setup_env() {
  if [ ! -f .env ]; then
    echo -e "${YELLOW}⚙  No .env file found. Creating from .env.example…${RESET}"
    cp .env.example .env

    echo ""
    echo -e "${BOLD}Action required:${RESET}"
    echo "  1. Open .env in a text editor"
    echo "  2. Set OPENAI_API_KEY to your OpenAI API key"
    echo "     (or set OPENAI_BASE_URL to point to a local LLM)"
    echo ""
    echo "  Pro users: set CLOUD_OPENAI_API_KEY and GUMROAD_PRODUCT_PERMALINK"
    echo "             on your cloud server (never in the downloadable package)."
    echo ""
    read -rp "Press Enter once you have saved .env to continue…"
  else
    echo -e "${GREEN}✓${RESET} .env already exists — skipping."
  fi
}

build_and_start() {
  echo ""
  echo -e "${CYAN}${BOLD}Building System Link…${RESET}"
  docker compose build --quiet

  echo ""
  echo -e "${CYAN}${BOLD}Starting services…${RESET}"
  docker compose up -d

  echo ""
  echo -e "${GREEN}${BOLD}✓ System Link is running!${RESET}"
  echo ""
  echo "  Open:   http://localhost:3000"
  echo "  Stop:   docker compose down"
  echo "  Logs:   docker compose logs -f"
  echo ""
}

open_browser() {
  local url="http://localhost:3000"
  if command -v open &>/dev/null; then        # macOS
    open "$url" &>/dev/null || true
  elif command -v xdg-open &>/dev/null; then  # Linux
    xdg-open "$url" &>/dev/null || true
  fi
}

# ─── Main ────────────────────────────────────────────────────────────────────
print_banner

echo -e "${BOLD}Checking dependencies…${RESET}"
check_dependency docker
# Support both `docker compose` (v2 plugin) and `docker-compose` (v1 standalone)
if ! docker compose version &>/dev/null 2>&1; then
  check_dependency docker-compose
fi

setup_env
build_and_start
open_browser
