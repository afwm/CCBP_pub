import json
import os
from pathlib import Path
from .logging_config import get_logger

APP_NAME = "CCBP"
AUTHOR_NAME = "YourAppNameOrAuthor" # Optional: Usually same as APP_NAME
CONFIG_FILE_NAME = "config.json"

logger = get_logger(__name__)

class ConfigManager:
    """Manages application configuration using a JSON file."""

    def __init__(self, config_file=CONFIG_FILE_NAME):
        """Initializes the ConfigManager."""
        self.config_file = config_file
        self.config = {}
        self._load_defaults()
        self.load_config()

    def _load_defaults(self):
        """Loads the default configuration settings."""
        self.config = {
            "input_dir": "",
            "output_dir": "",
            "crop_settings": {
                "enabled": False,
                "x": 0,
                "y": 0,
                "width": 0,
                "height": 0
            },
            "batch_settings": {
                "enabled": False,
                "some_batch_param": "default_value"
            },
            "theme": "System", # Default theme
            "log_level": "INFO" # Default log level
        }
        logger.debug("Loaded default configuration.")

    def load_config(self):
        """Loads the configuration from the JSON file."""
        try:
            if os.path.exists(self.config_file):
                with open(self.config_file, 'r', encoding='utf-8') as f:
                    loaded_config = json.load(f)
                    # Merge loaded config with defaults to ensure all keys exist
                    self._recursive_update(self.config, loaded_config)
                logger.info(f"Configuration loaded from {self.config_file}")
            else:
                logger.info("Configuration file not found. Using defaults and creating file.")
                self.save_config() # Create the file with defaults if it doesn't exist
        except json.JSONDecodeError:
            logger.error(f"Error decoding JSON from {self.config_file}. Using default configuration.", exc_info=True)
            self._load_defaults() # Fallback to defaults
        except Exception:
            logger.error(f"Failed to load configuration from {self.config_file}. Using default configuration.", exc_info=True)
            self._load_defaults() # Fallback to defaults

    def save_config(self):
        """Saves the current configuration to the JSON file."""
        try:
            # Ensure the directory exists
            os.makedirs(os.path.dirname(self.config_file), exist_ok=True)
            with open(self.config_file, 'w', encoding='utf-8') as f:
                json.dump(self.config, f, indent=4, ensure_ascii=False)
            logger.info(f"Configuration saved to {self.config_file}")
        except Exception:
            logger.error(f"Failed to save configuration to {self.config_file}", exc_info=True)

    def get(self, key, default=None):
        """Gets a configuration value."""
        keys = key.split('.')
        value = self.config
        try:
            for k in keys:
                if isinstance(value, dict):
                    value = value[k]
                else:
                    # Handle case where intermediate key is not a dict
                    logger.warning(f"Config key '{key}' path invalid at '{k}'.")
                    return default
            return value
        except KeyError:
            logger.warning(f"Config key '{key}' not found. Returning default value: {default}")
            return default
        except Exception as e:
            logger.error(f"Error getting config key '{key}': {e}", exc_info=True)
            return default

    def set(self, key, value):
        """Sets a configuration value and saves the configuration."""
        keys = key.split('.')
        d = self.config
        try:
            for k in keys[:-1]:
                d = d.setdefault(k, {})
            d[keys[-1]] = value
            logger.debug(f"Set config key '{key}' to '{value}'")
            self.save_config()
        except Exception as e:
            logger.error(f"Error setting config key '{key}': {e}", exc_info=True)

    def _recursive_update(self, base_dict, update_dict):
        """Recursively updates a dictionary."""
        for key, value in update_dict.items():
            if isinstance(value, dict) and key in base_dict and isinstance(base_dict[key], dict):
                self._recursive_update(base_dict[key], value)
            else:
                base_dict[key] = value

    def _get_default_settings(self):
        # Define default values for all settings
        return {
            'license_key': '', 
            'expiry_date': '-', 
            'work_env_folder': str(Path.home() / "CapCutBatchProcessor_Work"), # Default to user's home
            # Add other potential settings with defaults
            'log_level': 'INFO',
            'theme': 'System' # Example: System, Light, Dark
        }

    def _ensure_config_dir_exists(self):
        try:
            self._config_dir.mkdir(parents=True, exist_ok=True)
        except OSError as e:
            print(f"Error creating config directory {self._config_dir}: {e}")
            # Handle error appropriately, maybe raise it or use a fallback

    def _load_settings(self):
        self._ensure_config_dir_exists()
        loaded_settings = {}
        if self._config_file.exists():
            try:
                with open(self._config_file, 'r', encoding='utf-8') as f:
                    loaded_settings = json.load(f)
            except (json.JSONDecodeError, OSError) as e:
                print(f"Error loading config file {self._config_file}: {e}. Using defaults.")
                # Optionally back up the corrupted file
                # Consider showing an error to the user
        
        # Merge defaults with loaded settings (defaults provide missing keys)
        # Create a new dict to ensure all default keys are present
        final_settings = self._defaults.copy()
        final_settings.update(loaded_settings) # Overwrite defaults with loaded values
        
        # Prune settings that are no longer in defaults (optional, prevents stale keys)
        keys_to_remove = [k for k in final_settings if k not in self._defaults]
        for key in keys_to_remove:
             print(f"Removing obsolete config key: {key}")
             del final_settings[key]
             
        # Save back immediately if pruning happened or loaded settings were empty/corrupt
        if not loaded_settings or keys_to_remove:
             print("Saving merged/pruned settings after initial load.")
             self._save_settings(final_settings) # Save the potentially modified settings
             
        return final_settings

    def _save_settings(self, settings_to_save):
        self._ensure_config_dir_exists()
        try:
            with open(self._config_file, 'w', encoding='utf-8') as f:
                json.dump(settings_to_save, f, indent=4)
            return True
        except OSError as e:
            print(f"Error saving config file {self._config_file}: {e}")
            # Consider showing an error to the user
            return False

    def get_setting(self, key, default=None):
        # Return the value from current settings, falling back to provided default
        return self.settings.get(key, default)

    def get_all_settings(self):
        # Return a copy to prevent external modification
        return self.settings.copy()

    def save_setting(self, key, value):
        """Saves a single setting and persists to file."""
        if key in self._defaults: # Only save known keys (optional strictness)
            self.settings[key] = value
            return self._save_settings(self.settings)
        else:
            print(f"Warning: Attempted to save unknown setting key '{key}'. Ignoring.")
            return False
            
    def save_settings_dict(self, settings_dict):
         """Saves multiple settings from a dictionary and persists to file."""
         updated = False
         for key, value in settings_dict.items():
             if key in self._defaults:
                 self.settings[key] = value
                 updated = True
             else:
                 print(f"Warning: Ignoring unknown setting key '{key}' during bulk save.")
         
         if updated:
             return self._save_settings(self.settings)
         else:
             return True # No known keys were updated, but not an error

    def reset_to_defaults(self):
        """Resets settings to defaults and persists to file."""
        self.settings = self._defaults.copy()
        return self._save_settings(self.settings)

    def get_config_file_path(self):
        return str(self._config_file)

# Example Usage (for testing)
if __name__ == "__main__":
    config = ConfigManager()
    print("Current settings:", config.get_all_settings())
    print("Config file path:", config.get_config_file_path())
    
    # Example: Change a setting
    # config.save_setting('log_level', 'DEBUG')
    # print("Log level:", config.get_setting('log_level'))
    
    # Example: Reset
    # config.reset_to_defaults()
    # print("Settings after reset:", config.get_all_settings()) 