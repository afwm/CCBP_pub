import json
from pathlib import Path
import logging  # logging モジュールをインポート

# from ..utils.logging_config import get_logger # Relative import fails when run standalone
# Use standard logging for the old handler validation
logger = logging.getLogger("capcut_handler_old") 
# Ensure basicConfig is called in validate_engine.py if needed

# from .file_system_handler import FileSystemHandler # Relative import fails
# We need to load FileSystemHandler from the old location too if it's used
# Assuming it's in CCBP_old/models/file_system_handler.py
try:
    # This is tricky, need to adjust sys.path or load differently.
    # Simplest for validation might be to copy the old FileSystemHandler too?
    # Or, rely on the *new* FileSystemHandler if compatible enough?
    # Let's assume for now the old handler might not *need* the old FS handler
    # OR that the new one is compatible enough for find_change_material.
    # This might require revisiting if path finding fails.
    from ccbp.core.file_system_handler import FileSystemHandler
    logger.info("Old handler is using the *new* FileSystemHandler for validation.")
except ImportError:
    logger.error("Could not import FileSystemHandler for old handler validation.")
    # Define a dummy class or raise error if FSHandler is critical for old logic
    class FileSystemHandler: # Dummy
        @staticmethod
        def find_change_material(*args, **kwargs):
            logger.warning("Dummy FileSystemHandler.find_change_material called")
            return None

# logger = get_logger(__name__)


class CapcutHandler:
    """Handles loading, modifying, and saving CapCut project JSON files."""

    META_INFO_FILE = "draft_meta_info.json"
    DRAFT_INFO_FILE = "draft_info.json"

    def __init__(
        self,
        project_path: str,
        template_material_base: str,
        change_material_base: str,  # 必須引数に戻す
    ):
        """Initializes the handler for a specific generated project directory.

        Args:
            project_path: Path to the root of the copied/generated project directory.
            template_material_base: Base path for TemplateMaterial.
            change_material_base: Base path for ChangeMaterial.
        """
        self.project_path = Path(project_path)
        self.meta_path = self.project_path / self.META_INFO_FILE
        self.draft_path = self.project_path / self.DRAFT_INFO_FILE
        self.template_material_base = template_material_base
        self.change_material_base = change_material_base  # 必須に戻す

        if not self.meta_path.is_file() or not self.draft_path.is_file():
            raise FileNotFoundError(
                f"Required JSON files not found in {self.project_path}"
            )

        try:
            with open(self.meta_path, "r", encoding="utf-8") as f:
                self.meta_data = json.load(f)
            with open(self.draft_path, "r", encoding="utf-8") as f:
                self.draft_data = json.load(f)
        except json.JSONDecodeError as e:
            logger.error(f"Error decoding JSON in {self.project_path}: {e}")
            raise ValueError(f"Invalid JSON format in project files: {e}") from e
        except Exception as e:
            logger.error(
                f"Error loading project files in {self.project_path}: {e}",
                exc_info=True,
            )
            raise IOError(f"Could not load project files: {e}") from e

        self.template_project_name = self._extract_template_name_from_meta()
        logger.info(f"Initialized CapcutHandler for project: {self.project_path.name}")

    def _extract_template_name_from_meta(self):
        """Extracts the original template project name from draft_fold_path."""
        try:
            # Expecting path like ".../TemplateProjectName"
            folder_path = self.meta_data.get("draft_fold_path", "")
            template_name = Path(folder_path).name
            if template_name:
                logger.debug(f"Extracted template project name: {template_name}")
                return template_name
            else:
                logger.warning(
                    "Could not extract template project name from draft_fold_path.",
                    exc_info=True,
                )
                return "UnknownTemplate"  # Fallback
        except Exception as e:
            logger.warning(f"Error extracting template name: {e}", exc_info=True)
            return "UnknownTemplate"  # Fallback

    def _extract_original_material_paths(self) -> list[Path]:
        """Extracts original material file paths referenced in the project JSONs.

        Returns:
            A list of Path objects representing the original material files.
            Returns an empty list if no materials are found or errors occur.
        """
        original_paths = set()  # 重複を避けるためにセットを使用
        logger.debug("Extracting original material paths from project JSON...")

        # draft_meta_info.json から抽出
        if "draft_materials" in self.meta_data:
            for material_group in self.meta_data["draft_materials"]:
                if material_group.get("type") == 0 and "value" in material_group:
                    for material in material_group["value"]:
                        if "file_Path" in material:
                            original_path = Path(material["file_Path"])
                            if original_path.is_file():
                                original_paths.add(original_path)
                            # else:
                            # logger.warning(f"Original material path not found: {original_path}")

        # draft_info.json から抽出 (必要に応じて追加実装)
        # 現在の構造では draft_info.json 内の直接的なファイルパス参照は限定的かもしれない
        # 例: "extra_material_refs" など特定のキーを探索する必要があるか確認
        # def find_paths_recursive(item):
        #     if isinstance(item, dict):
        #         for key, value in item.items():
        #             # 特定のキーをチェック (例: 'path', 'file_Path')
        #             if key in ['path', 'file_Path'] and isinstance(value, str):
        #                 p = Path(value)
        #                 if p.is_file():
        #                     original_paths.add(p)
        #             else:
        #                 find_paths_recursive(value)
        #     elif isinstance(item, list):
        #         for elem in item:
        #             find_paths_recursive(elem)
        #
        # find_paths_recursive(self.draft_data)

        logger.info(f"Extracted {len(original_paths)} unique original material paths.")
        return list(original_paths)

    def update_project_name(self, new_name: str):
        """Updates the project name in the meta data."""
        if "draft_name" in self.meta_data:
            self.meta_data["draft_name"] = new_name
            logger.debug(f"Updated project name to: {new_name}")
        else:
            logger.warning("'draft_name' key not found in meta data.")

    def _recursive_update_paths(self, item, material_map):
        """Recursively finds and updates file paths within a nested structure."""
        if isinstance(item, dict):
            new_dict = {}
            for k, v in item.items():
                # Check if the value itself is a potential path string to update
                # Check common path keys used in JSON structures, add font_path
                potential_path_keys = [
                    "file_Path",
                    "path",
                    "filePath",
                    "source_path",
                    "relativePath",
                    "url",
                    "font_path",
                ]
                if k in potential_path_keys and isinstance(v, str):
                    original_path_str = v
                    # Try to find the corresponding final path using the original path or placeholder
                    # Ensure extra_info_value is treated as string even if None
                    extra_info_value = item.get("extra_info")
                    placeholder_base = (extra_info_value or "").split(".")[
                        0
                    ]  # Safely handle None
                    found_key = None
                    if placeholder_base and placeholder_base in material_map:
                        found_key = placeholder_base
                    elif original_path_str in material_map:
                        found_key = original_path_str

                    if found_key:
                        new_path_str = material_map[found_key]
                        if original_path_str != new_path_str:
                            # ★デバッグログ追加 (日本語化)
                            logger.debug(
                                f"キー '{k}' のパスをマップキー '{found_key}' を使用して更新: {original_path_str} -> {new_path_str}"
                            )
                            new_dict[k] = new_path_str
                        else:
                            new_dict[k] = v  # No change
                    else:
                        # If no specific mapping found, but value looks like a path AND exists in map values,
                        # maybe update it? This is risky without knowing the structure.
                        # For now, just keep the original if no key matches.
                        new_dict[k] = v  # No mapping found, keep original
                # Also check for paths hidden inside JSON strings
                elif isinstance(v, str):
                    try:
                        # Avoid trying to decode already processed path strings or simple strings
                        if not v.strip().startswith(("{", "[")):
                            raise json.JSONDecodeError("Not a JSON string", v, 0)

                        nested_data = json.loads(v)
                        replaced_nested_data = self._recursive_update_paths(
                            nested_data, material_map
                        )
                        new_json_string = json.dumps(
                            replaced_nested_data,
                            ensure_ascii=False,
                            separators=(",", ":"),
                        )
                        # ★デバッグログ追加 (日本語化)
                        if v != new_json_string:
                            logger.debug(f"キー '{k}' の JSON 文字列コンテンツを更新")
                        new_dict[k] = new_json_string

                    except json.JSONDecodeError:
                        # Not a JSON string or shouldn't be decoded, process recursively as is
                        # Basically, only recurse if it's a dictionary or list. Keep strings as is if not paths.
                        new_dict[k] = v  # Keep original string if not path/JSON
                else:
                    # Recursively process other values (dicts and lists)
                    new_dict[k] = self._recursive_update_paths(v, material_map)
            return new_dict
        elif isinstance(item, list):
            return [self._recursive_update_paths(elem, material_map) for elem in item]
        # Return non-dict/list/string items as is
        return item

    def update_material_paths(self, csv_row_data: dict):
        """Updates material file paths: 1. Point to TemplateMaterial, 2. Override with ChangeMaterial if specified in CSV."""
        project_name_from_csv = csv_row_data.get("ProjectName", self.project_path.name)
        material_final_path_map = {}  # Maps placeholder_base or original_path to final decided path

        if (
            not self.template_project_name
            or self.template_project_name == "UnknownTemplate"
        ):
            logger.error(
                "Cannot update material paths: Template project name is unknown."
            )
            return
        if not self.template_material_base:
            logger.error(
                "Cannot update material paths: Template material base path is not set."
            )
            return

        template_material_project_path = (
            Path(self.template_material_base) / self.template_project_name
        )
        logger.info(
            f"Determining final material paths (Template base: {template_material_project_path})"
        )

        # --- Determine Final Path for Each Material --- (Iterate through meta first)
        # This builds the map of which final path each material should have
        if "draft_materials" in self.meta_data:
            for material_group in self.meta_data["draft_materials"]:
                if material_group.get("type") == 0 and "value" in material_group:
                    for material in material_group["value"]:
                        original_file_path_str = material.get("file_Path")
                        placeholder_base = material.get("extra_info", "").split(".")[0]
                        final_path_str = (
                            None  # Stores the final path decided for this material
                        )
                        map_key = (
                            placeholder_base
                            if placeholder_base
                            else original_file_path_str
                        )  # Key for the map

                        # 1. Determine default path from TemplateMaterial
                        default_template_path_str = None
                        if original_file_path_str:
                            original_file_path = Path(original_file_path_str)
                            original_filename = original_file_path.name
                            material_type_folder = (
                                original_file_path.parent.name
                            )  # Assume parent is type

                            # Basic check if parent folder name looks like a known type
                            if (
                                material_type_folder
                                in FileSystemHandler.MATERIAL_SUBFOLDERS
                            ):
                                default_template_path = (
                                    template_material_project_path
                                    / material_type_folder
                                    / original_filename
                                )
                                default_template_path_str = str(
                                    default_template_path.resolve()
                                )
                                final_path_str = default_template_path_str  # Default is TemplateMaterial
                            else:
                                # Fallback if type cannot be determined from path
                                logger.warning(
                                    f"Could not determine material type folder from original path: {original_file_path_str}. Using original path as default."
                                )
                                final_path_str = original_file_path_str  # Keep original if type unknown
                        else:
                            # Skip if no original path found in meta
                            logger.warning(
                                f"Material missing original file_Path: {material.get('id', 'Unknown ID')}"
                            )
                            continue

                        # 2. Check CSV for override and search ChangeMaterial
                        if placeholder_base and placeholder_base in csv_row_data:
                            csv_filename = csv_row_data[placeholder_base]
                            if csv_filename:
                                if not self.change_material_base:
                                    logger.warning(
                                        f"Cannot search ChangeMaterial for '{csv_filename}': ChangeMaterial path not configured."
                                    )
                                else:
                                    # Re-determine material type based on placeholder for safety
                                    material_type = "".join(
                                        filter(str.isalpha, placeholder_base)
                                    )
                                    if (
                                        material_type
                                        in FileSystemHandler.MATERIAL_SUBFOLDERS
                                    ):
                                        change_path = FileSystemHandler.find_change_material(
                                            csv_filename=csv_filename,
                                            project_name=project_name_from_csv,
                                            material_type=material_type,
                                            change_material_base=self.change_material_base,
                                        )
                                        if change_path:
                                            logger.info(
                                                f"Using ChangeMaterial path for '{placeholder_base}': {change_path}"
                                            )
                                            final_path_str = change_path  # Override with ChangeMaterial path
                                        else:
                                            logger.warning(
                                                f"Override material '{csv_filename}' for key '{placeholder_base}' not found in ChangeMaterial. Using default: {final_path_str}"
                                            )
                                    else:
                                        logger.warning(
                                            f"Could not determine material type from placeholder '{placeholder_base}' for ChangeMaterial search."
                                        )
                            # else: No filename in CSV, use default path determined in step 1
                        # else: No placeholder or placeholder not in CSV, use default path

                        # Store the final decision for this material in the map
                        if map_key and final_path_str:
                            material_final_path_map[map_key] = final_path_str
                            # Also store mapping from original path if possible
                            if (
                                original_file_path_str
                                and original_file_path_str != map_key
                            ):
                                material_final_path_map[original_file_path_str] = (
                                    final_path_str
                                )

        logger.info(
            f"Final path map determined for {len(material_final_path_map)} material keys."
        )
        # logger.debug(f"Final Path Map: {material_final_path_map}") # Log map for debugging if needed

        # --- Apply Final Paths Recursively --- (Apply to both meta_data and draft_data)
        logger.info("Applying final paths to draft_meta_info.json...")
        self.meta_data = self._recursive_update_paths(
            self.meta_data, material_final_path_map
        )

        logger.info("Applying final paths to draft_info.json...")
        self.draft_data = self._recursive_update_paths(
            self.draft_data, material_final_path_map
        )

        logger.info("Finished updating material paths in both JSON files.")

    def replace_text_placeholders(self, csv_row_data: dict):
        """Recursively replaces text placeholders (e.g., ##text_00##) in draft_data."""
        self.draft_data = self._recursive_replace(self.draft_data, csv_row_data)
        logger.info("Finished replacing text placeholders.")

    def _recursive_replace(self, item, csv_row_data):
        """Helper function to recursively traverse and replace placeholders."""
        if isinstance(item, dict):
            return {
                k: self._recursive_replace(v, csv_row_data) for k, v in item.items()
            }
        elif isinstance(item, list):
            return [self._recursive_replace(elem, csv_row_data) for elem in item]
        elif isinstance(item, str):
            # Attempt to parse string as JSON first
            try:
                nested_data = json.loads(item)
                # If successful, recursively replace in the nested structure
                replaced_nested_data = self._recursive_replace(
                    nested_data, csv_row_data
                )
                # Return the modified structure as a JSON string
                # Use ensure_ascii=False for wider character support, separators to remove whitespace
                return json.dumps(
                    replaced_nested_data, ensure_ascii=False, separators=(",", ":")
                )
            except json.JSONDecodeError:
                # Not a JSON string, perform direct placeholder replacement
                original_value = item
                new_value = item
                for key, value in csv_row_data.items():
                    placeholder = f"##{key}##"
                    if placeholder in new_value:
                        # Ensure value is a string before replacing
                        new_value = new_value.replace(
                            placeholder, str(value) if value is not None else ""
                        )
                if new_value != original_value:
                    logger.debug(f"Replaced text: '{original_value}' -> '{new_value}'")
                return new_value
        else:
            return item

    def save_changes(self):
        """Saves the modified meta_data and draft_data back to their files."""
        logger.info(f"Saving changes to {self.meta_path} and {self.draft_path}")
        try:
            # Save with ensure_ascii=False for broader character support
            with open(self.meta_path, "w", encoding="utf-8") as f:
                json.dump(self.meta_data, f, indent=4, ensure_ascii=False)
            with open(self.draft_path, "w", encoding="utf-8") as f:
                json.dump(self.draft_data, f, indent=4, ensure_ascii=False)
            logger.info("Successfully saved changes.")
        except (IOError, TypeError) as e:
            logger.error(f"Error writing JSON files: {e}", exc_info=True)
            raise IOError(f"Could not save project files: {e}") from e


# FileSystemHandler のインポート位置は元に戻した
# from .file_system_handler import FileSystemHandler
