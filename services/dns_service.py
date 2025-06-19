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
                response = create_dns_entry([config_data["ip"]], query, domain)
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
                    response = create_dns_entry([config_data['subdomains'][subdomain]], query, domain, subdomain)
                    return response.to_wire()
            else:
                if "*" in config_data['subdomains']:
                    logging.info(f"Star(*) Pattern Match found for subdomain: {subdomain} under domain: {domain}")
                    if config_data['subdomains']['*'].endswith('.local'):
                        logging.info(f"Handling mDNS query for .local domain: {qname}")
                        response = resolve_mdns(config_data['subdomains']['*'], query, domain, subdomain)
                        return response.to_wire()
                    else:
                        response = create_dns_entry([config_data['subdomains']['*']], query, domain, subdomain)
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
    # Determine query types requested
    query_types = [q.rdtype for q in query.question]
    responses = []
    for qtype in query_types:
        record_type = dns.rdatatype.to_text(qtype)
        # Check For Cache
        if sqlite_database.check_if_resolution_valid(domain, subdomain, record_type):
            ips = sqlite_database.get_ips_from_db(domain, subdomain, record_type)
            if use_mdns:
                for ip in ips:
                    responses.append(create_mdns_entry(ip, query, domain, subdomain))
            else:
                responses.append(create_dns_entry(ips, query, domain, subdomain))
        elif use_mdns:
            # Check For MDns
            responses.append(resolve_mdns(qname, query, domain, subdomain))
        else:
            # External DNS Call
            resolver = dns.resolver.Resolver()
            resolvers = config.get("resolvers", [DEFAULT_DNS_RESOLVER])
            resolver.nameservers = resolvers
            try:
                answer = resolver.resolve(qname, record_type)
                ips = [rdata.address for rdata in answer]
                responses.append(create_dns_entry(ips, query, domain, subdomain))
                threading.Thread(target=sqlite_database.store_ips_in_db, args=(domain, subdomain, record_type, ips)).start()
            except Exception as e:
                logging.error(f"Error resolving {qname} for type {record_type}: {e}")
    # Combine all responses into one DNS message if possible
    if responses:
        # Use the first response as the base and add all answers
        base_response = dns.message.make_response(query)
        for resp in responses:
            for rrset in resp.answer:
                base_response.answer.append(rrset)
        return base_response
    else:
        response = dns.message.make_response(query)
        response.set_rcode(dns.rcode.SERVFAIL)
        return response
