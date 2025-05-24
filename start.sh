#!/bin/bash
set -e

# Start D-Bus session daemon in background
dbus-daemon --session --print-address --fork

# Start Avahi daemon in background
avahi-daemon --daemonize

# Start Python server in background
python dns_server.py &

# Keep the container alive (wait forever)
tail -f /dev/null