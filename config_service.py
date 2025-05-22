import json
import logging


def load_config(config_file="config.json"):
    logging.debug(f"Loading configuration from {config_file}")
    try:
        with open(config_file, 'r') as file:
            config = json.load(file)
            logging.info("Configuration loaded successfully.")
            return config
    except Exception as e:
        logging.error(f"Failed to load configuration: {e}")
        raise

def save_config(config, config_file="config.json"):
    logging.debug(f"Saving configuration to {config_file}")
    try:
        with open(config_file, 'w') as file:
            json.dump(config, file, indent=2)
            logging.info("Configuration saved successfully.")
    except Exception as e:
        logging.error(f"Failed to save configuration: {e}")
        raise