#!/bin/bash
# OmniWalk - show where the live dashboard is on the internet, or open a
# tunnel by hand if the automatic one (smartcane-live.service) is off.
#
# Run ON THE PI:
#     bash ~/smartcane/tools/go_live.sh
#
# Needs: cloudflared installed (docs/deployment.md) and the cane service
# running with --demo-port 8080. Prints the links and, for a tunnel it opened
# itself, closes it on Ctrl-C. With --demo-public (the default service) the
# links need no token, otherwise they carry it.
set -u
PORT=${PORT:-8080}
TOKEN_FILE=$HOME/.config/smartcane/demo_token
PAGES=https://adeliusa486.github.io/OmniWalk/live.html

command -v cloudflared >/dev/null || { echo "cloudflared is not installed, see docs/deployment.md"; exit 1; }

if ! curl -sf "http://localhost:$PORT/health" >/dev/null; then
  echo "The dashboard is not running on port $PORT."
  echo "Is the cane running?  systemctl --user status smartcane"
  echo "Its ExecStart in ~/.config/systemd/user/smartcane.service must have '--demo-port $PORT'"
  echo "(the repository's code/smartcane.service does). After a change:"
  echo "    systemctl --user daemon-reload && systemctl --user restart smartcane"
  exit 1
fi
Q=""
if [ "$(curl -s -o /dev/null -w '%{http_code}' "http://localhost:$PORT/state.json")" = "403" ]; then
  Q="?token=$(cat "$TOKEN_FILE")"
fi

# The cane already puts itself online at boot (smartcane-live.service): give
# out that address instead of opening a second tunnel.
if systemctl --user is-active --quiet smartcane-live; then
  URL=$(grep -o 'https://[a-z0-9-]*\.trycloudflare\.com' "$HOME/.cache/smartcane/live_tunnel.log" 2>/dev/null | head -1)
  if [ -n "$URL" ]; then
    echo "The cane is already online (smartcane-live)."
    echo "Live dashboard, direct:   $URL/$Q"
    echo "Through the website:      $PAGES$Q"
    exit 0
  fi
fi

# Kept after the demo for diagnosis (one tunnel per file, overwritten next time).
LOG=$HOME/.cache/smartcane/cloudflared.log
mkdir -p "$(dirname "$LOG")"
cloudflared tunnel --no-autoupdate --url "http://localhost:$PORT" > "$LOG" 2>&1 &
PID=$!
trap 'kill $PID 2>/dev/null; echo; echo "Tunnel closed. The dashboard is no longer public."' EXIT INT TERM

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
for _ in $(seq 1 45); do
  if curl -sf -m 5 "$URL/health" >/dev/null 2>&1 \
     || curl -sf -m 5 --doh-url https://1.1.1.1/dns-query "$URL/health" >/dev/null 2>&1; then
    ONLINE=1
    break
  fi
  sleep 2
done
if [ -z "$ONLINE" ]; then
  echo "Not answering yet after 90 s. Try the links in a minute. cloudflared says:"
  grep -E "ERR|WRN" "$LOG" | tail -3
fi

echo
echo "Live dashboard, direct:   $URL/$Q"
echo "Through the website:      $PAGES?cane=$URL${Q:+&${Q#?}}"
echo
echo "Give judges either link. Keep this terminal open. Ctrl-C closes the tunnel."
wait $PID
