#!/usr/bin/env bash
set -euo pipefail

# ─── Configuration ───────────────────────────────────────────────────────────
SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
LOG_DIR="$SCRIPT_DIR/logs"
JAVA_PROJECT="${JAVA_PROJECT_DIR:-/Users/claymorgan/IdeaProjects/VectorSearchDemo-test4}"

PYTHON_PORT=8000
JAVA_PORT=8080
DB_HOST=localhost
DB_PORT=5433
DB_NAME=llmdb
DB_USERNAME=postgres
DB_PASSWORD=postgres
DB_CONTAINER=claude-rag-pg

HEALTH_POLL_INTERVAL=3
HEALTH_POLL_TIMEOUT=120

# ─── Python venv detection ──────────────────────────────────────────────────
if [ -f "$SCRIPT_DIR/.venv/bin/python3" ]; then
  PYTHON="$SCRIPT_DIR/.venv/bin/python3"
elif [ -f "$SCRIPT_DIR/venv/bin/python3" ]; then
  PYTHON="$SCRIPT_DIR/venv/bin/python3"
else
  PYTHON="python3"
fi

# ─── Java 17+ detection ─────────────────────────────────────────────────────
JAVA_HOME_17="$(/usr/libexec/java_home -v 17 2>/dev/null || true)"
if [ -n "$JAVA_HOME_17" ]; then
  export JAVA_HOME="$JAVA_HOME_17"
  export PATH="$JAVA_HOME/bin:$PATH"
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
DRY_RUN=false
SKIP_PYTHON=false
SKIP_JAVA=false
SKIP_BUILD=false

for arg in "$@"; do
  case "$arg" in
    --dry-run)      DRY_RUN=true ;;
    --skip-python)  SKIP_PYTHON=true ;;
    --skip-java)    SKIP_JAVA=true ;;
    --skip-build)   SKIP_BUILD=true ;;
    -h|--help)
      echo "Usage: $0 [--dry-run] [--skip-python] [--skip-java] [--skip-build]"
      echo ""
      echo "  --dry-run       Print what would happen without executing"
      echo "  --skip-python   Only start Java service (Python already running)"
      echo "  --skip-java     Only start Python service"
      echo "  --skip-build    Skip Maven build (use existing JAR)"
      echo ""
      echo "Environment:"
      echo "  JAVA_PROJECT_DIR  Path to VectorSearchDemo-test4 (default: $JAVA_PROJECT)"
      exit 0
      ;;
    *) err "Unknown flag: $arg"; exit 1 ;;
  esac
done

if $DRY_RUN; then
  echo -e "${YELLOW}${BOLD}=== DRY RUN — no changes will be made ===${RESET}"
fi

# ─── Helpers ─────────────────────────────────────────────────────────────────
check_command() {
  if ! command -v "$1" &>/dev/null; then
    err "$1 is required but not found in PATH"
    return 1
  fi
}

wait_for_health() {
  local url="$1"
  local name="$2"
  local elapsed=0

  info "Waiting for $name health check at $url ..."
  while [ $elapsed -lt $HEALTH_POLL_TIMEOUT ]; do
    if curl -sf "$url" &>/dev/null; then
      ok "$name is healthy"
      return 0
    fi
    sleep $HEALTH_POLL_INTERVAL
    elapsed=$((elapsed + HEALTH_POLL_INTERVAL))
  done

  err "$name failed to become healthy after ${HEALTH_POLL_TIMEOUT}s"
  err "Check logs: $LOG_DIR/"
  return 1
}

is_port_in_use() {
  lsof -i ":$1" -sTCP:LISTEN &>/dev/null
}

export_db_env() {
  export DB_HOST DB_PORT DB_NAME DB_USERNAME DB_PASSWORD
}

# ─── Prerequisites ───────────────────────────────────────────────────────────
header "Checking prerequisites"

MISSING=false
check_command docker || MISSING=true
if ! "$PYTHON" --version &>/dev/null; then
  err "Python not found (checked venv and PATH)"
  MISSING=true
fi
check_command curl || MISSING=true

if ! $SKIP_JAVA; then
  check_command java || MISSING=true
  if ! $SKIP_BUILD; then
    check_command mvn || MISSING=true
  fi
fi

if $MISSING; then
  err "Missing required tools — install them and try again"
  exit 1
fi

ok "All prerequisites found"

# Check Python dependencies are installed
if ! $SKIP_PYTHON && ! $DRY_RUN; then
  if ! "$PYTHON" -c "import psycopg2" &>/dev/null; then
    warn "Python dependencies not installed in venv"
    info "Installing from requirements.txt..."
    "$PYTHON" -m pip install -r "$SCRIPT_DIR/requirements.txt" -q
    ok "Dependencies installed"
  fi
fi

if $DRY_RUN; then
  info "[DRY RUN] Would ensure PostgreSQL container ($DB_CONTAINER) is running on port $DB_PORT"
  info "[DRY RUN] Would create database '$DB_NAME' if it doesn't exist"
  if ! $SKIP_PYTHON; then
    info "[DRY RUN] Would run schema migration (migrate_schema.py)"
    info "[DRY RUN] Would start Python FastAPI service on port $PYTHON_PORT"
  fi
  if ! $SKIP_JAVA; then
    if ! $SKIP_BUILD; then
      info "[DRY RUN] Would build Java service (mvn clean package)"
    fi
    info "[DRY RUN] Would start Java Spring Boot service on port $JAVA_PORT"
  fi
  echo ""
  ok "Dry run complete — no changes made"
  exit 0
fi

# ─── Ensure log directory ───────────────────────────────────────────────────
mkdir -p "$LOG_DIR"

# ─── PostgreSQL container ────────────────────────────────────────────────────
header "PostgreSQL ($DB_CONTAINER on port $DB_PORT)"

CONTAINER_STATE="$(docker inspect -f '{{.State.Running}}' "$DB_CONTAINER" 2>/dev/null || echo "not_found")"

if [ "$CONTAINER_STATE" = "true" ]; then
  ok "Container $DB_CONTAINER is already running"
elif [ "$CONTAINER_STATE" = "false" ]; then
  info "Container $DB_CONTAINER exists but is stopped — starting..."
  docker start "$DB_CONTAINER"
  sleep 2
  ok "Container started"
else
  err "Container $DB_CONTAINER not found."
  err "Create it first:  docker run -d --name claude-rag-pg -p 5433:5432 -e POSTGRES_PASSWORD=postgres pgvector/pgvector:pg16"
  exit 1
fi

# ─── Create database if needed ───────────────────────────────────────────────
header "Database ($DB_NAME)"

DB_EXISTS=$(PGPASSWORD=$DB_PASSWORD psql -h $DB_HOST -p $DB_PORT -U $DB_USERNAME -tAc "SELECT 1 FROM pg_database WHERE datname='$DB_NAME'" postgres 2>/dev/null || echo "")

if [ "$DB_EXISTS" = "1" ]; then
  ok "Database '$DB_NAME' already exists"
else
  info "Creating database '$DB_NAME'..."
  PGPASSWORD=$DB_PASSWORD psql -h $DB_HOST -p $DB_PORT -U $DB_USERNAME -c "CREATE DATABASE $DB_NAME;" postgres
  ok "Database created"
fi

# ─── Schema migration ───────────────────────────────────────────────────────
if ! $SKIP_PYTHON; then
  header "Schema migration"
  export_db_env
  info "Running migrate_schema.py..."
  "$PYTHON" "$SCRIPT_DIR/migrate_schema.py" 2>&1 | tail -5
  ok "Migration complete"
fi

# ─── Python service ─────────────────────────────────────────────────────────
if ! $SKIP_PYTHON; then
  header "Python FastAPI service (port $PYTHON_PORT)"

  if is_port_in_use $PYTHON_PORT; then
    warn "Port $PYTHON_PORT is already in use — skipping Python service start"
    warn "If this is stale, run: ./local-dev-stop.sh"
  else
    export_db_env
    warn "First startup may download ~3GB of ML models — this is normal"
    info "Starting uvicorn on port $PYTHON_PORT..."
    nohup "$PYTHON" -m uvicorn app:app --host 0.0.0.0 --port $PYTHON_PORT \
      > "$LOG_DIR/python-service.log" 2>&1 &
    PYTHON_PID=$!
    echo "$PYTHON_PID" > "$LOG_DIR/python-service.pid"
    info "PID: $PYTHON_PID (logged to $LOG_DIR/python-service.log)"

    wait_for_health "http://localhost:$PYTHON_PORT/health" "Python service"
  fi
fi

# ─── Java service — build ───────────────────────────────────────────────────
if ! $SKIP_JAVA; then
  if [ ! -d "$JAVA_PROJECT" ]; then
    err "Java project not found at: $JAVA_PROJECT"
    err "Set JAVA_PROJECT_DIR env var to the correct path"
    exit 1
  fi

  if ! $SKIP_BUILD; then
    header "Building Java service"
    info "Running mvn clean package (this may take a minute)..."
    mvn -f "$JAVA_PROJECT/pom.xml" clean package -DskipTests -q
    ok "Build complete"
  fi

  # ─── Java service — start ─────────────────────────────────────────────────
  header "Java Spring Boot service (port $JAVA_PORT)"

  if is_port_in_use $JAVA_PORT; then
    warn "Port $JAVA_PORT is already in use — skipping Java service start"
    warn "If this is stale, run: ./local-dev-stop.sh"
  else
    JAR_FILE="$(find "$JAVA_PROJECT/target" -name '*.jar' -not -name '*-sources.jar' -not -name '*-javadoc.jar' | head -1)"
    if [ -z "$JAR_FILE" ]; then
      err "No JAR file found in $JAVA_PROJECT/target/"
      err "Run without --skip-build to build first"
      exit 1
    fi

    export_db_env
    export EMBEDDING_SERVICE_URL="http://localhost:$PYTHON_PORT"

    info "Starting Java service from $JAR_FILE..."
    nohup java -Xms256m -Xmx512m -jar "$JAR_FILE" \
      > "$LOG_DIR/java-service.log" 2>&1 &
    JAVA_PID=$!
    echo "$JAVA_PID" > "$LOG_DIR/java-service.pid"
    info "PID: $JAVA_PID (logged to $LOG_DIR/java-service.log)"

    wait_for_health "http://localhost:$JAVA_PORT/api/health" "Java service"
  fi
fi

# ─── Summary ─────────────────────────────────────────────────────────────────
header "Local dev environment is ready"
echo ""
echo -e "  ${BOLD}Services:${RESET}"
if ! $SKIP_PYTHON; then
  PPID_DISPLAY="$(cat "$LOG_DIR/python-service.pid" 2>/dev/null || echo "?")"
  echo -e "    Python FastAPI   ${GREEN}http://localhost:$PYTHON_PORT${RESET}   (PID: $PPID_DISPLAY)"
  echo -e "      Health:        http://localhost:$PYTHON_PORT/health"
fi
if ! $SKIP_JAVA; then
  JPID_DISPLAY="$(cat "$LOG_DIR/java-service.pid" 2>/dev/null || echo "?")"
  echo -e "    Java Spring Boot ${GREEN}http://localhost:$JAVA_PORT${RESET}   (PID: $JPID_DISPLAY)"
  echo -e "      Health:        http://localhost:$JAVA_PORT/api/health"
fi
echo -e "    PostgreSQL       ${GREEN}localhost:$DB_PORT${RESET}          (container: $DB_CONTAINER)"
echo ""
echo -e "  ${BOLD}Logs:${RESET}"
echo -e "    $LOG_DIR/python-service.log"
echo -e "    $LOG_DIR/java-service.log"
echo ""
echo -e "  ${BOLD}Stop:${RESET}  ./local-dev-stop.sh"
echo -e "  ${BOLD}Test:${RESET}  ./test-inference-api.sh http://localhost:$PYTHON_PORT"
echo ""
