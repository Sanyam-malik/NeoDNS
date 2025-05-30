import logging
import os
import sqlite3
import time

from dotenv import load_dotenv

# Load environment variables from .env file
load_dotenv()

logging.basicConfig(level=logging.DEBUG, format='%(asctime)s - %(levelname)s - %(message)s')
DNS_CACHE = bool(True if os.getenv("CACHE", "false").lower() == "true" else False)
# SQLite database name
DB_NAME = 'dns_resolutions.db'

def exists_db():
    return True if os.path.exists(DB_NAME) else False

def create_db():
    """Create or recreate the SQLite database and table."""
    if DNS_CACHE:
        logging.debug("DNS Caching is enabled...(create_db)")
    else:
        logging.debug("DNS Caching is disabled...(create_db)")
        return

    logging.debug(f"Creating/recreating database: {DB_NAME}")
    if os.path.exists(DB_NAME):
        os.remove(DB_NAME)  # Remove the existing DB if it exists

    conn = sqlite3.connect(DB_NAME)
    cursor = conn.cursor()
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS domain_resolutions (
            domain TEXT NOT NULL,
            subdomain TEXT,
            ip TEXT NOT NULL,
            timestamp INTEGER NOT NULL,
            PRIMARY KEY (domain, subdomain)
        )
    ''')
    conn.commit()
    conn.close()
    logging.info(f"Database {DB_NAME} created/recreated successfully.")


def get_ip_from_db(domain, subdomain=None):
    """Retrieve IP from the SQLite database."""
    if DNS_CACHE:
        logging.debug("DNS Caching is enabled...(get_ip_from_db)")
    else:
        logging.debug("DNS Caching is disabled...(get_ip_from_db)")
        return None

    if exists_db() is False:
        create_db()

    conn = sqlite3.connect(DB_NAME)
    cursor = conn.cursor()
    if subdomain:
        cursor.execute("SELECT ip FROM domain_resolutions WHERE domain = ? AND subdomain = ?",
                       (domain, subdomain))
    else:
        cursor.execute("SELECT ip FROM domain_resolutions WHERE domain = ? AND subdomain IS NULL", (domain,))
    result = cursor.fetchone()
    conn.close()
    if result:
        return result[0]
    return None


def store_ip_in_db(domain, subdomain, ip):
    """Store the IP resolution in the SQLite database with the current timestamp."""
    if DNS_CACHE:
        logging.debug("DNS Caching is enabled...(store_ip_in_db)")
    else:
        logging.debug("DNS Caching is disabled...(store_ip_in_db)")
        return

    if exists_db() is False:
        create_db()

    timestamp = int(time.time())  # Get current time in seconds since the epoch
    conn = sqlite3.connect(DB_NAME)
    cursor = conn.cursor()

    # Delete any existing entry with the same domain and subdomain (if subdomain exists)
    if subdomain:
        cursor.execute(
            "DELETE FROM domain_resolutions WHERE domain = ? AND subdomain = ?",
            (domain, subdomain)
        )
    else:
        cursor.execute(
            "DELETE FROM domain_resolutions WHERE domain = ? AND subdomain IS NULL",
            (domain,)
        )

    # Insert the new entry
    if subdomain:
        cursor.execute(
            "INSERT OR REPLACE INTO domain_resolutions (domain, subdomain, ip, timestamp) VALUES (?, ?, ?, ?)",
            (domain, subdomain, ip, timestamp))
    else:
        cursor.execute(
            "INSERT OR REPLACE INTO domain_resolutions (domain, subdomain, ip, timestamp) VALUES (?, NULL, ?, ?)",
            (domain, ip, timestamp))

    conn.commit()
    conn.close()

def check_if_resolution_valid(domain, subdomain=None):
    """Check the timestamp and remove entry if older than 5 minutes."""
    if DNS_CACHE:
        logging.debug("DNS Caching is enabled...(check_if_resolution_valid)")
    else:
        logging.debug("DNS Caching is disabled...(check_if_resolution_valid)")
        return False

    if exists_db() is False:
        create_db()

    conn = sqlite3.connect(DB_NAME)
    cursor = conn.cursor()
    five_minutes = 5 * 60  # 5 minutes in seconds
    current_time = int(time.time())

    if subdomain:
        cursor.execute("SELECT timestamp FROM domain_resolutions WHERE domain = ? AND subdomain = ?",
                       (domain, subdomain))
    else:
        cursor.execute("SELECT timestamp FROM domain_resolutions WHERE domain = ? AND subdomain IS NULL", (domain,))

    result = cursor.fetchone()
    if result:
        timestamp = result[0]
        if current_time - timestamp > five_minutes:
            # If the timestamp is older than 5 minutes, delete the entry and return False
            if subdomain:
                cursor.execute("DELETE FROM domain_resolutions WHERE domain = ? AND subdomain = ?",
                               (domain, subdomain))
            else:
                cursor.execute("DELETE FROM domain_resolutions WHERE domain = ? AND subdomain IS NULL",
                               (domain,))
            conn.commit()
            conn.close()
            logging.info(f"Entry for {domain} {subdomain if subdomain else ''} removed due to timeout.")
            return False
        else:
            # If the entry is still valid, return True
            conn.close()
            return True
    conn.close()
    return False
