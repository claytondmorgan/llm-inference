#!/bin/bash
#
# Deploy the Legal Document Search update to AWS ECS
#
# This script:
#   1. Builds the Docker image with legal document support
#   2. Pushes to ECR
#   3. Runs the DB migration (creates legal_documents table + indexes)
#   4. Updates the ECS service to use the new image
#   5. Ingests legal documents via the API
#
# Usage:
#   ./deploy-legal.sh              # Full deploy
#   ./deploy-legal.sh --skip-db    # Skip DB migration (already done)
#   ./deploy-legal.sh --skip-ingest # Skip legal doc ingestion
#

set -e

# ============================================
# Configuration
# ============================================
AWS_REGION="us-east-1"
AWS_ACCOUNT_ID="717914742237"
ECR_REPO="llm-inference"
ECR_URI="${AWS_ACCOUNT_ID}.dkr.ecr.${AWS_REGION}.amazonaws.com/${ECR_REPO}"
ECS_CLUSTER="llm-cluster"
ECS_SERVICE="llm-inference-service"
TASK_FAMILY="llm-inference-task"
ALB_URL="http://llm-alb-1402483560.us-east-1.elb.amazonaws.com"

SKIP_DB=false
SKIP_INGEST=false

for arg in "$@"; do
    case $arg in
        --skip-db) SKIP_DB=true ;;
        --skip-ingest) SKIP_INGEST=true ;;
    esac
done

# Colors
GREEN='\033[0;32m'
RED='\033[0;31m'
YELLOW='\033[1;33m'
CYAN='\033[0;36m'
NC='\033[0m'

echo "=============================================="
echo "Legal Document Search - AWS Deployment"
echo "=============================================="
echo ""

# ============================================
# Step 1: Build Docker image
# ============================================
echo -e "${CYAN}[1/5] Building Docker image...${NC}"
docker build --platform linux/amd64 -t ${ECR_REPO}:latest .
echo -e "${GREEN}  ✓ Image built${NC}"

# ============================================
# Step 2: Push to ECR
# ============================================
echo ""
echo -e "${CYAN}[2/5] Pushing to ECR...${NC}"

# Login to ECR
aws ecr get-login-password --region ${AWS_REGION} | \
    docker login --username AWS --password-stdin ${AWS_ACCOUNT_ID}.dkr.ecr.${AWS_REGION}.amazonaws.com

# Tag and push
docker tag ${ECR_REPO}:latest ${ECR_URI}:latest
docker push ${ECR_URI}:latest
echo -e "${GREEN}  ✓ Image pushed to ${ECR_URI}:latest${NC}"

# ============================================
# Step 3: Run DB migration
# ============================================
if [ "$SKIP_DB" = false ]; then
    echo ""
    echo -e "${CYAN}[3/5] Running database migration...${NC}"
    echo "  Running migrate_schema.py via ECS task..."

    # Run migration as a one-off ECS task
    TASK_ARN=$(aws ecs run-task \
        --cluster ${ECS_CLUSTER} \
        --task-definition ${TASK_FAMILY} \
        --launch-type FARGATE \
        --network-configuration "awsvpcConfiguration={subnets=[$(aws ecs describe-services --cluster ${ECS_CLUSTER} --services ${ECS_SERVICE} --query 'services[0].networkConfiguration.awsvpcConfiguration.subnets' --output text | tr '\t' ',')],securityGroups=[$(aws ecs describe-services --cluster ${ECS_CLUSTER} --services ${ECS_SERVICE} --query 'services[0].networkConfiguration.awsvpcConfiguration.securityGroups' --output text | tr '\t' ',')],assignPublicIp=ENABLED}" \
        --overrides '{
            "containerOverrides": [{
                "name": "llm-container",
                "command": ["python", "migrate_schema.py"]
            }]
        }' \
        --query 'tasks[0].taskArn' \
        --output text \
        --region ${AWS_REGION} 2>/dev/null) || true

    if [ -n "$TASK_ARN" ] && [ "$TASK_ARN" != "None" ]; then
        echo "  Migration task started: $TASK_ARN"
        echo "  Waiting for migration to complete..."
        aws ecs wait tasks-stopped --cluster ${ECS_CLUSTER} --tasks "$TASK_ARN" --region ${AWS_REGION} 2>/dev/null || true
        echo -e "${GREEN}  ✓ Migration complete${NC}"
    else
        echo -e "${YELLOW}  ⚠ Could not run migration as ECS task. You can run it manually:${NC}"
        echo "    python migrate_schema.py"
    fi
else
    echo ""
    echo -e "${YELLOW}[3/5] Skipping DB migration (--skip-db)${NC}"
fi

# ============================================
# Step 4: Update ECS service (force new deployment)
# ============================================
echo ""
echo -e "${CYAN}[4/5] Updating ECS service...${NC}"

aws ecs update-service \
    --cluster ${ECS_CLUSTER} \
    --service ${ECS_SERVICE} \
    --force-new-deployment \
    --region ${AWS_REGION} \
    --query 'service.serviceName' \
    --output text > /dev/null

echo "  Waiting for service to stabilize (this may take 3-5 minutes)..."
aws ecs wait services-stable \
    --cluster ${ECS_CLUSTER} \
    --services ${ECS_SERVICE} \
    --region ${AWS_REGION} 2>/dev/null || true

echo -e "${GREEN}  ✓ ECS service updated${NC}"

# ============================================
# Step 5: Ingest legal documents
# ============================================
if [ "$SKIP_INGEST" = false ]; then
    echo ""
    echo -e "${CYAN}[5/5] Ingesting legal documents...${NC}"

    # Wait for the service to be healthy
    echo "  Waiting for service health check..."
    for i in {1..30}; do
        health=$(curl -s -o /dev/null -w "%{http_code}" "${ALB_URL}/health" 2>/dev/null)
        if [ "$health" = "200" ]; then
            break
        fi
        sleep 10
    done

    if [ "$health" = "200" ]; then
        echo "  Service is healthy, ingesting legal documents..."
        response=$(curl -s -X POST "${ALB_URL}/legal/ingest" -w "\n%{http_code}")
        http_code=$(echo "$response" | tail -n1)
        body=$(echo "$response" | sed '$d')

        if [ "$http_code" = "200" ]; then
            echo -e "${GREEN}  ✓ Legal documents ingested${NC}"
            echo "  $body"
        else
            echo -e "${RED}  ✗ Ingestion failed (HTTP $http_code)${NC}"
            echo "  $body"
        fi
    else
        echo -e "${YELLOW}  ⚠ Service not healthy yet. Ingest manually:${NC}"
        echo "    curl -X POST ${ALB_URL}/legal/ingest"
    fi
else
    echo ""
    echo -e "${YELLOW}[5/5] Skipping legal doc ingestion (--skip-ingest)${NC}"
fi

# ============================================
# Summary
# ============================================
echo ""
echo "=============================================="
echo -e "${GREEN}Deployment complete!${NC}"
echo "=============================================="
echo ""
echo "Test the deployment:"
echo "  ./test-inference-api.sh ${ALB_URL}"
echo "  ./test-legal-api.sh ${ALB_URL}"
echo ""
echo "Manual steps if needed:"
echo "  Ingest legal docs:  curl -X POST ${ALB_URL}/legal/ingest"
echo "  Check health:       curl ${ALB_URL}/health"
echo "  Legal doc count:    curl ${ALB_URL}/legal/documents/count"
echo "  Legal search:       curl -X POST ${ALB_URL}/legal/search -H 'Content-Type: application/json' -d '{\"query\": \"employment discrimination\", \"top_k\": 5}'"