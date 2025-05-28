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
from services.upstream_dns_service import create_dns_entry
from services.upstream_mdns_service import resolve_mdns, create_mdns_entry
from services.utility_service import separate_domain_and_subdomain, get_ip_or_domain

# Logging setup
logging.basicConfig(level=logging.DEBUG, format='%(asctime)s - %(levelname)s - %(message)s')
DEFAULT_DNS_RESOLVER = '8.8.8.8'

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

def resolve_dns_entry(qname, query, config):
    subdomain, domain = separate_domain_and_subdomain(qname)
    use_mdns = qname.endswith('.local')
    # Check For Cache
    if sqlite_database.check_if_resolution_valid(domain, subdomain):
        ip = sqlite_database.get_ip_from_db(domain, subdomain)
        if use_mdns:
            response = create_mdns_entry(ip, query, domain, subdomain)
        else:
            response = create_dns_entry(ip, query, domain, subdomain)
    elif use_mdns:
        # Check For MDns
        response = resolve_mdns(qname, query, domain, subdomain)
    else:
        # External DNS Call
        ip = get_ip_or_domain(qname)
        resolvers = config.get("resolvers", [DEFAULT_DNS_RESOLVER])
        resolver_ip = random.choice(resolvers) if resolvers else DEFAULT_DNS_RESOLVER
        response = dns.query.udp(query, resolver_ip)
        threading.Thread(target=sqlite_database.store_ip_in_db, args=(domain, subdomain, ip)).start()
    return response
