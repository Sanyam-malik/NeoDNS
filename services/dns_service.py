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
import database
from services.upstream_dns_service import create_dns_entry
from services.upstream_mdns_service import resolve_mdns, create_mdns_entry
from services.utility_service import separate_domain_and_subdomain, get_ip_or_domain
import subprocess

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
            # Serve from cache if valid
            if database.cache_check_valid(domain, None, "A"):
                ips = database.cache_get_ips(domain, None, "A")
                logging.info(f"Serving cached DNS data for domain='{domain}', subdomain=None, type='A': {ips}")
                response = create_dns_entry(ips, query, domain)
                return response.to_wire()
            ip_value = config_data["ip"]
            ips = []
            mdns_hosts = []
            if isinstance(ip_value, list):
                for ip in ip_value:
                    if str(ip).endswith('.local'):
                        mdns_hosts.append(ip)
                    else:
                        ips.append(ip)
            else:
                if str(ip_value).endswith('.local'):
                    mdns_hosts.append(ip_value)
                else:
                    ips.append(ip_value)
            # Resolve all mDNS hosts
            for mdns_host in mdns_hosts:
                try:
                    result = subprocess.run(['avahi-resolve', '--name', mdns_host], capture_output=True, text=True)
                    if result.returncode == 0:
                        resolved_ip = result.stdout.strip().split('\t')[1]
                        ips.append(resolved_ip)
                    else:
                        logging.error(f"Failed to resolve mDNS for {mdns_host}")
                except Exception as e:
                    logging.error(f"Exception during mDNS resolution for {mdns_host}: {e}")
            if ips:
                response = create_dns_entry(ips, query, domain)
                logging.info(f"Caching DNS data for domain='{domain}', subdomain=None, type='A': {ips}")
                threading.Thread(target=database.cache_store_ips, args=(domain, None, "A", ips)).start()
                return response.to_wire()
            else:
                response = dns.message.make_response(query)
                response.set_rcode(dns.rcode.SERVFAIL)
                return response.to_wire()

        if qname.endswith('.' + domain):
            subdomain = qname[:len(qname) - len(domain) - 1]
            if subdomain in config_data['subdomains']:
                logging.info(f"Match found for subdomain: {subdomain} under domain: {domain}")
                # Serve from cache if valid
                if database.cache_check_valid(domain, subdomain, "A"):
                    ips = database.cache_get_ips(domain, subdomain, "A")
                    logging.info(f"Serving cached DNS data for domain='{domain}', subdomain='{subdomain}', type='A': {ips}")
                    response = create_dns_entry(ips, query, domain, subdomain)
                    return response.to_wire()
                sub_value = config_data['subdomains'][subdomain]
                ips = []
                mdns_hosts = []
                if isinstance(sub_value, list):
                    for ip in sub_value:
                        if str(ip).endswith('.local'):
                            mdns_hosts.append(ip)
                        else:
                            ips.append(ip)
                else:
                    if str(sub_value).endswith('.local'):
                        mdns_hosts.append(sub_value)
                    else:
                        ips.append(sub_value)
                for mdns_host in mdns_hosts:
                    try:
                        result = subprocess.run(['avahi-resolve', '--name', mdns_host], capture_output=True, text=True)
                        if result.returncode == 0:
                            resolved_ip = result.stdout.strip().split('\t')[1]
                            ips.append(resolved_ip)
                        else:
                            logging.error(f"Failed to resolve mDNS for {mdns_host}")
                    except Exception as e:
                        logging.error(f"Exception during mDNS resolution for {mdns_host}: {e}")
                if ips:
                    response = create_dns_entry(ips, query, domain, subdomain)
                    logging.info(f"Caching DNS data for domain='{domain}', subdomain='{subdomain}', type='A': {ips}")
                    threading.Thread(target=database.cache_store_ips, args=(domain, subdomain, "A", ips)).start()
                    return response.to_wire()
                else:
                    response = dns.message.make_response(query)
                    response.set_rcode(dns.rcode.SERVFAIL)
                    return response.to_wire()
            else:
                if "*" in config_data['subdomains']:
                    logging.info(f"Star(*) Pattern Match found for subdomain: {subdomain} under domain: {domain}")
                    # Serve from cache if valid
                    if database.cache_check_valid(domain, subdomain, "A"):
                        ips = database.cache_get_ips(domain, subdomain, "A")
                        logging.info(f"Serving cached DNS data for domain='{domain}', subdomain='{subdomain}', type='A': {ips}")
                        response = create_dns_entry(ips, query, domain, subdomain)
                        return response.to_wire()
                    star_value = config_data['subdomains']['*']
                    ips = []
                    mdns_hosts = []
                    if isinstance(star_value, list):
                        for ip in star_value:
                            if str(ip).endswith('.local'):
                                mdns_hosts.append(ip)
                            else:
                                ips.append(ip)
                    else:
                        if str(star_value).endswith('.local'):
                            mdns_hosts.append(star_value)
                        else:
                            ips.append(star_value)
                    for mdns_host in mdns_hosts:
                        try:
                            result = subprocess.run(['avahi-resolve', '--name', mdns_host], capture_output=True, text=True)
                            if result.returncode == 0:
                                resolved_ip = result.stdout.strip().split('\t')[1]
                                ips.append(resolved_ip)
                            else:
                                logging.error(f"Failed to resolve mDNS for {mdns_host}")
                        except Exception as e:
                            logging.error(f"Exception during mDNS resolution for {mdns_host}: {e}")
                    if ips:
                        response = create_dns_entry(ips, query, domain, subdomain)
                        logging.info(f"Caching DNS data for domain='{domain}', subdomain='{subdomain}', type='A': {ips}")
                        threading.Thread(target=database.cache_store_ips, args=(domain, subdomain, "A", ips)).start()
                        return response.to_wire()
                    else:
                        response = dns.message.make_response(query)
                        response.set_rcode(dns.rcode.SERVFAIL)
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
        if database.cache_check_valid(domain, subdomain, record_type):
            ips = database.cache_get_ips(domain, subdomain, record_type)
            logging.info(f"Serving cached DNS data for domain='{domain}', subdomain='{subdomain}', type='{record_type}': {ips}")
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
                # For A/AAAA keep using IP addresses for existing flow
                if record_type in ("A", "AAAA"):
                    ips = [getattr(rdata, 'address', rdata.to_text()) for rdata in answer]
                    responses.append(create_dns_entry(ips, query, domain, subdomain))
                    logging.info(f"Caching resolver DNS data for domain='{domain}', subdomain='{subdomain}', type='{record_type}': {ips}")
                    threading.Thread(target=database.cache_store_ips, args=(domain, subdomain, record_type, ips)).start()
                else:
                    # Generic types: build response from rrset and cache textual rdata
                    rrset = answer.rrset
                    resp = dns.message.make_response(query)
                    resp.answer.append(rrset)
                    responses.append(resp)
                    values = [rdata.to_text() for rdata in answer]
                    logging.info(f"Caching resolver DNS data for domain='{domain}', subdomain='{subdomain}', type='{record_type}': {values}")
                    threading.Thread(target=database.cache_store_ips, args=(domain, subdomain, record_type, values)).start()
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
