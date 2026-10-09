#!/usr/bin/env python3
"""Smart cane - Wi-Fi through NetworkManager (nmcli).

Used by the Wi-Fi QR code on the button (wifi_qr.py), the admin page
(admin_api.py) and the setup hotspot (wifi_hotspot.py).

nmcli runs as pi, never through sudo: sudo logs the whole command line, and
a Wi-Fi password is part of it. 10-omniwalk-wifi.rules (polkit) gives pi the
NetworkManager rights this needs. The password is never printed or logged.
"""
import subprocess
import sys

IFACE = "wlan0"
CONNECT_WAIT_S = 25
HOTSPOT = "OmniWalk-Setup"      # profile name and network name of the hotspot
HOTSPOT_ADDR = "10.42.0.1"      # NetworkManager's address in shared mode


def _nmcli(*args, run=subprocess.run):
    return run(["nmcli", *args], capture_output=True, text=True,
               timeout=CONNECT_WAIT_S + 10)


def split_terse(line):
    """Fields of one `nmcli -t` line: ':' separates, '\\:' and '\\\\' are
    literal."""
    out, cur, i = [], "", 0
    while i < len(line):
        c = line[i]
        if c == "\\" and i + 1 < len(line):
            cur += line[i + 1]
            i += 2
            continue
        if c == ":":
            out.append(cur)
            cur = ""
        else:
            cur += c
        i += 1
    out.append(cur)
    return out


def wifi_profiles(run=subprocess.run):
    """[(profile name, network name)] of the saved Wi-Fi networks, the setup
    hotspot left out."""
    out = _nmcli("-t", "-f", "NAME,TYPE", "connection", "show", run=run)
    found = []
    for line in out.stdout.splitlines():
        f = split_terse(line)
        if len(f) < 2 or f[1] != "802-11-wireless" or f[0] == HOTSPOT:
            continue
        got = _nmcli("-g", "802-11-wireless.ssid", "connection", "show", "id",
                     f[0], run=run)
        found.append((f[0], got.stdout.strip() if got.returncode == 0 else ""))
    return found


def saved_profile(ssid, run=subprocess.run):
    """Name of an existing Wi-Fi profile for this network name, or None."""
    for name, s in wifi_profiles(run=run):
        if s == ssid:
            return name
    return None


def security_args(net):
    """nmcli settings for the network's security."""
    s, pw = net["security"], net["password"]
    if s == "open":
        return []
    if s == "wep":
        return ["wifi-sec.key-mgmt", "none", "wifi-sec.wep-key-type", "key",
                "wifi-sec.wep-key0", pw]
    return ["wifi-sec.key-mgmt", "sae" if s == "sae" else "wpa-psk",
            "wifi-sec.psk", pw]


def security_from_scan(text, password):
    """Security kind for a network as nmcli's scan shows it ("WPA2",
    "WPA1 WPA2", "WPA3", "WEP", "--" or ""). Without a scan: open if there
    is no password, else WPA (NetworkManager's wpa-psk covers WPA and WPA2,
    and WPA3 networks in transition mode)."""
    t = (text or "").upper()
    if "802.1X" in t:
        return "enterprise"
    if "WPA3" in t and "WPA2" not in t and "WPA1" not in t:
        return "sae"
    if "WEP" in t:
        return "wep"
    if t in ("--",) or (not t and not password):
        return "open"
    return "wpa"


def profile_commands(net, existing):
    """The nmcli argument lists that save the network."""
    common = ["connection.autoconnect", "yes",
              "802-11-wireless.hidden", "yes" if net["hidden"] else "no"]
    if existing is None:
        return [["connection", "add", "type", "wifi", "ifname", IFACE,
                 "con-name", net["ssid"], "ssid", net["ssid"],
                 *common, *security_args(net)]]
    cmds = []
    if net["security"] == "open":
        cmds.append(["connection", "modify", "id", existing, "remove",
                     "802-11-wireless-security"])
    cmds.append(["connection", "modify", "id", existing, *common,
                 *security_args(net)])
    return cmds


def networks(rescan=True, run=subprocess.run):
    """Networks in range, strongest first: [{"ssid", "signal" (0-100),
    "security", "active"}], one entry per name."""
    out = None
    for r in (("yes", "no") if rescan else ("no",)):   # NM refuses a rescan
        out = _nmcli("-t", "-f", "ACTIVE,SSID,SIGNAL,SECURITY", "device",   # right after one
                     "wifi", "list", "ifname", IFACE, "--rescan", r, run=run)
        if out.returncode == 0:
            break
    best = {}
    for line in out.stdout.splitlines():
        f = split_terse(line)
        if len(f) < 4 or not f[1]:
            continue
        try:
            signal = int(f[2])
        except ValueError:
            signal = 0
        n = {"ssid": f[1], "signal": signal, "security": f[3],
             "active": f[0] == "yes"}
        old = best.get(n["ssid"])
        if old is None or n["active"] or (not old["active"] and signal > old["signal"]):
            best[n["ssid"]] = n
    return sorted(best.values(), key=lambda n: (not n["active"], -n["signal"]))


def scan(run=subprocess.run):
    """(network names in range, the one wlan0 is on now or None)."""
    nets = networks(run=run)
    active = next((n["ssid"] for n in nets if n["active"]), None)
    return {n["ssid"] for n in nets}, active


def device_status(run=subprocess.run):
    """{"connected": bool, "connection": profile in use or "", "ip": address
    or ""}. connected only once fully up (state 100), not while joining."""
    out = _nmcli("-g", "GENERAL.STATE,GENERAL.CONNECTION,IP4.ADDRESS", "device",
                 "show", IFACE, run=run)
    lines = (out.stdout.splitlines() + ["", "", ""])[:3]
    return {"connected": lines[0].strip().startswith("100"),
            "connection": lines[1].strip(),
            "ip": lines[2].split("/")[0].split("|")[0].strip()}


def save(net, run=subprocess.run):
    """Save (or update) the network. Returns the profile name, or None."""
    ssid = net["ssid"]
    existing = saved_profile(ssid, run=run)
    for cmd in profile_commands(net, existing):
        res = _nmcli(*cmd, run=run)
        if res.returncode != 0:
            print(f"  WIFI save {ssid!r} failed: {res.stderr.strip()[:200]}",
                  file=sys.stderr)
            return None
    print(f"  WIFI saved {ssid!r} ({net['security']}"
          f"{', hidden' if net['hidden'] else ''})")
    return existing or ssid


def plan(net, run=subprocess.run):
    """What joining would do now: "already" (on it), "away" (not in range,
    joining would only drop the current network) or "join"."""
    seen, active = scan(run=run)
    if active == net["ssid"]:
        return "already"
    if seen and net["ssid"] not in seen and not net["hidden"]:
        return "away"
    return "join"


def activate(name, ssid, run=subprocess.run):
    """Join a saved network now: (code, sentence). code "connected",
    "password" (refused) or "failed". A failed join leaves NetworkManager to
    go back to a network it knows."""
    res = _nmcli("--wait", str(CONNECT_WAIT_S), "connection", "up", "id", name,
                 run=run)
    if res.returncode == 0:
        print(f"  WIFI joined {ssid!r}")
        return "connected", f"Connected to {ssid}."
    err = (res.stderr or "").strip()
    print(f"  WIFI join {ssid!r} failed: {err[:200]}", file=sys.stderr)
    if "secrets" in err.lower():
        return "password", f"{ssid} did not accept the password. It is saved anyway."
    return "failed", f"Saved {ssid}, but could not join it now. The cane joins it when it is in range."


def join_result(net, run=subprocess.run):
    """Save the network and join it now: (code, sentence to speak)."""
    ssid = net["ssid"]
    if net["security"] == "enterprise":
        return "enterprise", f"{ssid} needs a user name. The cane cannot join it."
    name = save(net, run=run)
    if name is None:
        return "save_failed", f"Could not save Wi-Fi {ssid}."
    # Joining drops the current network first, so only try when it can work.
    p = plan(net, run=run)
    if p == "already":
        return "already", f"Already connected to {ssid}. Its password is saved."
    if p == "away":
        return "away", f"Saved {ssid}. It is not in range now. The cane joins it when it is."
    return activate(name, ssid, run=run)


def join(net, run=subprocess.run):
    """Save the network and join it now. Returns a sentence to speak."""
    return join_result(net, run=run)[1]


def forget(name, run=subprocess.run):
    """Delete a saved network: (ok, message). Not the one in use, which
    would cut the cane off, and never the setup hotspot."""
    if name == HOTSPOT:
        return False, "The setup hotspot cannot be removed here."
    if device_status(run=run)["connection"] == name:
        return False, f"The cane is using {name}. Join another network first."
    res = _nmcli("connection", "delete", "id", name, run=run)
    if res.returncode != 0:
        return False, f"Could not remove {name}."
    print(f"  WIFI forgot {name!r}")
    return True, f"Removed {name}."


# ---- setup hotspot ----------------------------------------------------------

def hotspot_active(run=subprocess.run):
    return device_status(run=run)["connection"] == HOTSPOT


def hotspot_up(run=subprocess.run):
    """Open the setup hotspot (open network, the cane at HOTSPOT_ADDR).
    Changing anything still needs the admin password. True if it is up."""
    out = _nmcli("-t", "-f", "NAME", "connection", "show", run=run)
    if HOTSPOT not in [split_terse(l)[0] for l in out.stdout.splitlines()]:
        res = _nmcli("connection", "add", "type", "wifi", "ifname", IFACE,
                     "con-name", HOTSPOT, "ssid", HOTSPOT,
                     "connection.autoconnect", "no",
                     "802-11-wireless.mode", "ap", "802-11-wireless.band", "bg",
                     "ipv4.method", "shared", "ipv6.method", "disabled", run=run)
        if res.returncode != 0:
            print(f"  WIFI hotspot profile failed: {res.stderr.strip()[:200]}",
                  file=sys.stderr)
            return False
    res = _nmcli("--wait", "15", "connection", "up", "id", HOTSPOT, run=run)
    if res.returncode != 0:
        print(f"  WIFI hotspot failed: {res.stderr.strip()[:200]}", file=sys.stderr)
        return False
    return True


def hotspot_down(run=subprocess.run):
    """Close the setup hotspot, so NetworkManager tries known networks."""
    return _nmcli("connection", "down", "id", HOTSPOT, run=run).returncode == 0
