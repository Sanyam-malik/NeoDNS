#!/bin/bash
set -ex

dbus-daemon --session --print-address --fork
avahi-daemon --daemonize

# Run python and print errors
exec python dns_server.py