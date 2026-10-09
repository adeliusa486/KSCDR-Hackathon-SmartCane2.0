#!/usr/bin/env python3
"""Smart cane - join a Wi-Fi network by showing its QR code to the camera.

Phones share a Wi-Fi network as a QR code (Android: Wi-Fi settings, the gear
next to the network, "QR code"; iPhone: through a QR app or the router's
sticker). The text in it looks like

    WIFI:T:WPA;S:Home Net;P:secret;H:false;;

Hold the cane's button for 1 s ("read text") with the code in front of the
camera. If the photo holds a Wi-Fi code, the cane saves the network with
NetworkManager and joins it at once (wifi_net.py), instead of reading text. A network it
cannot join right now (out of range, wrong password) stays saved, and the cane
goes back to the network it had.

The camera's lens has fixed focus for 2-4 m (MEMORY.md), so a phone held
close is soft and one held far is small. Several photos are tried, each also
enlarged and sharpened. A big code (laptop screen, printed sheet) at 40-80 cm
reads best.

The password is never printed, logged or spoken.

    python3 wifi_qr.py --decode photo.jpg     # what code is in this photo?
"""
import argparse
import sys

# The network side lives in wifi_net.py, shared with the admin page.
from wifi_net import join, join_result  # noqa: F401  (assistant.py calls wifi_qr.join)


def parse_wifi(text):
    """Fields of a WIFI: QR text, or None if it is not one.

    Returns {"ssid", "password", "security", "hidden"}, security one of
    "wpa" (WPA/WPA2 personal), "sae" (WPA3), "wep", "open" or "enterprise"
    (needs a user name, not supported)."""
    if not text or not text[:5].upper() == "WIFI:":
        return None
    fields, cur, i, body = {}, "", 0, text[5:]
    while i < len(body):
        c = body[i]
        if c == "\\" and i + 1 < len(body):      # \; \, \: \\ \" are literal
            cur += body[i + 1]
            i += 2
            continue
        if c == ";":
            if ":" in cur:
                k, v = cur.split(":", 1)
                fields[k.strip().upper()] = v
            cur = ""
        else:
            cur += c
        i += 1
    if ":" in cur:
        k, v = cur.split(":", 1)
        fields[k.strip().upper()] = v

    def unquote(v):
        return v[1:-1] if len(v) >= 2 and v[0] == v[-1] == '"' else v

    ssid = unquote(fields.get("S", ""))
    if not ssid:
        return None
    password = unquote(fields.get("P", ""))
    t = fields.get("T", "").strip().upper()
    if "EAP" in t or "E" in fields:
        security = "enterprise"
    elif t in ("NOPASS", "NONE") or (not t and not password):
        security = "open"
    elif t == "WEP":
        security = "wep"
    elif t in ("SAE", "WPA3"):
        security = "sae"
    else:                                        # WPA, WPA2, WPA/WPA2, blank
        security = "wpa"
    hidden = fields.get("H", "").strip().lower() == "true"
    return {"ssid": ssid, "password": password, "security": security,
            "hidden": hidden}


def look(jpeg):
    """What QR code a JPEG holds: (network, state).

    state "wifi" (network is parse_wifi()'s dict), "other" (a QR code that is
    not a Wi-Fi one), "unreadable" (a code was found but not decoded: another
    photo may work) or "none". The photo is tried as it is, then enlarged,
    sharpened and its centre enlarged, because the code is often small or
    soft in this camera's wide, fixed-focus view."""
    try:
        import cv2
        import numpy as np
    except ImportError:
        return None, "none"
    img = cv2.imdecode(np.frombuffer(jpeg, np.uint8), cv2.IMREAD_GRAYSCALE)
    if img is None:
        return None, "none"
    det = cv2.QRCodeDetector()
    decode = _decoder(det)
    h, w = img.shape[:2]
    big = cv2.resize(img, (w * 2, h * 2), interpolation=cv2.INTER_CUBIC)
    sharp = cv2.addWeighted(big, 1.8, cv2.GaussianBlur(big, (0, 0), 3), -0.8, 0)
    centre = img[h // 4: 3 * h // 4, w // 4: 3 * w // 4]
    centre = cv2.resize(centre, (w, h), interpolation=cv2.INTER_CUBIC)
    for view in (img, big, sharp, centre):
        text = decode(view)
        net = parse_wifi(text)
        if net:
            return net, "wifi"
        if text:
            return None, "other"
    # Locating a code works in every OpenCV build, decoding does not.
    try:
        seen = det.detect(img)[0] or det.detect(big)[0]
    except cv2.error:
        seen = False
    return None, "unreadable" if seen else "none"


def _decoder(det):
    """A function: grey image -> QR text or "". zbar (python3-pyzbar) where
    it is installed. Debian's OpenCV 4.6 on the cane is built without quirc
    and only prints "Library QUIRC is not linked. No decoding is performed"
    (9 Oct 2026), so OpenCV's own decoder is only the fallback (it works in
    the pip wheels, as on the laptop)."""
    try:
        from pyzbar import pyzbar

        def zbar(img):
            for r in pyzbar.decode(img, symbols=[pyzbar.ZBarSymbol.QRCODE]):
                return r.data.decode("utf-8", "replace")
            return ""
        return zbar
    except Exception:          # no pyzbar, or no libzbar under it
        pass
    import cv2

    def opencv(img):
        try:
            return det.detectAndDecode(img)[0]
        except cv2.error:
            return ""
    return opencv


def warm_up():
    """Load OpenCV and zbar ahead of the first long press: look() took
    1.7 s the first time on the cane and 0.6 s after (9 Oct 2026)."""
    try:
        import cv2
        _decoder(cv2.QRCodeDetector())
    except Exception:
        pass


def main():
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--decode", metavar="JPEG",
                    help="print the Wi-Fi network in this photo's QR code")
    args = ap.parse_args()
    if args.decode:
        with open(args.decode, "rb") as fh:
            net, state = look(fh.read())
        if net is None:
            print(f"no Wi-Fi QR code ({state})")
            return 1
        print(f"network {net['ssid']!r}, {net['security']}, "
              f"hidden={net['hidden']}, password {len(net['password'])} characters")
        return 0
    ap.print_help()
    return 0


if __name__ == "__main__":
    sys.exit(main())
