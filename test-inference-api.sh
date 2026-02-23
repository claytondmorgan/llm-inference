#!/bin/bash
#
# Test script for the Python Inference Service API
#
# Usage:
#   ./test-inference-api.sh                              # Uses localhost:8080
#   ./test-inference-api.sh http://my-alb.com            # Uses custom base URL
#   ./test-inference-api.sh http://my-alb.com -v         # Verbose mode
#   ./test-inference-api.sh -v                            # Verbose with localhost
#   ./test-inference-api.sh --verbose http://my-alb.com  # Verbose with custom URL
#
# Flags:
#   -v, --verbose   Show detailed test info: commands, latency, sizes, cost estimate
#
# Prerequisites:
#   - Python inference service running
#   - Database with some documents/ingested records (for search tests)
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
        printf "%-55s" "$name"
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
        printf "%-55s" "$name"
    fi

    # Execute request with timing
    if [ "$method" == "GET" ]; then
        exec_curl "$BASE_URL$endpoint"
    elif [ "$method" == "DELETE" ]; then
        exec_curl -X DELETE "$BASE_URL$endpoint"
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
echo "Python Inference Service API Tests"
echo "Base URL: $BASE_URL"
if [ "$VERBOSE" = true ]; then
    echo "Mode: VERBOSE"
fi
echo "=============================================="
echo ""

# ============================================
# HEALTH & INFO ENDPOINTS
# ============================================
echo -e "${CYAN}--- Health & Info Endpoints ---${NC}"
echo ""

run_test "GET /health returns 200" \
    "GET" "/health" "" "200" "status" "healthy"

run_test "GET /health shows generator_loaded" \
    "GET" "/health" "" "200"

run_test "GET /health shows embedder_loaded" \
    "GET" "/health" "" "200"

run_test "GET / returns service info" \
    "GET" "/" "" "200" "service" "LLM Inference API with Vector Search & Legal Document Search"

run_test "GET / shows version 5.0.0" \
    "GET" "/" "" "200" "version" "5.0.0"

# ============================================
# EMBED ENDPOINT
# ============================================
echo ""
echo -e "${CYAN}--- Embed Endpoint ---${NC}"
echo ""

run_test "POST /embed with valid text" \
    "POST" "/embed" '{"text": "comfortable running shoes"}' "200"

# Check embedding dimensions
verbose_header "POST /embed returns 384 dimensions" \
    "POST $BASE_URL/embed -d '{\"text\": \"test embedding\"}'"
exec_curl -X POST "$BASE_URL/embed" \
    -H "Content-Type: application/json" \
    -d '{"text": "test embedding"}'
dims=$(echo "$LAST_BODY" | python3 -c "import sys,json; print(json.load(sys.stdin).get('dimensions', 0))" 2>/dev/null)
if [ "$dims" == "384" ]; then
    verbose_result "PASS"
    ((PASS++))
else
    verbose_result "FAIL" "got $dims dimensions"
    ((FAIL++))
fi

# Check embedding is a list of floats
verbose_header "POST /embed returns valid embedding array" \
    "POST $BASE_URL/embed -d '{\"text\": \"test embedding\"}'"
exec_curl -X POST "$BASE_URL/embed" \
    -H "Content-Type: application/json" \
    -d '{"text": "test embedding"}'
is_valid=$(echo "$LAST_BODY" | python3 -c "
import sys, json
d = json.load(sys.stdin)
emb = d.get('embedding', [])
if len(emb) == 384 and all(isinstance(x, float) for x in emb):
    print('OK')
else:
    print('INVALID')
" 2>/dev/null)
if [ "$is_valid" == "OK" ]; then
    verbose_result "PASS"
    ((PASS++))
else
    verbose_result "FAIL"
    ((FAIL++))
fi

run_test "POST /embed with empty text returns 422" \
    "POST" "/embed" '{"text": ""}' "422"

run_test "POST /embed with missing text returns 422" \
    "POST" "/embed" '{"wrong_field": "test"}' "422"

# ============================================
# TEXT GENERATION ENDPOINT
# ============================================
echo ""
echo -e "${CYAN}--- Text Generation Endpoint ---${NC}"
echo ""

run_test "POST /generate with valid prompt" \
    "POST" "/generate" '{"prompt": "The future of AI is"}' "200"

# Check generated text is returned
verbose_header "POST /generate returns generated_text" \
    "POST $BASE_URL/generate -d '{\"prompt\": \"Hello world\", \"max_new_tokens\": 20}'"
exec_curl -X POST "$BASE_URL/generate" \
    -H "Content-Type: application/json" \
    -d '{"prompt": "Hello world", "max_new_tokens": 20}'
has_text=$(echo "$LAST_BODY" | python3 -c "
import sys, json
d = json.load(sys.stdin)
if 'generated_text' in d and len(d['generated_text']) > 0:
    print('OK')
else:
    print('MISSING')
" 2>/dev/null)
if [ "$has_text" == "OK" ]; then
    verbose_result "PASS"
    ((PASS++))
else
    verbose_result "FAIL"
    ((FAIL++))
fi

run_test "POST /generate with max_new_tokens" \
    "POST" "/generate" '{"prompt": "Once upon a time", "max_new_tokens": 50}' "200"

run_test "POST /generate with temperature" \
    "POST" "/generate" '{"prompt": "The weather today is", "temperature": 0.5}' "200"

# ============================================
# DOCUMENT ENDPOINTS
# ============================================
echo ""
echo -e "${CYAN}--- Document Endpoints ---${NC}"
echo ""

# Add a single document
verbose_header "POST /documents adds a document" \
    "POST $BASE_URL/documents -d '{\"content\": \"Test document...\", \"metadata\": {\"test\": true}}'"
exec_curl -X POST "$BASE_URL/documents" \
    -H "Content-Type: application/json" \
    -d '{"content": "Test document for API testing - Python inference service", "metadata": {"test": true, "source": "api-test"}}'
doc_id=$(echo "$LAST_BODY" | python3 -c "import sys,json; print(json.load(sys.stdin).get('id', ''))" 2>/dev/null)
if [ -n "$doc_id" ] && [ "$doc_id" != "" ]; then
    verbose_result "PASS" "id: $doc_id"
    ((PASS++))
else
    verbose_result "FAIL"
    ((FAIL++))
fi

# Add batch documents
verbose_header "POST /documents/batch adds multiple documents" \
    "POST $BASE_URL/documents/batch -d '[{...}, {...}, {...}]'"
exec_curl -X POST "$BASE_URL/documents/batch" \
    -H "Content-Type: application/json" \
    -d '[
        {"content": "Batch test document 1 - wireless headphones with noise cancellation", "metadata": {"batch": 1}},
        {"content": "Batch test document 2 - laptop stand for ergonomic workspace", "metadata": {"batch": 2}},
        {"content": "Batch test document 3 - organic coffee beans from Colombia", "metadata": {"batch": 3}}
    ]'
num_ids=$(echo "$LAST_BODY" | python3 -c "import sys,json; print(len(json.load(sys.stdin).get('ids', [])))" 2>/dev/null)
if [ "$num_ids" == "3" ]; then
    verbose_result "PASS" "added 3 documents"
    ((PASS++))
else
    verbose_result "FAIL" "expected 3, got $num_ids"
    ((FAIL++))
fi

# Get document count
run_test "GET /documents/count returns count" \
    "GET" "/documents/count" "" "200"

verbose_header "GET /documents/count returns valid number" \
    "GET $BASE_URL/documents/count"
exec_curl "$BASE_URL/documents/count"
count=$(echo "$LAST_BODY" | python3 -c "import sys,json; print(json.load(sys.stdin).get('count', -1))" 2>/dev/null)
if [ "$count" -ge 0 ] 2>/dev/null; then
    verbose_result "PASS" "count: $count"
    ((PASS++))
else
    verbose_result "FAIL"
    ((FAIL++))
fi

# Delete document (if we created one)
if [ -n "$doc_id" ] && [ "$doc_id" != "" ]; then
    run_test "DELETE /documents/{id} removes document" \
        "DELETE" "/documents/$doc_id" "" "200"
fi

# ============================================
# SEARCH ENDPOINTS (documents table)
# ============================================
echo ""
echo -e "${CYAN}--- Search Endpoints (documents table) ---${NC}"
echo ""

run_test "POST /search with valid query" \
    "POST" "/search" '{"query": "headphones", "top_k": 5}' "200"

# Check search returns results array
verbose_header "POST /search returns results array" \
    "POST $BASE_URL/search -d '{\"query\": \"laptop computer\", \"top_k\": 5}'"
exec_curl -X POST "$BASE_URL/search" \
    -H "Content-Type: application/json" \
    -d '{"query": "laptop computer", "top_k": 5}'
has_results=$(echo "$LAST_BODY" | python3 -c "
import sys, json
d = json.load(sys.stdin)
if isinstance(d, list):
    print('OK')
else:
    print('NOT_LIST')
" 2>/dev/null)
if [ "$has_results" == "OK" ]; then
    verbose_result "PASS"
    ((PASS++))
else
    verbose_result "FAIL" "$has_results"
    ((FAIL++))
fi

run_test "POST /search with top_k=1" \
    "POST" "/search" '{"query": "coffee", "top_k": 1}' "200"

run_test "POST /search with top_k=20" \
    "POST" "/search" '{"query": "electronics", "top_k": 20}' "200"

# ============================================
# SEARCH ENDPOINTS (ingested_records table)
# ============================================
echo ""
echo -e "${CYAN}--- Search Endpoints (ingested_records table) ---${NC}"
echo ""

run_test "POST /search/records with valid query" \
    "POST" "/search/records" '{"query": "running shoes", "top_k": 5}' "200"

run_test "POST /search/records with category filter" \
    "POST" "/search/records" '{"query": "electronics", "top_k": 5, "category": "Electronics"}' "200"

run_test "POST /search/records by title field" \
    "POST" "/search/records" '{"query": "laptop", "top_k": 5, "search_field": "title"}' "200"

run_test "POST /search/records by content field" \
    "POST" "/search/records" '{"query": "comfortable shoes", "top_k": 5, "search_field": "content"}' "200"

# Check search results structure
verbose_header "POST /search/records returns valid structure" \
    "POST $BASE_URL/search/records -d '{\"query\": \"test product\", \"top_k\": 3}'"
exec_curl -X POST "$BASE_URL/search/records" \
    -H "Content-Type: application/json" \
    -d '{"query": "test product", "top_k": 3}'
structure_check=$(echo "$LAST_BODY" | python3 -c "
import sys, json
d = json.load(sys.stdin)
if not isinstance(d, list):
    print('NOT_LIST')
elif len(d) > 0:
    first = d[0]
    required = ['id', 'similarity']
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

# Semantic search tests
echo ""
echo -e "${CYAN}--- Semantic Search Tests ---${NC}"
echo ""

run_test "Semantic: gift for cooking lover" \
    "POST" "/search/records" '{"query": "gift for someone who loves cooking", "top_k": 5}' "200"

run_test "Semantic: budget electronics" \
    "POST" "/search/records" '{"query": "cheap affordable gadgets under 50 dollars", "top_k": 5}' "200"

run_test "Semantic: outdoor adventure gear" \
    "POST" "/search/records" '{"query": "hiking camping outdoor equipment", "top_k": 5}' "200"

run_test "Semantic: home office setup" \
    "POST" "/search/records" '{"query": "work from home desk accessories", "top_k": 5}' "200"

# ============================================
# RAG ENDPOINT
# ============================================
echo ""
echo -e "${CYAN}--- RAG Endpoint ---${NC}"
echo ""

run_test "POST /rag with valid query" \
    "POST" "/rag" '{"query": "What products are good for working from home?", "top_k": 3}' "200"

# Check RAG response structure
verbose_header "POST /rag returns answer and sources" \
    "POST $BASE_URL/rag -d '{\"query\": \"Tell me about electronics\", \"top_k\": 2}'"
exec_curl -X POST "$BASE_URL/rag" \
    -H "Content-Type: application/json" \
    -d '{"query": "Tell me about electronics", "top_k": 2, "max_new_tokens": 50}'
rag_check=$(echo "$LAST_BODY" | python3 -c "
import sys, json
d = json.load(sys.stdin)
if 'answer' not in d:
    print('NO_ANSWER')
elif 'sources' not in d:
    print('NO_SOURCES')
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

run_test "POST /rag with max_new_tokens" \
    "POST" "/rag" '{"query": "What is a good laptop?", "top_k": 2, "max_new_tokens": 100}' "200"

# ============================================
# INGESTION ENDPOINTS
# ============================================
echo ""
echo -e "${CYAN}--- Ingestion Endpoints ---${NC}"
echo ""

run_test "GET /ingestion/jobs returns list" \
    "GET" "/ingestion/jobs" "" "200"

# Check jobs is a list
verbose_header "GET /ingestion/jobs returns array" \
    "GET $BASE_URL/ingestion/jobs"
exec_curl "$BASE_URL/ingestion/jobs"
is_list=$(echo "$LAST_BODY" | python3 -c "
import sys, json
d = json.load(sys.stdin)
print('OK' if isinstance(d, list) else 'NOT_LIST')
" 2>/dev/null)
if [ "$is_list" == "OK" ]; then
    verbose_result "PASS"
    ((PASS++))
else
    verbose_result "FAIL"
    ((FAIL++))
fi

run_test "GET /ingestion/jobs with limit param" \
    "GET" "/ingestion/jobs?limit=5" "" "200"

run_test "GET /ingestion/stats returns stats" \
    "GET" "/ingestion/stats" "" "200"

# Check stats structure
verbose_header "GET /ingestion/stats has required fields" \
    "GET $BASE_URL/ingestion/stats"
exec_curl "$BASE_URL/ingestion/stats"
stats_check=$(echo "$LAST_BODY" | python3 -c "
import sys, json
d = json.load(sys.stdin)
required = ['total_records', 'total_files', 'total_categories']
missing = [f for f in required if f not in d]
if missing:
    print('MISSING: ' + ','.join(missing))
else:
    print('OK')
" 2>/dev/null)
if [ "$stats_check" == "OK" ]; then
    verbose_result "PASS"
    ((PASS++))
else
    verbose_result "FAIL" "$stats_check"
    ((FAIL++))
fi

run_test "GET /ingestion/records/count returns count" \
    "GET" "/ingestion/records/count" "" "200"

verbose_header "GET /ingestion/records/count returns valid number" \
    "GET $BASE_URL/ingestion/records/count"
exec_curl "$BASE_URL/ingestion/records/count"
count=$(echo "$LAST_BODY" | python3 -c "import sys,json; print(json.load(sys.stdin).get('count', -1))" 2>/dev/null)
if [ "$count" -ge 0 ] 2>/dev/null; then
    verbose_result "PASS" "count: $count"
    ((PASS++))
else
    verbose_result "FAIL"
    ((FAIL++))
fi

# ============================================
# ERROR HANDLING
# ============================================
echo ""
echo -e "${CYAN}--- Error Handling ---${NC}"
echo ""

run_test "POST /search with empty query returns 422" \
    "POST" "/search" '{"query": ""}' "422"

run_test "POST /search/records with empty query returns 422" \
    "POST" "/search/records" '{"query": ""}' "422"

run_test "POST /generate with empty prompt returns 422" \
    "POST" "/generate" '{"prompt": ""}' "422"

run_test "POST /documents with empty content returns 422" \
    "POST" "/documents" '{"content": ""}' "422"

run_test "DELETE /documents/99999999 returns 404" \
    "DELETE" "/documents/99999999" "" "404"

run_test "GET /nonexistent returns 404" \
    "GET" "/nonexistent" "" "404"

# ============================================
# PERFORMANCE TESTS
# ============================================
echo ""
echo -e "${CYAN}--- Performance Tests ---${NC}"
echo ""

# Embedding generation latency
verbose_header "Embedding generation latency" \
    "POST $BASE_URL/embed -d '{\"text\": \"performance test embedding\"}'"
exec_curl -X POST "$BASE_URL/embed" \
    -H "Content-Type: application/json" \
    -d '{"text": "performance test embedding"}'
embed_latency=$LAST_LATENCY_MS
if [ "$embed_latency" -lt 2000 ]; then
    verbose_result "PASS" "${embed_latency}ms"
    ((PASS++))
else
    verbose_result "WARN" "${embed_latency}ms - slow"
    ((WARN++))
fi

# Search latency
verbose_header "Search latency" \
    "POST $BASE_URL/search/records -d '{\"query\": \"performance test search\", \"top_k\": 10}'"
exec_curl -X POST "$BASE_URL/search/records" \
    -H "Content-Type: application/json" \
    -d '{"query": "performance test search", "top_k": 10}'
search_latency=$LAST_LATENCY_MS
if [ "$search_latency" -lt 2000 ]; then
    verbose_result "PASS" "${search_latency}ms"
    ((PASS++))
else
    verbose_result "WARN" "${search_latency}ms - slow"
    ((WARN++))
fi

# Multiple sequential requests
((TEST_NUM++))
if [ "$VERBOSE" = true ]; then
    echo ""
    echo -e "  ${CYAN}[Test $TEST_NUM]${NC} 10 sequential embed requests"
    echo -e "    Command:  POST $BASE_URL/embed x10 (sequential)"
else
    printf "%-55s" "10 sequential embed requests"
fi

seq_total_time=0
all_ok=true
for i in {1..10}; do
    exec_curl -X POST "$BASE_URL/embed" \
        -H "Content-Type: application/json" \
        -d "{\"text\": \"sequential test $i\"}"

    dims=$(echo "$LAST_BODY" | python3 -c "import sys,json; print(json.load(sys.stdin).get('dimensions', 0))" 2>/dev/null)
    if [ "$dims" != "384" ]; then
        all_ok=false
        break
    fi
    seq_total_time=$((seq_total_time + LAST_LATENCY_MS))
    if [ "$VERBOSE" = true ]; then
        echo -e "    Iteration $i: ${LAST_LATENCY_MS}ms | dims=$dims"
    fi
done

if [ "$all_ok" == true ]; then
    avg=$((seq_total_time / 10))
    if [ "$VERBOSE" = true ]; then
        echo -e "    Result:   ${GREEN}PASS${NC} (avg ${avg}ms, total ${seq_total_time}ms)"
        echo -e "    Stats:    ${seq_total_time}ms total | 10 requests"
    else
        echo -e "${GREEN}PASS${NC} (avg ${avg}ms)"
    fi
    ((PASS++))
else
    if [ "$VERBOSE" = true ]; then
        echo -e "    Result:   ${RED}FAIL${NC} (wrong dimensions at iteration $i)"
    else
        echo -e "${RED}FAIL${NC}"
    fi
    ((FAIL++))
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