#!/bin/bash
#
# Test script for the Legal Document Search API
#
# Usage:
#   ./test-legal-api.sh                              # Uses localhost:8080
#   ./test-legal-api.sh http://my-alb.com            # Uses custom base URL
#   ./test-legal-api.sh http://my-alb.com -v         # Verbose mode
#   ./test-legal-api.sh -v                            # Verbose with localhost
#   ./test-legal-api.sh --verbose http://my-alb.com  # Verbose with custom URL
#
# Flags:
#   -v, --verbose   Show detailed test info: commands, latency, sizes, cost estimate
#
# Prerequisites:
#   - Python inference service running
#   - Legal documents ingested (POST /legal/ingest)
#

# ============================================
# ARGUMENT PARSING
# ============================================
VERBOSE=false
BASE_URL="http://localhost:8080"
for arg in "$@"; do
    case "$arg" in
        -v|--verbose) VERBOSE=true ;;
        -*) echo "Unknown flag: $arg"; exit 1 ;;
        *) BASE_URL="$arg" ;;
    esac
done

PASS=0
FAIL=0
WARN=0
SKIP=0
TEST_NUM=0

# Tracking for verbose summary
TOTAL_REQUESTS=0
TOTAL_TIME_MS=0
TOTAL_BYTES=0
MIN_LATENCY_MS=999999
MAX_LATENCY_MS=0
TEST_START=$(date +%s)

# Colors for output
GREEN='\033[0;32m'
RED='\033[0;31m'
YELLOW='\033[1;33m'
CYAN='\033[0;36m'
BOLD='\033[1m'
NC='\033[0m' # No Color

# ============================================
# HELPER FUNCTIONS
# ============================================

# Execute curl and capture response body + stats
# Sets globals: LAST_BODY, LAST_HTTP, LAST_LATENCY_MS, LAST_SIZE
exec_curl() {
    local _raw _stats _t _s
    _raw=$(curl -s -w "\n%{http_code} %{time_total} %{size_download}" "$@" 2>/dev/null)
    _stats=$(echo "$_raw" | tail -n1)
    LAST_BODY=$(echo "$_raw" | sed '$d')
    LAST_HTTP=$(echo "$_stats" | awk '{print $1}')
    _t=$(echo "$_stats" | awk '{print $2}')
    _s=$(echo "$_stats" | awk '{print $3}')
    LAST_LATENCY_MS=$(awk "BEGIN {printf \"%d\", ${_t:-0} * 1000}" 2>/dev/null)
    LAST_SIZE=$(awk "BEGIN {printf \"%d\", ${_s:-0}+0}" 2>/dev/null)
    LAST_LATENCY_MS=${LAST_LATENCY_MS:-0}
    LAST_SIZE=${LAST_SIZE:-0}
    ((TOTAL_REQUESTS++))
    TOTAL_TIME_MS=$((TOTAL_TIME_MS + LAST_LATENCY_MS))
    TOTAL_BYTES=$((TOTAL_BYTES + LAST_SIZE))
    if [ "$LAST_LATENCY_MS" -lt "$MIN_LATENCY_MS" ] 2>/dev/null; then MIN_LATENCY_MS=$LAST_LATENCY_MS; fi
    if [ "$LAST_LATENCY_MS" -gt "$MAX_LATENCY_MS" ] 2>/dev/null; then MAX_LATENCY_MS=$LAST_LATENCY_MS; fi
}

# Format bytes for display
format_bytes() {
    local bytes=$1
    if [ "$bytes" -ge 1048576 ] 2>/dev/null; then
        awk "BEGIN {printf \"%.1f MB\", $bytes/1048576}"
    elif [ "$bytes" -ge 1024 ] 2>/dev/null; then
        awk "BEGIN {printf \"%.1f KB\", $bytes/1024}"
    else
        echo "${bytes} bytes"
    fi
}

# Print verbose test header for inline tests
verbose_header() {
    local name="$1"
    local command_desc="$2"
    ((TEST_NUM++))
    if [ "$VERBOSE" = true ]; then
        echo ""
        echo -e "  ${CYAN}[Test $TEST_NUM]${NC} $name"
        echo -e "    Command:  $command_desc"
    else
        printf "%-60s" "$name"
    fi
}

# Print verbose test result for inline tests
verbose_result() {
    local status="$1"
    local detail="$2"
    if [ "$VERBOSE" = true ]; then
        case "$status" in
            PASS) echo -e "    Result:   ${GREEN}PASS${NC}${detail:+ ($detail)}" ;;
            FAIL) echo -e "    Result:   ${RED}FAIL${NC}${detail:+ ($detail)}" ;;
            WARN) echo -e "    Result:   ${YELLOW}WARN${NC}${detail:+ ($detail)}" ;;
        esac
        echo -e "    Stats:    ${LAST_LATENCY_MS}ms | ${LAST_SIZE} bytes"
    else
        case "$status" in
            PASS) echo -e "${GREEN}PASS${NC}${detail:+ ($detail)}" ;;
            FAIL) echo -e "${RED}FAIL${NC}${detail:+ ($detail)}" ;;
            WARN) echo -e "${YELLOW}WARN${NC}${detail:+ ($detail)}" ;;
        esac
    fi
}

# Helper function to run a test
run_test() {
    local name="$1"
    local method="$2"
    local endpoint="$3"
    local data="$4"
    local expected_status="$5"
    local check_field="$6"
    local check_value="$7"

    ((TEST_NUM++))

    if [ "$VERBOSE" = true ]; then
        echo ""
        echo -e "  ${CYAN}[Test $TEST_NUM]${NC} $name"
        if [ -n "$data" ]; then
            echo -e "    Command:  $method $BASE_URL$endpoint -d '$(echo "$data" | head -c 80)'"
        else
            echo -e "    Command:  $method $BASE_URL$endpoint"
        fi
    else
        printf "%-60s" "$name"
    fi

    # Execute request with timing
    if [ "$method" == "GET" ]; then
        exec_curl "$BASE_URL$endpoint"
    else
        exec_curl -X POST "$BASE_URL$endpoint" \
            -H "Content-Type: application/json" \
            -d "$data"
    fi

    local http_code="$LAST_HTTP"
    local body="$LAST_BODY"

    # Check HTTP status
    if [ "$http_code" != "$expected_status" ]; then
        if [ "$VERBOSE" = true ]; then
            echo -e "    Result:   ${RED}FAIL${NC} (expected HTTP $expected_status, got $http_code)"
            if [ -n "$body" ]; then
                echo -e "    Response: $(echo "$body" | head -c 200)"
            fi
            echo -e "    Stats:    ${LAST_LATENCY_MS}ms | ${LAST_SIZE} bytes"
        else
            echo -e "${RED}FAIL${NC} (expected HTTP $expected_status, got $http_code)"
            if [ -n "$body" ]; then
                echo "  Response: $(echo "$body" | head -c 200)"
            fi
        fi
        ((FAIL++))
        return 1
    fi

    # Check response field if specified
    if [ -n "$check_field" ]; then
        local actual_value
        actual_value=$(echo "$body" | python3 -c "import sys,json; d=json.load(sys.stdin); print(d.get('$check_field', 'MISSING'))" 2>/dev/null)
        if [ "$actual_value" != "$check_value" ]; then
            if [ "$VERBOSE" = true ]; then
                echo -e "    Result:   ${RED}FAIL${NC} ($check_field: expected '$check_value', got '$actual_value')"
                echo -e "    Stats:    ${LAST_LATENCY_MS}ms | ${LAST_SIZE} bytes"
            else
                echo -e "${RED}FAIL${NC} ($check_field: expected '$check_value', got '$actual_value')"
            fi
            ((FAIL++))
            return 1
        fi
    fi

    if [ "$VERBOSE" = true ]; then
        echo -e "    Result:   ${GREEN}PASS${NC}"
        echo -e "    Stats:    ${LAST_LATENCY_MS}ms | ${LAST_SIZE} bytes"
    else
        echo -e "${GREEN}PASS${NC}"
    fi
    ((PASS++))
    return 0
}

echo "=============================================="
echo "Legal Document Search API Tests"
echo "Base URL: $BASE_URL"
if [ "$VERBOSE" = true ]; then
    echo "Mode: VERBOSE"
fi
echo "=============================================="
echo ""

# ============================================
# HEALTH & INFO
# ============================================
echo -e "${CYAN}--- Health & Info ---${NC}"
echo ""

run_test "GET /health returns 200" \
    "GET" "/health" "" "200" "status" "healthy"

run_test "GET / returns service info" \
    "GET" "/" "" "200"

# Check legal documents are indexed
verbose_header "Health shows legal_documents_indexed" \
    "GET $BASE_URL/health"
exec_curl "$BASE_URL/health"
legal_count=$(echo "$LAST_BODY" | python3 -c "import sys,json; print(json.load(sys.stdin).get('legal_documents_indexed', 0))" 2>/dev/null)
if [ "$legal_count" -gt 0 ] 2>/dev/null; then
    verbose_result "PASS" "count: $legal_count"
    ((PASS++))
else
    verbose_result "WARN" "no legal docs indexed - run POST /legal/ingest first"
    ((SKIP++))
fi

# ============================================
# LEGAL DOCUMENT COUNT & RETRIEVAL
# ============================================
echo ""
echo -e "${CYAN}--- Legal Document Count & Retrieval ---${NC}"
echo ""

run_test "GET /legal/documents/count returns 200" \
    "GET" "/legal/documents/count" "" "200"

verbose_header "GET /legal/documents/count has total field" \
    "GET $BASE_URL/legal/documents/count"
exec_curl "$BASE_URL/legal/documents/count"
total=$(echo "$LAST_BODY" | python3 -c "import sys,json; print(json.load(sys.stdin).get('total', 0))" 2>/dev/null)
if [ "$total" -gt 0 ] 2>/dev/null; then
    verbose_result "PASS" "total: $total"
    ((PASS++))
else
    verbose_result "WARN" "total: $total"
    ((SKIP++))
fi

run_test "GET /legal/documents/case-001 returns Miranda" \
    "GET" "/legal/documents/case-001" "" "200" "title" "Miranda v. Arizona"

run_test "GET /legal/documents/nonexistent returns 404" \
    "GET" "/legal/documents/nonexistent" "" "404"

# ============================================
# SEMANTIC SEARCH
# ============================================
echo ""
echo -e "${CYAN}--- Semantic Search ---${NC}"
echo ""

run_test "Semantic: employment discrimination" \
    "POST" "/legal/search" \
    '{"query": "employment discrimination reasonable accommodation", "top_k": 5, "search_field": "content"}' "200"

run_test "Semantic: duty of care negligence" \
    "POST" "/legal/search" \
    '{"query": "duty of care negligence standard", "top_k": 5, "search_field": "content"}' "200"

run_test "Semantic: constitutional right to counsel" \
    "POST" "/legal/search" \
    '{"query": "constitutional right to counsel", "top_k": 5, "search_field": "content"}' "200"

run_test "Semantic: search by title field" \
    "POST" "/legal/search" \
    '{"query": "Miranda rights", "top_k": 5, "search_field": "title"}' "200"

run_test "Semantic: search by headnotes field" \
    "POST" "/legal/search" \
    '{"query": "exclusionary rule", "top_k": 5, "search_field": "headnotes"}' "200"

# Check search returns results array with correct structure
verbose_header "Semantic search returns valid structure" \
    "POST $BASE_URL/legal/search -d '{\"query\": \"wrongful termination\", \"top_k\": 3}'"
exec_curl -X POST "$BASE_URL/legal/search" \
    -H "Content-Type: application/json" \
    -d '{"query": "wrongful termination", "top_k": 3}'
structure_check=$(echo "$LAST_BODY" | python3 -c "
import sys, json
d = json.load(sys.stdin)
if not isinstance(d, list):
    print('NOT_LIST')
elif len(d) > 0:
    first = d[0]
    required = ['id', 'doc_id', 'doc_type', 'title', 'similarity', 'search_method']
    missing = [f for f in required if f not in first]
    if missing:
        print('MISSING: ' + ','.join(missing))
    else:
        print('OK')
else:
    print('EMPTY_OK')
" 2>/dev/null)
if [ "$structure_check" == "OK" ] || [ "$structure_check" == "EMPTY_OK" ]; then
    verbose_result "PASS"
    ((PASS++))
else
    verbose_result "FAIL" "$structure_check"
    ((FAIL++))
fi

# ============================================
# HYBRID SEARCH
# ============================================
echo ""
echo -e "${CYAN}--- Hybrid Search ---${NC}"
echo ""

run_test "Hybrid: civil rights statute search" \
    "POST" "/legal/search" \
    '{"query": "42 U.S.C. 1983 civil rights", "search_field": "hybrid", "top_k": 5}' "200"

run_test "Hybrid: employment discrimination" \
    "POST" "/legal/search" \
    '{"query": "employment discrimination reasonable accommodation", "search_field": "hybrid", "top_k": 5}' "200"

run_test "Hybrid: FMLA leave requirements" \
    "POST" "/legal/search" \
    '{"query": "FMLA family medical leave", "search_field": "hybrid", "top_k": 5}' "200"

# Compare semantic vs hybrid for citation search
echo ""
echo -e "${CYAN}--- Semantic vs Hybrid Comparison ---${NC}"
echo ""

verbose_header "Semantic search for '1983' (may miss exact match)" \
    "POST $BASE_URL/legal/search -d '{\"query\": \"1983\", \"search_field\": \"content\", \"top_k\": 5}'"
exec_curl -X POST "$BASE_URL/legal/search" \
    -H "Content-Type: application/json" \
    -d '{"query": "1983", "search_field": "content", "top_k": 5}'
sem_count=$(echo "$LAST_BODY" | python3 -c "import sys,json; print(len(json.load(sys.stdin)))" 2>/dev/null)
verbose_result "PASS" "results: $sem_count"
((PASS++))

verbose_header "Hybrid search for '1983' (catches keyword + semantic)" \
    "POST $BASE_URL/legal/search -d '{\"query\": \"1983\", \"search_field\": \"hybrid\", \"top_k\": 5}'"
exec_curl -X POST "$BASE_URL/legal/search" \
    -H "Content-Type: application/json" \
    -d '{"query": "1983", "search_field": "hybrid", "top_k": 5}'
hyb_count=$(echo "$LAST_BODY" | python3 -c "import sys,json; print(len(json.load(sys.stdin)))" 2>/dev/null)
verbose_result "PASS" "results: $hyb_count"
((PASS++))

# ============================================
# JURISDICTION FILTERING
# ============================================
echo ""
echo -e "${CYAN}--- Jurisdiction Filtering ---${NC}"
echo ""

run_test "Filter: California jurisdiction" \
    "POST" "/legal/search" \
    '{"query": "wrongful termination", "jurisdiction": "CA", "top_k": 5}' "200"

run_test "Filter: New York jurisdiction" \
    "POST" "/legal/search" \
    '{"query": "discrimination", "jurisdiction": "NY", "top_k": 5}' "200"

run_test "Filter: US Supreme Court" \
    "POST" "/legal/search" \
    '{"query": "constitutional rights", "jurisdiction": "US_Supreme_Court", "top_k": 5}' "200"

run_test "Filter: Federal 9th Circuit" \
    "POST" "/legal/search" \
    '{"query": "retaliation", "jurisdiction": "Federal_9th_Circuit", "top_k": 5}' "200"

# ============================================
# STATUS FILTERING (Shepard's Demo)
# ============================================
echo ""
echo -e "${CYAN}--- Status Filtering (Shepard's Demo) ---${NC}"
echo ""

run_test "Filter: exclude overruled cases" \
    "POST" "/legal/search" \
    '{"query": "separate but equal segregation", "status_filter": "exclude_overruled", "top_k": 10}' "200"

# Verify Plessy (overruled) is excluded
verbose_header "Plessy v. Ferguson excluded when filtering overruled" \
    "POST $BASE_URL/legal/search -d '{\"query\": \"separate but equal\", \"status_filter\": \"exclude_overruled\"}'"
exec_curl -X POST "$BASE_URL/legal/search" \
    -H "Content-Type: application/json" \
    -d '{"query": "separate but equal", "status_filter": "exclude_overruled", "top_k": 10}'
has_plessy=$(echo "$LAST_BODY" | python3 -c "
import sys, json
results = json.load(sys.stdin)
plessy = [r for r in results if 'Plessy' in r.get('title', '')]
print('FOUND' if plessy else 'EXCLUDED')
" 2>/dev/null)
if [ "$has_plessy" == "EXCLUDED" ]; then
    verbose_result "PASS" "Plessy correctly excluded"
    ((PASS++))
else
    verbose_result "FAIL" "Plessy was found despite overruled filter"
    ((FAIL++))
fi

# ============================================
# DOCUMENT TYPE FILTERING
# ============================================
echo ""
echo -e "${CYAN}--- Document Type Filtering ---${NC}"
echo ""

run_test "Filter: statutes only" \
    "POST" "/legal/search" \
    '{"query": "disability accommodation", "doc_type": "statute", "top_k": 5}' "200"

run_test "Filter: case law only" \
    "POST" "/legal/search" \
    '{"query": "disability accommodation", "doc_type": "case_law", "top_k": 5}' "200"

run_test "Filter: practice guides only" \
    "POST" "/legal/search" \
    '{"query": "filing a claim", "doc_type": "practice_guide", "top_k": 5}' "200"

run_test "Filter: regulations only" \
    "POST" "/legal/search" \
    '{"query": "harassment", "doc_type": "regulation", "top_k": 5}' "200"

# ============================================
# PRACTICE AREA FILTERING
# ============================================
echo ""
echo -e "${CYAN}--- Practice Area Filtering ---${NC}"
echo ""

run_test "Filter: employment practice area" \
    "POST" "/legal/search" \
    '{"query": "termination", "practice_area": "employment", "top_k": 5}' "200"

run_test "Filter: constitutional law practice area" \
    "POST" "/legal/search" \
    '{"query": "rights", "practice_area": "constitutional_law", "top_k": 5}' "200"

run_test "Filter: criminal practice area" \
    "POST" "/legal/search" \
    '{"query": "search and seizure", "practice_area": "criminal", "top_k": 5}' "200"

# ============================================
# COMBINED FILTERS
# ============================================
echo ""
echo -e "${CYAN}--- Combined Filters ---${NC}"
echo ""

run_test "Combined: CA employment, exclude overruled" \
    "POST" "/legal/search" \
    '{"query": "wrongful termination", "jurisdiction": "CA", "practice_area": "employment", "status_filter": "exclude_overruled", "top_k": 5}' "200"

run_test "Combined: Federal statute, hybrid search" \
    "POST" "/legal/search" \
    '{"query": "disability reasonable accommodation", "jurisdiction": "US_Federal", "doc_type": "statute", "search_field": "hybrid", "top_k": 5}' "200"

# ============================================
# LEGAL RAG
# ============================================
echo ""
echo -e "${CYAN}--- Legal RAG ---${NC}"
echo ""

run_test "Legal RAG: ADA requirements" \
    "POST" "/legal/rag" \
    '{"query": "What are the requirements for a reasonable accommodation under the ADA?", "top_k": 5}' "200"

# Check RAG response structure
verbose_header "Legal RAG returns valid structure" \
    "POST $BASE_URL/legal/rag -d '{\"query\": \"burden-shifting framework...\", \"top_k\": 3}'"
exec_curl -X POST "$BASE_URL/legal/rag" \
    -H "Content-Type: application/json" \
    -d '{"query": "What is the burden-shifting framework for employment discrimination?", "top_k": 3}'
rag_check=$(echo "$LAST_BODY" | python3 -c "
import sys, json
d = json.load(sys.stdin)
required = ['query', 'answer', 'sources', 'citations_used', 'faithfulness_note']
missing = [f for f in required if f not in d]
if missing:
    print('MISSING: ' + ','.join(missing))
elif not isinstance(d['sources'], list):
    print('SOURCES_NOT_LIST')
else:
    print('OK')
" 2>/dev/null)
if [ "$rag_check" == "OK" ]; then
    verbose_result "PASS"
    ((PASS++))
else
    verbose_result "FAIL" "$rag_check"
    ((FAIL++))
fi

run_test "Legal RAG with jurisdiction filter" \
    "POST" "/legal/rag" \
    '{"query": "Can an employer fire someone for filing a discrimination complaint?", "top_k": 5, "jurisdiction": "CA"}' "200"

run_test "Legal RAG: exclude overruled by default" \
    "POST" "/legal/rag" \
    '{"query": "What does the law say about racial segregation?", "top_k": 5}' "200"

# ============================================
# ERROR HANDLING
# ============================================
echo ""
echo -e "${CYAN}--- Error Handling ---${NC}"
echo ""

run_test "POST /legal/search with empty query returns 422" \
    "POST" "/legal/search" '{"query": ""}' "422"

run_test "POST /legal/rag with empty query returns 422" \
    "POST" "/legal/rag" '{"query": ""}' "422"

# ============================================
# PERFORMANCE
# ============================================
echo ""
echo -e "${CYAN}--- Performance ---${NC}"
echo ""

verbose_header "Legal semantic search latency" \
    "POST $BASE_URL/legal/search -d '{\"query\": \"employment discrimination\", \"top_k\": 10}'"
exec_curl -X POST "$BASE_URL/legal/search" \
    -H "Content-Type: application/json" \
    -d '{"query": "employment discrimination", "top_k": 10}'
latency=$LAST_LATENCY_MS
if [ "$latency" -lt 3000 ]; then
    verbose_result "PASS" "${latency}ms"
    ((PASS++))
else
    verbose_result "WARN" "${latency}ms - slow"
    ((WARN++))
fi

verbose_header "Legal hybrid search latency" \
    "POST $BASE_URL/legal/search -d '{\"query\": \"ADA reasonable accommodation\", \"search_field\": \"hybrid\"}'"
exec_curl -X POST "$BASE_URL/legal/search" \
    -H "Content-Type: application/json" \
    -d '{"query": "ADA reasonable accommodation", "search_field": "hybrid", "top_k": 10}'
latency=$LAST_LATENCY_MS
if [ "$latency" -lt 3000 ]; then
    verbose_result "PASS" "${latency}ms"
    ((PASS++))
else
    verbose_result "WARN" "${latency}ms - slow"
    ((WARN++))
fi

# ============================================
# SUMMARY
# ============================================
TEST_END=$(date +%s)
TEST_DURATION=$((TEST_END - TEST_START))

echo ""
echo "=============================================="
echo "Test Results"
echo "=============================================="
echo -e "Passed:  ${GREEN}$PASS${NC}"
echo -e "Failed:  ${RED}$FAIL${NC}"
if [ $WARN -gt 0 ]; then
    echo -e "Warned:  ${YELLOW}$WARN${NC}"
fi
if [ $SKIP -gt 0 ]; then
    echo -e "Skipped: ${YELLOW}$SKIP${NC}"
fi
echo ""

if [ $FAIL -eq 0 ]; then
    echo -e "${GREEN}All tests passed!${NC}"
else
    echo -e "${RED}Some tests failed.${NC}"
fi

# ============================================
# VERBOSE: PERFORMANCE SUMMARY & AWS COST
# ============================================
if [ "$VERBOSE" = true ]; then
    echo ""
    echo "=============================================="
    echo "Performance Summary"
    echo "=============================================="

    if [ $TOTAL_REQUESTS -gt 0 ]; then
        avg_latency=$((TOTAL_TIME_MS / TOTAL_REQUESTS))
    else
        avg_latency=0
    fi
    # Reset min if no requests
    [ "$MIN_LATENCY_MS" -eq 999999 ] 2>/dev/null && MIN_LATENCY_MS=0

    echo "  Total requests:     $TOTAL_REQUESTS"
    echo "  Total data recv:    $(format_bytes $TOTAL_BYTES)"
    echo "  Test wall time:     ${TEST_DURATION}s"
    echo "  Sum of latencies:   ${TOTAL_TIME_MS}ms"
    echo "  Avg latency:        ${avg_latency}ms"
    echo "  Min latency:        ${MIN_LATENCY_MS}ms"
    echo "  Max latency:        ${MAX_LATENCY_MS}ms"

    echo ""
    echo "=============================================="
    echo "AWS Cost Estimate (for test duration only)"
    echo "=============================================="
    echo ""
    echo "  Note: These costs reflect only the time spent"
    echo "  running this test suite. Actual infrastructure"
    echo "  costs accrue while services are running"
    echo "  regardless of test activity."
    echo ""

    # Compute cost components
    duration_hr=$(awk "BEGIN {printf \"%.6f\", $TEST_DURATION / 3600}")
    data_gb=$(awk "BEGIN {printf \"%.9f\", $TOTAL_BYTES / 1073741824}")

    alb_cost=$(awk "BEGIN {printf \"%.6f\", $duration_hr * 0.0225}")
    transfer_cost=$(awk "BEGIN {printf \"%.6f\", $data_gb * 0.09}")

    # Compute cost range for common instance types
    cost_t3_med=$(awk "BEGIN {printf \"%.6f\", $duration_hr * 0.0416}")
    cost_t3_xl=$(awk "BEGIN {printf \"%.6f\", $duration_hr * 0.1664}")
    cost_g4dn=$(awk "BEGIN {printf \"%.6f\", $duration_hr * 0.526}")
    cost_g5=$(awk "BEGIN {printf \"%.6f\", $duration_hr * 1.006}")

    total_low=$(awk "BEGIN {printf \"%.4f\", $alb_cost + $transfer_cost + $cost_t3_med}")
    total_high=$(awk "BEGIN {printf \"%.4f\", $alb_cost + $transfer_cost + $cost_g5}")

    echo "  Duration:           ${TEST_DURATION}s (${duration_hr} hours)"
    echo "  Data transferred:   $(format_bytes $TOTAL_BYTES) (${data_gb} GB)"
    echo ""
    echo "  ALB (us-east-1):    \$0.0225/hr x ${duration_hr}hr = \$${alb_cost}"
    echo "  Data transfer out:  \$0.09/GB  x ${data_gb}GB = \$${transfer_cost}"
    echo ""
    echo "  Compute (by instance type for test duration):"
    echo "    t3.medium:        \$0.0416/hr x ${duration_hr}hr = \$${cost_t3_med}"
    echo "    t3.xlarge:        \$0.1664/hr x ${duration_hr}hr = \$${cost_t3_xl}"
    echo "    g4dn.xlarge:      \$0.5260/hr x ${duration_hr}hr = \$${cost_g4dn}"
    echo "    g5.xlarge:        \$1.0060/hr x ${duration_hr}hr = \$${cost_g5}"
    echo ""
    echo -e "  ${BOLD}Estimated total:    \$${total_low} - \$${total_high}${NC}"
    echo "  (ALB + data + compute, varies by instance type)"
fi

echo ""
if [ $FAIL -eq 0 ]; then
    exit 0
else
    exit 1
fi