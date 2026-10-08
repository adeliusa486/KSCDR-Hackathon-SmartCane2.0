#!/bin/bash
# Smart cane - put the live dashboard on the internet for a demo.
#
# Run ON THE PI, in a terminal you keep open for the demo:
#     bash ~/smartcane/tools/go_live.sh
#
# Needs: cloudflared installed (docs/deployment.md) and the cane service
# running with --demo-port 8080. Opens a Cloudflare quick tunnel (no account),
# prints the two links to give judges, and closes the tunnel on Ctrl-C.
# The dashboard shows the camera: it always requires the token.
set -u
PORT=${PORT:-8080}
TOKEN_FILE=$HOME/.config/smartcane/demo_token
PAGES=https://adeliusa486.github.io/KSCDR-Hackathon-SmartCane2.0/live.html

command -v cloudflared >/dev/null || { echo "cloudflared is not installed, see docs/deployment.md"; exit 1; }

if [ ! -s "$TOKEN_FILE" ]; then
  umask 077
  mkdir -p "$(dirname "$TOKEN_FILE")"
  python3 -c "import secrets; print(secrets.token_urlsafe(12))" > "$TOKEN_FILE"
  echo "Created a new token. Restart the cane so the dashboard uses it:"
  echo "    systemctl --user restart smartcane"
  exit 1
fi
TOKEN=$(cat "$TOKEN_FILE")

if ! curl -sf "http://localhost:$PORT/health" >/dev/null; then
  echo "The dashboard is not running on port $PORT."
  echo "Is the cane running?  systemctl --user status smartcane"
  echo "Its ExecStart in ~/.config/systemd/user/smartcane.service must end with '--demo-port $PORT'"
  echo "(the repository's code/smartcane.service does). After a change:"
  echo "    systemctl --user daemon-reload && systemctl --user restart smartcane"
  exit 1
fi
if [ "$(curl -s -o /dev/null -w '%{http_code}' "http://localhost:$PORT/state.json")" != "403" ]; then
  echo "WARNING: the dashboard answers without a token. Restart the cane after creating $TOKEN_FILE."
  exit 1
fi

LOG=$(mktemp)
cloudflared tunnel --no-autoupdate --url "http://localhost:$PORT" > "$LOG" 2>&1 &
PID=$!
trap 'kill $PID 2>/dev/null; rm -f "$LOG"; echo; echo "Tunnel closed. The dashboard is no longer public."' EXIT INT TERM

URL=""
for _ in $(seq 1 40); do
  URL=$(grep -o 'https://[a-z0-9-]*\.trycloudflare\.com' "$LOG" | head -1)
  [ -n "$URL" ] && break
  sleep 1
done
if [ -z "$URL" ]; then
  echo "No tunnel address after 40 s. Last lines from cloudflared:"
  tail -5 "$LOG"
  exit 1
fi

# A new address takes 15 to 30 s to reach DNS. Hand out links only once the
# tunnel answers from outside (Cloudflare's resolver as a fallback check).
echo "Tunnel $URL opened, waiting for it to come online..."
ONLINE=""
for _ in $(seq 1 30); do
  if curl -sf -m 5 "$URL/health" >/dev/null 2>&1 \
     || curl -sf -m 5 --doh-url https://1.1.1.1/dns-query "$URL/health" >/dev/null 2>&1; then
    ONLINE=1
    break
  fi
  sleep 2
done
[ -z "$ONLINE" ] && echo "Not answering yet after 60 s. Try the links in a minute."

echo
echo "Live dashboard, direct:   $URL/?token=$TOKEN"
echo "Through the website:      $PAGES?cane=$URL&token=$TOKEN"
echo
echo "Give judges either link. Keep this terminal open. Ctrl-C closes the tunnel."
wait $PID
