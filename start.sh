#!/bin/bash
set -ex

dbus-daemon --session --print-address --fork

# Run avahi-daemon in foreground for debugging
avahi-daemon --debug &
AVAHI_PID=$!

# Run Python server in foreground
exec python dns_server.py

# Optionally wait for avahi if python exits (not usually needed)
wait $AVAHI_PID