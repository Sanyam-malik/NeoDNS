import platform
import socket
import subprocess
import threading

import dns.resolver
import dns.message
import dns.query
import dns.rrset
import dns.name
import dns.rdatatype
import dns.rdata
import dns.rdtypes.IN.A
import dns.rdtypes.IN.AAAA
import yaml
import logging

import sqlite_database

# Set up logging configuration
logging.basicConfig(level=logging.DEBUG, format='%(asctime)s - %(levelname)s - %(message)s')
DNS_RESOLVER = '8.8.8.8'

# Load special domain configurations from a YAML file
def load_config(config_file="config.yml"):
    logging.debug(f"Loading configuration from {config_file}")
    try:
        with open(config_file, 'r') as file:
            config = yaml.safe_load(file)
            logging.info("Configuration loaded successfully.")
            return config
    except Exception as e:
        logging.error(f"Failed to load configuration: {e}")
        raise

def is_valid_ip(ip):
    """Check if the input is a valid IP address (IPv4 or IPv6)."""
    try:
        socket.inet_pton(socket.AF_INET, ip)  # IPv4
        return "IPv4"
    except socket.error:
        try:
            socket.inet_pton(socket.AF_INET6, ip)  # IPv6
            return "IPv6"
        except socket.error:
            return None

def get_ip_or_domain(input_str):
    """Resolve domain name to its IP address using dnspython."""
    if is_valid_ip(input_str):
        return input_str  # If it's already an IP address, return it.
    else:
        try:
            # Resolve domain name to its IP address using dnspython
            answer = dns.resolver.resolve(input_str, 'A')  # 'A' record for IPv4
            return answer[0].to_text()  # Return the first resolved IP
        except (dns.resolver.NXDOMAIN, dns.resolver.NoAnswer, dns.exception.DNSException) as e:
            return input_str

# Create a DNS answer record for A (IPv4) or AAAA (IPv6) records
def create_dns_record(domain, ttl, ip):
    """Create DNS records (A for IPv4, AAAA for IPv6) for a domain with a specified TTL and IP."""
    ip_type = is_valid_ip(ip)

    if ip_type == "IPv4":
        logging.debug(f"Creating A record for domain: {domain} with IP: {ip} and TTL: {ttl}")
        name = dns.name.from_text(domain)
        rdata = dns.rdtypes.IN.A.A(dns.rdataclass.IN, dns.rdatatype.A, ip)
        rrset = dns.rrset.RRset(name, dns.rdataclass.IN, dns.rdatatype.A)
        rrset.add(rdata)
    elif ip_type == "IPv6":
        logging.debug(f"Creating AAAA record for domain: {domain} with IP: {ip} and TTL: {ttl}")
        name = dns.name.from_text(domain)
        rdata = dns.rdtypes.IN.AAAA.AAAA(dns.rdataclass.IN, dns.rdatatype.AAAA, ip)
        rrset = dns.rrset.RRset(name, dns.rdataclass.IN, dns.rdatatype.AAAA)
        rrset.add(rdata)
    else:
        raise ValueError("Invalid IP address format")

    rrset.ttl = ttl
    return rrset

# Handle DNS queries, checking the domain and subdomains against the config
def handle_dns_query(data, client_address, config):
    """Handle incoming DNS query and resolve based on config."""
    logging.debug(f"Handling DNS query from {client_address}")
    query = dns.message.from_wire(data)
    qname = query.question[0].name.to_text().strip('.')
    logging.debug(f"Query for: {qname}")

    # Search for the domain or subdomain in the config
    for domain, config_data in config['special_domains'].items():
        logging.debug(f"Checking domain: {domain} against config")
        if qname == domain:
            logging.info(f"Exact match for domain: {domain}")
            if config_data["ip"].endswith('.local'):
                logging.info(f"Handling mDNS query for .local domain: {qname}")
                response = resolve_mdns(config_data["ip"], query, domain)
                return response.to_wire()
            else:
                response = create_dns_entry(config_data["ip"], query, domain)
                return response.to_wire()

        # Handle subdomains
        if qname.endswith('.' + domain):
            subdomain = qname[:len(qname) - len(domain) - 1]  # Extract subdomain part
            if subdomain in config_data['subdomains']:
                logging.info(f"Match found for subdomain: {subdomain} under domain: {domain}")
                if config_data['subdomains'][subdomain].endswith('.local'):
                    logging.info(f"Handling mDNS query for .local domain: {qname}")
                    response = resolve_mdns(config_data['subdomains'][subdomain], query, domain, subdomain)
                    return response.to_wire()
                else:
                    response = create_dns_entry(config_data['subdomains'][subdomain], query, domain, subdomain)
                    return response.to_wire()

    # If no special config found, forward the query to Google's DNS
    try:
        logging.debug(f"No match found, forwarding query to Google's DNS")
        response = resolve_dns_entry(qname, query)
    except Exception as e:
        logging.error(f"Error querying Google's DNS: {e}")
        response = dns.message.make_response(query)
        response.set_rcode(dns.rcode.SERVFAIL)

    return response.to_wire()

def resolve_mdns(ip_host, query, domain, subdomain=None):
    """Resolve mDNS queries for .local domains using Avahi."""
    try:
        # Run Avahi-resolve command to resolve .local domain
        result = subprocess.run(['avahi-resolve', '--name', ip_host], capture_output=True, text=True)

        if result.returncode == 0:
            # Parse the result
            ip = result.stdout.strip().split('\t')[1]  # Get the IP address from the output
            ip_type = is_valid_ip(ip)

            if ip_type == "IPv4":
                logging.info(f"Resolved mDNS for {ip_host} to IPv4 address {ip}")
            elif ip_type == "IPv6":
                logging.info(f"Resolved mDNS for {ip_host} to IPv6 address {ip}")
            else:
                logging.error(f"Resolved mDNS for {ip_host} to an invalid IP: {ip}")
                return dns.message.make_response(query).set_rcode(dns.rcode.SERVFAIL)

            return create_dns_entry(ip, query, domain, subdomain)
        else:
            logging.error(f"Failed to resolve mDNS for {ip_host}")
            return dns.message.make_response(query).set_rcode(dns.rcode.SERVFAIL)
    except Exception as e:
        logging.error(f"Error resolving mDNS for {ip_host}: {e}")
        return dns.message.make_response(query).set_rcode(dns.rcode.SERVFAIL)

def resolve_dns_entry(qname, query):
    subdomain, domain = separate_domain_and_subdomain(qname)
    if sqlite_database.check_if_resolution_valid(domain, subdomain):
        ip = sqlite_database.get_ip_from_db(domain, subdomain)
        response = create_dns_entry(ip, query, domain, subdomain)
    else:
        ip = get_ip_or_domain(qname)
        response = dns.query.udp(query, DNS_RESOLVER)
    threading.Thread(target=sqlite_database.store_ip_in_db, args=(domain, subdomain, ip)).start()
    return response

def separate_domain_and_subdomain(qname):
    parts = qname.split('.')
    if len(parts) > 2:
        subdomain = '.'.join(parts[:-2])
        domain = '.'.join(parts[-2:])
    else:
        subdomain = None
        domain = qname
    return subdomain, domain

def create_dns_entry(ip, query, domain, subdomain=None):
    if sqlite_database.check_if_resolution_valid(domain, subdomain):
        old_ip = sqlite_database.get_ip_from_db(domain, subdomain)
        if str(old_ip) != str(ip):
            ip = get_ip_or_domain(ip)
        else:
            ip = old_ip
    else:
        ip = get_ip_or_domain(ip)

    if subdomain:
        full_domain = f"{subdomain}.{domain}"
    else:
        full_domain = domain

    response = dns.message.make_response(query)
    answer = create_dns_record(full_domain, 3600, ip)
    response.answer.append(answer)
    threading.Thread(target=sqlite_database.store_ip_in_db, args=(domain, subdomain, ip)).start()
    return response

def start_dns_server(host='0.0.0.0', port=1053, config_file="config.yml"):
    """Start a DNS server that loads domain configs from a YAML file."""
    sqlite_database.create_db()
    logging.debug(f"Starting DNS server on {host}:{port}")
    try:
        config = load_config(config_file)
        sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        sock.bind((host, port))
        logging.info(f"DNS server running on {host}:{port}...")

        while True:
            data, client_address = sock.recvfrom(512)  # DNS packet size max is 512 bytes
            logging.info(f"Received query from {client_address}")
            response = handle_dns_query(data, client_address, config)
            sock.sendto(response, client_address)

    except Exception as e:
        logging.error(f"Error starting DNS server: {e}")
        raise

if __name__ == '__main__':
    start_dns_server()
