#!/usr/bin/env python3
"""Smart cane - open a setup hotspot when no known Wi-Fi is in reach.

Run by smartcane-hotspot.service. At a new place the cane has no internet, so
the website's admin page cannot reach it. Then, after NO_WIFI_S without a
Wi-Fi connection, the cane opens its own Wi-Fi network "OmniWalk-Setup".
Join it with a phone and open http://10.42.0.1:8080/admin: the same admin page,
where a network is chosen (the admin password is still needed).

The hotspot stays at least HOTSPOT_MIN_S, longer while a phone is on it (up to
HOTSPOT_MAX_S), then closes so NetworkManager can look for known networks
again, and opens again if none turns up. Walking outdoors with no Wi-Fi the
cane therefore runs the hotspot most of the time, which costs little power and
changes nothing else: detection, speech and vibration never need Wi-Fi.

    systemctl --user status smartcane-hotspot
"""
import subprocess
import sys
import time

import wifi_net

NO_WIFI_S = 90           # no Wi-Fi connection this long: open the hotspot
HOTSPOT_MIN_S = 300      # then keep it at least this long
HOTSPOT_MAX_S = 1200     # and never longer than this, phone or not
TICK_S = 5


def phones_on_hotspot(run=subprocess.run):
    """Devices the cane has heard from on the hotspot lately."""
    try:
        out = run(["ip", "neigh", "show", "dev", wifi_net.IFACE],
                  capture_output=True, text=True, timeout=5).stdout
    except (OSError, subprocess.SubprocessError):
        return 0
    prefix = wifi_net.HOTSPOT_ADDR.rsplit(".", 1)[0] + "."
    return sum(1 for l in out.splitlines()
               if l.startswith(prefix) and any(s in l for s in ("REACHABLE", "DELAY", "PROBE", "STALE")))


class Manager:
    def __init__(self, wifi=wifi_net, clock=time.monotonic, phones=phones_on_hotspot):
        self.wifi, self.clock, self.phones = wifi, clock, phones
        self.no_wifi_since = None
        self.hotspot_since = None

    def step(self):
        """One look at the Wi-Fi. Returns what it did or saw."""
        now = self.clock()
        st = self.wifi.device_status()
        if st["connection"] == self.wifi.HOTSPOT:
            if self.hotspot_since is None:          # found it up (a restart)
                self.hotspot_since = now
            age = now - self.hotspot_since
            if age >= HOTSPOT_MAX_S or (age >= HOTSPOT_MIN_S and not self.phones()):
                self.wifi.hotspot_down()
                self.hotspot_since = None
                self.no_wifi_since = now            # a full search before reopening
                return "down"
            return "hotspot"
        self.hotspot_since = None
        if st["connected"]:
            self.no_wifi_since = None
            return "connected"
        if self.no_wifi_since is None:
            self.no_wifi_since = now
        if now - self.no_wifi_since >= NO_WIFI_S:
            if self.wifi.hotspot_up():
                self.hotspot_since = now
                return "up"
            self.no_wifi_since = now                # failed: wait a full period
            return "failed"
        return "searching"


def main():
    m = Manager()
    last = None
    print(f"setup hotspot {wifi_net.HOTSPOT!r} opens after {NO_WIFI_S} s without Wi-Fi, "
          f"page at http://{wifi_net.HOTSPOT_ADDR}:8080/admin")
    while True:
        try:
            what = m.step()
        except Exception as e:                      # nmcli hiccup: try again
            what = f"error {e!r}"
        if what != last and what not in ("searching",):
            print({"up": "no known Wi-Fi: setup hotspot open",
                   "down": "setup hotspot closed, looking for known Wi-Fi",
                   "connected": "on Wi-Fi",
                   "hotspot": "setup hotspot open",
                   "failed": "could not open the setup hotspot"}.get(what, what), flush=True)
        last = what
        time.sleep(TICK_S)


if __name__ == "__main__":
    sys.exit(main())
