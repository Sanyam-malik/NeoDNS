import logging
import os
import socket
import threading

from dotenv import load_dotenv

import config_service
from services import dns_service

# Load environment variables from .env file
load_dotenv()

DNS_PORT = int(os.getenv("DNS_PORT", 1053))
DNS_HOST = "0.0.0.0"
CONFIG_FILE = "config.json"

# Set up logging
logging.basicConfig(level=logging.DEBUG, format='%(asctime)s - %(levelname)s - %(message)s')

# Globals for thread control
dns_server_thread = None
dns_server_stop_event = threading.Event()

def read_config(config_file):
    return config_service.load_config(config_file)

def start_dns_server(stop_event):
    logging.info(f"Starting DNS server on {DNS_HOST}:{DNS_PORT}")
    sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)

    try:
        sock.bind((DNS_HOST, DNS_PORT))
        sock.settimeout(3.0)

        while not stop_event.is_set():
            try:
                data, addr = sock.recvfrom(512)
                logging.info(f"Received DNS query from {addr}")
                response = dns_service.handle_dns_query(data, addr, read_config(CONFIG_FILE))
                sock.sendto(response, addr)
            except socket.timeout:
                continue
            except Exception as e:
                logging.error(f"Error processing DNS query: {e}")

    except OSError as e:
        logging.error(f"Could not bind socket: {e}")
    finally:
        sock.close()
        logging.info("DNS server stopped")

def start_dns_server_thread():
    global dns_server_thread, dns_server_stop_event

    if dns_server_thread and dns_server_thread.is_alive():
        logging.warning("DNS server thread is already running.")
        return False

    dns_server_stop_event.clear()
    dns_server_thread = threading.Thread(target=start_dns_server, args=(dns_server_stop_event,), daemon=True)
    dns_server_thread.start()
    return True

def stop_dns_server_thread():
    global dns_server_thread, dns_server_stop_event

    if not dns_server_thread or not dns_server_thread.is_alive():
        logging.warning("DNS server thread is not running.")
        return False

    dns_server_stop_event.set()
    dns_server_thread.join()
    dns_server_thread = None
    return True

def reload_dns_server_thread():
    logging.info("Reloading DNS server thread.")
    stopped = stop_dns_server_thread()
    started = start_dns_server_thread()
    return stopped and started