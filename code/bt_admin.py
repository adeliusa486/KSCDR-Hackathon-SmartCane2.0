#!/usr/bin/env python3
"""Smart cane - Bluetooth devices for the admin page, through bluetoothctl.

List paired devices, scan for new ones, pair (earbuds in pairing mode), trust,
connect, forget. Which device the cane speaks through is kept in
~/.config/smartcane/earbuds (one address). speak_detect.py reads it at start
and the admin page changes it while the cane runs.

    python3 bt_admin.py --list
    python3 bt_admin.py --scan 8
"""
import argparse
import os
import queue
import re
import subprocess
import threading
import time

EARBUDS_FILE = os.path.expanduser("~/.config/smartcane/earbuds")
DEFAULT_EARBUDS = "B0:38:E2:19:DC:CC"    # the Soundcore earbuds paired first
MAC = re.compile(r"^[0-9A-F]{2}(:[0-9A-F]{2}){5}$")
ANSI = re.compile(r"\x1b\[[0-9;]*[A-Za-z]|\x01|\x02")


def valid_mac(mac):
    return bool(MAC.match((mac or "").upper()))


def _btctl(*args, timeout=15, run=subprocess.run):
    try:
        return run(["bluetoothctl", *args], capture_output=True, text=True,
                   timeout=timeout)
    except subprocess.TimeoutExpired:
        return subprocess.CompletedProcess(args, 1, "", "timed out")


def earbuds():
    """Address of the device the cane speaks through."""
    try:
        with open(EARBUDS_FILE) as fh:
            mac = fh.read().strip().upper()
        if valid_mac(mac):
            return mac
    except OSError:
        pass
    return DEFAULT_EARBUDS


def save_earbuds(mac):
    os.makedirs(os.path.dirname(EARBUDS_FILE), exist_ok=True)
    tmp = EARBUDS_FILE + ".tmp"
    with open(tmp, "w") as fh:
        fh.write(mac.upper() + "\n")
    os.replace(tmp, EARBUDS_FILE)


def _devices(which=None, run=subprocess.run):
    """{address: name} from `bluetoothctl devices [Paired|Connected]`."""
    out = _btctl("devices", *([which] if which else []), run=run).stdout
    found = {}
    for line in ANSI.sub("", out).splitlines():
        parts = line.strip().split(" ", 2)
        if len(parts) >= 2 and parts[0] == "Device" and valid_mac(parts[1]):
            found[parts[1].upper()] = parts[2] if len(parts) > 2 else ""
    return found


def info(mac, run=subprocess.run):
    """`bluetoothctl info` as a dict (Name, Icon, Paired, Connected, ...)."""
    out = _btctl("info", mac, run=run).stdout
    got = {}
    for line in ANSI.sub("", out).splitlines():
        if ":" in line and line.startswith(("\t", " ")):
            k, v = line.strip().split(":", 1)
            got.setdefault(k.strip(), v.strip())
    return got


def _entry(mac, name, run):
    i = info(mac, run=run)
    return {"mac": mac, "name": i.get("Name") or name or mac,
            "icon": i.get("Icon", ""), "paired": i.get("Paired") == "yes",
            "connected": i.get("Connected") == "yes"}


def paired(run=subprocess.run):
    """Paired devices, the cane's earbuds first."""
    ear = earbuds()
    found = [dict(_entry(m, n, run), earbuds=(m == ear))
             for m, n in _devices("Paired", run=run).items()]
    return sorted(found, key=lambda d: (not d["earbuds"], not d["connected"], d["name"]))


def scan(seconds=8, run=subprocess.run):
    """Devices in range that are not paired yet. Audio devices first. The
    other device must be in pairing mode to show up."""
    seconds = max(3, min(20, int(seconds)))
    _btctl("--timeout", str(seconds), "scan", "on", timeout=seconds + 10, run=run)
    known = _devices("Paired", run=run)
    found = []
    for mac, name in _devices(run=run).items():
        if mac in known:
            continue
        e = _entry(mac, name, run)
        # A name that is only the address again means nothing was heard.
        if e["name"].replace("-", ":").upper() == mac and not e["icon"]:
            continue
        found.append(e)
    return sorted(found, key=lambda d: (not d["icon"].startswith("audio"), d["name"]))[:30]


class _Session:
    """One interactive bluetoothctl, for pairing (it needs an agent alive in
    the same process for the whole exchange)."""

    def __init__(self, popen=subprocess.Popen):
        self.p = popen(["bluetoothctl"], stdin=subprocess.PIPE,
                       stdout=subprocess.PIPE, stderr=subprocess.STDOUT,
                       text=True, bufsize=1)
        self.lines = queue.Queue()
        self.log = []
        threading.Thread(target=self._read, daemon=True).start()

    def _read(self):
        for line in self.p.stdout:
            self.lines.put(ANSI.sub("", line).strip())

    def send(self, cmd):
        self.p.stdin.write(cmd + "\n")
        self.p.stdin.flush()

    def wait(self, wanted, timeout):
        """The first wanted text seen within timeout s, or None."""
        end = time.monotonic() + timeout
        while time.monotonic() < end:
            try:
                line = self.lines.get(timeout=max(0.05, end - time.monotonic()))
            except queue.Empty:
                break
            self.log.append(line)
            for w in wanted:
                if w.lower() in line.lower():
                    return w
        return None

    def close(self):
        try:
            self.send("quit")
            self.p.wait(timeout=3)
        except Exception:
            self.p.kill()


def pair(mac, popen=subprocess.Popen):
    """Pair, trust and connect a device in pairing mode: (ok, message)."""
    mac = mac.upper()
    if not valid_mac(mac):
        return False, "Not a Bluetooth address."
    s = _Session(popen=popen)
    try:
        s.send("agent NoInputNoOutput")
        s.wait(["Agent registered", "already registered"], 3)
        s.send("default-agent")
        s.wait(["Default agent request successful"], 3)
        # The device must be in BlueZ's list from a recent scan to be paired.
        s.send("scan on")
        s.wait([f"Device {mac}"], 10)
        s.send("scan off")
        s.send(f"pair {mac}")
        got = s.wait(["Pairing successful", "AlreadyExists", "Failed to pair",
                      "not available"], 30)
        if got in (None, "Failed to pair", "not available"):
            return False, ("The device did not answer. Put it in pairing mode "
                           "and scan again." if got != "Failed to pair"
                           else "Pairing failed. Put it in pairing mode and try again.")
        s.send(f"trust {mac}")
        s.wait(["trust succeeded"], 5)
        s.send(f"connect {mac}")
        got = s.wait(["Connection successful", "Failed to connect"], 20)
        if got != "Connection successful":
            return True, "Paired, but it did not connect. Try Connect in a moment."
        return True, "Paired and connected."
    finally:
        s.close()


def connect(mac, run=subprocess.run):
    out = _btctl("--timeout", "20", "connect", mac, timeout=30, run=run)
    ok = "Connection successful" in ANSI.sub("", out.stdout)
    return ok, ("Connected." if ok else "Could not connect. Is it switched on and near the cane?")


def forget(mac, run=subprocess.run):
    if mac.upper() == earbuds():
        return False, "The cane speaks through this device. Choose other earbuds first."
    out = _btctl("remove", mac, run=run)
    ok = "removed" in ANSI.sub("", out.stdout).lower()
    return ok, ("Removed." if ok else "Could not remove it.")


def main():
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--list", action="store_true", help="paired devices")
    ap.add_argument("--scan", type=int, metavar="S", help="scan S seconds")
    args = ap.parse_args()
    if args.scan:
        for d in scan(args.scan):
            print(f"{d['mac']}  {d['icon'] or '-':16s} {d['name']}")
    else:
        for d in paired():
            flags = ("earbuds " if d["earbuds"] else "") + ("connected" if d["connected"] else "")
            print(f"{d['mac']}  {d['icon'] or '-':16s} {d['name']}  {flags}")


if __name__ == "__main__":
    main()
