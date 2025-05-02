# -*- coding: utf-8 -*-
"""The core engine for applying path and text replacement rules."""

import json
import logging
from typing import Dict, Any, List, Optional

from .config import RuleConfig
from .exceptions import PathMappingError
from .rules import Rule, create_rule

logger = logging.getLogger(__name__)

class PathMappingEngine:
    """Applies configured rules to replace paths and text within nested data structures."""

    def __init__(self, config_path: Optional[str] = None):
        """Initializes the PathMappingEngine.

        Args:
            config_path: Path to the JSON configuration file.
                         If None, default rules/behavior might apply (TBD) or fail.
                         It's recommended to always provide a path.
        """
        try:
            self.config = RuleConfig(config_path)
        except PathMappingError as e:
            logger.error(f"Failed to initialize RuleConfig: {e}")
            # Decide how to handle config errors: raise, or operate with no rules?
            # For now, let's raise to make the issue explicit.
            raise

        self.path_rules: List[Rule] = []
        self.text_rules: List[Rule] = []
        self._initialize_rules()

    def _initialize_rules(self) -> None:
        """Initializes rule objects from the loaded configuration."""
        self.path_rules = []
        self.text_rules = []

        logger.debug("Initializing path rules...")
        for rule_config in self.config.get_path_rules():
            rule_instance = create_rule(rule_config)
            if rule_instance:
                self.path_rules.append(rule_instance)
            # create_rule already logs errors/warnings

        logger.debug("Initializing text rules...")
        for rule_config in self.config.get_text_rules():
            rule_instance = create_rule(rule_config)
            if rule_instance:
                self.text_rules.append(rule_instance)

        logger.info(f"PathMappingEngine initialized with {len(self.path_rules)} path rules and {len(self.text_rules)} text rules.")

    def _is_system_path(self, path_str: str) -> bool:
        """Checks if the given path string matches any ignore patterns."""
        if not isinstance(path_str, str):
            return False
        for sys_path_part in self.config.get_system_paths_to_ignore():
            if sys_path_part in path_str:
                # Consider adding logging here if debugging system path ignores is needed
                # logger.debug(f"Path '{path_str}' ignored as it contains system path part '{sys_path_part}'.")
                return True
        return False

    def _process_path_value(self, key: str, value: str, context: Dict[str, Any]) -> str:
        """Applies path rules to a string value identified as a potential path."""
        if self._is_system_path(value):
             logger.debug(f"Skipping system path for key '{key}': '{value}'")
             return value

        processed_value = value
        rule_applied_flag = False
        for rule in self.path_rules:
            if rule.applies_to_key(key):
                try:
                    new_value = rule.apply(processed_value, context)
                    if new_value != processed_value:
                        logger.debug(f"Path rule '{rule.id}' applied for key '{key}'. Value changed.")
                        processed_value = new_value
                        rule_applied_flag = True
                        # Decide on rule execution strategy:
                        # Option 1: Stop after first successful rule application (current implementation)
                        break
                        # Option 2: Apply all matching rules sequentially (remove break)
                        # if rule_applied_flag:
                        #      logger.info(f"Path for key '{key}' changed from '{value}' to '{processed_value}'")
                except Exception as e:
                    logger.error(f"Error applying path rule '{rule.id}' to key '{key}', value '{processed_value}': {e}", exc_info=True)
                    # Continue with the original or last successful value?
                    # Let's keep the value before the error and continue to next rule (if applying sequentially)
                    # or just return the value before error if stopping on first success.
                    break # Stop processing path rules for this key on error

        # +++ Add detailed logging +++
        if value != processed_value:
            logger.info(f"PATH RULE APPLIED: Key='{key}', Original='{value}', New='{processed_value}'")
        elif not rule_applied_flag:
            logger.debug(f"PATH RULE CHECKED: Key='{key}', Value='{value}' (No applicable rule found or no change)")
        # +++ End added logging +++

        return processed_value

    def _process_text_value(self, key: str, value: str, context: Dict[str, Any]) -> str:
        """Applies text rules to a string value.

        Handles nested JSON content if the key is configured for it.
        """
        processed_value = value
        original_value_for_log = value # Keep original for comparison

        # 1. Handle potential nested JSON content first
        if key in self.config.get_json_content_keys() and value.strip().startswith( ("{", "[") ):
            try:
                nested_data = json.loads(value)
                logger.debug(f"Processing nested JSON content for key '{key}'.")
                # IMPORTANT: Need a fresh context or manage item carefully if modifying in place
                # Creating a shallow copy of context might be safer
                nested_context = context.copy()
                processed_nested_data = self._process_item(nested_data, nested_context)
                # Re-encode. Use separators for compact output matching CapCut?
                # Check if CapCut uses spaces after separators: json.dumps(..., separators=(',', ': ')) vs (',', ':')
                processed_value = json.dumps(processed_nested_data, ensure_ascii=False, separators=(',', ':'))
                if processed_value != value:
                    logger.debug(f"Nested JSON content updated for key '{key}'.")
                    # Update value for subsequent text rules
                # No else needed, if decoding fails, treat as plain text below
            except json.JSONDecodeError:
                logger.debug(f"Value for key '{key}' looks like JSON but failed to decode. Processing as plain text.")
            except Exception as e:
                 logger.error(f"Error processing nested JSON for key '{key}': {e}", exc_info=True)
                 # Continue processing original value as plain text

        # 2. Apply text rules (to potentially re-encoded JSON string or original string)
        current_value_for_text_rules = processed_value
        rule_applied_flag = False
        # +++ Add detailed logging +++
        text_rule_log_applied = []
        # +++ End added logging +++
        for rule in self.text_rules:
            if rule.applies_to_key(key):
                try:
                    new_value = rule.apply(current_value_for_text_rules, context)
                    if new_value != current_value_for_text_rules:
                        logger.debug(f"Text rule '{rule.id}' applied for key '{key}'. Value changed.")
                        current_value_for_text_rules = new_value
                        rule_applied_flag = True
                        # +++ Add detailed logging +++
                        text_rule_log_applied.append(rule.id)
                        # +++ End added logging +++
                        # Apply text rules sequentially? Stop on first? Let's apply sequentially.
                        # break # Uncomment to stop after first text rule match
                except Exception as e:
                    logger.error(f"Error applying text rule '{rule.id}' to key '{key}', value '{current_value_for_text_rules}': {e}", exc_info=True)
                    # Continue with the next rule, using the value before the error

        # Log final change if any rule modified the text
        if original_value_for_log != current_value_for_text_rules:
             logger.info(f"Text Processed: Key='{key}', Original='{original_value_for_log[:70]}...', New='{current_value_for_text_rules[:70]}...' (Rules: {text_rule_log_applied})")
        elif not rule_applied_flag and not key in self.config.get_json_content_keys(): # Avoid logging unchanged non-JSON keys too much
            if len(original_value_for_log) < 200: # Log short unchanged values
                logger.debug(f"TEXT RULE CHECKED: Key='{key}', Value='{original_value_for_log}' (No applicable rule found or no change)")
            else:
                logger.debug(f"TEXT RULE CHECKED: Key='{key}', Value='{original_value_for_log[:70]}...' (No applicable rule found or no change)")
        # +++ End added logging +++

        return current_value_for_text_rules

    def _process_item(self, item: Any, context: Dict[str, Any]) -> Any:
        """Recursively processes an item (dict, list, or primitive)."""
        if isinstance(item, dict):
            processed_dict = {}
            original_item_context = context.get('item') # Backup parent item context if needed
            context['item'] = item # Set current item for rule context
            for k, v in item.items():
                if isinstance(v, str):
                    # Apply path rules first if applicable
                    processed_v = self._process_path_value(k, v, context)
                    # Then apply text rules to the (potentially path-replaced) value
                    processed_dict[k] = self._process_text_value(k, processed_v, context)
                elif isinstance(v, (dict, list)):
                    # Recursively process nested dictionaries and lists
                    processed_dict[k] = self._process_item(v, context)
                else:
                    # Keep non-string, non-dict, non-list values as is
                    processed_dict[k] = v
            # Restore parent item context if it was backed up, or clear
            context['item'] = original_item_context if original_item_context is not None else {}
            return processed_dict

        elif isinstance(item, list):
            # Process each element in the list recursively
            return [self._process_item(elem, context) for elem in item]

        else:
            # Return primitive types unchanged
            return item

    def process_json(self, json_data: Any, material_map: Dict[str, Any], csv_row_data: Dict[str, Any]) -> Any:
        """Processes the entire JSON data structure using the configured rules.

        Args:
            json_data: The Python object (dict or list) representing the loaded JSON.
            material_map: The map derived from CSV and material lookups.
            csv_row_data: The raw data from the current CSV row.

        Returns:
            The processed Python object with paths and text replaced.

        Raises:
            PathMappingError: If a critical error occurs during processing.
        """
        if not isinstance(json_data, (dict, list)):
            logger.warning("Input json_data is not a dict or list. Returning as is.")
            return json_data

        # Initial context for the top-level call
        initial_context = {
            'material_map': material_map or {},
            'csv_row_data': csv_row_data or {},
            'item': {} # Represents the dictionary currently being processed (updated in _process_item)
        }

        logger.info("Starting JSON processing with PathMappingEngine...")
        # +++ Add detailed logging +++
        # Limit log size for very large inputs
        input_summary = str(json_data)[:500] + ('...' if len(str(json_data)) > 500 else '')
        material_map_summary = str(material_map)[:500] + ('...' if len(str(material_map)) > 500 else '')
        csv_summary = str(csv_row_data)[:500] + ('...' if len(str(csv_row_data)) > 500 else '')
        logger.debug(f"Engine Input Data (Summary):\n  JSON: {input_summary}\n  MaterialMap: {material_map_summary}\n  CSV: {csv_summary}")
        # +++ End added logging +++
        try:
            processed_data = self._process_item(json_data, initial_context)
            logger.info("JSON processing completed successfully.")
            # +++ Add detailed logging +++
            output_summary = str(processed_data)[:500] + ('...' if len(str(processed_data)) > 500 else '')
            logger.debug(f"Engine Output Data (Summary):\n{output_summary}")
            # +++ End added logging +++
            return processed_data
        except Exception as e:
            logger.exception(f"An unexpected error occurred during JSON processing: {e}")
            # Depending on desired behavior, either re-raise or return original/partially processed data
            raise PathMappingError(f"Failed to process JSON data: {e}") from e 