import logging
import threading

import dns

# import sqlite_database  # No longer needed
from services.utility_service import get_ip_or_domain, create_dns_record

logging.basicConfig(level=logging.DEBUG, format='%(asctime)s - %(levelname)s - %(message)s')

def create_dns_entry(ips, query, domain, subdomain=None):
    full_domain = f"{subdomain}.{domain}" if subdomain else domain
    response = dns.message.make_response(query)
    if not isinstance(ips, list):
        ips = [ips]
    for ip in ips:
        answer = create_dns_record(full_domain, 3600, ip)
        response.answer.append(answer)
    return response

