#!/usr/bin/env bash
set -euo pipefail

# ─── Configuration ───────────────────────────────────────────────────────────
SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
LOG_DIR="$SCRIPT_DIR/logs"
KILL_TIMEOUT=10
# ─────────────────────────────────────────────────────────────────────────────

# ─── Color helpers ───────────────────────────────────────────────────────────
if [[ -t 1 ]]; then
  RED='\033[0;31m'; GREEN='\033[0;32m'; YELLOW='\033[1;33m'; CYAN='\033[0;36m'; BOLD='\033[1m'; RESET='\033[0m'
else
  RED=''; GREEN=''; YELLOW=''; CYAN=''; BOLD=''; RESET=''
fi

info()    { echo -e "${CYAN}[INFO]${RESET}  $*"; }
ok()      { echo -e "${GREEN}[OK]${RESET}    $*"; }
warn()    { echo -e "${YELLOW}[WARN]${RESET}  $*"; }
err()     { echo -e "${RED}[ERROR]${RESET} $*" >&2; }
header()  { echo -e "\n${BOLD}── $* ──${RESET}"; }

# ─── Stop a service by PID file ──────────────────────────────────────────────
stop_service() {
  local name="$1"
  local pid_file="$LOG_DIR/${name}.pid"

  if [ ! -f "$pid_file" ]; then
    info "No PID file for $name — skipping"
    return 0
  fi

  local pid
  pid="$(cat "$pid_file")"

  if ! kill -0 "$pid" 2>/dev/null; then
    info "$name (PID $pid) is not running — cleaning up PID file"
    rm -f "$pid_file"
    return 0
  fi

  info "Stopping $name (PID $pid)..."
  kill "$pid" 2>/dev/null || true

  # Wait for graceful shutdown
  local elapsed=0
  while [ $elapsed -lt $KILL_TIMEOUT ]; do
    if ! kill -0 "$pid" 2>/dev/null; then
      ok "$name stopped gracefully"
      rm -f "$pid_file"
      return 0
    fi
    sleep 1
    elapsed=$((elapsed + 1))
  done

  # Force kill
  warn "$name did not stop after ${KILL_TIMEOUT}s — sending SIGKILL"
  kill -9 "$pid" 2>/dev/null || true
  rm -f "$pid_file"
  ok "$name force-stopped"
}

# ─── Main ────────────────────────────────────────────────────────────────────
header "Stopping local dev services"

stop_service "python-service"
stop_service "java-service"

echo ""
ok "All services stopped"
info "PostgreSQL container (claude-rag-pg) was NOT stopped — it's shared with claude-rag"
info "To stop it manually: docker stop claude-rag-pg"
echo ""
