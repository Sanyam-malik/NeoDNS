import platform
import random
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
import logging
import sqlite_database

# Logging setup
logging.basicConfig(level=logging.DEBUG, format='%(asctime)s - %(levelname)s - %(message)s')
DEFAULT_DNS_RESOLVER = '8.8.8.8'

def is_valid_ip(ip):
    try:
        socket.inet_pton(socket.AF_INET, ip)
        return "IPv4"
    except socket.error:
        try:
            socket.inet_pton(socket.AF_INET6, ip)
            return "IPv6"
        except socket.error:
            return None

def get_ip_or_domain(input_str):
    if is_valid_ip(input_str):
        return input_str
    try:
        answer = dns.resolver.resolve(input_str, 'A')
        return answer[0].to_text()
    except (dns.resolver.NXDOMAIN, dns.resolver.NoAnswer, dns.exception.DNSException) as e:
        return input_str

def create_dns_record(domain, ttl, ip):
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

def handle_dns_query(data, client_address, config):
    logging.debug(f"Handling DNS query from {client_address}")
    query = dns.message.from_wire(data)
    qname = query.question[0].name.to_text().strip('.')
    logging.debug(f"Query for: {qname}")

    for domain, config_data in config['domains'].items():
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

        if qname.endswith('.' + domain):
            subdomain = qname[:len(qname) - len(domain) - 1]
            if subdomain in config_data['subdomains']:
                logging.info(f"Match found for subdomain: {subdomain} under domain: {domain}")
                if config_data['subdomains'][subdomain].endswith('.local'):
                    logging.info(f"Handling mDNS query for .local domain: {qname}")
                    response = resolve_mdns(config_data['subdomains'][subdomain], query, domain, subdomain)
                    return response.to_wire()
                else:
                    response = create_dns_entry(config_data['subdomains'][subdomain], query, domain, subdomain)
                    return response.to_wire()
            else:
                if "*" in config_data['subdomains']:
                    logging.info(f"Star(*) Pattern Match found for subdomain: {subdomain} under domain: {domain}")
                    if config_data['subdomains']['*'].endswith('.local'):
                        logging.info(f"Handling mDNS query for .local domain: {qname}")
                        response = resolve_mdns(config_data['subdomains']['*'], query, domain, subdomain)
                        return response.to_wire()
                    else:
                        response = create_dns_entry(config_data['subdomains']['*'], query, domain, subdomain)
                        return response.to_wire()

    try:
        logging.debug(f"No match found, forwarding query to DNS resolver")
        response = resolve_dns_entry(qname, query, config)
    except Exception as e:
        logging.error(f"Error querying fallback resolver: {e}")
        response = dns.message.make_response(query)
        response.set_rcode(dns.rcode.SERVFAIL)

    return response.to_wire()

def resolve_mdns(ip_host, query, domain, subdomain=None):
    try:
        result = subprocess.run(['avahi-resolve', '--name', ip_host], capture_output=True, text=True)

        if result.returncode == 0:
            ip = result.stdout.strip().split('\t')[1]
            ip_type = is_valid_ip(ip)

            if ip_type:
                return create_dns_entry(ip, query, domain, subdomain)
            else:
                logging.error(f"Invalid IP resolved from mDNS: {ip}")
        else:
            logging.error(f"Failed to resolve mDNS for {ip_host}")
    except Exception as e:
        logging.error(f"Exception during mDNS resolution for {ip_host}: {e}")

    response = dns.message.make_response(query)
    response.set_rcode(dns.rcode.SERVFAIL)
    return response

def resolve_dns_entry(qname, query, config):
    subdomain, domain = separate_domain_and_subdomain(qname)
    if sqlite_database.check_if_resolution_valid(domain, subdomain):
        ip = sqlite_database.get_ip_from_db(domain, subdomain)
        response = create_dns_entry(ip, query, domain, subdomain)
    elif qname.endswith('.local'):
        response = resolve_mdns(qname, query, domain, subdomain)
    else:
        ip = get_ip_or_domain(qname)
        resolvers = config.get("resolvers", [DEFAULT_DNS_RESOLVER])
        resolver_ip = random.choice(resolvers) if resolvers else DEFAULT_DNS_RESOLVER
        response = dns.query.udp(query, resolver_ip)
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

    full_domain = f"{subdomain}.{domain}" if subdomain else domain

    response = dns.message.make_response(query)
    answer = create_dns_record(full_domain, 3600, ip)
    response.answer.append(answer)
    threading.Thread(target=sqlite_database.store_ip_in_db, args=(domain, subdomain, ip)).start()
    return response
