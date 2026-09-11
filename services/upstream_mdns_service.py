import logging
import subprocess
import threading

import dns

import database
from services.utility_service import is_valid_ip, create_dns_record

logging.basicConfig(level=logging.DEBUG, format='%(asctime)s - %(levelname)s - %(message)s')


def resolve_mdns(ip_host, query, domain, subdomain=None):
    try:
        result = subprocess.run(['avahi-resolve', '--name', ip_host], capture_output=True, text=True)

        if result.returncode == 0:
            ip = result.stdout.strip().split('\t')[1]
            ip_type = is_valid_ip(ip)

            if ip_type:
                return create_mdns_entry(ip, query, domain, subdomain)
            else:
                logging.error(f"Invalid IP resolved from mDNS: {ip}")
        else:
            logging.error(f"Failed to resolve mDNS for {ip_host}")
    except Exception as e:
        logging.error(f"Exception during mDNS resolution for {ip_host}: {e}")

    response = dns.message.make_response(query)
    response.set_rcode(dns.rcode.SERVFAIL)
    return response


def create_mdns_entry(ip, query, domain, subdomain=None):
    if database.cache_check_valid(domain, subdomain, "A"):
        old_ips = database.cache_get_ips(domain, subdomain, "A")
        if str(ip) in [str(old_ip) for old_ip in old_ips]:
            ip = str(ip)

    full_domain = f"{subdomain}.{domain}" if subdomain else domain

    response = dns.message.make_response(query)
    answer = create_dns_record(full_domain, 3600, ip)
    response.answer.append(answer)
    threading.Thread(target=database.cache_store_ips, args=(domain, subdomain, "A", [ip])).start()
    return response