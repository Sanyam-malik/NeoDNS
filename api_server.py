import atexit
import os
import logging
import signal
import sys

import dns
from flask import Flask, jsonify, request, render_template
from waitress import serve
from dotenv import load_dotenv

import config_service
import dns_server
import sqlite_database

# Load environment variables from .env file
load_dotenv()

# Get ports from environment variables with defaults
DNS_PORT = int(os.getenv("DNS_PORT", 1053))
API_PORT = int(os.getenv("API_PORT", 8000))

# Set up logging
logging.basicConfig(level=logging.DEBUG, format='%(asctime)s - %(levelname)s - %(message)s')

app = Flask(__name__)
CONFIG_FILE = "config.json"

@app.route('/')
def ui():
    return render_template("index.html")

@app.route('/api/config', methods=['GET'])
def get_config():
    config = config_service.load_config(CONFIG_FILE)
    if not config.get("resolvers"):
        config["resolvers"] = ["8.8.8.8"]
        config_service.save_config(config, CONFIG_FILE)
        reload_dns()
    return jsonify(config)

@app.route('/api/config', methods=['POST'])
def update_config():
    new_config = request.get_json()
    config_service.save_config(new_config, CONFIG_FILE)
    reload_dns()
    return jsonify({"message": "Config updated"}), 200

@app.route('/api/resolver', methods=['POST'])
def add_resolver():
    data = request.get_json()
    ip = data.get("ip")
    config = config_service.load_config(CONFIG_FILE)

    if "resolvers" not in config:
        config["resolvers"] = []

    if not config["resolvers"]:
        config["resolvers"].append("8.8.8.8")

    if ip not in config["resolvers"]:
        config["resolvers"].append(ip)
        config_service.save_config(config, CONFIG_FILE)
        reload_dns()

    return jsonify({"message": f"Resolver {ip} added."}), 200

@app.route('/api/resolver', methods=['DELETE'])
def delete_resolver():
    data = request.get_json()
    ip = data.get("ip")
    config = config_service.load_config(CONFIG_FILE)
    if "resolvers" in config and ip in config["resolvers"]:
        config["resolvers"].remove(ip)
        config_service.save_config(config, CONFIG_FILE)
        reload_dns()
        return jsonify({"message": "Resolver removed"}), 200
    return jsonify({"error": "Resolver not found"}), 404

@app.route('/api/domain', methods=['POST'])
def add_or_update_domain():
    data = request.get_json()
    domain = data.get("domain")
    ip = data.get("ip")
    subdomains = data.get("subdomains", {})

    config = config_service.load_config(CONFIG_FILE)

    if "domains" not in config:
        config["domains"] = {}

    config["domains"][domain] = {"ip": ip, "subdomains": subdomains}
    config_service.save_config(config, CONFIG_FILE)
    reload_dns()
    return jsonify({"message": f"Domain {domain} added/updated."}), 200

@app.route('/api/domain', methods=['DELETE'])
def delete_domain():
    data = request.get_json()
    domain = data.get("domain")
    config = config_service.load_config(CONFIG_FILE)

    if "domains" not in config:
        config["domains"] = {}

    if domain in config["domains"]:
        del config["domains"][domain]
        config_service.save_config(config, CONFIG_FILE)
        reload_dns()
        return jsonify({"message": f"Domain {domain} removed."}), 200

    return jsonify({"error": "Domain not found"}), 404

@app.route('/api/subdomain', methods=['POST'])
def add_or_update_subdomain():
    data = request.get_json()
    domain = data.get("domain")
    subdomain = data.get("subdomain")
    ip = data.get("ip")
    config = config_service.load_config(CONFIG_FILE)

    if "domains" not in config:
        config["domains"] = {}

    if domain not in config["domains"]:
        return jsonify({"error": f"Domain {domain} not found"}), 404

    if "subdomains" not in config["domains"][domain]:
        config["domains"][domain]["subdomains"] = {}

    config["domains"][domain]["subdomains"][subdomain] = ip
    config_service.save_config(config, CONFIG_FILE)
    reload_dns()
    return jsonify({"message": f"Subdomain {subdomain} added/updated under domain {domain}."}), 200

@app.route('/api/subdomain', methods=['DELETE'])
def delete_subdomain():
    data = request.get_json()
    domain = data.get("domain")
    subdomain = data.get("subdomain")
    config = config_service.load_config(CONFIG_FILE)

    if "domains" not in config:
        config["domains"] = {}

    if domain not in config["domains"]:
        return jsonify({"error": f"Domain {domain} not found"}), 404

    if subdomain not in config["domains"][domain].get("subdomains", {}):
        return jsonify({"error": f"Subdomain {subdomain} not found in domain {domain}."}), 404

    del config["domains"][domain]["subdomains"][subdomain]
    config_service.save_config(config, CONFIG_FILE)
    reload_dns()
    return jsonify({"message": f"Subdomain {subdomain} removed from domain {domain}."}), 200

@app.route('/api/dig', methods=['POST'])
def perform_dig():
    data = request.get_json()
    domain = data.get("domain")

    if not domain:
        return jsonify({"error": "No domain provided"}), 400

    try:
        query = dns.message.make_query(domain, dns.rdatatype.A)
        response = dns.query.udp(query, "127.0.0.1", port=DNS_PORT, timeout=3)

        result_lines = []
        for answer in response.answer:
            for item in answer.items:
                result_lines.append(f"{domain} A {item.address}")

        return jsonify({"output": "\n".join(result_lines) or "No A records found."}), 200

    except Exception as e:
        logging.error(f"UDP DNS query failed: {e}")
        return jsonify({"error": str(e)}), 500

def start_api_server(host='0.0.0.0', port=API_PORT):
    logging.info(f"API server running on http://{host}:{port}")
    serve(app, host=host, port=port)

def reload_dns():
    if dns_server.reload_dns_server_thread():
        sqlite_database.delete_db()
        logging.debug("DNS Server Status: Restarted")

# Graceful shutdown
def shutdown_handler(*args):
    logging.debug("Shutting down Flask and DNS server...")
    if sqlite_database.delete_db():
        logging.debug("Cleared DNS Cache....")
    dns_server.stop_dns_server_thread()
    sys.exit(0)

# Handle exit signals
signal.signal(signal.SIGINT, shutdown_handler)
signal.signal(signal.SIGTERM, shutdown_handler)
atexit.register(dns_server.stop_dns_server_thread)

if __name__ == '__main__':
    if dns_server.start_dns_server_thread():
        logging.debug("DNS Server Status: Started")
    start_api_server()
