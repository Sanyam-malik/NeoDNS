#!/bin/bash
set -ex

# Start D-Bus session daemon and set environment variable correctly
eval "$(dbus-daemon --session --print-address --fork)"

echo "D-Bus started at: $DBUS_SESSION_BUS_ADDRESS"

# Start Avahi daemon in user mode with no chroot and debug enabled
avahi-daemon --no-chroot --no-drop-root --debug &

# Run your Python DNS server
exec python dns_server.py