#!/usr/bin/env bash
set -euo pipefail

# ─── Configuration ───────────────────────────────────────────────────────────
REGION="us-east-1"
CLUSTER="llm-cluster"
RDS_ID="llm-postgres"
RDS_SNAPSHOT_ID="llm-postgres-dormant"
RDS_INSTANCE_CLASS="db.t3.medium"
RDS_SUBNET_GROUP="llm-db-subnet-group"
RDS_SECURITY_GROUP="sg-078ee389b94733a6a"
ALB_HEALTH_URL="http://llm-alb-1402483560.us-east-1.elb.amazonaws.com/api/health"

SERVICES=(llm-inference-service llm-search-engine)
TARGETS=(1 2)
# Note: llm-ingestion-worker stays at 0 (on-demand only)

RDS_POLL_INTERVAL=30
RDS_POLL_TIMEOUT=900
ECS_POLL_INTERVAL=15
ECS_POLL_TIMEOUT=300
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

for i in "${!SERVICES[@]}"; do
  svc="${SERVICES[$i]}"
  target="${TARGETS[$i]}"

  result=$(aws ecs describe-services \
    --cluster "$CLUSTER" \
    --services "$svc" \
    --region "$REGION" \
    --query 'services[0].{desired:desiredCount,running:runningCount,status:status}' \
    --output json 2>/dev/null || echo '{}')

  desired=$(echo "$result" | grep -o '"desired": *[0-9]*' | grep -o '[0-9]*' || echo "?")
  running=$(echo "$result" | grep -o '"running": *[0-9]*' | grep -o '[0-9]*' || echo "?")
  status=$(echo "$result" | grep -o '"status": *"[^"]*"' | cut -d'"' -f4 || echo "?")

  if [[ "$running" == "$target" && "$desired" == "$target" ]]; then
    ok "$svc: already at target (desired=$desired, running=$running)"
  else
    info "$svc: desired=$desired, running=$running, status=$status (target=$target)"
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

# ─── Step 1: Start or restore RDS ───────────────────────────────────────────
if ! $SKIP_RDS; then
  header "Starting RDS instance"

  rds_status=$(aws rds describe-db-instances \
    --db-instance-identifier "$RDS_ID" \
    --region "$REGION" \
    --query 'DBInstances[0].DBInstanceStatus' \
    --output text 2>/dev/null || echo "not-found")

  if [[ "$rds_status" == "available" ]]; then
    ok "RDS $RDS_ID: already available"
  elif $DRY_RUN; then
    if [[ "$rds_status" == "not-found" ]]; then
      info "[DRY RUN] Would restore RDS from snapshot $RDS_SNAPSHOT_ID"
    else
      info "[DRY RUN] Would start RDS instance $RDS_ID (currently: $rds_status)"
    fi
  else
    if [[ "$rds_status" == "not-found" ]]; then
      # Instance doesn't exist — check for snapshot and restore
      snap_status=$(aws rds describe-db-snapshots \
        --db-snapshot-identifier "$RDS_SNAPSHOT_ID" \
        --region "$REGION" \
        --query 'DBSnapshots[0].Status' \
        --output text 2>/dev/null || echo "not-found")

      if [[ "$snap_status" == "available" ]]; then
        info "RDS instance not found — restoring from snapshot $RDS_SNAPSHOT_ID..."
        aws rds restore-db-instance-from-db-snapshot \
          --db-instance-identifier "$RDS_ID" \
          --db-snapshot-identifier "$RDS_SNAPSHOT_ID" \
          --db-instance-class "$RDS_INSTANCE_CLASS" \
          --db-subnet-group-name "$RDS_SUBNET_GROUP" \
          --vpc-security-group-ids "$RDS_SECURITY_GROUP" \
          --no-publicly-accessible \
          --no-multi-az \
          --region "$REGION" \
          --output text >/dev/null
        ok "RDS restore-from-snapshot issued"
      else
        err "No RDS instance and no snapshot found ($RDS_SNAPSHOT_ID: $snap_status)"
        err "Cannot start database. Aborting."
        exit 1
      fi
    elif [[ "$rds_status" == "stopped" ]]; then
      info "Starting RDS instance $RDS_ID..."
      aws rds start-db-instance \
        --db-instance-identifier "$RDS_ID" \
        --region "$REGION" \
        --output text >/dev/null
      ok "RDS start-db-instance issued"
    elif [[ "$rds_status" == "starting" || "$rds_status" == "creating" ]]; then
      info "RDS $RDS_ID is already coming up ($rds_status)..."
    else
      warn "RDS $RDS_ID in unexpected state: $rds_status — waiting for it to resolve"
    fi

    # ─── Step 2: Wait for RDS available ──────────────────────────────────
    header "Waiting for RDS to become available"
    elapsed=0
    while (( elapsed < RDS_POLL_TIMEOUT )); do
      rds_status=$(aws rds describe-db-instances \
        --db-instance-identifier "$RDS_ID" \
        --region "$REGION" \
        --query 'DBInstances[0].DBInstanceStatus' \
        --output text 2>/dev/null || echo "not-found")

      if [[ "$rds_status" == "available" ]]; then
        ok "RDS $RDS_ID is available (took ${elapsed}s)"
        break
      fi

      info "RDS status: $rds_status (${elapsed}s / ${RDS_POLL_TIMEOUT}s)..."
      sleep "$RDS_POLL_INTERVAL"
      elapsed=$(( elapsed + RDS_POLL_INTERVAL ))
    done

    if [[ "$rds_status" != "available" ]]; then
      warn "Timeout waiting for RDS (${RDS_POLL_TIMEOUT}s). Current status: $rds_status"
      warn "Proceeding with ECS startup — services may fail health checks until RDS is ready"
    fi
  fi
else
  info "Skipping RDS (--skip-rds)"
fi

# ─── Step 3: Scale ECS services ─────────────────────────────────────────────
header "Scaling ECS services"

for i in "${!SERVICES[@]}"; do
  svc="${SERVICES[$i]}"
  target="${TARGETS[$i]}"

  current_desired=$(aws ecs describe-services \
    --cluster "$CLUSTER" \
    --services "$svc" \
    --region "$REGION" \
    --query 'services[0].desiredCount' \
    --output text 2>/dev/null || echo "0")

  if [[ "$current_desired" == "$target" ]]; then
    ok "$svc: already at desired=$target, skipping"
    continue
  fi

  if $DRY_RUN; then
    info "[DRY RUN] Would scale $svc from desired=$current_desired to $target"
  else
    info "Scaling $svc to desired=$target (was $current_desired)..."
    aws ecs update-service \
      --cluster "$CLUSTER" \
      --service "$svc" \
      --desired-count "$target" \
      --region "$REGION" \
      --query 'service.serviceName' \
      --output text >/dev/null
    ok "$svc scaled to $target"
  fi
done

# ─── Step 4: Wait for tasks to reach RUNNING ────────────────────────────────
if ! $DRY_RUN; then
  header "Waiting for tasks to reach RUNNING"

  elapsed=0
  while (( elapsed < ECS_POLL_TIMEOUT )); do
    all_running=true
    for i in "${!SERVICES[@]}"; do
      svc="${SERVICES[$i]}"
      target="${TARGETS[$i]}"
      running=$(aws ecs describe-services \
        --cluster "$CLUSTER" \
        --services "$svc" \
        --region "$REGION" \
        --query 'services[0].runningCount' \
        --output text 2>/dev/null || echo "0")

      if (( running < target )); then
        all_running=false
        info "$svc: $running / $target running (${elapsed}s / ${ECS_POLL_TIMEOUT}s)..."
        break
      fi
    done

    if $all_running; then
      ok "All ECS services at target count"
      break
    fi

    sleep "$ECS_POLL_INTERVAL"
    elapsed=$(( elapsed + ECS_POLL_INTERVAL ))
  done

  if ! $all_running; then
    warn "Timeout reached (${ECS_POLL_TIMEOUT}s). Some services may still be starting."
  fi
fi

# ─── Step 5: Health check ───────────────────────────────────────────────────
if ! $DRY_RUN && command -v curl &>/dev/null; then
  header "Health check"

  # Give ALB a moment to register targets
  sleep 5

  http_code=$(curl -s -o /dev/null -w '%{http_code}' --max-time 10 "$ALB_HEALTH_URL" 2>/dev/null || echo "000")

  if [[ "$http_code" == "200" ]]; then
    ok "Health check passed (HTTP $http_code): $ALB_HEALTH_URL"
  elif [[ "$http_code" == "000" ]]; then
    warn "Health check: could not connect to $ALB_HEALTH_URL"
    warn "Services may still be registering with the ALB — try again in a minute"
  else
    warn "Health check returned HTTP $http_code (expected 200)"
    warn "Endpoint: $ALB_HEALTH_URL"
  fi
fi

# ─── Step 6: Summary ────────────────────────────────────────────────────────
header "Startup summary"

if $DRY_RUN; then
  echo -e "${YELLOW}No changes were made (dry run)${RESET}"
  echo ""
  echo "Actions that would be taken:"
  if ! $SKIP_RDS; then
    echo "  - Restore/start RDS instance $RDS_ID (from snapshot if needed)"
    echo "  - Wait for RDS to become available"
  fi
  echo "  - Scale llm-inference-service → desired 1  (8 vCPU, 16GB)"
  echo "  - Scale llm-search-engine     → desired 2  (0.5 vCPU, 1GB each)"
  echo "  - llm-ingestion-worker stays at 0 (on-demand)"
  echo "  - Health check ALB endpoint"
else
  echo "Started:"
  if ! $SKIP_RDS; then
    echo "  - RDS instance $RDS_ID"
  fi
  echo "  - llm-inference-service: 1 task  (8 vCPU, 16GB)"
  echo "  - llm-search-engine:     2 tasks (0.5 vCPU, 1GB each)"
  echo "  - llm-ingestion-worker:  0 (on-demand)"
fi

echo ""
echo -e "Estimated running cost: ${YELLOW}\$21.00/day${RESET}"
echo ""
echo -e "${CYAN}Tip:${RESET} To shut down and save costs, run: ./aws-shutdown.sh"
echo -e "${CYAN}Tip:${RESET} Both scripts work from either project directory."
echo -e "     Symlink for Java project: ln -s ../PycharmProjects/llm-inference-test6/aws-startup.sh VectorSearchDemo-test4/aws-startup.sh"
