# Step 1.2 failure log

Every fault seen during Step 1.2, in the order found. Nothing here is hidden
or tidied up. Items owned by a later step say so.

## G1. The Pi dropped off the network at about 21:20 and came back at 21:26 (cause unknown)

- 21:18:52 last good SSH (up 19 min, boot 20:59).
- 21:20 to 21:21: SSH timed out, then ARP failed ("Destination host
  unreachable"). The Pi was off the network, not just slow.
- Adeel reported it "turned on" again. New boot at 21:26:23.
- **The previous boot's logs are lost.** `journald.conf` line 18 had
  `Storage=volatile`, so there is no record of a crash, panic, power loss or
  shutdown. This is the second time today a power-related event could not be
  fully reconstructed.
- Clues, not proof:
  - `chosen/bootloader/rsts` = `0x00001000`. On Pi boards this bit is usually
    read as a power-on reset. Not confirmed for the Pi 5 from documentation.
  - The clock was correct at boot (21:26:58) while `timedatectl` said
    "System clock synchronized: no", and `fake-hwclock.data` held 21:17:01.
    So the time came from the RTC, which suggests the RTC kept power.
  - The ESP32 had been up 108 s at 21:28:10, so it restarted with the Pi.
    It is powered from the Pi's USB, so the Pi's USB 5 V went away.
- Most likely explanation: a power event on the UPS supply. Not proven.

**Change made:** `/etc/systemd/journald.conf.d/50-smartcane-persistent.conf`
sets `Storage=persistent`, `SystemMaxUse=200M`. Undo by deleting the file
and restarting `systemd-journald`. Needed so Step 1.2's "unexpected reboot"
failure condition can be diagnosed.

## G2. Under-voltage on the UPS supply at normal service load

| Boot | Time | Load at the time |
|---|---|---|
| 20:59 | 21:03:16 | service had started 50 s earlier (vision + Hailo + ESP32) |
| 21:26 | 21:27:33 | service running normally |
| 21:26 | 21:27:59 | service running normally |
| 21:26 | 21:29:22 to 21:29:28 | service running, snapshot script |
| 21:26 | 21:29:34 | service running, snapshot script |
| 21:26 | 21:32:29 | Part A ladder, 43 s into the `service` phase (ladder aborted) |
| 21:26 | 21:34:12, 21:34:20 | service restored after the ladder |
| 21:26 | 21:35:27, 21:35:55, 21:36:26, 21:37:02 | service running normally, no other load |

11 events in 9.5 min on the 21:26 boot. The service was stopped at 21:37 to
end it.

The Step 1.1 retest window (3 min, 21:0x) saw none. Under-voltage is not
limited to heavy load: the current supply cannot carry the cane's normal
operation. This is the problem Step 1.2 exists to fix.

## G3. Boot took 11.1 s

`systemd-analyze`: 7.443 s kernel + 3.663 s userspace = 11.107 s. Previous
measurements 6.8 s, 6.995 s, 9.394 s. Under-voltage may slow the kernel
phase. Recheck boot time on the new supply. Fact 12 of the Phase 2 draft
needs the range widened to 7.0 to 11.1 s.

## G4. After boot, the service's ESP32 link stayed dead (owner: Step 1.5)

- 21:26:42 service logged `ESP32 LINK SILENT`. No `ESP32 link back` followed
  in the next 80 s.
- Meanwhile the ESP32 was running and sending: a direct capture at 21:28
  (service stopped) got D lines with ESP32 uptime 108 s.
- After `systemctl --user restart`, the link came up at once.
- So the service can start, fail to read the ESP32, and never recover. The
  reader thread in `esp32_link.py` catches `SerialException` and keeps
  reading the same handle. It never reopens the port.
- The user would have heard "Warning, distance sensors not responding" every
  30 s, but the earbuds were not connected (`AUDIO DEAD`), so in practice
  they heard nothing. The ESP32's own buzzing still worked.

## G5. Serial bridge errors and the stale burst again (owner: Step 1.5)

- The 6 s direct capture at 21:28 saw 3,222 D lines, an apparent 538 Hz.
  That is the F5 stale burst from Step 1.1 again.
- `dmesg` at the same moment: `cp210x ttyUSB0: failed set request 0x12
  status: -110`. Request 0x12 is very likely the purge sent by
  `reset_input_buffer()`, timing out. The same error stopped the full flash
  read in Step 1.1 (F3). A purge that times out may explain why
  `reset_input_buffer()` did not clear the stale data in F5. Not proven.
- The ESP32 received one garbled command (`E unknown command 'bev...'`) when
  the port opened.

## G6. Earbuds did not reconnect after boot (known, Step 1.1)

`br-connection-profile-unavailable` at 21:26:42, then `AUDIO DEAD` and a
reconnect attempt every 10 s. Same as 21:02. Probably the earbuds are off or
in their case. Not a power fault, but it means no speech was reaching anyone.

## G7. The persistent journal does not survive a power cut (found 2 Oct, 21:52)

Found while drafting the Phase 4 prompt, checked on the Pi:

- `/var/log` is a `log2ram` tmpfs, 128 MB (`findmnt /var/log`). The new
  `Storage=persistent` journal writes to `/var/log/journal`, which is RAM.
- `log2ram` copies it to the SD card (`/var/hdd.log`) only from
  `log2ram-daily.timer` (next run 23:55) and at a clean shutdown.
- So an under-voltage reset or power cut still loses every log line since the
  last sync. That is exactly the event G1 could not diagnose, and exactly
  what the journal change was meant to catch.
- `SystemMaxUse=200M` is larger than the 128 MB tmpfs it lives in.

Not fixed. Options for Step 1.2 Part B: exclude `/var/log/journal` from
log2ram, or set `Storage=persistent` with journald writing straight to the
SD card and `SyncIntervalSec` short, then cap the journal well below the
free space. Test by cutting power and reading the previous boot's log.

### G7 fix applied and tested, 2 Oct 2026, 22:56 to 23:12

Applied `code/tools/journal_persist.sh` (log2ram off, journal on the SD
card, `SyncIntervalSec=15s`), on the old UPS supply because the Pi had just
had another unexplained outage (G8). Service kept stopped (Part A decision).
"Power cut" below means a kernel crash-reboot (`echo b > /proc/sysrq-trigger`),
a proxy: it drops everything not yet on the card, but the card itself stays
powered. Real plug pulls are still to do.

| # | Result |
|---|---|
| J1 | **PASS.** `verify` exit 0, `/var/log` on the card, previous boots listed after a reboot |
| J2 | **PASS 3/3 after a second fix.** First run: root lines 20 s before the crash survived 3/3, but lines from user `pi` were lost entirely. With the default `SplitMode=uid`, `pi`'s messages (smartcane.service runs as `pi`) went to a separate user-1000 journal, which was set aside as `*.journal~` after every crash, and the crashed boot showed 0 `pi` entries, 4 of 4 times. Fixed with `SplitMode=none`. Then `pi` lines 21 s before the crash survived 3/3 |
| J3 | **FAIL 3/3 as written.** A crit line 1 s before the crash was lost every time, although journald documents an immediate sync for CRIT. Controls: after `journalctl --sync` the line survives 2/2, and plain lines survive up to 3.0 s before the crash (6 of 8 one-per-second lines, 2 trials). Measured log blind window: the last ~3 s before a crash |
| J4 | **PASS so far.** 0 ext4 errors in 11 crash-reboots, only the normal orphan cleanup. `fsck` on the next SD image still to do |

J3 decision for Adeel: accept a 3 s blind window (under-voltage warnings on
2 Oct came seconds to minutes before the faults they caused), or add kernel
pstore/ramoops, which keeps the kernel log across a reset (not across a real
power cut). Not blocking: Part B waits for the USB-C supply anyway.

Bonus data for Step 1.5 T10: **the ESP32 restarted with the Pi in 11 of 11
Pi resets** (1 clean reboot, 10 crash-reboots). Its `millis` always read about
0.4 s less than the Pi's uptime, so the ESP32 is unpowered or held in reset
from the Pi's shutdown until shortly after the Pi kernel starts.

## G8. The Pi stopped answering on the network for about 18 min (21:51 to 22:09)

The synced journals of that boot show no under-voltage, no Wi-Fi
disconnect, wlan0 associated with its lease the whole time, yet the laptop
got no ARP reply. The outage ended with `Power key pressed short` at
22:09:17 (a person pressing the power button, presumably Adeel), a second
press at 22:45:46, and power-on at 22:53. Both shutdowns were clean, so the
logs of those boots survived even under log2ram. Leading candidate: Wi-Fi
power saving (NetworkManager `powersave 0 = default`, `iw` not installed to
confirm). Not fixed. Worth testing because it may also explain older "SSH
drops" that were blamed on under-voltage.
