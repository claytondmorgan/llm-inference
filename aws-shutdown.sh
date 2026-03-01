#!/usr/bin/env bash
set -euo pipefail

# ─── Configuration ───────────────────────────────────────────────────────────
REGION="us-east-1"
CLUSTER="llm-cluster"
RDS_ID="llm-postgres"

SERVICES=(llm-inference-service llm-search-engine llm-ingestion-worker)

ECS_POLL_INTERVAL=10
ECS_POLL_TIMEOUT=120
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
SKIP_RDS=false

for arg in "$@"; do
  case "$arg" in
    --dry-run)  DRY_RUN=true ;;
    --skip-rds) SKIP_RDS=true ;;
    -h|--help)
      echo "Usage: $0 [--dry-run] [--skip-rds]"
      echo ""
      echo "  --dry-run   Print what would happen without executing"
      echo "  --skip-rds  Only manage ECS services, leave RDS alone"
      exit 0
      ;;
    *) err "Unknown flag: $arg"; exit 1 ;;
  esac
done

if $DRY_RUN; then
  echo -e "${YELLOW}${BOLD}=== DRY RUN — no changes will be made ===${RESET}"
fi

# ─── Preflight ───────────────────────────────────────────────────────────────
if ! command -v aws &>/dev/null; then
  err "AWS CLI not found. Install it: https://docs.aws.amazon.com/cli/latest/userguide/install-cliv2.html"
  exit 1
fi

header "Current state"

# ─── Step 1: Check current state ────────────────────────────────────────────
for svc in "${SERVICES[@]}"; do
  result=$(aws ecs describe-services \
    --cluster "$CLUSTER" \
    --services "$svc" \
    --region "$REGION" \
    --query 'services[0].{desired:desiredCount,running:runningCount,status:status}' \
    --output json 2>/dev/null || echo '{}')

  desired=$(echo "$result" | grep -o '"desired": *[0-9]*' | grep -o '[0-9]*' || echo "?")
  running=$(echo "$result" | grep -o '"running": *[0-9]*' | grep -o '[0-9]*' || echo "?")
  status=$(echo "$result" | grep -o '"status": *"[^"]*"' | cut -d'"' -f4 || echo "?")

  if [[ "$running" == "0" && "$desired" == "0" ]]; then
    ok "$svc: already idle (desired=$desired, running=$running, status=$status)"
  else
    info "$svc: desired=$desired, running=$running, status=$status"
  fi
done

if ! $SKIP_RDS; then
  rds_status=$(aws rds describe-db-instances \
    --db-instance-identifier "$RDS_ID" \
    --region "$REGION" \
    --query 'DBInstances[0].DBInstanceStatus' \
    --output text 2>/dev/null || echo "unknown")
  info "RDS $RDS_ID: $rds_status"
fi

# ─── Step 2: Scale ECS services to 0 ────────────────────────────────────────
header "Scaling ECS services to 0"

for svc in "${SERVICES[@]}"; do
  current_desired=$(aws ecs describe-services \
    --cluster "$CLUSTER" \
    --services "$svc" \
    --region "$REGION" \
    --query 'services[0].desiredCount' \
    --output text 2>/dev/null || echo "0")

  if [[ "$current_desired" == "0" ]]; then
    ok "$svc: already at desired=0, skipping"
    continue
  fi

  if $DRY_RUN; then
    info "[DRY RUN] Would scale $svc from desired=$current_desired to 0"
  else
    info "Scaling $svc to desired=0 (was $current_desired)..."
    aws ecs update-service \
      --cluster "$CLUSTER" \
      --service "$svc" \
      --desired-count 0 \
      --region "$REGION" \
      --query 'service.serviceName' \
      --output text >/dev/null
    ok "$svc scaled to 0"
  fi
done

# ─── Step 3: Wait for running tasks to drain ────────────────────────────────
if ! $DRY_RUN; then
  header "Waiting for tasks to drain"

  elapsed=0
  while (( elapsed < ECS_POLL_TIMEOUT )); do
    all_drained=true
    for svc in "${SERVICES[@]}"; do
      running=$(aws ecs describe-services \
        --cluster "$CLUSTER" \
        --services "$svc" \
        --region "$REGION" \
        --query 'services[0].runningCount' \
        --output text 2>/dev/null || echo "0")

      if [[ "$running" != "0" ]]; then
        all_drained=false
        info "$svc: $running task(s) still running (${elapsed}s / ${ECS_POLL_TIMEOUT}s)..."
        break
      fi
    done

    if $all_drained; then
      ok "All ECS tasks drained"
      break
    fi

    sleep "$ECS_POLL_INTERVAL"
    elapsed=$(( elapsed + ECS_POLL_INTERVAL ))
  done

  if ! $all_drained; then
    warn "Timeout reached (${ECS_POLL_TIMEOUT}s). Some tasks may still be draining."
  fi
fi

# ─── Step 4: Stop RDS ───────────────────────────────────────────────────────
if ! $SKIP_RDS; then
  header "Stopping RDS instance"

  rds_status=$(aws rds describe-db-instances \
    --db-instance-identifier "$RDS_ID" \
    --region "$REGION" \
    --query 'DBInstances[0].DBInstanceStatus' \
    --output text 2>/dev/null || echo "unknown")

  if [[ "$rds_status" == "stopped" || "$rds_status" == "stopping" ]]; then
    ok "RDS $RDS_ID: already $rds_status"
  elif $DRY_RUN; then
    info "[DRY RUN] Would stop RDS instance $RDS_ID (currently: $rds_status)"
  else
    info "Stopping RDS instance $RDS_ID (currently: $rds_status)..."
    aws rds stop-db-instance \
      --db-instance-identifier "$RDS_ID" \
      --region "$REGION" \
      --output text >/dev/null
    ok "RDS stop-db-instance issued"
  fi
else
  info "Skipping RDS (--skip-rds)"
fi

# ─── Step 5: Summary ────────────────────────────────────────────────────────
header "Shutdown summary"

if $DRY_RUN; then
  echo -e "${YELLOW}No changes were made (dry run)${RESET}"
  echo ""
  echo "Actions that would be taken:"
  echo "  - Scale llm-inference-service → desired 0"
  echo "  - Scale llm-search-engine     → desired 0"
  echo "  - Scale llm-ingestion-worker  → desired 0"
  if ! $SKIP_RDS; then
    echo "  - Stop RDS instance $RDS_ID"
  fi
else
  echo "Shut down:"
  echo "  - ECS services scaled to desired=0"
  if ! $SKIP_RDS; then
    echo "  - RDS instance $RDS_ID stopping"
  fi
fi

echo ""
echo -e "Estimated idle cost: ${GREEN}\$2.30/day${RESET} (ALB + stopped RDS storage)"
echo ""
echo -e "${CYAN}Tip:${RESET} To bring everything back up, run: ./aws-startup.sh"
