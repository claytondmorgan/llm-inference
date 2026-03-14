# AWS Dormant Mode: Snapshot-and-Delete RDS Strategy

**Date:** 2026-03-13
**Problem solved:** AWS auto-restarts stopped RDS instances after 7 days, causing idle costs to jump from $0.83/day to $2.56/day without warning.

## What changed

### Previous behavior (stop/start)
- **Shutdown:** ECS scaled to 0, RDS stopped
- **Startup:** RDS started from stopped state
- **Flaw:** AWS automatically restarts stopped RDS after 7 days — no way to prevent this
- **Idle cost:** $2.30/day (when RDS auto-restarted: $2.56/day)

### New behavior (snapshot/delete)
- **Shutdown:** ECS scaled to 0, RDS snapshotted as `llm-postgres-dormant`, then RDS instance deleted
- **Startup:** If RDS instance is missing, restores from snapshot `llm-postgres-dormant` (~10 min)
- **Idle cost:** $0.83/day (no auto-restart possible — instance doesn't exist)

## Idle cost breakdown ($0.83/day)

| Service | $/day | Notes |
|---|---|---|
| ALB (llm-alb) | $0.54 | Always-on; ECS services register to it |
| VPC (NAT/endpoints) | $0.12 | Networking foundation |
| ECR (container images) | $0.08 | Stores Docker images |
| Secrets Manager | $0.01 | Stores DB credentials |
| S3 | ~$0.00 | Negligible |

## Files modified

### `aws-shutdown.sh`
**Step 4 replaced:** Was `stop-db-instance` → now snapshot-and-delete:
1. If RDS is stopped, starts it first (can't snapshot a stopped instance)
2. Waits for RDS to become `available`
3. Deletes any previous `llm-postgres-dormant` snapshot
4. Creates new snapshot `llm-postgres-dormant`
5. Waits for snapshot to complete
6. Deletes the RDS instance (skip-final-snapshot since we just took one)
7. Safety: if snapshot times out, RDS is NOT deleted

**Config added:**
```bash
RDS_SNAPSHOT_ID="llm-postgres-dormant"
RDS_SNAPSHOT_POLL_INTERVAL=15
RDS_SNAPSHOT_POLL_TIMEOUT=600
```

### `aws-startup.sh`
**Step 1 replaced:** Was `start-db-instance` → now restore-or-start:
1. Checks if RDS instance exists via `describe-db-instances`
2. If `not-found`: looks for snapshot `llm-postgres-dormant` and restores with original config
3. If `stopped`: starts normally (backward compatible)
4. If `available`: skips (already running)
5. Waits for RDS to become available (timeout increased to 900s for restore)

**Config added:**
```bash
RDS_SNAPSHOT_ID="llm-postgres-dormant"
RDS_INSTANCE_CLASS="db.t3.medium"
RDS_SUBNET_GROUP="llm-db-subnet-group"
RDS_SECURITY_GROUP="sg-078ee389b94733a6a"
```

**RDS restore command:**
```bash
aws rds restore-db-instance-from-db-snapshot \
  --db-instance-identifier llm-postgres \
  --db-snapshot-identifier llm-postgres-dormant \
  --db-instance-class db.t3.medium \
  --db-subnet-group-name llm-db-subnet-group \
  --vpc-security-group-ids sg-078ee389b94733a6a \
  --no-publicly-accessible \
  --no-multi-az \
  --region us-east-1
```

### `.claude/commands/shutdown.md`
Updated skill description to reflect snapshot-and-delete behavior and $0.83/day idle cost.

### `.claude/commands/startup-and-test.md`
Updated skill description to document snapshot restore logic on startup.

## RDS instance configuration (preserved in snapshot)

| Property | Value |
|---|---|
| Instance ID | `llm-postgres` |
| Snapshot ID | `llm-postgres-dormant` |
| Engine | PostgreSQL 16.3 |
| Instance class | `db.t3.medium` |
| Storage | 20 GB gp2 |
| Subnet group | `llm-db-subnet-group` |
| Security group | `sg-078ee389b94733a6a` |
| Master username | `llmadmin` |
| Port | 5432 |
| Public access | No |
| Multi-AZ | No |

## Current state (as of 2026-03-13)

- ECS services: all at desired=0 (idle)
- RDS instance: **deleted** (does not exist)
- RDS snapshot: `llm-postgres-dormant` (available, 20 GB)
- To bring everything up: run `./aws-startup.sh` or use `/startup-and-test`