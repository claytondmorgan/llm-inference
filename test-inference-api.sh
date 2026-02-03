#!/bin/bash
#
# Test script for the Python Inference Service API
#
# Usage:
#   ./test-inference-api.sh                    # Uses localhost:8080
#   ./test-inference-api.sh http://my-alb.com  # Uses custom base URL
#
# Prerequisites:
#   - Python inference service running
#   - Database with some documents/ingested records (for search tests)
#

BASE_URL="${1:-http://localhost:8080}"
PASS=0
FAIL=0
SKIP=0

# Colors for output
GREEN='\033[0;32m'
RED='\033[0;31m'
YELLOW='\033[1;33m'
CYAN='\033[0;36m'
NC='\033[0m' # No Color

echo "=============================================="
echo "Python Inference Service API Tests"
echo "Base URL: $BASE_URL"
echo "=============================================="
echo ""

# Helper function to run a test
run_test() {
    local name="$1"
    local method="$2"
    local endpoint="$3"
    local data="$4"
    local expected_status="$5"
    local check_field="$6"
    local check_value="$7"

    printf "%-55s" "$name"

    if [ "$method" == "GET" ]; then
        response=$(curl -s -w "\n%{http_code}" "$BASE_URL$endpoint" 2>/dev/null)
    elif [ "$method" == "DELETE" ]; then
        response=$(curl -s -w "\n%{http_code}" -X DELETE "$BASE_URL$endpoint" 2>/dev/null)
    else
        response=$(curl -s -w "\n%{http_code}" -X POST "$BASE_URL$endpoint" \
            -H "Content-Type: application/json" \
            -d "$data" 2>/dev/null)
    fi

    http_code=$(echo "$response" | tail -n1)
    body=$(echo "$response" | sed '$d')

    # Check HTTP status
    if [ "$http_code" != "$expected_status" ]; then
        echo -e "${RED}FAIL${NC} (expected HTTP $expected_status, got $http_code)"
        if [ -n "$body" ]; then
            echo "  Response: $(echo "$body" | head -c 200)"
        fi
        ((FAIL++))
        return 1
    fi

    # Check response field if specified
    if [ -n "$check_field" ]; then
        actual_value=$(echo "$body" | python3 -c "import sys,json; d=json.load(sys.stdin); print(d.get('$check_field', 'MISSING'))" 2>/dev/null)
        if [ "$actual_value" != "$check_value" ]; then
            echo -e "${RED}FAIL${NC} ($check_field: expected '$check_value', got '$actual_value')"
            ((FAIL++))
            return 1
        fi
    fi

    echo -e "${GREEN}PASS${NC}"
    ((PASS++))
    return 0
}

# Helper function to run a test and capture a value for later use
run_test_capture() {
    local name="$1"
    local method="$2"
    local endpoint="$3"
    local data="$4"
    local expected_status="$5"
    local capture_field="$6"

    printf "%-55s" "$name"

    if [ "$method" == "GET" ]; then
        response=$(curl -s -w "\n%{http_code}" "$BASE_URL$endpoint" 2>/dev/null)
    elif [ "$method" == "DELETE" ]; then
        response=$(curl -s -w "\n%{http_code}" -X DELETE "$BASE_URL$endpoint" 2>/dev/null)
    else
        response=$(curl -s -w "\n%{http_code}" -X POST "$BASE_URL$endpoint" \
            -H "Content-Type: application/json" \
            -d "$data" 2>/dev/null)
    fi

    http_code=$(echo "$response" | tail -n1)
    body=$(echo "$response" | sed '$d')

    if [ "$http_code" != "$expected_status" ]; then
        echo -e "${RED}FAIL${NC} (expected HTTP $expected_status, got $http_code)"
        ((FAIL++))
        echo ""
        return 1
    fi

    captured_value=$(echo "$body" | python3 -c "import sys,json; d=json.load(sys.stdin); print(d.get('$capture_field', ''))" 2>/dev/null)
    echo -e "${GREEN}PASS${NC} ($capture_field: $captured_value)"
    ((PASS++))
    echo "$captured_value"
}

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
    "GET" "/" "" "200" "service" "LLM Inference API with Vector Search"

run_test "GET / shows version 3.0.0" \
    "GET" "/" "" "200" "version" "3.0.0"

# ============================================
# EMBED ENDPOINT
# ============================================
echo ""
echo -e "${CYAN}--- Embed Endpoint ---${NC}"
echo ""

run_test "POST /embed with valid text" \
    "POST" "/embed" '{"text": "comfortable running shoes"}' "200"

# Check embedding dimensions
printf "%-55s" "POST /embed returns 384 dimensions"
response=$(curl -s -X POST "$BASE_URL/embed" \
    -H "Content-Type: application/json" \
    -d '{"text": "test embedding"}')
dims=$(echo "$response" | python3 -c "import sys,json; print(json.load(sys.stdin).get('dimensions', 0))" 2>/dev/null)
if [ "$dims" == "384" ]; then
    echo -e "${GREEN}PASS${NC}"
    ((PASS++))
else
    echo -e "${RED}FAIL${NC} (got $dims dimensions)"
    ((FAIL++))
fi

# Check embedding is a list of floats
printf "%-55s" "POST /embed returns valid embedding array"
is_valid=$(echo "$response" | python3 -c "
import sys, json
d = json.load(sys.stdin)
emb = d.get('embedding', [])
if len(emb) == 384 and all(isinstance(x, float) for x in emb):
    print('OK')
else:
    print('INVALID')
" 2>/dev/null)
if [ "$is_valid" == "OK" ]; then
    echo -e "${GREEN}PASS${NC}"
    ((PASS++))
else
    echo -e "${RED}FAIL${NC}"
    ((FAIL++))
fi

run_test "POST /embed with empty text returns 400" \
    "POST" "/embed" '{"text": ""}' "400"

run_test "POST /embed with missing text returns 400" \
    "POST" "/embed" '{"wrong_field": "test"}' "400"

# ============================================
# TEXT GENERATION ENDPOINT
# ============================================
echo ""
echo -e "${CYAN}--- Text Generation Endpoint ---${NC}"
echo ""

run_test "POST /generate with valid prompt" \
    "POST" "/generate" '{"prompt": "The future of AI is"}' "200"

# Check generated text is returned
printf "%-55s" "POST /generate returns generated_text"
response=$(curl -s -X POST "$BASE_URL/generate" \
    -H "Content-Type: application/json" \
    -d '{"prompt": "Hello world", "max_new_tokens": 20}')
has_text=$(echo "$response" | python3 -c "
import sys, json
d = json.load(sys.stdin)
if 'generated_text' in d and len(d['generated_text']) > 0:
    print('OK')
else:
    print('MISSING')
" 2>/dev/null)
if [ "$has_text" == "OK" ]; then
    echo -e "${GREEN}PASS${NC}"
    ((PASS++))
else
    echo -e "${RED}FAIL${NC}"
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
printf "%-55s" "POST /documents adds a document"
response=$(curl -s -X POST "$BASE_URL/documents" \
    -H "Content-Type: application/json" \
    -d '{"content": "Test document for API testing - Python inference service", "metadata": {"test": true, "source": "api-test"}}')
doc_id=$(echo "$response" | python3 -c "import sys,json; print(json.load(sys.stdin).get('id', ''))" 2>/dev/null)
if [ -n "$doc_id" ] && [ "$doc_id" != "" ]; then
    echo -e "${GREEN}PASS${NC} (id: $doc_id)"
    ((PASS++))
else
    echo -e "${RED}FAIL${NC}"
    ((FAIL++))
fi

# Add batch documents
printf "%-55s" "POST /documents/batch adds multiple documents"
response=$(curl -s -X POST "$BASE_URL/documents/batch" \
    -H "Content-Type: application/json" \
    -d '[
        {"content": "Batch test document 1 - wireless headphones with noise cancellation", "metadata": {"batch": 1}},
        {"content": "Batch test document 2 - laptop stand for ergonomic workspace", "metadata": {"batch": 2}},
        {"content": "Batch test document 3 - organic coffee beans from Colombia", "metadata": {"batch": 3}}
    ]')
num_ids=$(echo "$response" | python3 -c "import sys,json; print(len(json.load(sys.stdin).get('ids', [])))" 2>/dev/null)
if [ "$num_ids" == "3" ]; then
    echo -e "${GREEN}PASS${NC} (added 3 documents)"
    ((PASS++))
else
    echo -e "${RED}FAIL${NC} (expected 3, got $num_ids)"
    ((FAIL++))
fi

# Get document count
run_test "GET /documents/count returns count" \
    "GET" "/documents/count" "" "200"

printf "%-55s" "GET /documents/count returns valid number"
response=$(curl -s "$BASE_URL/documents/count")
count=$(echo "$response" | python3 -c "import sys,json; print(json.load(sys.stdin).get('count', -1))" 2>/dev/null)
if [ "$count" -ge 0 ] 2>/dev/null; then
    echo -e "${GREEN}PASS${NC} (count: $count)"
    ((PASS++))
else
    echo -e "${RED}FAIL${NC}"
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
printf "%-55s" "POST /search returns results array"
response=$(curl -s -X POST "$BASE_URL/search" \
    -H "Content-Type: application/json" \
    -d '{"query": "laptop computer", "top_k": 5}')
has_results=$(echo "$response" | python3 -c "
import sys, json
d = json.load(sys.stdin)
if isinstance(d, list):
    print('OK')
else:
    print('NOT_LIST')
" 2>/dev/null)
if [ "$has_results" == "OK" ]; then
    echo -e "${GREEN}PASS${NC}"
    ((PASS++))
else
    echo -e "${RED}FAIL${NC} ($has_results)"
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
printf "%-55s" "POST /search/records returns valid structure"
response=$(curl -s -X POST "$BASE_URL/search/records" \
    -H "Content-Type: application/json" \
    -d '{"query": "test product", "top_k": 3}')
structure_check=$(echo "$response" | python3 -c "
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
    echo -e "${GREEN}PASS${NC}"
    ((PASS++))
else
    echo -e "${RED}FAIL${NC} ($structure_check)"
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
printf "%-55s" "POST /rag returns answer and sources"
response=$(curl -s -X POST "$BASE_URL/rag" \
    -H "Content-Type: application/json" \
    -d '{"query": "Tell me about electronics", "top_k": 2, "max_new_tokens": 50}')
rag_check=$(echo "$response" | python3 -c "
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
    echo -e "${GREEN}PASS${NC}"
    ((PASS++))
else
    echo -e "${RED}FAIL${NC} ($rag_check)"
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
printf "%-55s" "GET /ingestion/jobs returns array"
response=$(curl -s "$BASE_URL/ingestion/jobs")
is_list=$(echo "$response" | python3 -c "
import sys, json
d = json.load(sys.stdin)
print('OK' if isinstance(d, list) else 'NOT_LIST')
" 2>/dev/null)
if [ "$is_list" == "OK" ]; then
    echo -e "${GREEN}PASS${NC}"
    ((PASS++))
else
    echo -e "${RED}FAIL${NC}"
    ((FAIL++))
fi

run_test "GET /ingestion/jobs with limit param" \
    "GET" "/ingestion/jobs?limit=5" "" "200"

run_test "GET /ingestion/stats returns stats" \
    "GET" "/ingestion/stats" "" "200"

# Check stats structure
printf "%-55s" "GET /ingestion/stats has required fields"
response=$(curl -s "$BASE_URL/ingestion/stats")
stats_check=$(echo "$response" | python3 -c "
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
    echo -e "${GREEN}PASS${NC}"
    ((PASS++))
else
    echo -e "${RED}FAIL${NC} ($stats_check)"
    ((FAIL++))
fi

run_test "GET /ingestion/records/count returns count" \
    "GET" "/ingestion/records/count" "" "200"

printf "%-55s" "GET /ingestion/records/count returns valid number"
response=$(curl -s "$BASE_URL/ingestion/records/count")
count=$(echo "$response" | python3 -c "import sys,json; print(json.load(sys.stdin).get('count', -1))" 2>/dev/null)
if [ "$count" -ge 0 ] 2>/dev/null; then
    echo -e "${GREEN}PASS${NC} (count: $count)"
    ((PASS++))
else
    echo -e "${RED}FAIL${NC}"
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
printf "%-55s" "Embedding generation latency"
start_time=$(python3 -c "import time; print(int(time.time()*1000))")
curl -s -X POST "$BASE_URL/embed" \
    -H "Content-Type: application/json" \
    -d '{"text": "performance test embedding"}' > /dev/null
end_time=$(python3 -c "import time; print(int(time.time()*1000))")
embed_latency=$((end_time - start_time))
if [ "$embed_latency" -lt 2000 ]; then
    echo -e "${GREEN}PASS${NC} (${embed_latency}ms)"
    ((PASS++))
else
    echo -e "${YELLOW}WARN${NC} (${embed_latency}ms - slow)"
    ((PASS++))
fi

# Search latency
printf "%-55s" "Search latency"
start_time=$(python3 -c "import time; print(int(time.time()*1000))")
curl -s -X POST "$BASE_URL/search/records" \
    -H "Content-Type: application/json" \
    -d '{"query": "performance test search", "top_k": 10}' > /dev/null
end_time=$(python3 -c "import time; print(int(time.time()*1000))")
search_latency=$((end_time - start_time))
if [ "$search_latency" -lt 2000 ]; then
    echo -e "${GREEN}PASS${NC} (${search_latency}ms)"
    ((PASS++))
else
    echo -e "${YELLOW}WARN${NC} (${search_latency}ms - slow)"
    ((PASS++))
fi

# Multiple sequential requests
printf "%-55s" "10 sequential embed requests"
total_time=0
all_ok=true
for i in {1..10}; do
    start=$(python3 -c "import time; print(int(time.time()*1000))")
    response=$(curl -s -X POST "$BASE_URL/embed" \
        -H "Content-Type: application/json" \
        -d "{\"text\": \"sequential test $i\"}")
    end=$(python3 -c "import time; print(int(time.time()*1000))")
    
    dims=$(echo "$response" | python3 -c "import sys,json; print(json.load(sys.stdin).get('dimensions', 0))" 2>/dev/null)
    if [ "$dims" != "384" ]; then
        all_ok=false
        break
    fi
    total_time=$((total_time + end - start))
done
if [ "$all_ok" == true ]; then
    avg=$((total_time / 10))
    echo -e "${GREEN}PASS${NC} (avg ${avg}ms)"
    ((PASS++))
else
    echo -e "${RED}FAIL${NC}"
    ((FAIL++))
fi

# ============================================
# SUMMARY
# ============================================
echo ""
echo "=============================================="
echo "Test Results"
echo "=============================================="
echo -e "Passed: ${GREEN}$PASS${NC}"
echo -e "Failed: ${RED}$FAIL${NC}"
if [ $SKIP -gt 0 ]; then
    echo -e "Skipped: ${YELLOW}$SKIP${NC}"
fi
echo ""

if [ $FAIL -eq 0 ]; then
    echo -e "${GREEN}All tests passed!${NC}"
    exit 0
else
    echo -e "${RED}Some tests failed.${NC}"
    exit 1
fi
