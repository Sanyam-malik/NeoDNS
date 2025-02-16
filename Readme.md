# NeoDNS

NeoDNS is a DNS service designed to allow external applications and servers to seamlessly connect inside Docker containers. This service simplifies the process of configuring DNS for containers, enabling them to interact with external services or resolve domain names effortlessly. NeoDNS leverages Docker's networking capabilities to create a smooth and flexible solution for containerized environments.

## Features

- **External DNS Resolution**: Easily resolve external domains inside Docker containers.
- **Customizable DNS Settings**: Configure custom DNS servers for specific needs.
- **Simple Integration**: Simple to set up and integrate into existing Docker workflows.
- **Compatibility**: Works with both Docker and Docker Compose setups.
- **Secure and Reliable**: Ensures DNS requests are handled securely, with minimal overhead.
- **Supports Avahi Daemon**: Ensures Avahi mdns hosts are resolved correctly.

## Prerequisites

Before using NeoDNS, ensure you have the following:

- Docker >= 20.10.0
- Docker Compose (if using Compose)
- Basic knowledge of Docker and DNS management

## Installation

### 1. Clone the Repository

```bash
git clone https://github.com/Sanyam-malik/NeoDNS.git
cd NeoDNS
```

### 2. Docker Configuration
Make sure to configure your Docker container’s DNS settings to point to the NeoDNS service. You can either do this in your Docker container's configuration file or use Docker Compose.

Example Docker run command:

```bash
docker build -t neodns:latest
docker run -d \
  --name neodns \
  --restart always \
  -p 53:53/udp \
  -v ./config.yml:/app/config.yml \
  neodns:latest
```
Or in a Docker Compose file:

```yaml
version: '3.8'

services:
  neodns:
    build: .
    container_name: neodns
    ports:
      - "53:53/udp"
    volumes:
      - ./config.yml:/app/config.yml
    restart: always
    networks:
      - neodns_network

networks:
  neodns_network:
    driver: bridge
```

## Common Issues

### Avahi is Returning IPv6 address

Docker containers use IPv4 address by default if Avahi retutns Ipv6 address it will not be resolved
So, To force Avahi use Ipv4 run this:

```bash
sudo sed -i '/^use-ipv6=/c\use-ipv6=no' /etc/avahi/avahi-daemon.conf && sudo systemctl restart avahi-daemon
```


## Configuring Endpoints in config.yml

You can configure domain mappings and their associated subdomains by adding them to the config.yml file. This allows you to map special domains to local IPs and configure specific subdomains for each service.
```yaml
special_domains:
  "maxim.com":
    ip: "maxim.local"
    subdomains:
      "unleash": "unleash.local"
      "kafka": "kafka.local"
      "postgres": "postgresql.local"
      "mongodb": "mongodb.local"
      "forgejo": "forgejo.local"
      "jenkins": "jenkins.local"
      "minio": "minio.local"
      "redis": "redis.local"
      "sonar": "sonarqube.local"
      "keycloak": "keycloak.local"
      "netflix": "netflix.local"
      "prometheus": "prometheus.local"
      "jaeger": "jaeger.local"
      "omv": "omv.local"
```

```bash
ping -c 4 maxim.com
```
will resolve to ip address of maxim.local in same way if we
```bash
ping -c 4 postgres.maxim.com
```
it will be resolved to ip address of postgresql.local

Here maxim.local and postgresql.local are set to dhcp network mode instead of static network

By using this dns servvice we can also resolve netflix.com -> bing.com

