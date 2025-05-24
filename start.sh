#!/bin/bash
set -e

# Start private D-Bus session daemon and export its address
eval "$(dbus-daemon --session --print-address --fork)"
echo "Started private D-Bus session bus: $DBUS_SESSION_BUS_ADDRESS"

# Start avahi-daemon in user mode, tied to this session bus
avahi-daemon --no-chroot --no-drop-root --debug --config-file=/etc/avahi/avahi-daemon.conf &

# Wait a moment for Avahi to initialize
sleep 2

# Run your Python DNS server
exec python dns_server.py