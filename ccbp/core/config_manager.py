import json
import os
from pathlib import Path
import logging
import sys
# --- Crypto and Env Imports ---
from cryptography.fernet import Fernet, InvalidToken
import base64
# Remove dotenv imports
# from dotenv import load_dotenv, set_key, find_dotenv
# --- End Crypto and Env Imports ---

try:
    from platformdirs import user_config_dir
    PLATFORMDIRS_AVAILABLE = True
except ImportError:
    PLATFORMDIRS_AVAILABLE = False
    import sys # Fallback uses sys

# --- Configuration Keys ---
# Use simple strings as keys for this implementation
KEY_CROP_INPUT_DIR = 'crop_input_dir'
KEY_CROP_OUTPUT_DIR = 'crop_output_dir'
KEY_WORKING_DIRECTORY = 'working_directory'
KEY_LICENSE_KEY = 'license_key'
KEY_INTERNAL_FERNET_KEY = "internal/fernet_key" # ADDED internal key constant

# --- License Cache Keys --- 
KEY_LICENSE_STATUS = "license.status"
KEY_LICENSE_EXPIRES = "license.expires"
KEY_LICENSE_VALIDATED_AT = "license.validated_at"
KEY_LICENSE_LAST_MESSAGE = "license.last_message"
# --- End License Cache Keys --- 

# --- Batch Processing Keys ---
KEY_BATCH_CSV_FILE = "batch/csv_file"
KEY_BATCH_TEMPLATE_DIR = "batch/template_dir"
KEY_BATCH_TEMPLATE_MATERIAL_DIR = "batch/template_material_dir"
KEY_BATCH_REPLACE_MATERIAL_DIR = "batch/replace_material_dir"
KEY_BATCH_OUTPUT_DIR = "batch/output_dir"
KEY_BATCH_OUTPUT_CSV_DIR = "batch/output_csv_dir"

# --- License Related Keys ---
KEY_LICENSE_API_URL = "license/api_url"
KEY_LICENSE_FERNET_KEY = "license/fernet_key" # Sensitive - consider environment variables
# ---------------------------

# --- Trial Period Keys ---
KEY_INSTALL_DATE = "system.install_date"
KEY_LAST_VALID_DATE = "system.last_valid_date"
KEY_DAILY_BATCH_COUNT = "usage.daily_batch_count"
KEY_BATCH_COUNT_DATE = "usage.batch_count_date"
# --- End Trial Period Keys ---

# --- Key for Fernet Key Storage (in .env) ---
# Note: This key itself is NOT stored in config.json
# ENV_FERNET_KEY = "CCBP_FERNET_KEY" # REMOVED
# --- End Key ---

# --- Define which keys stored in config.json should be encrypted --- 
ENCRYPTED_CONFIG_KEYS = {
    KEY_LICENSE_KEY,
    # Add other sensitive keys here in the future if needed
}
# --- End Define --- 

# --- Keys to Exclude from User Save ---
# These keys are typically set during build and should not be overwritten by user config
KEYS_TO_EXCLUDE_FROM_USER_SAVE = {
    KEY_LICENSE_API_URL,
    KEY_LICENSE_FERNET_KEY, 
    # Add KEY_INTERNAL_FERNET_KEY if it should also be excluded from user save
}
# --- End Exclude --- 

APP_NAME = "CCBP" # Define your application name here
CONFIG_FILENAME = "config.json"

logger = logging.getLogger(__name__) # Use standard logging

# Default configuration values (sensitive values should be empty or None)
DEFAULT_CONFIG = {
    KEY_WORKING_DIRECTORY: "",
    KEY_LICENSE_KEY: "", # Encrypted, so default is empty string
    # License Cache (not encrypted)
    KEY_LICENSE_STATUS: None,
    KEY_LICENSE_EXPIRES: None,
    KEY_LICENSE_VALIDATED_AT: None,
    KEY_LICENSE_LAST_MESSAGE: "未確認",
    # Batch defaults
    KEY_BATCH_CSV_FILE: "",
    KEY_BATCH_TEMPLATE_DIR: "",
    KEY_BATCH_TEMPLATE_MATERIAL_DIR: "",
    KEY_BATCH_REPLACE_MATERIAL_DIR: "",
    KEY_BATCH_OUTPUT_DIR: "",
    KEY_BATCH_OUTPUT_CSV_DIR: "",
    # Crop defaults
    KEY_CROP_INPUT_DIR: "",
    KEY_CROP_OUTPUT_DIR: "",
    # Add license keys with defaults
    KEY_LICENSE_API_URL: "", # Set your default API URL here if applicable
    KEY_LICENSE_FERNET_KEY: "", # Keep empty, generate dynamically or use env var
    KEY_INTERNAL_FERNET_KEY: "", # ADDED default for internal key
}

class ConfigManager:
    """Manages loading and saving application configuration in a user-specific directory."""

    def __init__(self):
        self.config_file_path = self._get_config_file_path()
        self.config = {}
        # Initialize fernet to None first
        self.fernet: Fernet | None = None 
        # --- Load config FIRST --- 
        self.load() # Load config from file or defaults
        # --- Initialize Fernet using key from config, or generate new --- 
        self._load_or_create_internal_fernet_instance() 

    def _load_or_create_internal_fernet_instance(self):
        """Loads the internal Fernet key from config, initializes Fernet instance, or generates/saves a new key."""
        key_str_b64 = self.config.get(KEY_INTERNAL_FERNET_KEY)
        initialized = False

        if key_str_b64:
            logger.debug(f"Attempting to load internal Fernet key from config key: {KEY_INTERNAL_FERNET_KEY}")
            key_str_b64_stripped = key_str_b64.strip()
            logger.debug(f"[DEBUG] key_str_b64_stripped from file: '{key_str_b64_stripped}' (len: {len(key_str_b64_stripped)})")
            
            if len(key_str_b64_stripped) == 44: # 正しい長さかチェック
                try:
                    # 文字列をそのままバイト列にエンコード (これがFernetコンストラクタが期待する形式)
                    key_b64_bytes_for_fernet = key_str_b64_stripped.encode('utf-8')
                    logger.debug(f"[DEBUG] key_b64_bytes_for_fernet (should be 44 bytes): {key_b64_bytes_for_fernet} (len: {len(key_b64_bytes_for_fernet)})")

                    # Base64エンコードされたバイト列でFernetを初期化
                    self.fernet = Fernet(key_b64_bytes_for_fernet)
                    logger.info("Internal Fernet instance initialized successfully using key from config.")
                    initialized = True

                except (ValueError, TypeError) as fernet_init_error:
                    logger.warning(f"Key length is 44, but failed to initialize Fernet: {fernet_init_error}. Key might be invalid format. Will generate a new key.")
                except Exception as e:
                     logger.warning(f"Unexpected error initializing Fernet with key from config: {e}. Will generate a new key.")
            else:
                logger.warning(f"Invalid key string length found in config ({len(key_str_b64_stripped)} chars). Expected 44. Will generate a new key.")

        if not initialized:
            logger.info("Generating new internal Fernet key and initializing instance...")
            try:
                # 1. Base64エンコード済みの44バイトキー生成
                new_key_b64_bytes = Fernet.generate_key()
                logger.debug(f"[DEBUG] Generated key (base64 bytes, should be 44): {new_key_b64_bytes} (len: {len(new_key_b64_bytes)})")
                self.fernet = Fernet(new_key_b64_bytes) # インスタンス初期化
                logger.info("Internal Fernet instance initialized successfully with newly generated key.")

                # 2. Base64バイト列をそのままUTF-8文字列にデコードして保存
                new_key_str_b64 = new_key_b64_bytes.decode('utf-8') # ← 再エンコードしない！
                logger.debug(f"[DEBUG] Key string to save (should be 44 chars): '{new_key_str_b64}' (len: {len(new_key_str_b64)})")


                # 3. Base64エンコードされた「文字列」をconfig辞書に格納
                self.config[KEY_INTERNAL_FERNET_KEY] = new_key_str_b64
                # ★★★ 辞書にセットした直後の値もログ出力 ★★★
                logger.debug(f"[DEBUG] Key string in self.config before save: '{self.config.get(KEY_INTERNAL_FERNET_KEY)}'")
                logger.info(f"Attempting to save new base64 key string to config key '{KEY_INTERNAL_FERNET_KEY}'...")

                # 4. config辞書全体を保存
                self.save() # Save immediately after generating
                logger.info("New internal Fernet key generated and saved to config.json.")

            except Exception as e:
                logger.exception(f"CRITICAL: Error generating/saving internal Fernet key or initializing instance: {e}")
                self.fernet = None

        if not self.fernet:
             logger.error("Internal Fernet instance could not be initialized. Encryption/decryption will be disabled.")

    def _get_config_file_path(self) -> Path:
        """Determines the path for the config.json file."""
        config_dir = None
        if PLATFORMDIRS_AVAILABLE:
            try:
                # Use user_config_dir which is appropriate for config files
                config_dir = Path(user_config_dir(APP_NAME, ensure_exists=True))
                logger.info(f"Using config directory: {config_dir}")
            except Exception as e:
                logger.warning(f"platformdirs failed to get user_config_dir: {e}. Falling back.")
        
        if config_dir is None: # Fallback if platformdirs fails or is not available
            if sys.platform == "win32":
                app_data = os.getenv("APPDATA")
                if not app_data:
                    app_data = Path.home()
                config_dir = Path(app_data) / APP_NAME
            elif sys.platform == "darwin":
                config_dir = Path.home() / "Library" / "Application Support" / APP_NAME
            else: # Linux/Other
                config_dir = Path.home() / ".config" / APP_NAME
            
            logger.warning(f"Using fallback config directory: {config_dir}")
            try:
                config_dir.mkdir(parents=True, exist_ok=True)
            except OSError as e:
                logger.error(f"Failed to create fallback config directory {config_dir}: {e}")
                # If directory creation fails, fallback to current dir (not ideal)
                return Path.cwd() / CONFIG_FILENAME 

        return config_dir / CONFIG_FILENAME

    def _get_default_config(self) -> dict:
        """Provides the default configuration values."""
        return DEFAULT_CONFIG.copy() # Return a copy to prevent modification

    def load(self):
        """Loads configuration from the JSON file(s) with new priority order."""
        default_config = self._get_default_config()
        base_config = {}
        user_config = {}
        loaded_base = False
        loaded_user = False
        is_frozen = getattr(sys, 'frozen', False)
        logger.debug(f"[ConfigManager] Environment check: sys.frozen = {is_frozen}")

        # 1. Determine the path for the bundled config file
        bundle_config_path = None
        try:
            if is_frozen:
                # Bundled environment
                exe_path = Path(sys.executable).resolve()
                logger.debug(f"[ConfigManager] Running bundled. Executable path: {exe_path}")
                base_dir = exe_path.parent # Directory containing the executable

                if sys.platform == "darwin":
                    # On macOS .app bundles, data files are typically in Contents/Resources
                    # Check relative to the .app bundle structure if possible
                    # Go up from MacOS dir -> Contents dir -> Resources dir
                    potential_resources_dir = base_dir.parent / "Resources"
                    if potential_resources_dir.is_dir():
                         bundle_config_path = potential_resources_dir / CONFIG_FILENAME
                         logger.debug(f"[ConfigManager] macOS bundle detected. Checking Resources path: {bundle_config_path}")
                    else:
                         # Fallback for non-standard bundle or other structures
                         bundle_config_path = base_dir / CONFIG_FILENAME
                         logger.warning(f"[ConfigManager] macOS bundle structure not standard? Falling back to exe dir path: {bundle_config_path}")
                else:
                    # Windows or Linux standalone: Assume config is alongside the executable
                    bundle_config_path = base_dir / CONFIG_FILENAME
                    logger.debug(f"[ConfigManager] Windows/Linux bundle. Checking exe dir path: {bundle_config_path}")

            else:
                # Development environment: Assume project root is 2 levels above this file
                project_root = Path(__file__).resolve().parents[2]
                bundle_config_path = project_root / CONFIG_FILENAME
                logger.debug(f"[ConfigManager] Running from source. Checking project root path: {bundle_config_path}")

        except Exception as e:
            logger.error(f"[ConfigManager] Error determining bundled config path: {e}", exc_info=True)
            # Attempt fallback to CWD if path determination failed
            if bundle_config_path is None:
                 bundle_config_path = Path.cwd() / CONFIG_FILENAME
                 logger.warning(f"[ConfigManager] Falling back to CWD for bundled config path: {bundle_config_path}")


        logger.info(f"[ConfigManager] Final path determined for bundled config: {bundle_config_path}")

        # 2. Try loading bundled config
        if bundle_config_path and bundle_config_path.exists():
            try:
                with open(bundle_config_path, 'r', encoding='utf-8') as f:
                    config_content = f.read()
                    logger.debug(f"[ConfigManager] Found bundled config content (first 200 chars): {config_content[:200]}...")
                    f.seek(0)
                    base_config = json.load(f)
                logger.info(f"[ConfigManager] Successfully loaded bundled config from: {bundle_config_path}")
                loaded_base = True
                # ADDED: Log the API URL loaded from bundle if present
                if KEY_LICENSE_API_URL in base_config:
                     logger.info(f"[ConfigManager] API URL found in bundled config: '{base_config.get(KEY_LICENSE_API_URL)}'") # Use get for safety
                else:
                     logger.warning(f"[ConfigManager] '{KEY_LICENSE_API_URL}' not found in the loaded bundled config.")
                # END ADDED
            except Exception as e:
                logger.warning(f"[ConfigManager] Failed to read/parse bundled config file: {bundle_config_path} - {e}", exc_info=True)
        elif bundle_config_path:
            logger.error(f"[ConfigManager] CRITICAL: Bundled config file *NOT FOUND* at expected location: {bundle_config_path}") # More critical logging
        else:
             logger.error("[ConfigManager] CRITICAL: Could not determine a valid path for the bundled config file.")

        # 3. Load user config
        logger.debug(f"[ConfigManager] Attempting to load user config from: {self.config_file_path}")
        if self.config_file_path.exists():
            try:
                with open(self.config_file_path, 'r', encoding='utf-8') as f:
                    user_config = json.load(f)
                logger.info(f"[ConfigManager] Loaded user config: {self.config_file_path}")
                loaded_user = True
            except Exception as e:
                logger.warning(f"[ConfigManager] Failed to load user config: {self.config_file_path} - {e}", exc_info=True)
        else:
             logger.debug(f"[ConfigManager] User config not found (this is normal on first run): {self.config_file_path}")

        # 4. Merge (Default -> Bundled -> User)
        logger.debug(f"[ConfigManager] Merging config sources...")
        logger.debug(f"[ConfigManager] Keys from Default: {list(default_config.keys())}")
        logger.debug(f"[ConfigManager] Keys from Bundled: {list(base_config.keys())}")
        logger.debug(f"[ConfigManager] Keys from User: {list(user_config.keys())}")

        self.config = {**default_config, **base_config, **user_config}

        # Log final keys and source summary
        merged_keys = list(self.config.keys())
        source_log = []
        if loaded_base: source_log.append("Bundled")
        if loaded_user: source_log.append("User")
        if not source_log: source_log.append("Default only")
        logger.info(f"[ConfigManager] Config loading complete. Sources: {', '.join(source_log)}. Final keys count: {len(merged_keys)}")
        # ADDED: Log the final API URL after merge
        final_api_url = self.config.get(KEY_LICENSE_API_URL)
        logger.info(f"[ConfigManager] Final '{KEY_LICENSE_API_URL}' after merge: '{final_api_url}'")
        if not final_api_url and loaded_base and KEY_LICENSE_API_URL in base_config and base_config.get(KEY_LICENSE_API_URL):
             logger.error(f"[ConfigManager] CRITICAL: API URL was present in bundle but is missing after merge! Check user config overwrite.")
        elif not final_api_url and not loaded_base:
             logger.error(f"[ConfigManager] CRITICAL: API URL is missing because bundled config was not loaded.")
        elif not final_api_url:
             logger.error(f"[ConfigManager] CRITICAL: API URL is missing for an unknown reason after merge.")
        # END ADDED

    def save(self):
        """Saves the current configuration to the user's JSON file, excluding sensitive build-time keys."""
        try:
            # Ensure the directory exists before saving
            self.config_file_path.parent.mkdir(parents=True, exist_ok=True) 

            # Create a copy to modify for saving
            config_to_save = self.config.copy()

            # --- ADDED: Exclude specific keys before saving to user config ---
            excluded_keys = []
            for key in KEYS_TO_EXCLUDE_FROM_USER_SAVE:
                if key in config_to_save:
                    del config_to_save[key]
                    excluded_keys.append(key)
            if excluded_keys:
                logger.debug(f"Excluding keys from user config save: {excluded_keys}")
            # --- END ADDED ---

            with open(self.config_file_path, 'w', encoding='utf-8') as f:
                json.dump(config_to_save, f, indent=4, ensure_ascii=False)
            logger.info(f"User configuration saved to {self.config_file_path}") # Clarify this is USER config

        except IOError as e:
            logger.error(f"Failed to save user configuration to {self.config_file_path}: {e}")
        except Exception as e: # Catch any other unexpected errors
            logger.exception(f"Unexpected error saving user config: {e}")

    def get(self, key: str, default=None):
        """Gets a configuration value, decrypting if necessary."""
        value = self.config.get(key)

        if value is not None and key in ENCRYPTED_CONFIG_KEYS:
            # Check self.fernet directly
            if not self.fernet:
                logger.error(f"Cannot decrypt key '{key}' because Fernet is not initialized.")
                return default
            if not isinstance(value, str) or not value: # Ensure value is non-empty string before decode
                logger.warning(f"Value for encrypted key '{key}' is not a valid string ('{value}'). Returning default.")
                return default
            try:
                # Assume value is base64 encoded string of encrypted bytes
                encrypted_bytes = base64.urlsafe_b64decode(value.encode('utf-8'))
                decrypted_bytes = self.fernet.decrypt(encrypted_bytes)
                decrypted_value = decrypted_bytes.decode('utf-8')
                logger.debug(f"Decrypted value for key '{key}'")
                return decrypted_value
            except InvalidToken:
                 logger.error(f"Failed to decrypt value for key '{key}': Invalid token (key mismatch or corrupted data). Returning default.")
                 return default
            except (TypeError, ValueError, base64.binascii.Error) as e:
                 logger.warning(f"Failed to decode or decrypt value for key '{key}'. It might be plaintext or corrupted: {e}. Returning default.")
                 return default
            except Exception as e:
                 logger.exception(f"Unexpected error decrypting value for key '{key}': {e}. Returning default.")
                 return default
        elif value is not None:
             return value
        else:
             return default

    def set(self, key: str, value):
        """Sets a configuration value, encrypting if necessary. Does not save automatically."""
        if key in ENCRYPTED_CONFIG_KEYS:
            if value is None or value == "": # Treat None or empty string as clearing the encrypted value
                 encrypted_value_str = "" # Store empty string for cleared encrypted keys
                 logger.debug(f"Setting encrypted key '{key}' to empty.")
            # Check self.fernet directly
            elif not self.fernet:
                 logger.error(f"Cannot encrypt key '{key}' because Fernet is not initialized. Storing as empty string.")
                 encrypted_value_str = ""
            else:
                 try:
                     # Ensure value is bytes before encrypting
                     value_bytes = str(value).encode('utf-8') 
                     encrypted_bytes = self.fernet.encrypt(value_bytes)
                     # Store as base64 encoded string
                     encrypted_value_str = base64.urlsafe_b64encode(encrypted_bytes).decode('utf-8')
                     logger.debug(f"Encrypted value set for key '{key}'")
                 except Exception as e:
                     logger.exception(f"Failed to encrypt value for key '{key}': {e}. Storing as empty string.")
                     encrypted_value_str = "" # Store empty string on encryption failure
            self.config[key] = encrypted_value_str
        else:
            # Not an encrypted key, store as is
            self.config[key] = value
            logger.debug(f"Config set (plaintext): {{'{key}': {value}}}") # Log the change

# Example usage (for testing if run directly)
if __name__ == '__main__':
    logging.basicConfig(level=logging.DEBUG)
    config_manager = ConfigManager()
    
    print("Current config:", config_manager.config)
    print("Config file path:", config_manager.config_file_path)
    
    # Example: Get a value
    input_dir = config_manager.get(KEY_CROP_INPUT_DIR)
    print(f"Initial {KEY_CROP_INPUT_DIR}: '{input_dir}'")
    
    # Example: Set a value and save
    new_path = str(Path.home() / "Videos" / "CropInput")
    print(f"Setting {KEY_CROP_INPUT_DIR} to '{new_path}'")
    config_manager.set(KEY_CROP_INPUT_DIR, new_path)
    config_manager.save()
    
    # Example: Load again to verify
    config_manager_new = ConfigManager()
    updated_input_dir = config_manager_new.get(KEY_CROP_INPUT_DIR)
    print(f"Updated {KEY_CROP_INPUT_DIR} after load: '{updated_input_dir}'")

    # Example: Set output path
    output_path = str(Path.home() / "Videos" / "CropOutput")
    print(f"Setting {KEY_CROP_OUTPUT_DIR} to '{output_path}'")
    config_manager_new.set(KEY_CROP_OUTPUT_DIR, output_path)
    config_manager_new.save() 