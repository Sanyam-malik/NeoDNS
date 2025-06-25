import logging
import os
import sqlite3
import time

from dotenv import load_dotenv

# Load environment variables from .env file
load_dotenv()

logging.basicConfig(level=logging.DEBUG, format='%(asctime)s - %(levelname)s - %(message)s')
DNS_CACHE = bool(True if os.getenv("CACHE", "true").lower() == "true" else False)
# SQLite database name
DB_NAME = 'dns_resolutions.db'

def exists_db():
    return True if os.path.exists(DB_NAME) else False

def delete_db():
    if exists_db():
        os.remove(DB_NAME)
        return True
    return False


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
            record_type TEXT NOT NULL,
            ip TEXT NOT NULL,
            timestamp INTEGER NOT NULL,
            PRIMARY KEY (domain, subdomain, record_type, ip)
        )
    ''')
    conn.commit()
    conn.close()
    logging.info(f"Database {DB_NAME} created/recreated successfully.")


def get_ips_from_db(domain, subdomain=None, record_type="A"):
    """Retrieve all IPs for a given domain, subdomain, and record type from the SQLite database."""
    if DNS_CACHE:
        logging.debug("DNS Caching is enabled...(get_ips_from_db)")
    else:
        logging.debug("DNS Caching is disabled...(get_ips_from_db)")
        return []

    if not exists_db():
        create_db()

    conn = sqlite3.connect(DB_NAME)
    cursor = conn.cursor()
    if subdomain:
        cursor.execute("SELECT ip FROM domain_resolutions WHERE domain = ? AND subdomain = ? AND record_type = ?",
                       (domain, subdomain, record_type))
    else:
        cursor.execute("SELECT ip FROM domain_resolutions WHERE domain = ? AND subdomain IS NULL AND record_type = ?", (domain, record_type))
    results = cursor.fetchall()
    conn.close()
    return [row[0] for row in results]


def store_ips_in_db(domain, subdomain, record_type, ips):
    """Store multiple IPs for a given domain, subdomain, and record type in the SQLite database with the current timestamp."""
    if DNS_CACHE:
        logging.debug("DNS Caching is enabled...(store_ips_in_db)")
    else:
        logging.debug("DNS Caching is disabled...(store_ips_in_db)")
        return

    if not exists_db():
        create_db()

    timestamp = int(time.time())  # Get current time in seconds since the epoch
    conn = sqlite3.connect(DB_NAME)
    cursor = conn.cursor()

    # Delete any existing entries with the same domain, subdomain, and record_type
    if subdomain:
        cursor.execute(
            "DELETE FROM domain_resolutions WHERE domain = ? AND subdomain = ? AND record_type = ?",
            (domain, subdomain, record_type)
        )
    else:
        cursor.execute(
            "DELETE FROM domain_resolutions WHERE domain = ? AND subdomain IS NULL AND record_type = ?",
            (domain, record_type)
        )

    # Insert the new entries
    for ip in ips:
        if subdomain:
            cursor.execute(
                "INSERT OR REPLACE INTO domain_resolutions (domain, subdomain, record_type, ip, timestamp) VALUES (?, ?, ?, ?, ?)",
                (domain, subdomain, record_type, ip, timestamp))
        else:
            cursor.execute(
                "INSERT OR REPLACE INTO domain_resolutions (domain, subdomain, record_type, ip, timestamp) VALUES (?, NULL, ?, ?, ?)",
                (domain, record_type, ip, timestamp))

    conn.commit()
    conn.close()

def check_if_resolution_valid(domain, subdomain=None, record_type="A"):
    """Check the timestamp and remove entry if older than 5 minutes for all records of a type."""
    if DNS_CACHE:
        logging.debug("DNS Caching is enabled...(check_if_resolution_valid)")
    else:
        logging.debug("DNS Caching is disabled...(check_if_resolution_valid)")
        return False

    if not exists_db():
        create_db()

    conn = sqlite3.connect(DB_NAME)
    cursor = conn.cursor()
    five_minutes = 5 * 60  # 5 minutes in seconds
    current_time = int(time.time())

    if subdomain:
        cursor.execute("SELECT timestamp FROM domain_resolutions WHERE domain = ? AND subdomain = ? AND record_type = ?",
                       (domain, subdomain, record_type))
    else:
        cursor.execute("SELECT timestamp FROM domain_resolutions WHERE domain = ? AND subdomain IS NULL AND record_type = ?", (domain, record_type))

    results = cursor.fetchall()
    if results:
        # Check all timestamps, if any are expired, delete all and return False
        for (timestamp,) in results:
            if current_time - timestamp > five_minutes:
                if subdomain:
                    cursor.execute("DELETE FROM domain_resolutions WHERE domain = ? AND subdomain = ? AND record_type = ?",
                                   (domain, subdomain, record_type))
                else:
                    cursor.execute("DELETE FROM domain_resolutions WHERE domain = ? AND subdomain IS NULL AND record_type = ?",
                                   (domain, record_type))
                conn.commit()
                conn.close()
                logging.info(f"Entry for {domain} {subdomain if subdomain else ''} {record_type} removed due to timeout.")
                return False
        conn.close()
        return True
    conn.close()
    return False
