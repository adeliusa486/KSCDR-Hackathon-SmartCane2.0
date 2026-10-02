# Step 1.2: fix Raspberry Pi power before optimizing AI

**Status: BLOCKED.** Part A (the current supply) is measured and fails. Part B,
the step itself, needs a 5 V / 5 A USB-C supply on the Pi's USB-C port. It
cannot be done remotely. Phase 1 cannot continue until it passes.

Files: `test_plan.md` (method and pass criteria, fixed before measuring),
`results.json`, `raw_results.csv`, `terminal_output.txt`, `failure_log.md`
(G1 to G6), `before/` and `after/` (snapshots around Part A), `data/`.

## Part A result: the UPS supply cannot run the cane

The load ladder (`code/tools/power_soak.sh`, abort on first under-voltage)
never got past the second phase.

| Phase | Result |
|---|---|
| idle, 125 s | 0 under-voltage events. EXT5V min 4.930 V |
| service (camera, Hailo, ESP32, audio), 43 s | **under-voltage at 21:32:29**, load stopped. EXT5V min 4.754 V at 1 Hz |
| bench, bench_cpu, svc_cpu | not reached |

Over the whole 21:26 boot there were **11 under-voltage events in 9.5 min**,
all with nothing heavier than the normal service running. The previous boot
had one at 21:03:16, and the Pi dropped off the network at about 21:20 for a
reason the volatile journal did not keep (G1).

The 1 Hz EXT5V samples never went below 4.749 V while the kernel flagged
under-voltage 11 times, so the dips are shorter than 1 s. Use the kernel
event count, not the ADC samples, to judge a supply.

The service was stopped at 21:37 so the bench Pi stops browning out. Start it
again with `systemctl --user start smartcane.service`.

## What Part B needs (Adeel)

1. A 5 V / 5 A USB-C PD supply (Raspberry Pi 27 W PSU or equivalent).
2. Power the Pi down. Remove the UPS feed from the 5V header pin. Plug the
   USB-C supply into the Pi's USB-C port. Never connect both at once.
3. Power up and leave it on the network. The rest is remote:
   `max_current` must read 5000, then the short ladder, then 30 min, 60 min
   and 2 h runs at worst-case load (`svc_cpu`), and 30 min at `bench_cpu`.
   About 4 h in total.

The UPS's role in the final product (battery) is decided in Step 1.3 from
measured current, not here.

## Changes made in this step

- Persistent journal: `/etc/systemd/journald.conf.d/50-smartcane-persistent.conf`
  (`Storage=persistent`, `SystemMaxUse=200M`). Undo by deleting the file and
  restarting `systemd-journald`.
- `smartcane.service` stopped (see above).
- New tools: `code/tools/power_soak.sh` (on the Pi in
  `~/smartcane/tools/`) and `code/tools/soak_summary.py` (laptop).

## Tool defects found and fixed during the step

1. The kernel event filter matched the module list printed in every Hailo
   driver warning (it contains `cp210x`). Lines with "Modules linked in" are
   now dropped.
2. Vision liveness first read the service journal. `speak_detect.py` consumes
   detect.py's reports through a pipe and never logs them, so it always read
   0. Replaced by detect.py's CPU time per second.
3. The process pattern `detect.py` also matched `speak_detect.py`, so the
   first liveness test (`data/harness_check`) measured the wrong process. Its
   `detect_cpu` column is invalid. The pattern is now `smartcane/[d]etect.py`.
   Measured by hand afterwards: detect.py used 0.48 s CPU in 5 s (about 10 %
   of a core) while running normally.
4. Files rewritten by Python on Windows came out with CRLF endings and bash
   on the Pi failed. Both tools are LF again.

detect.py CPU time is a proxy. It catches a hang like the 2 Oct one, but not
a loop that spins without inferring. A real vision watchdog belongs to the
fault-handling work (F1).
