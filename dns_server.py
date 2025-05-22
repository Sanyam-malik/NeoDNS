import os
import socket
import threading
import logging
import json

import dns
from flask import Flask, jsonify, request, render_template
from waitress import serve
from dotenv import load_dotenv

import config_service
import dns_service
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

# Shared config and reload event
config_lock = threading.Lock()
shared_config = {}
reload_event = threading.Event()

def load_and_set_config(config_file):
    global shared_config
    with open(config_file, 'r') as f:
        config = json.load(f)
    with config_lock:
        shared_config = config

def start_dns_server(host='0.0.0.0', port=DNS_PORT, config_file=CONFIG_FILE):
    sqlite_database.create_db()
    logging.debug(f"Starting DNS server on {host}:{port}")
    try:
        load_and_set_config(config_file)
        sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        sock.bind((host, port))
        logging.info(f"DNS server running on {host}:{port}...")

        while True:
            if reload_event.is_set():
                logging.info("Reloading DNS config...")
                load_and_set_config(config_file)
                reload_event.clear()

            sock.settimeout(1.0)
            try:
                data, client_address = sock.recvfrom(512)
            except socket.timeout:
                continue

            logging.info(f"Received query from {client_address}")
            with config_lock:
                response = dns_service.handle_dns_query(data, client_address, shared_config)
            sock.sendto(response, client_address)

    except Exception as e:
        logging.error(f"Error starting DNS server: {e}")
        raise

@app.route('/')
def ui():
    return render_template("index.html")

@app.route('/api/config', methods=['GET'])
def get_config():
    config = config_service.load_config(CONFIG_FILE)
    if not config.get("resolvers"):
        config["resolvers"] = ["8.8.8.8"]
        config_service.save_config(config, CONFIG_FILE)
    return jsonify(config)

@app.route('/api/config', methods=['POST'])
def update_config():
    new_config = request.get_json()
    config_service.save_config(new_config, CONFIG_FILE)
    reload_event.set()
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
        reload_event.set()

    return jsonify({"message": f"Resolver {ip} added."}), 200

@app.route('/api/resolver', methods=['DELETE'])
def delete_resolver():
    data = request.get_json()
    ip = data.get("ip")
    config = config_service.load_config(CONFIG_FILE)
    if "resolvers" in config and ip in config["resolvers"]:
        config["resolvers"].remove(ip)
        config_service.save_config(config, CONFIG_FILE)
        reload_event.set()
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
    reload_event.set()
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
        reload_event.set()
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
    reload_event.set()
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
    reload_event.set()
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

if __name__ == '__main__':
    dns_thread = threading.Thread(target=start_dns_server, daemon=True)
    dns_thread.start()
    start_api_server()
