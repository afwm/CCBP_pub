import os
import shutil
import logging
from pathlib import Path
import json
import csv
import re # Need re for path splitting

# Setup logging
logging.basicConfig(level=logging.INFO, format='%(levelname)s: %(message)s') # Use INFO level for this script
logger = logging.getLogger(__name__)

# Define paths (adjust as necessary)
VALIDATION_OUTPUT_DIR = Path("validation_output")

def load_json(file_path):
    """Loads JSON data from a file."""
    if not file_path.is_file():
        logger.error(f"File not found: {file_path}")
        return None
    try:
        with open(file_path, 'r', encoding='utf-8') as f:
            return json.load(f)
    except json.JSONDecodeError as e:
        logger.error(f"Error decoding JSON from {file_path}: {e}")
        return None
    except Exception as e:
        logger.error(f"Error loading JSON from {file_path}: {e}")
        return None

def find_key_paths(data, target_key, current_path=""):
    """Recursively finds all paths to a target key in nested dicts/lists."""
    paths = []
    if isinstance(data, dict):
        for k, v in data.items():
            new_path = f"{current_path}.{k}" if current_path else k
            if k == target_key:
                paths.append(new_path)
            # Recurse into value
            paths.extend(find_key_paths(v, target_key, new_path))
    elif isinstance(data, list):
        for i, item in enumerate(data):
            new_path = f"{current_path}[{i}]"
            # Recurse into list item
            paths.extend(find_key_paths(item, target_key, new_path))
    # Ignore other types (str, int, etc.)
    return paths

def get_value_by_path(data, path_str):
    """Gets value from nested structure using dot/bracket notation path."""
    # Simple splitting, might need refinement for complex keys with dots/brackets
    keys = re.split(r'[\.\[\]]+', path_str)
    keys = [k for k in keys if k] # Remove empty strings resulting from split
    current = data
    try:
        for key in keys:
            if isinstance(current, list):
                # Try converting key to int for list index
                try:
                    idx = int(key)
                    if idx >= len(current):
                        # logger.debug(f"Index {idx} out of bounds for list at path segment of '{path_str}'")
                        return None # Index out of bounds
                    current = current[idx]
                except ValueError:
                    # logger.debug(f"Cannot use non-integer key '{key}' for list access at path segment of '{path_str}'")
                    return None # Key is not an integer index for list
            elif isinstance(current, dict):
                if key not in current:
                    # logger.debug(f"Key '{key}' not found in dict at path segment of '{path_str}'")
                    return None # Key not found
                current = current[key]
            else:
                # logger.debug(f"Cannot traverse further into non-dict/list item at path segment of '{path_str}'")
                return None # Path segment leads into a non-container type
        return current
    except (KeyError, IndexError, TypeError, ValueError) as e:
        # logger.debug(f"Error accessing path '{path_str}': {e}")
        return None # Error during access

def compare_files(old_file, new_file, key_to_compare):
    """Compares two JSON files based on a specific key."""
    logger.info(f"--- Comparing key '{key_to_compare}' in {old_file.name} vs {new_file.name} ---")
    data_old = load_json(old_file)
    data_new = load_json(new_file)

    if data_old is None or data_new is None:
        logger.error("Cannot compare files, loading failed.")
        return False

    # Find all paths to the key in the 'old' file structure
    key_paths = find_key_paths(data_old, key_to_compare)
    if not key_paths:
        logger.info(f"Key '{key_to_compare}' not found in {old_file.name}.")
        return True # No key means no differences to find based on it

    diff_found = False
    for p in key_paths:
        value_old = get_value_by_path(data_old, p)
        value_new = get_value_by_path(data_new, p) # Try getting value from same path in new data

        # Handle cases where path might not exist in new structure or value extraction fails
        if value_old != value_new:
            diff_found = True
            logger.warning(f"Difference found at path: {p}")
            # Limit output length for readability
            val_old_str = str(value_old)[:200] + ('...' if len(str(value_old)) > 200 else '')
            val_new_str = str(value_new)[:200] + ('...' if len(str(value_new)) > 200 else '')
            logger.warning(f"  Old: {val_old_str}")
            logger.warning(f"  New: {val_new_str}")

    if not diff_found:
        logger.info(f"No differences found for key '{key_to_compare}' between the files.")
    else:
         logger.warning(f"Differences found for key '{key_to_compare}'.")

    return not diff_found


def main():
    logger.info("Starting JSON output comparison...")

    # --- Compare draft_info.json ---
    file_old_draft = VALIDATION_OUTPUT_DIR / "output_old_draft_1.json"
    file_new_draft = VALIDATION_OUTPUT_DIR / "output_new_draft_1.json"
    compare_files(file_old_draft, file_new_draft, "path")

    # --- Compare draft_meta_info.json ---
    file_old_meta = VALIDATION_OUTPUT_DIR / "output_old_meta_1.json"
    file_new_meta = VALIDATION_OUTPUT_DIR / "output_new_meta_1.json"
    compare_files(file_old_meta, file_new_meta, "file_Path")

    logger.info("Comparison finished.")

if __name__ == "__main__":
    main() 