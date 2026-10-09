#!/usr/bin/env python3
"""Smart cane - the admin API behind admin.html (the owner's control page).

Served by demo_server.py under /admin/api/ on the cane, so it works through
the public tunnel (from the website's admin.html), on the home network
(http://<cane>:8080/admin) and on the setup hotspot (http://10.42.0.1:8080/admin).

The website is static (GitHub Pages), so the password is checked here, on the
cane, never in the page. The camera view stays public. Everything that changes
the cane needs a login:

    GET  /admin/api/status          password set? local network? logged in?
    POST /admin/api/setup           {"password"}  the first password, only
                                    from the home network or the hotspot
    POST /admin/api/login           {"password"} -> {"session"}
    POST /admin/api/logout
    POST /admin/api/password        {"old", "new"}
    GET  /admin/api/wifi            current network, networks in range, saved
    POST /admin/api/wifi/join       {"ssid", "password", "security", "hidden"}
    POST /admin/api/wifi/forget     {"name"}
    GET  /admin/api/bt              paired devices, which are the earbuds
    POST /admin/api/bt/scan         {"seconds"}
    POST /admin/api/bt/pair         {"mac"}  pair, trust, connect, use for speech
    POST /admin/api/bt/use          {"mac"}  speak through this paired device
    POST /admin/api/bt/connect      {"mac"}
    POST /admin/api/bt/forget       {"mac"}

A login is "Authorization: Bearer <session>", valid 12 h, kept in memory (a
restart logs everyone out). The password is stored as PBKDF2-SHA256 in
~/.config/smartcane/admin_password (0600). After 5 wrong passwords in 5 min,
logins pause for a minute.

Browser checks (a page on another site must not drive the cane through the
owner's browser): requests that carry an Origin must come from the website or
the cane itself, and the Host must be an IP address, a .local name or the
tunnel, which stops DNS rebinding. The first password can only be set from a
private address that is not the tunnel (cloudflared connects from 127.0.0.1).

    python3 admin_api.py --reset-password    forget the password (on the cane)
"""
import argparse
import hashlib
import hmac
import ipaddress
import json
import os
import re
import secrets
import sys
import threading
import time

import bt_admin
import wifi_net

PASSWORD_FILE = os.path.expanduser("~/.config/smartcane/admin_password")
SITE_ORIGIN = "https://adeliusa486.github.io"
SESSION_S = 12 * 3600
ITERATIONS = 200_000
MIN_PASSWORD = 8
FAILS_MAX, FAILS_WINDOW_S, LOCK_S = 5, 300, 60
HOST_OK = re.compile(r"^(\d{1,3}(\.\d{1,3}){3}|\[[0-9a-f:]+\]|localhost|[a-z0-9-]+\.local|"
                     r"[a-z0-9-]+\.trycloudflare\.com)(:\d+)?$", re.I)


class ApiError(Exception):
    def __init__(self, code, message):
        super().__init__(message)
        self.code = code


def hash_password(password, salt=None, iterations=ITERATIONS):
    salt = salt or secrets.token_bytes(16)
    digest = hashlib.pbkdf2_hmac("sha256", password.encode(), salt, iterations)
    return {"salt": salt.hex(), "iterations": iterations, "hash": digest.hex()}


def check_password(password, stored):
    digest = hashlib.pbkdf2_hmac("sha256", password.encode(),
                                 bytes.fromhex(stored["salt"]), stored["iterations"])
    return hmac.compare_digest(digest.hex(), stored["hash"])


# Home networks and the hotspot (10.42.0.x). Not ipaddress's is_private, which
# also counts documentation and other reserved ranges.
LOCAL_NETS = [ipaddress.ip_network(n) for n in
              ("10.0.0.0/8", "172.16.0.0/12", "192.168.0.0/16", "fc00::/7", "fe80::/10")]


def is_local(client_ip, headers):
    """A request from the home network or the hotspot, not from the tunnel
    (cloudflared connects from 127.0.0.1 and adds Cf-* headers)."""
    if any(k.lower().startswith("cf-") for k in headers):
        return False
    try:
        ip = ipaddress.ip_address(client_ip)
    except ValueError:
        return False
    if getattr(ip, "ipv4_mapped", None):
        ip = ip.ipv4_mapped
    return any(ip in n for n in LOCAL_NETS)


class AdminAPI:
    def __init__(self, password_file=PASSWORD_FILE, say=None, set_earbuds=None,
                 wifi=wifi_net, bt=bt_admin, site_origin=SITE_ORIGIN,
                 background=None):
        self.password_file = password_file
        self.say = say or (lambda text: None)
        self.set_earbuds = set_earbuds or (lambda mac: None)
        self.wifi = wifi
        self.bt = bt
        self.site_origin = site_origin
        # Runs work that must outlive the request (joining another network
        # cuts the tunnel the answer travels through).
        self.background = background or (lambda fn: threading.Thread(
            target=fn, daemon=True).start())
        self.sessions = {}
        self.fails = []
        self.locked_until = 0.0
        self.lock = threading.Lock()

    # ---- password and sessions ---------------------------------------------

    def _stored(self):
        try:
            with open(self.password_file) as fh:
                return json.load(fh)
        except (OSError, ValueError):
            return None

    def _store(self, password):
        os.makedirs(os.path.dirname(self.password_file), exist_ok=True)
        tmp = self.password_file + ".tmp"
        fd = os.open(tmp, os.O_WRONLY | os.O_CREAT | os.O_TRUNC, 0o600)
        with os.fdopen(fd, "w") as fh:
            json.dump(hash_password(password), fh)
        os.replace(tmp, self.password_file)

    def _new_session(self):
        token = secrets.token_urlsafe(32)
        with self.lock:
            now = time.monotonic()
            self.sessions = {t: e for t, e in self.sessions.items() if e > now}
            self.sessions[token] = now + SESSION_S
        return {"session": token, "expires_in": SESSION_S}

    def _session_of(self, headers):
        auth = headers.get("Authorization", "")
        if not auth.startswith("Bearer "):
            return None
        token = auth[7:].strip()
        with self.lock:
            exp = self.sessions.get(token)
            if exp is None or exp < time.monotonic():
                self.sessions.pop(token, None)
                return None
        return token

    @staticmethod
    def _password(body, key="password"):
        pw = body.get(key)
        if not isinstance(pw, str) or not (MIN_PASSWORD <= len(pw) <= 128):
            raise ApiError(400, f"The password needs at least {MIN_PASSWORD} characters.")
        return pw

    def _login(self, body):
        now = time.monotonic()
        with self.lock:
            if now < self.locked_until:
                raise ApiError(429, "Too many wrong passwords. Wait a minute.")
        stored = self._stored()
        if stored is None:
            raise ApiError(409, "No admin password yet. Create one first.")
        pw = body.get("password")
        if isinstance(pw, str) and check_password(pw, stored):
            with self.lock:
                self.fails = []
            return self._new_session()
        with self.lock:
            self.fails = [t for t in self.fails if now - t < FAILS_WINDOW_S] + [now]
            if len(self.fails) >= FAILS_MAX:
                self.locked_until = now + LOCK_S
                self.fails = []
        print("  ADMIN wrong password", file=sys.stderr)
        raise ApiError(401, "Wrong password.")

    # ---- request checks --------------------------------------------------

    def origin_ok(self, headers):
        """Allowed browser origin for this request (or "" if it sent none)."""
        origin = headers.get("Origin", "")
        if not origin:
            return ""
        host = headers.get("Host", "")
        if origin == self.site_origin or re.sub(r"^https?://", "", origin) == host:
            return origin
        return None

    def cors_headers(self, headers):
        origin = self.origin_ok(headers)
        if not origin:
            return {}
        return {"Access-Control-Allow-Origin": origin, "Vary": "Origin",
                "Access-Control-Allow-Headers": "Authorization, Content-Type",
                "Access-Control-Allow-Methods": "GET, POST, OPTIONS",
                "Access-Control-Max-Age": "600"}

    # ---- dispatch ---------------------------------------------------------

    def handle(self, method, path, headers, body, client_ip):
        """One API request: (http code, JSON-able dict). Never raises."""
        try:
            if not HOST_OK.match(headers.get("Host", "")):
                raise ApiError(403, "Unknown host name.")
            if self.origin_ok(headers) is None:
                raise ApiError(403, "This page may not control the cane.")
            data = {}
            if method == "POST" and body:
                try:
                    data = json.loads(body)
                except ValueError:
                    raise ApiError(400, "Bad request.")
                if not isinstance(data, dict):
                    raise ApiError(400, "Bad request.")
            return 200, self._route(method, path, headers, data, client_ip)
        except ApiError as e:
            return e.code, {"error": str(e)}
        except Exception as e:                       # never a dead request
            print(f"  ADMIN {path} failed: {e!r}", file=sys.stderr)
            return 500, {"error": "The cane could not do that. Try again."}

    def _route(self, method, path, headers, data, client_ip):
        local = is_local(client_ip, headers)
        if path == "/admin/api/status" and method == "GET":
            return {"password_set": self._stored() is not None, "local": local,
                    "logged_in": self._session_of(headers) is not None,
                    "name": os.uname().nodename if hasattr(os, "uname") else "cane"}
        if method != "POST" and path in POSTS:
            raise ApiError(405, "Use POST.")
        if path == "/admin/api/setup":
            if self._stored() is not None:
                raise ApiError(409, "The password is already set. Log in instead.")
            if not local:
                raise ApiError(403, "For safety the first password can only be set from the "
                                    "cane's own network: home Wi-Fi or its setup hotspot.")
            self._store(self._password(data))
            print("  ADMIN password created")
            return self._new_session()
        if path == "/admin/api/login":
            return self._login(data)

        token = self._session_of(headers)
        if token is None:
            raise ApiError(401, "Please log in.")
        if path == "/admin/api/logout":
            with self.lock:
                self.sessions.pop(token, None)
            return {"ok": True}
        if path == "/admin/api/password":
            stored = self._stored()
            if not (isinstance(data.get("old"), str) and check_password(data["old"], stored)):
                raise ApiError(401, "The current password is wrong.")
            self._store(self._password(data, "new"))
            with self.lock:                        # everyone else logs in again
                self.sessions = {token: self.sessions[token]}
            print("  ADMIN password changed")
            return {"ok": True, "message": "Password changed."}
        if path == "/admin/api/wifi" and method == "GET":
            return self._wifi_status()
        if path == "/admin/api/wifi/join":
            return self._wifi_join(data)
        if path == "/admin/api/wifi/forget":
            ok, msg = self.wifi.forget(str(data.get("name", "")))
            return {"ok": ok, "message": msg}
        if path == "/admin/api/bt" and method == "GET":
            return {"devices": self.bt.paired(), "earbuds": self.bt.earbuds()}
        if path == "/admin/api/bt/scan":
            return {"found": self.bt.scan(int(data.get("seconds", 8) or 8))}
        mac = str(data.get("mac", "")).upper()
        if path.startswith("/admin/api/bt/") and not self.bt.valid_mac(mac):
            raise ApiError(400, "Not a Bluetooth address.")
        if path == "/admin/api/bt/pair":
            ok, msg = self.bt.pair(mac)
            if ok:
                self._use(mac)
                msg += " The cane now speaks through it."
            return {"ok": ok, "message": msg}
        if path == "/admin/api/bt/use":
            self._use(mac)
            ok, msg = self.bt.connect(mac)
            return {"ok": True, "message": "The cane now speaks through it. " +
                    ("" if ok else "It is not connected yet: switch it on near the cane.")}
        if path == "/admin/api/bt/connect":
            ok, msg = self.bt.connect(mac)
            return {"ok": ok, "message": msg}
        if path == "/admin/api/bt/forget":
            ok, msg = self.bt.forget(mac)
            return {"ok": ok, "message": msg}
        raise ApiError(404, "No such admin action.")

    # ---- Wi-Fi and Bluetooth ------------------------------------------------

    def _wifi_status(self):
        dev = self.wifi.device_status()
        nets = self.wifi.networks()
        saved = self.wifi.wifi_profiles()
        saved_ssids = {s for _, s in saved}
        for n in nets:
            n["saved"] = n["ssid"] in saved_ssids
        return {"connection": dev["connection"], "ip": dev["ip"],
                # The network's own name: profiles can be called anything
                # ("preconfigured" is the home Wi-Fi on this cane).
                "ssid": next((s for n, s in saved if n == dev["connection"]), dev["connection"]),
                "hotspot": dev["connection"] == self.wifi.HOTSPOT,
                "networks": nets,
                "saved": [{"name": n, "ssid": s, "active": n == dev["connection"]}
                          for n, s in saved]}

    def _wifi_join(self, data):
        ssid = data.get("ssid")
        password = data.get("password") or ""
        if not isinstance(ssid, str) or not (0 < len(ssid) <= 32) or not isinstance(password, str):
            raise ApiError(400, "Enter the network name.")
        security = self.wifi.security_from_scan(data.get("security", ""), password)
        if security == "enterprise":
            return {"ok": False, "code": "enterprise",
                    "message": f"{ssid} needs a user name. The cane cannot join it."}
        if security in ("wpa", "sae") and len(password) < 8:
            raise ApiError(400, "A Wi-Fi password has at least 8 characters.")
        net = {"ssid": ssid, "password": password, "security": security,
               "hidden": bool(data.get("hidden"))}
        name = self.wifi.save(net)
        if name is None:
            return {"ok": False, "code": "save_failed", "message": f"Could not save {ssid}."}
        p = self.wifi.plan(net)
        if p == "already":
            return {"ok": True, "code": "already",
                    "message": f"Already connected to {ssid}. Its password is saved."}
        if p == "away":
            return {"ok": True, "code": "away",
                    "message": f"Saved {ssid}. It is not in range now. The cane joins it when it is."}

        # Joining cuts the network this answer travels on, so answer first.
        def go():
            time.sleep(1.5)
            code, sentence = self.wifi.activate(name, ssid)
            self.say(sentence)
        self.background(go)
        return {"ok": True, "code": "joining",
                "message": f"Joining {ssid}. The cane leaves its current network now, so this page "
                           "loses it for about a minute. If the new network does not work, it goes "
                           "back to a network it knows. It says the result in the earbuds."}

    def _use(self, mac):
        self.bt.save_earbuds(mac)
        self.set_earbuds(mac)
        print(f"  ADMIN earbuds set to {mac}")


POSTS = {"/admin/api/setup", "/admin/api/login", "/admin/api/logout", "/admin/api/password",
         "/admin/api/wifi/join", "/admin/api/wifi/forget", "/admin/api/bt/scan",
         "/admin/api/bt/pair", "/admin/api/bt/use", "/admin/api/bt/connect",
         "/admin/api/bt/forget"}


def main():
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--reset-password", action="store_true",
                    help="delete the admin password: the next one is set from "
                         "the home network")
    args = ap.parse_args()
    if args.reset_password:
        try:
            os.remove(PASSWORD_FILE)
            print("admin password removed. Set a new one from the home network: "
                  "http://<cane>:8080/admin")
        except FileNotFoundError:
            print("no admin password was set")
        return 0
    ap.print_help()
    return 0


if __name__ == "__main__":
    sys.exit(main())
