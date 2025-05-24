#!/bin/bash
set -e

# Start dbus daemon, capture the address, export it
DBUS_SESSION_BUS_ADDRESS=$(dbus-daemon --session --print-address --fork)
export DBUS_SESSION_BUS_ADDRESS

echo "D-Bus session bus address: $DBUS_SESSION_BUS_ADDRESS"

# Start Avahi daemon (no chroot, no drop root to avoid issues)
avahi-daemon --no-chroot --no-drop-root --debug &

# Run the python DNS server
exec python dns_server.py