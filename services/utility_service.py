import logging
import socket

import dns

logging.basicConfig(level=logging.DEBUG, format='%(asctime)s - %(levelname)s - %(message)s')
def separate_domain_and_subdomain(qname):
    parts = qname.split('.')
    if len(parts) > 2:
        subdomain = '.'.join(parts[:-2])
        domain = '.'.join(parts[-2:])
    else:
        subdomain = None
        domain = qname
    return subdomain, domain

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