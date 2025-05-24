#!/bin/bash
set -e

# Start D-Bus session daemon in background (private socket)
dbus-daemon --session --print-address --fork

# Start Avahi daemon in background
avahi-daemon --daemonize

# Start your Python DNS server
exec python dns_server.py