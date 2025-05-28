import logging
import threading

import dns

import sqlite_database
from services.utility_service import get_ip_or_domain, create_dns_record

logging.basicConfig(level=logging.DEBUG, format='%(asctime)s - %(levelname)s - %(message)s')

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

