#!/usr/bin/env bash
# 24/7 server power profile for the mini (run with sudo).
set -euo pipefail

# On AC power: never sleep, keep disks awake, restart after power failure,
# no Power Nap weirdness. Display can sleep — that's fine for a headless box.
pmset -c sleep 0
pmset -c disksleep 0
pmset -c displaysleep 5
pmset -c autorestart 1
pmset -c powernap 0
pmset -c womp 1   # wake on LAN, handy for remote admin

echo "Power settings applied:"
pmset -g custom
