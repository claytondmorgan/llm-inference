#!/usr/bin/env bash
set -euo pipefail

# ─── Configuration ───────────────────────────────────────────────────────────
SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
LOG_DIR="$SCRIPT_DIR/logs"
PYTHON_URL="http://localhost:8000"
JAVA_URL="http://localhost:8080"

# ─── Python venv detection ──────────────────────────────────────────────────
if [ -f "$SCRIPT_DIR/.venv/bin/python3" ]; then
  PYTHON="$SCRIPT_DIR/.venv/bin/python3"
elif [ -f "$SCRIPT_DIR/venv/bin/python3" ]; then
  PYTHON="$SCRIPT_DIR/venv/bin/python3"
else
  PYTHON="python3"
fi
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

# ─── Parse flags ─────────────────────────────────────────────────────────────
SKIP_STARTUP=false
SKIP_PYTHON_TESTS=false
SKIP_JAVA_TESTS=false
SKIP_LEGAL_TESTS=false
SKIP_RAG_TESTS=false
VERBOSE=false
STARTUP_ARGS=""

for arg in "$@"; do
  case "$arg" in
    --skip-startup)      SKIP_STARTUP=true ;;
    --skip-python-tests) SKIP_PYTHON_TESTS=true ;;
    --skip-java-tests)   SKIP_JAVA_TESTS=true ;;
    --skip-legal-tests)  SKIP_LEGAL_TESTS=true ;;
    --skip-rag-tests)    SKIP_RAG_TESTS=true ;;
    --skip-build)        STARTUP_ARGS="$STARTUP_ARGS --skip-build" ;;
    -v|--verbose)        VERBOSE=true ;;
    -h|--help)
      echo "Usage: $0 [OPTIONS]"
      echo ""
      echo "Start all local services and run the full test battery."
      echo ""
      echo "Options:"
      echo "  --skip-startup       Skip starting services (already running)"
      echo "  --skip-python-tests  Skip Python inference API tests"
      echo "  --skip-java-tests    Skip Java search-engine API tests (not yet implemented)"
      echo "  --skip-legal-tests   Skip legal document search API tests"
      echo "  --skip-rag-tests     Skip claude-rag pytest suite"
      echo "  --skip-build         Pass --skip-build to local-dev.sh (skip Maven)"
      echo "  -v, --verbose        Pass verbose flag to test scripts"
      echo "  -h, --help           Show this help"
      exit 0
      ;;
    *) err "Unknown flag: $arg"; exit 1 ;;
  esac
done

VERBOSE_FLAG=""
if $VERBOSE; then
  VERBOSE_FLAG="-v"
fi

# Track overall results
SUITES_PASSED=0
SUITES_FAILED=0
SUITES_SKIPPED=0
SUITE_RESULTS=""
OVERALL_START=$(date +%s)

record_result() {
  local name="$1"
  local status="$2"
  if [ "$status" = "PASS" ]; then
    SUITE_RESULTS="${SUITE_RESULTS}\n    ${GREEN}PASS${RESET}  $name"
    SUITES_PASSED=$((SUITES_PASSED + 1))
  elif [ "$status" = "FAIL" ]; then
    SUITE_RESULTS="${SUITE_RESULTS}\n    ${RED}FAIL${RESET}  $name"
    SUITES_FAILED=$((SUITES_FAILED + 1))
  else
    SUITE_RESULTS="${SUITE_RESULTS}\n    ${YELLOW}SKIP${RESET}  $name"
    SUITES_SKIPPED=$((SUITES_SKIPPED + 1))
  fi
}

# ═════════════════════════════════════════════════════════════════════════════
echo -e "${BOLD}══════════════════════════════════════════════════${RESET}"
echo -e "${BOLD}  Local Dev — Start & Test (Full Battery)${RESET}"
echo -e "${BOLD}══════════════════════════════════════════════════${RESET}"

# ─── Step 1: Start services ─────────────────────────────────────────────────
if $SKIP_STARTUP; then
  header "Startup (skipped)"
  info "Assuming services are already running"
else
  header "Starting local services"
  if ! "$SCRIPT_DIR/local-dev.sh" $STARTUP_ARGS; then
    err "local-dev.sh failed — cannot run tests"
    exit 1
  fi
  ok "All services started"
fi

# ─── Step 2: Quick health gate ──────────────────────────────────────────────
header "Pre-test health check"

PYTHON_HEALTHY=false
JAVA_HEALTHY=false

if curl -sf "$PYTHON_URL/health" &>/dev/null; then
  ok "Python service ($PYTHON_URL) is healthy"
  PYTHON_HEALTHY=true
else
  warn "Python service ($PYTHON_URL) is NOT reachable"
fi

if curl -sf "$JAVA_URL/api/health" &>/dev/null; then
  ok "Java service ($JAVA_URL) is healthy"
  JAVA_HEALTHY=true
else
  warn "Java service ($JAVA_URL) is NOT reachable"
fi

# ─── Step 3: Python Inference API tests ──────────────────────────────────────
header "Test Suite 1: Python Inference API"

if $SKIP_PYTHON_TESTS; then
  info "Skipped (--skip-python-tests)"
  record_result "Python Inference API" "SKIP"
elif ! $PYTHON_HEALTHY; then
  warn "Python service not reachable — skipping"
  record_result "Python Inference API" "SKIP"
else
  info "Running: ./test-inference-api.sh $PYTHON_URL $VERBOSE_FLAG"
  echo ""
  if "$SCRIPT_DIR/test-inference-api.sh" "$PYTHON_URL" $VERBOSE_FLAG; then
    record_result "Python Inference API" "PASS"
  else
    record_result "Python Inference API" "FAIL"
  fi
fi

# ─── Step 4: Legal API tests ────────────────────────────────────────────────
header "Test Suite 2: Legal Document Search API"

if $SKIP_LEGAL_TESTS; then
  info "Skipped (--skip-legal-tests)"
  record_result "Legal Document Search API" "SKIP"
elif ! $PYTHON_HEALTHY; then
  warn "Python service not reachable — skipping"
  record_result "Legal Document Search API" "SKIP"
else
  info "Running: ./test-legal-api.sh $PYTHON_URL $VERBOSE_FLAG"
  echo ""
  if "$SCRIPT_DIR/test-legal-api.sh" "$PYTHON_URL" $VERBOSE_FLAG; then
    record_result "Legal Document Search API" "PASS"
  else
    record_result "Legal Document Search API" "FAIL"
  fi
fi

# ─── Step 5: Claude-RAG pytest suite ────────────────────────────────────────
header "Test Suite 3: Claude-RAG Pytest Suite"

if $SKIP_RAG_TESTS; then
  info "Skipped (--skip-rag-tests)"
  record_result "Claude-RAG Pytest Suite" "SKIP"
elif [ ! -d "$SCRIPT_DIR/claude-rag/tests" ]; then
  warn "claude-rag/tests/ not found — skipping"
  record_result "Claude-RAG Pytest Suite" "SKIP"
else
  info "Running: pytest claude-rag/tests/ -v --tb=short"
  echo ""
  if (cd "$SCRIPT_DIR/claude-rag" && PGPASSWORD=postgres PYTHONPATH=src "$PYTHON" -m pytest tests/ -v --tb=short 2>&1); then
    record_result "Claude-RAG Pytest Suite" "PASS"
  else
    record_result "Claude-RAG Pytest Suite" "FAIL"
  fi
fi

# ─── Step 6: Java API tests (placeholder) ───────────────────────────────────
# Note: No dedicated Java test script yet. The Java service proxies through
# the Python service, so its endpoints are implicitly tested above.
# When a test-java-api.sh is created, wire it in here.

# ─── Summary ─────────────────────────────────────────────────────────────────
OVERALL_END=$(date +%s)
OVERALL_DURATION=$((OVERALL_END - OVERALL_START))

echo ""
echo -e "${BOLD}══════════════════════════════════════════════════${RESET}"
echo -e "${BOLD}  Test Battery Results${RESET}"
echo -e "${BOLD}══════════════════════════════════════════════════${RESET}"
echo ""
echo -e "  ${BOLD}Suites:${RESET}"
echo -e "$SUITE_RESULTS"
echo ""
echo -e "  ${BOLD}Totals:${RESET}  ${GREEN}$SUITES_PASSED passed${RESET}, ${RED}$SUITES_FAILED failed${RESET}, ${YELLOW}$SUITES_SKIPPED skipped${RESET}"
echo -e "  ${BOLD}Duration:${RESET} ${OVERALL_DURATION}s"
echo ""

if [ $SUITES_FAILED -gt 0 ]; then
  echo -e "  ${RED}Some test suites failed.${RESET}"
  echo -e "  Check logs in: $LOG_DIR/"
  echo ""
  echo -e "  ${BOLD}Stop:${RESET}  ./local-dev-stop.sh"
  exit 1
else
  echo -e "  ${GREEN}All test suites passed!${RESET}"
  echo ""
  echo -e "  ${BOLD}Services are still running.${RESET}"
  echo -e "  Stop:  ./local-dev-stop.sh"
fi
echo ""
