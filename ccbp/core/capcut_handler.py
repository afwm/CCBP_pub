# -*- coding: utf-8 -*-
import json
from pathlib import Path
import logging
import os # Needed for default config path
import sys # Needed for _MEIPASS check
from typing import Dict, Any, Optional # Needed for type hinting

# Import dependent handlers 
from .file_system_handler import FileSystemHandler 
# CsvHandler is likely used by the BatchController/Worker, not directly here.

# Import the new path mapping engine
from .path_mapping_engine import PathMappingEngine, PathMappingError

logger = logging.getLogger(__name__)

# --- Constants for Material Type Mapping ---
# Maps CSV key prefixes to expected subdirectory names in Template/Change Material folders
# Note: Multiple prefixes might map to the same type directory (e.g., bgm_, se_, voice_ -> audio)
MATERIAL_TYPE_MAP = {
    "img": "image",  # Assuming 'image' or 'photo' - adjust if needed
    "photo": "photo", # Added explicit photo mapping
    "video": "video",
    "bgm": "audio",   # Assuming 'audio' or 'music'
    "se": "audio",    # Assuming 'audio' or 'music'
    "voice": "audio", # Assuming 'audio' or 'music'
    "music": "music", # Added explicit music mapping
    # Add other mappings as needed
}
# Define potential directory names for each logical type for searching TemplateMaterial
TEMPLATE_TYPE_DIRS = {
    "image": ["image", "photo", "img"],
    "video": ["video"],
    "audio": ["audio", "music", "bgm", "se", "voice"],
}
# -----------------------------------------

class CapcutHandler:
    """Handles loading, modifying, and saving CapCut project JSON files."""

    META_INFO_FILE = "draft_meta_info.json"
    DRAFT_INFO_FILE = "draft_info.json"
    DEFAULT_MAPPING_CONFIG_FILENAME = "path_mapping_rules.json"

    def __init__(self, project_path: str, mapping_config_path: Optional[str] = None):
        """Initializes the handler for a specific generated CapCut project directory.

        Args:
            project_path: Path to the root of the copied/generated project directory.
                          This directory MUST contain draft_meta_info.json and draft_info.json.
            mapping_config_path: Optional path to the mapping rules JSON configuration file.
                                If None, attempts to load a default configuration.
        """
        self.project_path = Path(project_path).resolve()
        self.meta_path = self.project_path / self.META_INFO_FILE
        self.draft_path = self.project_path / self.DRAFT_INFO_FILE
        self.meta_data = None
        self.draft_data = None
        self.template_project_name = None

        logger.info(f"Initializing CapcutHandler for project at: {self.project_path}")

        # Determine and load mapping configuration
        if mapping_config_path is None:
            # Determine base directory based on execution context
            if hasattr(sys, '_MEIPASS'):
                # Bundled environment (Nuitka)
                base_dir = Path(sys._MEIPASS)
                logger.info(f"Running in bundled environment. Base dir for config search: {base_dir}")
                # Assume config is copied to the root of the bundle alongside executable
                # Or potentially within a 'config' subdirectory relative to _MEIPASS
                # Try root first, then config subdir
                default_config_path = base_dir / self.DEFAULT_MAPPING_CONFIG_FILENAME
                if not default_config_path.is_file():
                    logger.debug(f"Default config not found at bundle root: {default_config_path}. Trying 'config' subdir...")
                    default_config_path = base_dir / "config" / self.DEFAULT_MAPPING_CONFIG_FILENAME
            else:
                # Development environment
                # ccbp/core/ -> ccbp/ -> ccbp/config/
                base_dir = Path(__file__).resolve().parent.parent
                logger.info(f"Running in development environment. Base dir for config search: {base_dir}")
                default_config_path = base_dir / "config" / self.DEFAULT_MAPPING_CONFIG_FILENAME

            # Check if the determined path exists
            if default_config_path.is_file():
                mapping_config_path = str(default_config_path)
                logger.info(f"Using default mapping configuration: {mapping_config_path}")
            else:
                logger.warning(f"Default mapping configuration not found at {default_config_path}. Proceeding without rules.")
                mapping_config_path = None # Ensure it's None if not found

        self.mapping_engine = PathMappingEngine(mapping_config_path) # Instantiates the engine

        if not self.project_path.is_dir():
            raise NotADirectoryError(f"Project path is not a valid directory: {self.project_path}")
        if not self.meta_path.is_file():
            raise FileNotFoundError(f"{self.META_INFO_FILE} not found in {self.project_path}")
        if not self.draft_path.is_file():
            raise FileNotFoundError(f"{self.DRAFT_INFO_FILE} not found in {self.project_path}")

        try:
            with open(self.meta_path, "r", encoding="utf-8") as f:
                self.meta_data = json.load(f)
            with open(self.draft_path, "r", encoding="utf-8") as f:
                self.draft_data = json.load(f)
            logger.debug(f"Successfully loaded JSON data for {self.project_path.name}")
        except json.JSONDecodeError as e:
            logger.error(f"Error decoding JSON in {self.project_path}: {e}")
            raise ValueError(f"Invalid JSON format in project files: {e}") from e
        except Exception as e:
            logger.error(f"Error loading project files {self.project_path}: {e}")
            raise IOError(f"Could not load project files: {e}") from e

        self.template_project_name = self._extract_template_name_from_meta()

    def _extract_template_name_from_meta(self) -> str:
        """Extracts the original template project name from draft_fold_path in meta_data."""
        try:
            folder_path_str = self.meta_data.get("draft_fold_path", "")
            if not folder_path_str:
                 logger.warning("'draft_fold_path' not found or empty in meta data.")
                 return "UnknownTemplate"
                 
            template_name = Path(folder_path_str).name
            if template_name:
                logger.debug(f"Extracted template project name: {template_name}")
                return template_name
            else:
                logger.warning("Could not extract template name from draft_fold_path.")
                return "UnknownTemplate"
        except Exception as e:
            logger.exception(f"Error extracting template name: {e}")
            return "UnknownTemplate"
            
    def get_template_project_name(self) -> str:
         """Returns the extracted template project name."""
         return self.template_project_name or "UnknownTemplate"

    def update_project_name(self, new_name: str) -> bool:
        """Updates the project name in the meta data (draft_name)."""
        if self.meta_data and "draft_name" in self.meta_data:
            self.meta_data["draft_name"] = new_name
            logger.debug(f"Updated project name (draft_name) to: {new_name}")
            return True
        else:
            logger.warning("Cannot update project name: 'draft_name' key not found in meta data.")
            return False

    def _build_material_map(self, csv_row_data: dict, template_material_base: str, change_material_base: str) -> dict:
        """Builds a map from original material identifier (placeholder or path)
        or CSV text key to its final value (absolute file path or text string).

        Priority:
        1. File Path: CSV Override (ChangeMaterial) -> TemplateMaterial -> Original Path
        2. Text: CSV Value
        """
        material_map = {}
        template_name = self.get_template_project_name()
        # Ensure template_material_base is a Path object and resolved
        if template_material_base:
            template_base_path = Path(template_material_base).resolve()
            # Check if base path already includes template name (e.g., user selected the specific template dir)
            if template_base_path.name == template_name:
                template_material_project_path = template_base_path
                logger.debug(f"Template base path '{template_base_path}' appears to already include the template name '{template_name}'. Using base path directly.")
            else:
                template_material_project_path = template_base_path / template_name
                logger.debug(f"Constructed template material project path: {template_material_project_path}")
        else:
            template_material_project_path = None
            logger.warning("Template Material Base path is not provided.")
        change_base_path = Path(change_material_base).resolve() if change_material_base else None
        project_name_for_change = csv_row_data.get("ProjectName", self.project_path.name)

        logger.info(f"Building material map for project {project_name_for_change}...")
        logger.debug(f"  Template Source: {template_material_project_path}")
        logger.debug(f"  Change Source: {change_base_path}")
        logger.debug(f"  CSV Data Keys: {list(csv_row_data.keys())}")

        processed_placeholders = set() # Processed placeholders to avoid duplicate processing
        logger.debug(f"--- Starting Material Loop for Project: {project_name_for_change} ---")

        # 1. Process materials defined in draft_meta_info.json
        if "draft_materials" in self.meta_data:
            for material_group in self.meta_data["draft_materials"]:
                if material_group.get("type") == 0 and "value" in material_group:
                    for material in material_group["value"]:
                        original_file_path_str = material.get("file_Path", "")
                        extra_info_val = material.get("extra_info", "")
                        placeholder_base = extra_info_val.split(".")[0] if isinstance(extra_info_val, str) else ""
                        material_type = material.get("type", "")

                        log_key = placeholder_base if placeholder_base else original_file_path_str
                        if not log_key:
                            logger.warning(f"Skipping material with no placeholder or original path: {material.get('id', 'N/A')}")
                            continue

                        if placeholder_base and placeholder_base in processed_placeholders:
                             logger.debug(f"Map Build [{log_key}]: Placeholder '{placeholder_base}' already processed. Skipping duplicate entry.")
                             continue
                        if placeholder_base:
                             processed_placeholders.add(placeholder_base)

                        final_path_str = None
                        source_log = "Unknown"

                        # --- Logic based on user requirement ---
                        csv_filename = None
                        csv_override_exists = False
                        if placeholder_base and placeholder_base in csv_row_data:
                            csv_filename = csv_row_data[placeholder_base]
                            if csv_filename: # Check if CSV specifies a non-empty filename
                                 csv_override_exists = True

                        mapped_type_dir = None
                        change_subdir_to_search = None
                        if placeholder_base:
                            for prefix, type_dir in MATERIAL_TYPE_MAP.items():
                                 if placeholder_base.startswith(prefix + '_'):
                                    mapped_type_dir = type_dir
                                    break
                        if not mapped_type_dir and material_type and material_type in FileSystemHandler.MATERIAL_SUBFOLDERS:
                             mapped_type_dir = material_type
                        if not mapped_type_dir and original_file_path_str:
                             parent_dir_name = Path(original_file_path_str).parent.name
                             logical_types = list(FileSystemHandler.TEMPLATE_TYPE_DIRS.keys())
                             if parent_dir_name in logical_types:
                                 mapped_type_dir = parent_dir_name

                        if placeholder_base:
                            parts = placeholder_base.split('_', 1)
                            if len(parts) > 0:
                                potential_prefix = parts[0]
                                direct_change_subdirs = ['bgm', 'img', 'se', 'video', 'voice']
                                if potential_prefix in direct_change_subdirs:
                                    change_subdir_to_search = potential_prefix

                        # --- Search for the final path ---
                        if not change_subdir_to_search and not mapped_type_dir:
                             logger.warning(f"Map Build [{log_key}]: Could not determine any material type directory. Cannot search. Keeping original path.")
                             final_path_str = original_file_path_str
                             source_log = "Original (Type Unknown)"
                        else:
                            if csv_override_exists:
                                if change_subdir_to_search:
                                    logger.debug(f"Map Build [{log_key}]: CSV override specified ('{csv_filename}'). Searching ChangeMaterial (subdir: {change_subdir_to_search})...")
                                    if change_base_path:
                                        logger.debug(f"Map Build [{log_key}]: Calling find_change_material(csv='{csv_filename}', proj='{project_name_for_change}', type='{change_subdir_to_search}', base='{change_base_path}')")
                                        change_path = FileSystemHandler.find_change_material(\
                                            csv_filename=csv_filename,\
                                            project_name=project_name_for_change,\
                                            material_type=change_subdir_to_search,\
                                            change_material_base=str(change_base_path)\
                                        )
                                        logger.debug(f"Map Build [{log_key}]: find_change_material result: '{change_path}'")
                                    if change_path:
                                        final_path_str = change_path
                                        source_log = "ChangeMaterial (CSV Override)"
                                        logger.info(f"Map Build [{log_key}]: Found in ChangeMaterial -> {final_path_str}")
                                    else:
                                        logger.warning(f"Map Build [{log_key}]: CSV specified '{csv_filename}', but not found in ChangeMaterial subdir '{change_subdir_to_search}'. Falling back to TemplateMaterial search.")
                                        if mapped_type_dir and original_file_path_str:
                                            original_filename = Path(original_file_path_str).name
                                            logger.debug(f"Map Build [{log_key}]: Calling find_template_material_by_name(filename='{original_filename}', proj_path='{template_material_project_path}', type='{mapped_type_dir}')")
                                            template_path = FileSystemHandler.find_template_material_by_name(
                                                 filename=original_filename,
                                                 template_material_project_path=template_material_project_path,
                                                 material_type=mapped_type_dir # Use logical type for template search
                                            )
                                            logger.debug(f"Map Build [{log_key}]: find_template_material_by_name result: '{template_path}'")
                                            if template_path:
                                                final_path_str = template_path
                                                source_log = "TemplateMaterial (CSV Fallback)"
                                                logger.info(f"Map Build [{log_key}]: Fallback found in TemplateMaterial -> {final_path_str}")
                                            else:
                                                logger.warning(f"Map Build [{log_key}]: Fallback failed. File '{original_filename}' not found in TemplateMaterial. Keeping original path.")
                                                final_path_str = original_file_path_str # Keep original if template also fails
                                                source_log = "Original (CSV Fallback Failed)"
                                        else:
                                            logger.warning(f"Map Build [{log_key}]: Cannot fallback to TemplateMaterial (original path missing). Keeping original path.")
                                            final_path_str = original_file_path_str # Keep original if possible
                                            source_log = "Original (Fallback Failed - No Orig Path)"
                                else:
                                    logger.warning(f"Map Build [{log_key}]: CSV override specified ('{csv_filename}'), but could not determine specific ChangeMaterial subdir from placeholder prefix. Falling back directly to TemplateMaterial search.")
                                    if mapped_type_dir and original_file_path_str:
                                        original_filename = Path(original_file_path_str).name
                                        logger.debug(f"Map Build [{log_key}]: Calling find_template_material_by_name (direct fallback): filename='{original_filename}', proj_path='{template_material_project_path}', type='{mapped_type_dir}'")
                                        template_path = FileSystemHandler.find_template_material_by_name(
                                            filename=original_filename,
                                            template_material_project_path=template_material_project_path,
                                            material_type=mapped_type_dir # Use logical type for template search
                                        )
                                        logger.debug(f"Map Build [{log_key}]: find_template_material_by_name (direct fallback) result: '{template_path}'")
                                        if template_path:
                                            final_path_str = template_path
                                            source_log = "TemplateMaterial (CSV Fallback)"
                                            logger.info(f"Map Build [{log_key}]: Fallback found in TemplateMaterial -> {final_path_str}")
                                        else:
                                            logger.warning(f"Map Build [{log_key}]: Fallback failed. File '{original_filename}' not found in TemplateMaterial. Keeping original path.")
                                            final_path_str = original_file_path_str # Keep original if template also fails
                                            source_log = "Original (CSV Fallback Failed)"
                                    else:
                                        logger.warning(f"Map Build [{log_key}]: Cannot fallback to TemplateMaterial (original path missing). Keeping original path.")
                                        final_path_str = original_file_path_str # Keep original if possible
                                        source_log = "Original (Fallback Failed - No Orig Path)"
                            else: # No CSV Override
                                logger.debug(f"Map Build [{log_key}]: No CSV override. Searching TemplateMaterial (type: {mapped_type_dir})...")
                                if mapped_type_dir and original_file_path_str:
                                    original_filename = Path(original_file_path_str).name
                                    logger.debug(f"Map Build [{log_key}]: Calling find_template_material_by_name (no override): filename='{original_filename}', proj_path='{template_material_project_path}', type='{mapped_type_dir}'")
                                    template_path = FileSystemHandler.find_template_material_by_name(
                                        filename=original_filename,
                                        template_material_project_path=template_material_project_path,
                                        material_type=mapped_type_dir # Use logical type here
                                        )
                                    logger.debug(f"Map Build [{log_key}]: find_template_material_by_name (no override) result: '{template_path}'")
                                    if template_path:
                                        final_path_str = template_path
                                        source_log = "TemplateMaterial (Default)"
                                        logger.info(f"Map Build [{log_key}]: Found in TemplateMaterial -> {final_path_str}")
                                    else:
                                        logger.warning(f"Map Build [{log_key}]: File '{original_filename}' not found in TemplateMaterial. Keeping original path.")
                                        final_path_str = original_file_path_str # Keep original if not found in template
                                        source_log = "Original (Template Not Found)"
                                else:
                                    logger.warning(f"Map Build [{log_key}]: Cannot search TemplateMaterial (original path missing). Cannot determine path.")
                                    final_path_str = "" # No path determined
                                    source_log = "Error (Missing Original Path)"

                        # --- Register the final path in the map ---
                        if final_path_str is not None:
                             map_register_key = placeholder_base if placeholder_base else original_file_path_str
                             if map_register_key:
                                  material_map[map_register_key] = final_path_str
                                  if original_file_path_str and original_file_path_str != map_register_key:
                                       material_map[original_file_path_str] = final_path_str
                                  logger.debug(f"Map Build [{log_key}]: Registered map '{map_register_key}' -> '{final_path_str}' (Source: {source_log})")
                                  if original_file_path_str and original_file_path_str != map_register_key:
                                       logger.debug(f"Map Build [{log_key}]: Also registered map '{original_file_path_str}' -> '{final_path_str}'")
                             else:
                                  logger.error(f"Map Build [{log_key}]: Could not determine a key to register the final path '{final_path_str}'. This is unexpected.")
                        else:
                             logger.error(f"Map Build [{log_key}]: final_path_str was None after processing. Logic error? Original path: '{original_file_path_str}'")

        # 2. Add text replacements from CSV data directly to the map
        logger.debug("Adding text values from CSV to material map...")
        for key, csv_value in csv_row_data.items():
            # Check if the key corresponds to a known material prefix
            is_material = False
            for prefix in MATERIAL_TYPE_MAP.keys():
                if key.startswith(prefix + '_'):
                    is_material = True
                    break
            # Add if it's NOT a material key, not ProjectName, and has a value
            if not is_material and key.lower() != 'projectname' and csv_value:
                if key not in material_map: # Avoid overwriting paths determined above by a text key
                    material_map[key] = str(csv_value)
                    logger.debug(f"Map Build [Text]: Added text key '{key}' -> '{csv_value}'")
                else:
                    # This can happen if a placeholder_base coincidentally matches a text key (e.g., extra_info="text_01.png")
                    logger.warning(f"Map Build [Text]: Key '{key}' already exists in map (value: '{material_map[key]}'). CSV text value '{csv_value}' will NOT overwrite it.")
        logger.info(f"Built final material map with {len(material_map)} entries.")
        # Limit the size of the logged map for readability if it's very large
        map_items_to_log = list(material_map.items())
        if len(map_items_to_log) > 50:
             logger.debug(f"Final Material Map (first 50 entries):\n{map_items_to_log[:50]}")
             logger.debug("... (map truncated in log)")
        else:
             logger.debug(f"Final Material Map:\n{material_map}")
        return material_map

    def update_material_paths(self, csv_row_data: dict, template_material_base: str, change_material_base: str) -> bool:
        """Updates material file paths AND text placeholders in both meta_data and draft_data."""
        project_name_for_log = csv_row_data.get("ProjectName", self.project_path.name)
        try:
            # Build the map using CSV data as the primary source
            material_map = self._build_material_map(csv_row_data, template_material_base, change_material_base)
            if not material_map:
                 logger.warning(f"Material map is empty for project {project_name_for_log}. No replacements possible based on CSV data.")
             # Continue anyway, as there might be JSON structure to process, but likely no changes
            else:
                logger.info(f"Material map built with {len(material_map)} entries for project {project_name_for_log}.")
            try:
                # Use the engine directly to process the data
                logger.debug(f"Updating paths and text in draft_meta_info.json for project {project_name_for_log}...")
                self.meta_data = self.mapping_engine.process_json(self.meta_data, material_map, csv_row_data)
                logger.debug(f"Updating paths and text in draft_info.json for project {project_name_for_log}...")
                self.draft_data = self.mapping_engine.process_json(self.draft_data, material_map, csv_row_data)

                logger.info(f"Path and text update process completed for project: {project_name_for_log}.")
                return True
            except Exception as e:
                logger.exception(f"Error during recursive path/text update for project {project_name_for_log}: {e}")
                return False

        except Exception as e:
            logger.exception(f"Error during path/text update (likely in map building) for project {project_name_for_log}: {e}")
            return False

    def save_changes(self) -> bool:
        """Saves the modified meta_data and draft_data back to their JSON files."""
        if self.meta_data is None or self.draft_data is None:
            logger.error("JSON data is not loaded or is invalid. Cannot save changes.")
            return False
            
        project_id_for_log = self.project_path.name # Use actual folder name for saving log
        logger.info(f"Saving changes to JSON files for project: {project_id_for_log}")
        try:
            # Create backup before overwriting - Consider making this optional or configurable
            # meta_backup_path = self.meta_path.with_suffix('.json.bak')
            # draft_backup_path = self.draft_path.with_suffix('.json.bak')
            # logger.debug(f"Backing up {self.meta_path} to {meta_backup_path}")
            # shutil.copy2(self.meta_path, meta_backup_path)
            # logger.debug(f"Backing up {self.draft_path} to {draft_backup_path}")
            # shutil.copy2(self.draft_path, draft_backup_path)


            with open(self.meta_path, 'w', encoding='utf-8') as f:
                # Use indent for readability during debugging, None or separators for production
                json.dump(self.meta_data, f, ensure_ascii=False, indent=2)
            logger.debug("Saved modified draft_meta_info.json")
            with open(self.draft_path, 'w', encoding='utf-8') as f:
                # Use indent for readability during debugging, None or separators for production
                json.dump(self.draft_data, f, ensure_ascii=False, indent=2)
            logger.debug("Saved modified draft_info.json")
            
            logger.info(f"Successfully saved changes for project: {project_id_for_log}")
            return True
        except IOError as e:
             logger.exception(f"Error writing JSON file for project {project_id_for_log}: {e}")
             return False
        except Exception as e:
             logger.exception(f"An unexpected error occurred saving JSON for {project_id_for_log}: {e}")
             return False 