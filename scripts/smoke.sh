#!/usr/bin/env bash
# Starts an image and checks health and a real engine move through the API.
# Usage: scripts/smoke.sh [IMAGE]
set -euo pipefail

image="${1:-chess-trainer:local}"
name="chess-trainer-smoke-$$"
port="${SMOKE_PORT:-8099}"
base="http://127.0.0.1:${port}"

cleanup() {
  docker logs "$name" 2>&1 | tail -20 || true
  docker rm -f "$name" >/dev/null 2>&1 || true
}
trap cleanup EXIT

docker run -d --name "$name" -p "127.0.0.1:${port}:8000" "$image" >/dev/null

for _ in $(seq 1 30); do
  curl -fsS "$base/api/health" >/dev/null 2>&1 && break
  sleep 1
done

health="$(curl -fsS "$base/api/health")"
echo "health: $health"
python3 - "$health" <<'PY'
import json, sys
body = json.loads(sys.argv[1])
assert body["status"] == "ok", body
assert body["engine"]["name"].startswith("Stockfish"), body
assert body["engine"]["build_tag"], body
PY

docker exec "$name" sh -c 'id -u | grep -qx 1000' || { echo "not running as uid 1000"; exit 1; }
curl -fsS "$base/" | grep -q '<title>' || { echo "frontend not served"; exit 1; }

# Alapin line: after 1.e4 c5 2.c3 the line ends, so the next bot move comes from Stockfish.
alapin="$(curl -fsS "$base/api/repertoires" | python3 -c '
import json, sys
repertoires = json.load(sys.stdin)["repertoires"]
print(next(v["variant_id"] for r in repertoires for v in r["variants"] if v["pgn"] == "1. e4 c5 2. c3"))
')"
game="$(curl -fsS -X POST "$base/api/games" -H 'content-type: application/json' \
  -d "{\"color\":\"white\",\"variant_ids\":[\"$alapin\"],\"level\":\"club\",\"pace\":\"instant\",\"time_control\":\"none\"}")"
game_id="$(python3 -c 'import json,sys; print(json.loads(sys.argv[1])["state"]["game_id"])' "$game")"
curl -fsS -X POST "$base/api/games/$game_id/moves" -H 'content-type: application/json' -d '{"uci":"e2e4"}' >/dev/null
reply="$(curl -fsS -X POST "$base/api/games/$game_id/moves" -H 'content-type: application/json' -d '{"uci":"c2c3"}')"
echo "engine reply: $reply"
python3 - "$reply" <<'PY'
import json, sys
body = json.loads(sys.argv[1])
assert body["bot_move"]["source"] == "engine", body
PY

echo "smoke test passed on $(docker image inspect "$image" --format '{{.Architecture}}')"
