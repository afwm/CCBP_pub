# -*- coding: utf-8 -*-
"""Defines the rule classes for path and text replacement."""

import logging
import re
from abc import ABC, abstractmethod
from pathlib import Path
from typing import Dict, Any, Optional, List, Union

from .exceptions import RuleError

logger = logging.getLogger(__name__)

# --- Base Rule Class ---

class Rule(ABC):
    """Abstract base class for all replacement rules."""

    def __init__(self, rule_config: Dict[str, Any]):
        """Initializes the Rule.

        Args:
            rule_config: A dictionary containing the rule's configuration.
        """
        self.id = rule_config.get('id', 'unknown_rule')
        self.description = rule_config.get('description', '')
        # Ensure target_keys is always a list, even if missing or None in config
        target_keys = rule_config.get('target_keys')
        if target_keys is None:
            self.target_keys: List[str] = []
            logger.warning(f"Rule '{self.id}': 'target_keys' is missing. Rule will not match any key.")
        elif not isinstance(target_keys, list):
            self.target_keys = [] # Or raise ConfigError?
            logger.error(f"Rule '{self.id}': 'target_keys' must be a list, but got {type(target_keys)}. Rule disabled for key matching.")
            # Consider raising ConfigError here for stricter validation
            # raise ConfigError(f"Rule '{self.id}': 'target_keys' must be a list.")
        else:
            self.target_keys = target_keys

        self.priority = rule_config.get('priority', 999)
        self.enabled = rule_config.get('enabled', True) # Enabled by default

    def applies_to_key(self, key: str) -> bool:
        """Checks if this rule should be applied to the given dictionary key."""
        if not self.target_keys: # If target_keys is empty or invalid
            return False
        return '*' in self.target_keys or key in self.target_keys

    @abstractmethod
    def apply(self, value: Any, context: Dict[str, Any]) -> Any:
        """Applies the rule logic to the given value.

        Args:
            value: The value to potentially modify.
            context: A dictionary containing contextual data like material_map,
                     csv_row_data, and the current item being processed.

        Returns:
            The modified value, or the original value if the rule doesn't apply
            or causes an error.
        """
        pass

# --- Concrete Rule Classes ---

class MaterialMapLookupRule(Rule):
    """Replaces a path using a lookup in the material_map.

    The key for the lookup is derived based on configured methods.
    """

    def __init__(self, rule_config: Dict[str, Any]):
        super().__init__(rule_config)
        self.lookup_methods = rule_config.get('lookup_methods', [])
        if not self.lookup_methods:
            logger.warning(f"Rule '{self.id}': 'lookup_methods' is missing or empty. Rule will not perform any lookup.")

    def apply(self, value: Any, context: Dict[str, Any]) -> Any:
        """Applies the material map lookup logic.

        Expects 'value' to be the original path string.
        Requires 'material_map' and 'item' (the current dict) in the context.
        """
        if not isinstance(value, str) or not value:
            return value # Only apply to non-empty strings

        material_map = context.get('material_map', {})
        item = context.get('item', {}) # The dictionary containing the path
        dict_id = item.get("id", item.get("local_material_id", "N/A")) # For logging

        if not material_map:
            logger.debug(f"Rule '{self.id}': Material map is empty. Skipping lookup for value '{value}'.")
            return value

        original_path_str = value
        logger.info(f"RULE '{self.id}' APPLYING TO: '{original_path_str}' (Dict ID: {dict_id})")

        for method_config in self.lookup_methods:
            if not isinstance(method_config, dict):
                logger.warning(f"Rule '{self.id}': Invalid lookup method configuration: {method_config}. Skipping.")
                continue

            method_name = method_config.get('method')
            logger.info(f"RULE '{self.id}' TRYING METHOD: '{method_name}'")
            derived_key = None
            lookup_source_desc = "unknown method"

            try:
                if method_name == 'extra_info':
                    lookup_source_desc = f"extra_info ('{item.get('extra_info')}')"
                    extra_info = item.get('extra_info')
                    if extra_info and isinstance(extra_info, str):
                        pattern = method_config.get('pattern', r'^([a-zA-Z0-9_.-]+)\\.?')
                        logger.debug(f"Rule '{self.id}': Using pattern '{pattern}' for extra_info '{extra_info}'")
                        # print(f"DEBUG MATCH ({self.id}): pattern={repr(pattern)}, extra_info={repr(extra_info)}") # PRINT DEBUG
                        match = re.match(pattern, extra_info)
                        if match:
                            derived_key = match.group(1)
                            logger.info(f"RULE '{self.id}' extra_info derived key: '{derived_key}'")
                        else:
                             logger.debug(f"Rule '{self.id}': extra_info '{extra_info}' did not match pattern '{pattern}'.")
                    else:
                         logger.debug(f"Rule '{self.id}': extra_info key missing or not string in item.")

                elif method_name == 'path_stem':
                    lookup_source_desc = f"path stem ('{original_path_str}')"
                    try:
                        derived_key = Path(original_path_str).stem
                        logger.info(f"RULE '{self.id}' path_stem derived key: '{derived_key}'")
                    except Exception as e:
                        logger.debug(f"Rule '{self.id}': Error extracting path stem from '{original_path_str}': {e}")
                        derived_key = None

                elif method_name == 'field_value':
                    field_name = method_config.get('field')
                    lookup_source_desc = f"field '{field_name}' ('{item.get(field_name)}')"
                    if field_name:
                        key_val = item.get(field_name)
                        if key_val and isinstance(key_val, str):
                            derived_key = key_val
                            logger.info(f"RULE '{self.id}' field_value ('{field_name}') derived key: '{derived_key}'")
                        else:
                             logger.debug(f"Rule '{self.id}': Field '{field_name}' missing or not string.")
                    else:
                         logger.warning(f"Rule '{self.id}': 'field' not specified for field_value method.")

                elif method_name == 'type_and_stem':
                    lookup_source_desc = f"type/stem ('{item.get('type')}' / '{original_path_str}')"
                    try:
                        item_type = item.get('type')
                        stem = Path(original_path_str).stem
                        if item_type and stem:
                            derived_key = stem
                            logger.info(f"RULE '{self.id}' type_and_stem derived key: '{derived_key}' (type: '{item_type}')")
                        else:
                             logger.debug(f"Rule '{self.id}': Missing type or stem for type_and_stem method.")
                    except Exception as e:
                        logger.debug(f"Rule '{self.id}': Error during type/stem fallback for '{original_path_str}': {e}")
                        derived_key = None

                else:
                    logger.warning(f"Rule '{self.id}': Unknown lookup method '{method_name}'. Skipping.")
                    continue

                logger.info(f"RULE '{self.id}' CHECKING derived_key: '{derived_key}' in material_map")
                if derived_key is not None and derived_key in material_map:
                    map_value = material_map[derived_key]
                    logger.info(f"RULE '{self.id}' FOUND key '{derived_key}' in map. Value: '{map_value}'")
                    if isinstance(map_value, str):
                        logger.info(f"RULE '{self.id}' RETURNING map_value: '{map_value}'")
                        return map_value
                    else:
                        logger.info(f"RULE '{self.id}' Found non-string value, returning original: '{original_path_str}'")
                        return original_path_str
                elif derived_key is not None:
                     logger.info(f"RULE '{self.id}' MISS for key '{derived_key}'")
                else:
                     logger.info(f"RULE '{self.id}' No key derived by method '{method_name}'")

            except Exception as e:
                logger.error(f"Rule '{self.id}': Error during lookup method '{method_name}' for value '{original_path_str}'. Error: {e}. Dict ID/LMI: {dict_id}", exc_info=True)
                # Continue to the next method in case of unexpected error

        # If no lookup method found a replacement
        logger.info(f"RULE '{self.id}' NO MATCH FOUND, RETURNING ORIGINAL: '{original_path_str}'")
        return original_path_str # Return original value if no match found


class RegexRule(Rule):
    """Replaces substrings using a regular expression."""

    def __init__(self, rule_config: Dict[str, Any]):
        super().__init__(rule_config)
        self.pattern_str = rule_config.get('pattern', '')
        self.replacement = rule_config.get('replacement', '') # .replace せずそのまま保持
        self.compiled_pattern = None

        if not self.pattern_str:
            logger.warning(f"Rule '{self.id}': 'pattern' is missing or empty. Rule will not perform any replacement.")
            self.enabled = False
        else:
            try:
                self.compiled_pattern = re.compile(self.pattern_str)
            except re.error as e:
                logger.error(f"Rule '{self.id}': Invalid regex pattern '{self.pattern_str}'. Rule disabled. Error: {e}")
                self.enabled = False
                self.compiled_pattern = None # Ensure it's None

    def apply(self, value: Any, context: Dict[str, Any]) -> Any:
        """Applies the regex substitution logic, handling backreferences."""
        if not self.compiled_pattern or not isinstance(value, str):
            return value

        def replacer(match):
            """Internal function to handle replacement with backreferences."""
            try:
                processed_replacement = self.replacement # Directly use the replacement string
                return match.expand(processed_replacement)
            except re.error as e:
                logger.error(f"Rule '{self.id}': Error expanding replacement '{processed_replacement}' for match '{match.group(0)}'. Error: {e}")
                return match.group(0)
            except Exception as e:
                logger.error(f"Rule '{self.id}': Unexpected error during replacement expansion. Error: {e}", exc_info=True)
                return match.group(0)

        try:
            new_value = self.compiled_pattern.sub(replacer, value)
            if new_value != value:
                 logger.debug(f"Rule '{self.id}': Regex applied. Original='{value}', New='{new_value}'") # 有用なログは残す
            return new_value
        except Exception as e:
            logger.error(f"Rule '{self.id}': Error applying regex substitution to value '{value}'. Pattern='{self.pattern_str}', Replacement='{self.replacement}'. Error: {e}", exc_info=True)
            return value


class RegexPlaceholderRule(Rule):
    """Replaces placeholders like ##key## or {{key}} using a data source."""

    def __init__(self, rule_config: Dict[str, Any]):
        super().__init__(rule_config)
        self.pattern_str = rule_config.get('pattern', '')
        self.source = rule_config.get('source') # e.g., 'material_map', 'csv_row_data'
        self.compiled_pattern = None

        if not self.pattern_str:
            logger.warning(f"Rule '{self.id}': 'pattern' is missing or empty. Rule will not perform any replacement.")
        elif not self.source:
            logger.warning(f"Rule '{self.id}': 'source' is missing. Rule requires a data source ('material_map' or 'csv_row_data'). Rule disabled.")
            self.enabled = False
        else:
            try:
                # Ensure pattern has at least one capture group for the key
                if re.compile(self.pattern_str).groups < 1:
                    raise RuleError("Pattern must contain at least one capture group for the key.")
                self.compiled_pattern = re.compile(self.pattern_str)
            except re.error as e:
                logger.error(f"Rule '{self.id}': Invalid regex pattern '{self.pattern_str}'. Rule disabled. Error: {e}")
                self.enabled = False
            except RuleError as e:
                logger.error(f"Rule '{self.id}': Invalid pattern configuration. Rule disabled. Error: {e}")
                self.enabled = False

    def apply(self, value: Any, context: Dict[str, Any]) -> Any:
        """Applies the placeholder replacement logic.

        Expects 'value' to be a string.
        Requires the specified 'source' (e.g., 'material_map') in the context.
        """
        if not self.compiled_pattern or not isinstance(value, str) or not self.source:
            return value

        source_data = context.get(self.source)
        if source_data is None:
            logger.warning(f"Rule '{self.id}': Required data source '{self.source}' not found in context. Skipping replacement for value '{value}'.")
            return value
        if not isinstance(source_data, dict):
            logger.warning(f"Rule '{self.id}': Data source '{self.source}' is not a dictionary (Type: {type(source_data)}). Skipping replacement.")
            return value

        # Use a mutable list to track if any replacement occurred
        replacements_made = [False]

        def replace_match(match):
            try:
                placeholder_key = match.group(1).strip() # Assume key is in the first capture group
                if placeholder_key in source_data:
                    replacement_value = str(source_data[placeholder_key]) # Ensure string
                    logger.debug(f"Rule '{self.id}': Replacing '{match.group(0)}' with value from '{self.source}' for key '{placeholder_key}'")
                    replacements_made[0] = True
                    return replacement_value
                else:
                    logger.warning(f"Rule '{self.id}': Placeholder key '{placeholder_key}' (from '{match.group(0)}') not found in data source '{self.source}'. Keeping original placeholder.")
                    logger.debug(f"Available keys in '{self.source}': {list(source_data.keys())}")
                    return match.group(0) # Keep original if key not found
            except IndexError:
                logger.error(f"Rule '{self.id}': Regex pattern '{self.pattern_str}' did not capture a group for value '{value}'. Keeping original.")
                return match.group(0)
            except Exception as e:
                logger.error(f"Rule '{self.id}': Error during placeholder replacement for key '{match.group(1)}'. Error: {e}", exc_info=True)
                return match.group(0)

        try:
            new_value = self.compiled_pattern.sub(replace_match, value)
            # Log only if a replacement actually happened
            # if replacements_made[0] and new_value != value: # Check both flag and value change
            #     logger.info(f"Rule '{self.id}': Text replaced via placeholder. Original='{value[:50]}...', New='{new_value[:50]}...'")
            return new_value
        except Exception as e:
            logger.error(f"Rule '{self.id}': Error applying placeholder substitution to value '{value}'. Pattern='{self.pattern_str}', Source='{self.source}'. Error: {e}", exc_info=True)
            return value

# --- Rule Factory --- #

RULE_TYPE_MAP = {
    'material_map_lookup': MaterialMapLookupRule,
    'regex': RegexRule,
    'regex_placeholder': RegexPlaceholderRule,
    # Add other rule types here
}

def create_rule(rule_config: Dict[str, Any]) -> Optional[Rule]:
    """Factory function to create a Rule instance from its configuration.

    Args:
        rule_config: A dictionary containing the configuration for a single rule.

    Returns:
        A Rule instance, or None if the rule type is unknown or config is invalid.
    """
    if not isinstance(rule_config, dict):
        logger.error(f"Invalid rule configuration: Expected dict, got {type(rule_config)}. Config: {rule_config}")
        return None

    rule_type = rule_config.get('type')
    rule_id = rule_config.get('id', 'unknown_rule')

    if not rule_type:
        logger.error(f"Rule '{rule_id}': Missing 'type' in configuration. Cannot create rule. Config: {rule_config}")
        return None

    rule_class = RULE_TYPE_MAP.get(rule_type)

    if rule_class:
        try:
            rule_instance = rule_class(rule_config)
            # Return instance only if it was enabled after initialization (e.g., regex compiled successfully)
            if rule_instance.enabled:
                logger.debug(f"Successfully created rule '{rule_instance.id}' of type '{rule_type}'.")
                return rule_instance
            else:
                logger.warning(f"Rule '{rule_id}' of type '{rule_type}' was created but is disabled due to initialization errors (e.g., invalid regex).")
                return None
        except Exception as e:
            logger.error(f"Rule '{rule_id}': Error initializing rule of type '{rule_type}'. Config: {rule_config}. Error: {e}", exc_info=True)
            return None
    else:
        logger.error(f"Rule '{rule_id}': Unknown rule type '{rule_type}'. Supported types: {list(RULE_TYPE_MAP.keys())}")
        return None 