# Use a lightweight Python base image
FROM python:3.9-slim

# Set the working directory inside the container
WORKDIR /app

# Install necessary dependencies
RUN apt-get update && \
    apt-get install -y avahi-daemon avahi-utils dbus && \
    rm -rf /var/lib/apt/lists/*

# Copy the current directory contents into the container at /app
COPY . /app

# Install necessary Python packages
RUN pip install --no-cache-dir -r requirements.txt

# Expose port 53 for DNS traffic
EXPOSE 1053/udp

# Expose port 53 for DNS traffic
EXPOSE 8000/tcp

# Start avahi-daemon in the background and run the Python DNS server
CMD dbus-daemon --session --nofork --print-address && avahi-daemon --daemonize && python dns_server.py