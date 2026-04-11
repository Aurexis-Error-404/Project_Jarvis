#!/usr/bin/env bash
# ─────────────────────────────────────────────────────────────
# JARVIS Pipeline Test Harness
# Integration Lead tool — run before logging results to integration-log.md
#
# Prerequisites:
#   npm install -g wscat
#   Backend running: cd backend && python main.py
#   Ollama running:  ollama serve
#
# Usage:
#   bash scripts/pipeline-test.sh [test_number]
#   bash scripts/pipeline-test.sh 1        # run PT #1 only
#   bash scripts/pipeline-test.sh all      # run PT #1 and PT #2
# ─────────────────────────────────────────────────────────────

WS_URL="ws://localhost:8765"
HTTP_URL="http://localhost:8000"
TIMEOUT=15  # seconds to wait for a response

RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
NC='\033[0m'

pass() { echo -e "${GREEN}[PASS]${NC} $1"; }
fail() { echo -e "${RED}[FAIL]${NC} $1"; }
info() { echo -e "${YELLOW}[INFO]${NC} $1"; }

# ─── Health check ─────────────────────────────────────────────
health_check() {
  info "Checking backend health at $HTTP_URL/health ..."
  STATUS=$(curl -s -o /dev/null -w "%{http_code}" "$HTTP_URL/health" 2>/dev/null)
  if [ "$STATUS" = "200" ]; then
    BODY=$(curl -s "$HTTP_URL/health")
    pass "Backend healthy: $BODY"
    return 0
  else
    fail "Backend not reachable (HTTP $STATUS). Start with: cd backend && python main.py"
    return 1
  fi
}

# ─── Ollama check ─────────────────────────────────────────────
ollama_check() {
  info "Checking Ollama at http://localhost:11434/api/tags ..."
  STATUS=$(curl -s -o /dev/null -w "%{http_code}" "http://localhost:11434/api/tags" 2>/dev/null)
  if [ "$STATUS" = "200" ]; then
    pass "Ollama running"
    return 0
  else
    fail "Ollama not running. Start with: ollama serve"
    return 1
  fi
}

# ─── PT #1: WebSocket echo ─────────────────────────────────────
pt1() {
  echo ""
  echo "══════════════════════════════════════════"
  echo "  PT #1 · WebSocket Echo — basic handshake"
  echo "══════════════════════════════════════════"

  if ! command -v wscat &>/dev/null; then
    fail "wscat not found. Install with: npm install -g wscat"
    return 1
  fi

  info "Sending user_query 'hello' in local mode..."
  RESPONSE=$(echo '{"event":"user_query","query":"hello","mode":"local"}' \
    | timeout $TIMEOUT wscat -c "$WS_URL" --wait 10 2>/dev/null)

  if echo "$RESPONSE" | grep -q '"event":"jarvis_response"'; then
    TEXT=$(echo "$RESPONSE" | python3 -c "import sys,json; d=json.loads(sys.stdin.read().strip().split('\n')[-2]); print(d.get('text','')[:80])" 2>/dev/null || echo "(could not parse text)")
    pass "Got jarvis_response: $TEXT"
  elif echo "$RESPONSE" | grep -q '"event":"jarvis_error"'; then
    fail "Got jarvis_error instead of response. Check Ollama is running."
    echo "  Response: $RESPONSE"
  else
    fail "No jarvis_response received within ${TIMEOUT}s"
    echo "  Raw response: $RESPONSE"
    echo ""
    echo "  Triage:"
    echo "    1. Is backend running?  curl $HTTP_URL/health"
    echo "    2. Is Ollama running?   curl http://localhost:11434/api/tags"
    echo "    3. Check event field — backend expects 'event', not 'type'"
  fi
}

# ─── PT #2: Tool-use — codebase awareness ─────────────────────
pt2() {
  echo ""
  echo "══════════════════════════════════════════"
  echo "  PT #2 · Tool-use loop — read_codebase"
  echo "══════════════════════════════════════════"

  info "Sending query: 'What files are in this project?'"
  RESPONSE=$(echo '{"event":"user_query","query":"What files are in this project?","mode":"cloud"}' \
    | timeout 30 wscat -c "$WS_URL" --wait 25 2>/dev/null)

  if echo "$RESPONSE" | grep -q '"tool":"read_codebase"'; then
    pass "read_codebase tool fired"
  else
    fail "read_codebase tool did NOT fire"
  fi

  if echo "$RESPONSE" | grep -q '"event":"jarvis_response"'; then
    pass "Got jarvis_response"
  else
    fail "No jarvis_response — tool loop may have crashed"
    echo "  Check backend logs: backend/logs/error.log"
  fi
}

# ─── PT #3b: Mode toggle ───────────────────────────────────────
pt3b() {
  echo ""
  echo "══════════════════════════════════════════"
  echo "  PT #3b · Mode Toggle — local ↔ cloud"
  echo "══════════════════════════════════════════"

  info "Sending mode_change to 'local'..."
  RESPONSE=$(echo '{"event":"mode_change","mode":"local"}' \
    | timeout 5 wscat -c "$WS_URL" --wait 3 2>/dev/null)

  if echo "$RESPONSE" | grep -q '"event":"jarvis_mode_ack"'; then
    if echo "$RESPONSE" | grep -q '"mode":"local"'; then
      pass "Mode ack received: local"
    else
      fail "Mode ack received but mode field wrong"
      echo "  $RESPONSE"
    fi
  else
    fail "No jarvis_mode_ack received"
    echo "  Check backend logs for mode_change handling"
  fi
}

# ─── Main ─────────────────────────────────────────────────────
TEST=${1:-"help"}

echo ""
echo "  JARVIS Pipeline Test Harness"
echo "  $(date -u +"%Y-%m-%dT%H:%M:%SZ")"
echo ""

case $TEST in
  1)
    health_check && ollama_check && pt1
    ;;
  2)
    health_check && pt2
    ;;
  3b)
    health_check && pt3b
    ;;
  all)
    health_check && ollama_check && pt1 && pt2 && pt3b
    ;;
  health)
    health_check && ollama_check
    ;;
  *)
    echo "Usage: bash scripts/pipeline-test.sh [1|2|3b|all|health]"
    echo ""
    echo "  health  — check backend + Ollama are running"
    echo "  1       — PT #1: WebSocket echo (basic handshake)"
    echo "  2       — PT #2: Tool-use loop (codebase awareness)"
    echo "  3b      — PT #3b: Mode toggle"
    echo "  all     — run health + PT #1 + PT #2 + PT #3b"
    echo ""
    echo "  Prerequisites:"
    echo "    npm install -g wscat"
    echo "    ollama serve"
    echo "    cd backend && python main.py"
    ;;
esac

echo ""
