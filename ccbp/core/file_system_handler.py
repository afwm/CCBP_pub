# -*- coding: utf-8 -*-
import shutil
from pathlib import Path
import csv
import datetime
import logging
import os
from typing import Optional, Dict, List

logger = logging.getLogger(__name__)

# Make constants accessible at module level or within the class
MATERIAL_SUBFOLDERS = ['video', 'audio', 'image', 'text', 'effect', 'sticker', 'filter', 'transition', 'font', 'music', 'photo', 'img', 'bgm', 'se', 'voice']  # Expanded list

# Copied from capcut_handler for use here
TEMPLATE_TYPE_DIRS: Dict[str, List[str]] = {
    "image": ["image", "photo", "img"],
    "video": ["video"],
    "audio": ["audio", "music", "bgm", "se", "voice"],
    # Add other types if needed, ensure keys match MATERIAL_TYPE_MAP values in CapcutHandler
}

class FileSystemHandler:
    """Handles file system operations like copying templates and writing CSVs."""

    # Constants can also be class attributes
    MATERIAL_SUBFOLDERS = MATERIAL_SUBFOLDERS
    TEMPLATE_TYPE_DIRS = TEMPLATE_TYPE_DIRS

    @staticmethod
    def copy_template_project(template_path_str: str, output_base_dir_str: str, project_name: str) -> str | None:
        """Copies the template project directory to the output directory."""
        template_path = Path(template_path_str)
        output_base_dir = Path(output_base_dir_str)
        # Sanitize project_name to be used as a folder name (basic example)
        safe_project_name = "".join(c if c.isalnum() or c in ('_', '-') else '_' for c in project_name)
        output_project_path = output_base_dir / safe_project_name

        if not template_path.is_dir():
            logger.error(f"Template project directory not found: {template_path}")
            return None

        try:
            output_base_dir.mkdir(parents=True, exist_ok=True)
            if output_project_path.exists():
                logger.warning(f"Output project directory already exists, overwriting: {output_project_path}")
                shutil.rmtree(output_project_path)
            
            shutil.copytree(template_path, output_project_path)
            logger.info(f"Copied template project to: {output_project_path}")
            return str(output_project_path)
        except (OSError, shutil.Error) as e:
            logger.error(f"Error copying template project {template_path} to {output_project_path}: {e}", exc_info=True)
            return None

    @staticmethod
    def generate_output_csv_path(output_dir_str: str, prefix="report") -> str | None:
        """Generates a timestamped CSV file path in the output directory."""
        output_dir = Path(output_dir_str)
        try:
            output_dir.mkdir(parents=True, exist_ok=True)
            timestamp = datetime.datetime.now().strftime("%Y%m%d_%H%M%S")
            filename = f"{prefix}_{timestamp}.csv"
            filepath = output_dir / filename
            logger.info(f"Generated output CSV path: {filepath}")
            return str(filepath)
        except OSError as e:
            logger.error(f"Error creating output directory {output_dir} for CSV: {e}")
            return None

    @staticmethod
    def write_output_csv(filepath_str: str, project_names: list[str]) -> bool:
        """Writes the list of generated project names to a CSV file."""
        filepath = Path(filepath_str)
        try:
            with open(filepath, 'w', newline='', encoding='utf-8-sig') as csvfile:
                writer = csv.writer(csvfile)
                writer.writerow(["GeneratedProjectName"]) # Header
                for name in project_names:
                    writer.writerow([name])
            logger.info(f"Successfully wrote generated project list to: {filepath}")
            return True
        except (IOError, csv.Error) as e:
            logger.error(f"Error writing output CSV to {filepath}: {e}", exc_info=True)
            return False

    @staticmethod
    def find_change_material(csv_filename: str, project_name: str, material_type: str, change_material_base: str) -> str | None:
        """Searches for a replacement material file in the change material directory structure.

        Assumes structure: change_material_base / project_name / material_type / csv_filename

        Args:
            csv_filename: The filename specified in the CSV.
            project_name: The project name (subfolder name).
            material_type: The type of material ('video', 'image', 'audio').
            change_material_base: The base directory for change materials.

        Returns:
            The absolute path to the found material file as a string, or None if not found.
        """
        logger.debug(f"find_change_material called with: csv='{csv_filename}', proj='{project_name}', type='{material_type}', base='{change_material_base}'")

        if not change_material_base or not csv_filename or not project_name or not material_type:
            logger.debug("find_change_material: Missing required arguments.")
            return None

        change_base_path = Path(change_material_base).resolve()
        # Basic sanitization for project name used in path
        safe_project_name = "".join(c if c.isalnum() or c in ('_', '-') else '_' for c in project_name)
        
        # ★★★ 型マッピングを削除し、material_type を直接使用 ★★★
        # type_folder_map = { ... } # 削除
        # type_dir = type_folder_map.get(material_type.lower(), material_type.lower()) # 削除
        type_dir = material_type # material_type をそのままディレクトリ名として使用

        # 型チェックは残しても良い (オプション)
        # if type_dir.lower() not in [f.lower() for f in FileSystemHandler.MATERIAL_SUBFOLDERS]:
        #     logger.warning(f"find_change_material: Material type '{type_dir}' might not be standard. Proceeding anyway.")

        # Construct the expected path
        potential_path = change_base_path / safe_project_name / type_dir / csv_filename
        logger.debug(f"find_change_material: Checking constructed path (pathlib): {potential_path}")

        # <<< 削除 >>>
        potential_path_str = str(potential_path)
        # <<< 削除 >>>
        # logger.debug(f"find_change_material: Path string repr: {repr(potential_path_str)}") # 不要
        # <<< 削除 >>>
        os_exists = os.path.exists(potential_path_str)
        os_isfile = os.path.isfile(potential_path_str)
        logger.debug(f"find_change_material: Checking with os.path: exists={os_exists}, isfile={os_isfile} for path '{potential_path_str}'") # 動作確認に有用なログは残す
        # <<< 削除 >>>

        if os_isfile: # os.path.isfile でチェックする
            logger.info(f"find_change_material: Found replacement material at: {potential_path}")
            return str(potential_path)
        else:
            # Optionally, check alternative structures if the first fails?
            # E.g., change_base_path / type_dir / csv_filename
            # For now, stick to the primary structure.
            logger.debug(f"find_change_material: Material not found at expected path: {potential_path} (checked with os.path.isfile)")
            return None

    @staticmethod
    def find_template_material_by_name(filename: str, template_material_project_path: Path, material_type: str) -> Optional[str]:
        """Searches for a file by name within the TemplateMaterial structure."""
        if not filename or not material_type:
            logger.debug(f"find_template_material_by_name: Missing filename ('{filename}') or material_type ('{material_type}').")
            return None
        if not template_material_project_path.is_dir():
             logger.warning(f"find_template_material_by_name: Template project path does not exist or is not a directory: {template_material_project_path}")
             return None

        # Use the class attribute or module-level constant
        possible_dirs = FileSystemHandler.TEMPLATE_TYPE_DIRS.get(material_type, [material_type]) # Default to just the type itself if not in map

        logger.debug(f"find_template_material_by_name: Searching for '{filename}' (type: '{material_type}') in dirs {possible_dirs} under {template_material_project_path}")

        for type_dir_name in possible_dirs:
            search_dir = template_material_project_path / type_dir_name
            if search_dir.is_dir():
                 # Simpler approach: Exact filename match first
                 target_file = search_dir / filename
                 if target_file.is_file():
                     logger.debug(f"find_template_material_by_name: Found exact match '{filename}' in '{search_dir}'")
                     return str(target_file.resolve())

        logger.debug(f"find_template_material_by_name: File '{filename}' not found in TemplateMaterial under '{material_type}' or related dirs at '{template_material_project_path}'")
        return None

    # Add other file system related methods as needed, e.g.:
    # - find_change_material(material_name, change_base_dir)
    # - validate_path(path_str, is_dir=False, is_file=False) 