#!/bin/bash
set -e

# Start D-Bus session daemon
DBUS_SESSION_BUS_ADDRESS=$(dbus-daemon --session --print-address --fork)
export DBUS_SESSION_BUS_ADDRESS
echo "D-Bus session bus address: $DBUS_SESSION_BUS_ADDRESS"

# Create a minimal avahi-daemon.conf to avoid system D-Bus usage
cat > /etc/avahi/avahi-daemon.conf <<EOF
[server]
use-ipv4=yes
use-ipv6=no
allow-interfaces=lo
enable-dbus=no

[publish]
disable-publishing=no

[reflector]
enable-reflector=no
EOF

# Start avahi-daemon with our generated config, in user-mode
avahi-daemon --no-chroot --no-drop-root -c /etc/avahi/avahi-daemon.conf --debug &

# Run the Python DNS server
exec python dns_server.py