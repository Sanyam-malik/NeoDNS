# Use a lightweight Python base image
FROM python:3.9-slim

# Set the working directory inside the container
WORKDIR /app

# Install only minimal utilities (no Avahi inside container)
RUN apt-get update && \
    apt-get install -y iputils-ping && \
    rm -rf /var/lib/apt/lists/*

# Copy the current directory contents into the container
COPY . /app

# Copy the startup script
COPY start.sh /app/start.sh

# Make the startup script executable
RUN chmod +x /app/start.sh

ENV DNS_PORT=53
ENV API_PORT=8002
ENV STANDALONE="false"

# Install Python dependencies
RUN pip install --no-cache-dir -r requirements.txt

EXPOSE 8000 53/udp
# Set the startup script as the entrypoint
CMD ["/app/start.sh"]