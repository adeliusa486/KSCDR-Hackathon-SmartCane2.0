#!/bin/bash
# OmniWalk - put the live dashboard online every time the cane starts, so the
# website's live page finds it by itself.
#
# Run by smartcane-live.service (a user service, like smartcane.service).
# Opens a Cloudflare quick tunnel to the dashboard, waits until it answers
# from outside, then posts "<address> <unix time> <signature>" to the relay
# topic the website reads (ntfy.sh/omniwalk-<first 16 hex of the public key's
# sha256>). The signature is Ed25519 with the cane's own key, so the website
# only ever connects to an address this cane posted. The private key never
# leaves the cane: ~/.config/smartcane/live_key.pem, created here on first
# run. Its public key is printed below and must match PUBKEY in
# code/demo_dashboard.html.
#
# The address is posted again every 30 min (the relay keeps messages 12 h).
# If cloudflared stops, this script exits and systemd starts it again, which
# gives a new address and a new post.
#
#   systemctl --user status smartcane-live          is it online?
#   tail ~/.cache/smartcane/live_tunnel.log         cloudflared's own log
#   systemctl --user disable --now smartcane-live   keep the cane off the internet
set -u
PORT=${PORT:-8080}
KEY=$HOME/.config/smartcane/live_key.pem
RELAY=${RELAY:-https://ntfy.sh}
LOG=$HOME/.cache/smartcane/live_tunnel.log

if [ ! -s "$KEY" ]; then
  mkdir -p "$(dirname "$KEY")"
  (umask 077; openssl genpkey -algorithm ed25519 -out "$KEY") || exit 1
fi
PUB=$(openssl pkey -in "$KEY" -pubout -outform DER | tail -c 32 | base64)
TOPIC=omniwalk-$(printf '%s' "$PUB" | base64 -d | sha256sum | cut -c1-16)
echo "public key $PUB, relay topic $TOPIC"

for _ in $(seq 1 60); do
  curl -sf -m 2 "http://localhost:$PORT/health" >/dev/null && break
  sleep 2
done

mkdir -p "$(dirname "$LOG")"
cloudflared tunnel --no-autoupdate --url "http://localhost:$PORT" > "$LOG" 2>&1 &
PID=$!
trap 'kill $PID 2>/dev/null' EXIT INT TERM

URL=""
for _ in $(seq 1 60); do
  URL=$(grep -o 'https://[a-z0-9-]*\.trycloudflare\.com' "$LOG" | head -1)
  [ -n "$URL" ] && break
  kill -0 $PID 2>/dev/null || break
  sleep 1
done
if [ -z "$URL" ]; then
  echo "no tunnel address (no internet?). cloudflared says:"
  tail -3 "$LOG"
  exit 1
fi

# A new address takes 15 to 30 s to reach DNS. Post it once it answers.
# cloudflared prints the address before Cloudflare accepts the tunnel, and
# sometimes gives up after it ("context deadline exceeded", 8 Oct 2026): then
# start over at once rather than wait on a dead address.
ONLINE=""
for _ in $(seq 1 60); do
  if ! kill -0 $PID 2>/dev/null; then
    echo "cloudflared stopped before going online:"
    grep ERR "$LOG" | tail -2
    exit 1
  fi
  if curl -sf -m 5 "$URL/health" >/dev/null 2>&1 \
     || curl -sf -m 5 --doh-url https://1.1.1.1/dns-query "$URL/health" >/dev/null 2>&1; then
    ONLINE=1
    break
  fi
  sleep 2
done
# The website checks the address answers before using it, so posting one
# that is still slow to resolve does no harm.
if [ -n "$ONLINE" ]; then echo "online at $URL"; else echo "not answering yet at $URL"; fi

# The time to sign with. The Pi has no clock battery: until NTP answers, its
# clock is the moment it was last switched off (17 h behind on 9 Oct 2026),
# and the website ignores a post signed more than 13 h ago. NTP took 87 and
# 130 s after power-on that day, the tunnel only 31 and 45 s, and waiting for
# NTP left the website on the examples for two minutes. So until NTP has
# synced, take the time from the relay's own HTTPS answer (its Date header,
# equal to the synced clock to the second), and post at once.
clock_ok() {
  [ "$(timedatectl show -p NTPSynchronized --value 2>/dev/null)" = yes ] \
    || [ -e /run/systemd/timesync/synchronized ]
}
relay_time() {
  local d
  d=$(curl -sI -m 5 "$RELAY" | tr -d '\r' | sed -n 's/^[Dd]ate: //p' | head -1)
  [ -n "$d" ] && date -d "$d" +%s
}

MSG=$(mktemp)
trap 'kill $PID 2>/dev/null; rm -f "$MSG"' EXIT INT TERM
post() {
  local sig ts clock=ntp
  if clock_ok; then
    ts=$(date +%s)
  else
    clock=relay
    ts=$(relay_time) || { echo "no trusted time yet, not posting"; return 1; }
  fi
  # From a file: openssl pkeyutl -rawin signs nothing when read from a pipe
  # (an empty signature on 8 Oct 2026).
  printf '%s' "$URL $ts" > "$MSG"
  sig=$(openssl pkeyutl -sign -rawin -inkey "$KEY" -in "$MSG" | base64 -w0)
  if [ ${#sig} -ne 88 ]; then
    echo "signing failed, not posting"
    return 1
  fi
  curl -sf -m 10 -d "$(cat "$MSG") $sig" "$RELAY/$TOPIC" >/dev/null || return 1
  echo "posted, signed $(date -d "@$ts" '+%F %T') ($clock time)"
}

while kill -0 $PID 2>/dev/null; do
  if post; then
    n=180
  else
    echo "relay not reachable, trying again in 30 s"
    n=3
  fi
  for _ in $(seq 1 $n); do
    kill -0 $PID 2>/dev/null || break
    sleep 10
  done
done
echo "tunnel closed"
exit 1
