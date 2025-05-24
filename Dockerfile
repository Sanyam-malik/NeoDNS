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

# Copy the startup script
COPY start.sh /app/start.sh

# Make the startup script executable
RUN chmod +x /app/start.sh

# Install necessary Python packages
RUN pip install --no-cache-dir -r requirements.txt

# Expose ports
EXPOSE 1053/udp
EXPOSE 8000/tcp

# Use the startup script as the container entrypoint
CMD ["/app/start.sh"]