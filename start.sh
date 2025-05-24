#!/bin/bash
set -e

# Correctly start dbus and set DBUS_SESSION_BUS_ADDRESS environment variable
eval "$(dbus-daemon --session --print-address --fork)"
echo "D-Bus session bus started at: $DBUS_SESSION_BUS_ADDRESS"

# Start avahi in user mode attached to that session bus
avahi-daemon --no-chroot --no-drop-root --debug --config-file=/etc/avahi/avahi-daemon.conf &

sleep 2

# Run your python DNS server
exec python dns_server.py
