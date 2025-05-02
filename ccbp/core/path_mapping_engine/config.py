# -*- coding: utf-8 -*-
"""Handles loading and validation of path mapping rule configuration."""

import json
import logging
from pathlib import Path
from typing import Dict, List, Any, Optional

from .exceptions import ConfigError

logger = logging.getLogger(__name__)

class RuleConfig:
    """Loads, validates, and manages the mapping rule configuration."""

    DEFAULT_CONFIG_SCHEMA_VERSION = "1.0"

    def __init__(self, config_path: Optional[str] = None):
        """Initializes the RuleConfig.

        Args:
            config_path: Path to the JSON configuration file.
                         If None, an empty configuration is used.
        """
        self.config_path = Path(config_path) if config_path else None
        self.config_data: Dict[str, Any] = {}
        self.path_rules: List[Dict[str, Any]] = []
        self.text_rules: List[Dict[str, Any]] = []
        self.system_paths_to_ignore: List[str] = []
        self.json_content_keys: List[str] = []

        if self.config_path:
            self.load_and_validate_config()
        else:
            logger.warning("No configuration path provided. Using empty configuration.")
            # Set defaults explicitly when no config file is loaded
            self.path_rules = []
            self.text_rules = []
            self.system_paths_to_ignore = []
            self.json_content_keys = ["content"] # Apply default here too

    def load_and_validate_config(self) -> None:
        """Loads and validates the configuration file."""
        if not self.config_path or not self.config_path.is_file():
            raise ConfigError(f"Configuration file not found or is not a file: {self.config_path}")

        try:
            logger.info(f"Loading configuration from: {self.config_path}")
            with open(self.config_path, "r", encoding="utf-8") as f:
                self.config_data = json.load(f)
            logger.debug("Configuration file loaded successfully.")
        except json.JSONDecodeError as e:
            logger.error(f"Error decoding JSON in configuration file {self.config_path}: {e}")
            raise ConfigError(f"Invalid JSON format in configuration file: {e}") from e
        except Exception as e:
            logger.error(f"Error reading configuration file {self.config_path}: {e}")
            raise ConfigError(f"Could not load configuration file: {e}") from e

        self._validate_config_structure()
        self._extract_and_sort_rules()

    def _validate_config_structure(self) -> None:
        """Performs basic validation of the loaded configuration structure."""
        logger.debug("Validating configuration structure.")
        # Version check (optional but recommended)
        version = self.config_data.get("version", self.DEFAULT_CONFIG_SCHEMA_VERSION)
        if version != self.DEFAULT_CONFIG_SCHEMA_VERSION:
             logger.warning(f"Configuration file version '{version}' does not match expected version '{self.DEFAULT_CONFIG_SCHEMA_VERSION}'. Proceeding, but compatibility issues may arise.")

        # Check for required top-level keys presence (optional keys handled by .get later)
        # We only raise error here if fundamentally required structure is missing.
        # For optional keys like text_rules, system_paths_to_ignore, etc.,
        # the .get() method in _extract_and_sort_rules provides defaults.
        if not isinstance(self.config_data.get("path_rules", []), list):
            raise ConfigError("'path_rules' must be a list or missing.")
        if not isinstance(self.config_data.get("text_rules", []), list):
            raise ConfigError("'text_rules' must be a list or missing.")
        if not isinstance(self.config_data.get("system_paths_to_ignore", []), list):
            raise ConfigError("'system_paths_to_ignore' must be a list or missing.")
        if not isinstance(self.config_data.get("json_content_keys", []), list):
             raise ConfigError("'json_content_keys' must be a list or missing.")

        logger.debug("Configuration structure validation passed.")
        # More specific validation can be added here if needed

    def _extract_and_sort_rules(self) -> None:
        """Extracts rules and other settings, sorting rules by priority."""
        logger.debug("Extracting and sorting rules.")
        # Get rules, providing an empty list as default if key is missing
        raw_path_rules = self.config_data.get("path_rules", [])
        raw_text_rules = self.config_data.get("text_rules", [])

        # Filter for enabled rules only before sorting
        enabled_path_rules = [rule for rule in raw_path_rules if isinstance(rule, dict) and rule.get('enabled', True)]
        enabled_text_rules = [rule for rule in raw_text_rules if isinstance(rule, dict) and rule.get('enabled', True)]

        # Sort by priority (lower number = higher priority)
        self.path_rules = sorted(enabled_path_rules, key=lambda x: x.get('priority', 999))
        self.text_rules = sorted(enabled_text_rules, key=lambda x: x.get('priority', 999))

        self.system_paths_to_ignore = self.config_data.get("system_paths_to_ignore", [])
        self.json_content_keys = self.config_data.get("json_content_keys", ["content"]) # Default 'content'

        logger.debug(f"Extracted {len(self.path_rules)} enabled path rules and {len(self.text_rules)} enabled text rules.")

    def get_path_rules(self) -> List[Dict[str, Any]]:
        """Returns the sorted list of enabled path rule configurations."""
        return self.path_rules

    def get_text_rules(self) -> List[Dict[str, Any]]:
        """Returns the sorted list of enabled text rule configurations."""
        return self.text_rules

    def get_system_paths_to_ignore(self) -> List[str]:
        """Returns the list of system path patterns to ignore."""
        return self.system_paths_to_ignore

    def get_json_content_keys(self) -> List[str]:
        """Returns the list of keys whose string values might contain nested JSON."""
        return self.json_content_keys 