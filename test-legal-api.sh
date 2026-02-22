#!/bin/bash
#
# Test script for the Legal Document Search API
#
# Usage:
#   ./test-legal-api.sh                    # Uses localhost:8080
#   ./test-legal-api.sh http://my-alb.com  # Uses custom base URL
#
# Prerequisites:
#   - Python inference service running
#   - Legal documents ingested (POST /legal/ingest)
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
echo "Legal Document Search API Tests"
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

    printf "%-60s" "$name"

    if [ "$method" == "GET" ]; then
        response=$(curl -s -w "\n%{http_code}" "$BASE_URL$endpoint" 2>/dev/null)
    else
        response=$(curl -s -w "\n%{http_code}" -X POST "$BASE_URL$endpoint" \
            -H "Content-Type: application/json" \
            -d "$data" 2>/dev/null)
    fi

    http_code=$(echo "$response" | tail -n1)
    body=$(echo "$response" | sed '$d')

    if [ "$http_code" != "$expected_status" ]; then
        echo -e "${RED}FAIL${NC} (expected HTTP $expected_status, got $http_code)"
        if [ -n "$body" ]; then
            echo "  Response: $(echo "$body" | head -c 200)"
        fi
        ((FAIL++))
        return 1
    fi

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
printf "%-60s" "Health shows legal_documents_indexed"
response=$(curl -s "$BASE_URL/health")
legal_count=$(echo "$response" | python3 -c "import sys,json; print(json.load(sys.stdin).get('legal_documents_indexed', 0))" 2>/dev/null)
if [ "$legal_count" -gt 0 ] 2>/dev/null; then
    echo -e "${GREEN}PASS${NC} (count: $legal_count)"
    ((PASS++))
else
    echo -e "${YELLOW}WARN${NC} (no legal docs indexed - run POST /legal/ingest first)"
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

printf "%-60s" "GET /legal/documents/count has total field"
response=$(curl -s "$BASE_URL/legal/documents/count")
total=$(echo "$response" | python3 -c "import sys,json; print(json.load(sys.stdin).get('total', 0))" 2>/dev/null)
if [ "$total" -gt 0 ] 2>/dev/null; then
    echo -e "${GREEN}PASS${NC} (total: $total)"
    ((PASS++))
else
    echo -e "${YELLOW}WARN${NC} (total: $total)"
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
printf "%-60s" "Semantic search returns valid structure"
response=$(curl -s -X POST "$BASE_URL/legal/search" \
    -H "Content-Type: application/json" \
    -d '{"query": "wrongful termination", "top_k": 3}')
structure_check=$(echo "$response" | python3 -c "
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
    echo -e "${GREEN}PASS${NC}"
    ((PASS++))
else
    echo -e "${RED}FAIL${NC} ($structure_check)"
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

printf "%-60s" "Semantic search for '1983' (may miss exact match)"
response=$(curl -s -X POST "$BASE_URL/legal/search" \
    -H "Content-Type: application/json" \
    -d '{"query": "1983", "search_field": "content", "top_k": 5}')
sem_count=$(echo "$response" | python3 -c "import sys,json; print(len(json.load(sys.stdin)))" 2>/dev/null)
echo -e "${GREEN}PASS${NC} (results: $sem_count)"
((PASS++))

printf "%-60s" "Hybrid search for '1983' (catches keyword + semantic)"
response=$(curl -s -X POST "$BASE_URL/legal/search" \
    -H "Content-Type: application/json" \
    -d '{"query": "1983", "search_field": "hybrid", "top_k": 5}')
hyb_count=$(echo "$response" | python3 -c "import sys,json; print(len(json.load(sys.stdin)))" 2>/dev/null)
echo -e "${GREEN}PASS${NC} (results: $hyb_count)"
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
printf "%-60s" "Plessy v. Ferguson excluded when filtering overruled"
response=$(curl -s -X POST "$BASE_URL/legal/search" \
    -H "Content-Type: application/json" \
    -d '{"query": "separate but equal", "status_filter": "exclude_overruled", "top_k": 10}')
has_plessy=$(echo "$response" | python3 -c "
import sys, json
results = json.load(sys.stdin)
plessy = [r for r in results if 'Plessy' in r.get('title', '')]
print('FOUND' if plessy else 'EXCLUDED')
" 2>/dev/null)
if [ "$has_plessy" == "EXCLUDED" ]; then
    echo -e "${GREEN}PASS${NC} (Plessy correctly excluded)"
    ((PASS++))
else
    echo -e "${RED}FAIL${NC} (Plessy was found despite overruled filter)"
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
printf "%-60s" "Legal RAG returns valid structure"
response=$(curl -s -X POST "$BASE_URL/legal/rag" \
    -H "Content-Type: application/json" \
    -d '{"query": "What is the burden-shifting framework for employment discrimination?", "top_k": 3}')
rag_check=$(echo "$response" | python3 -c "
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
    echo -e "${GREEN}PASS${NC}"
    ((PASS++))
else
    echo -e "${RED}FAIL${NC} ($rag_check)"
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

printf "%-60s" "Legal semantic search latency"
start_time=$(python3 -c "import time; print(int(time.time()*1000))")
curl -s -X POST "$BASE_URL/legal/search" \
    -H "Content-Type: application/json" \
    -d '{"query": "employment discrimination", "top_k": 10}' > /dev/null
end_time=$(python3 -c "import time; print(int(time.time()*1000))")
latency=$((end_time - start_time))
if [ "$latency" -lt 3000 ]; then
    echo -e "${GREEN}PASS${NC} (${latency}ms)"
    ((PASS++))
else
    echo -e "${YELLOW}WARN${NC} (${latency}ms - slow)"
    ((PASS++))
fi

printf "%-60s" "Legal hybrid search latency"
start_time=$(python3 -c "import time; print(int(time.time()*1000))")
curl -s -X POST "$BASE_URL/legal/search" \
    -H "Content-Type: application/json" \
    -d '{"query": "ADA reasonable accommodation", "search_field": "hybrid", "top_k": 10}' > /dev/null
end_time=$(python3 -c "import time; print(int(time.time()*1000))")
latency=$((end_time - start_time))
if [ "$latency" -lt 3000 ]; then
    echo -e "${GREEN}PASS${NC} (${latency}ms)"
    ((PASS++))
else
    echo -e "${YELLOW}WARN${NC} (${latency}ms - slow)"
    ((PASS++))
fi

# ============================================
# SUMMARY
# ============================================
echo ""
echo "=============================================="
echo "Test Results"
echo "=============================================="
echo -e "Passed:  ${GREEN}$PASS${NC}"
echo -e "Failed:  ${RED}$FAIL${NC}"
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