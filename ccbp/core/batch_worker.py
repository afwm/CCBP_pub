# -*- coding: utf-8 -*-
import os
import shutil
import csv
import time
from pathlib import Path
from PySide6.QtCore import QObject, Signal, QThread

# Import the core handlers this worker will use
from .file_system_handler import FileSystemHandler
from .capcut_handler import CapcutHandler
from .license_manager import LicenseManager

# Assuming logging is configured elsewhere
import logging
logger = logging.getLogger(__name__)

# Custom exception for cleaner cancellation flow
class OperationCancelledError(Exception):
    pass

class BatchWorker(QObject):
    """Performs the CapCut template batch processing in a separate thread."""
    
    # --- Signals --- 
    finished = Signal(bool, str) # success(bool), report_file_path(str) or error_message(str)
    # error_occurred = Signal(str) # Deprecated, using finished(False, msg)
    status_update = Signal(str) # For the status label
    progress_updated = Signal(int) # Overall progress (0-100)
    log_message = Signal(str) # For the log view

    def __init__(self, paths: dict, license_manager: LicenseManager):
        super().__init__()
        self._paths = paths
        self._license_manager = license_manager
        self._is_cancelled = False
        self._csv_data = []
        self.logger = logging.getLogger(__name__)
        # Handlers are initialized here if needed, or passed
        self.fs_handler = FileSystemHandler()
        self.capcut_handler = None # Initialize later with material map
        logger.info("BatchWorker initialized.")
        logger.debug(f" BatchWorker Paths Received: {self._paths}")

    def _validate_paths(self) -> tuple[bool, str]:
        """Validates the paths stored in self._paths. 
           Returns (True, "") on success, or (False, error_message) on failure.
        """
        error_messages = []
        # Define keys matching the dictionary returned by BatchTabView.get_paths()
        csv_path_key = 'csv_path'
        template_project_path_key = 'template_project_path'
        template_material_base_key = 'template_material_base'
        change_material_base_key = 'change_material_base' 
        output_projects_dir_key = 'output_projects_dir'
        output_csv_dir_key = 'output_csv_dir'

        # Files to check for existence
        required_files = {
            csv_path_key: self._paths.get(csv_path_key),
        }
        # Directories to check for existence (and create output dirs if needed)
        required_dirs = {
            template_project_path_key: self._paths.get(template_project_path_key),
            template_material_base_key: self._paths.get(template_material_base_key),
            change_material_base_key: self._paths.get(change_material_base_key), 
            output_projects_dir_key: self._paths.get(output_projects_dir_key),
            output_csv_dir_key: self._paths.get(output_csv_dir_key),
        }

        for key, path_str in required_files.items():
            if not path_str:
                error_messages.append(f"エラー: {key} ファイルのパスが指定されていません。")
                continue
            try:
                path = Path(path_str)
                if not path.is_file():
                    error_messages.append(f"エラー: 指定された {key} ファイルが見つからないか、ファイルではありません: {path_str}")
            except Exception as e:
                 error_messages.append(f"エラー: {key} パスが無効です ({e}): {path_str}")

        for key, path_str in required_dirs.items():
            is_required = key not in [change_material_base_key]
            
            if not path_str:
                if is_required:
                    error_messages.append(f"エラー: {key} フォルダのパスが指定されていません。")
                continue 
            
            try:
                path = Path(path_str)
                if not path.is_dir():
                    if key in [output_projects_dir_key, output_csv_dir_key]:
                        try:
                            path.mkdir(parents=True, exist_ok=True)
                            logger.info(f"Output directory created: {path_str}")
                        except Exception as e:
                             error_messages.append(f"エラー: 出力フォルダ '{key}' を作成できませんでした: {path_str}\n{e}")
                    else:
                        error_messages.append(f"エラー: 指定された {key} フォルダが見つからないか、フォルダではありません: {path_str}")
            except Exception as e:
                 error_messages.append(f"エラー: {key} パスが無効です ({e}): {path_str}")

        if error_messages:
            full_error_message = "\n".join(error_messages)
            logger.error(f"Path validation failed in worker:\n{full_error_message}")
            return False, full_error_message
            
        logger.info("Path validation successful in worker.")
        return True, ""

    def run(self):
        """Executes the batch processing loop after path validation and loading CSV data."""
        processed_count = 0
        error_count = 0
        generated_project_names = []
        start_time = time.time()
        
        try:
            # --- ADDED: License Check at the beginning --- 
            if not self._license_manager:
                 self.logger.error("LicenseManager not provided to BatchWorker.")
                 self.finished.emit(False, "内部エラー: ライセンス管理機能がありません。")
                 return

            can_process, message = self._license_manager.can_process_batch()
            if not can_process:
                self.logger.warning(f"Worker: Batch processing blocked by license: {message}")
                self.finished.emit(False, message) # Emit finish signal with license error
                return # Stop processing
            self.logger.info("Worker: License check passed.")
            # --- END License Check ---
            
            # --- Step 1: Validate Paths --- 
            self.status_update.emit("パスを検証中...")
            logger.info("Worker validating paths...")
            is_valid, error_msg = self._validate_paths()
            if not is_valid:
                 self.status_update.emit("エラー: パス設定を確認") # Update status
                 self.finished.emit(False, f"パス検証エラー:\n{error_msg}")
                 return
            logger.info("Worker path validation successful.")
            # self.status_update.emit("パス検証完了") # Optional status update here
            # -------------------------------

            # --- Step 2: Load CSV Data --- 
            csv_file_path = self._paths.get('csv_path') # Get CSV path now
            self.status_update.emit("CSV を読み込み中...") # Update status before loading
            logger.info(f"Worker starting CSV load from: {csv_file_path}")
            try:
                # Use utf-8-sig to handle potential BOM
                with open(csv_file_path, mode='r', newline='', encoding='utf-8-sig') as file:
                    reader = csv.DictReader(file)
                    # --- Basic CSV header validation --- 
                    required_headers = ["id", "ProjectName"]
                    if not reader.fieldnames:
                         raise ValueError("CSVファイルが空か、ヘッダー行が読み取れません。")
                    if not all(header in reader.fieldnames for header in required_headers):
                        missing = [h for h in required_headers if h not in reader.fieldnames]
                        raise ValueError(f"CSVヘッダーに必要な列がありません: {', '.join(missing)}")
                    # --- End Basic Validation --- 
                    self._csv_data = list(reader) # Read all rows into memory
                logger.info(f"Successfully loaded {len(self._csv_data)} rows from CSV in worker.")
                self.status_update.emit(f"CSV読み込み完了 ({len(self._csv_data)} 件)。処理を開始...")
            except FileNotFoundError:
                logger.error(f"CSV file not found by worker: {csv_file_path}")
                err_msg = f"指定されたCSVファイルが見つかりません:\n{csv_file_path}"
                self.status_update.emit(f"エラー: CSVファイルが見つかりません")
                raise FileNotFoundError(err_msg)
            except ValueError as ve:
                logger.error(f"CSV validation error in worker: {ve}")
                err_msg = f"CSVファイルの形式に問題があります:\n{ve}"
                self.status_update.emit(f"エラー: CSV形式の問題")
                raise ValueError(err_msg)
            except Exception as e:
                logger.exception(f"Error reading or processing CSV file {csv_file_path} in worker: {e}")
                err_msg = f"CSVファイルの読み込み中にエラー:\n{e}"
                self.status_update.emit(f"エラー: CSV読み込み失敗")
                raise IOError(err_msg)
            # --- End Load CSV Data --- 

            total_items = len(self._csv_data)
            if total_items == 0:
                self.log_message.emit("処理対象のデータがありません。")
                self.finished.emit(True, "") # Successful completion, no report needed
                return

            self.progress_updated.emit(0)

            # --- Path setup using validated self._paths --- 
            # No need for separate validation here anymore
            # Retrieve paths needed for the loop
            try:
                template_project_path = Path(self._paths.get('template_project_path', ''))
                template_material_base = Path(self._paths.get('template_material_base', ''))
                change_material_base = Path(self._paths.get('change_material_base', ''))
                output_projects_dir = Path(self._paths.get('output_projects_dir', ''))
                output_csv_dir = Path(self._paths.get('output_csv_dir', ''))
            except Exception as e:
                 logger.exception(f"Error creating Path objects from validated paths: {e}")
                 raise RuntimeError(f"パス設定の内部エラー: {e}")
            # ----------------------------------------------

            for index, row_data in enumerate(self._csv_data):
                item_num = index + 1
                progress = int(((item_num - 1) / total_items) * 100) 
                self.progress_updated.emit(progress)
                
                if self._is_cancelled:
                    raise OperationCancelledError("処理ループ中にキャンセルされました")

                project_name = row_data.get('ProjectName')
                if not project_name:
                    log_msg = f"項目 {item_num}: CSVに 'ProjectName' がありません。スキップします。"
                    self.log_message.emit(log_msg)
                    logger.warning(log_msg)
                    error_count += 1
                    continue

                self.status_update.emit(f"項目 {item_num}/{total_items}: '{project_name}' を処理中...")
                self.log_message.emit(f"--- 項目 {item_num}: {project_name} ---")
                logger.info(f"--- Processing item {item_num}/{total_items}: {project_name} ---")
                logger.debug(f"Processing row data: {row_data}")

                copied_project_path_str = None
                try:
                    self.log_message.emit("1. テンプレートをコピー中...")
                    logger.debug("Executing FileSystemHandler.copy_template_project...")
                    copied_project_path_str = FileSystemHandler.copy_template_project(
                        str(template_project_path), # Use path variable
                        str(output_projects_dir),   # Use path variable
                        project_name
                    )
                    if not copied_project_path_str:
                        raise RuntimeError("テンプレートのコピーに失敗しました。FileSystemHandler logged details.") 
                    self.log_message.emit(f"   -> コピー先: {copied_project_path_str}")
                    logger.info(f"Template copied successfully to: {copied_project_path_str}")

                    if self._is_cancelled:
                        raise OperationCancelledError(f"テンプレートコピー後にキャンセル ({project_name})")

                    self.log_message.emit("2. CapCutプロジェクトファイルを処理中...")
                    logger.debug(f"Initializing CapcutHandler for {copied_project_path_str}...")
                    self.capcut_handler = CapcutHandler(copied_project_path_str)
                    
                    name_updated = self.capcut_handler.update_project_name(project_name)
                    logger.debug(f"Project name update result: {name_updated}")

                    self.log_message.emit("   - 素材パスとテキストを更新中...")
                    logger.debug("Executing capcut_handler.update_material_paths...")
                    update_success = self.capcut_handler.update_material_paths(
                        row_data, 
                        str(template_material_base), # Use path variable
                        str(change_material_base) if change_material_base else "" # Use path variable
                    )
                    self.status_update.emit(f"項目 {item_num}/{total_items}: '{project_name}' パス/テキスト置換 {'完了' if update_success else '失敗'}")
                    logger.info(f"Material path and text update process completed for {project_name}. Success: {update_success}")
                    if not update_success:
                        raise RuntimeError("Failed to update material paths or text.")
                    
                    if self._is_cancelled:
                        raise OperationCancelledError(f"JSON変更後にキャンセル ({project_name})")

                    self.log_message.emit("   - 変更を保存中...")
                    logger.debug("Executing capcut_handler.save_changes...")
                    saved = self.capcut_handler.save_changes()
                    if not saved:
                        raise RuntimeError("変更されたJSONファイルの保存に失敗しました。CapcutHandler logged details.")
                    logger.info(f"Changes saved successfully for {project_name}.")
                        
                    self.log_message.emit(f"   -> プロジェクト '{project_name}' の処理が正常に完了しました。")
                    logger.info(f"Successfully processed item {item_num}: {project_name}")
                    processed_count += 1
                    generated_project_names.append(project_name)

                except OperationCancelledError as cancel_e:
                     raise cancel_e
                except (FileNotFoundError, ValueError, NotADirectoryError, RuntimeError, Exception) as item_e:
                    log_msg = f"項目 {item_num} ({project_name}): 処理中にエラー: {item_e}"
                    self.log_message.emit(log_msg)
                    logger.exception(log_msg)
                    error_count += 1
                    continue 

            # --- Loop Finished --- 
            self.progress_updated.emit(100)
            end_time = time.time()
            duration = end_time - start_time
            final_message = f"バッチ処理完了 ({duration:.1f}秒). {processed_count}件成功, {error_count}件エラー."
            self.log_message.emit(final_message)
            logger.info(final_message)
            self.status_update.emit(f"完了 ({processed_count}件成功, {error_count}件エラー)")
            
            report_path = None
            if generated_project_names:
                 self.log_message.emit("完了レポートCSVを作成中...")
                 report_path = FileSystemHandler.generate_output_csv_path(str(output_csv_dir)) # Use path variable
                 if report_path:
                     write_ok = FileSystemHandler.write_output_csv(report_path, generated_project_names)
                     if write_ok:
                          self.log_message.emit(f"レポートを保存しました: {report_path}")
                     else:
                          self.log_message.emit(f"警告: レポートCSVの書き込みに失敗しました ({report_path})")
                          report_path = "" 
                 else:
                      self.log_message.emit("警告: レポートCSVのパス生成に失敗しました。")
                      report_path = "" 
            
            self.finished.emit(error_count == 0, report_path if error_count == 0 and report_path is not None else f"{error_count}件のエラーが発生しました。詳細はログを確認してください。")

        except OperationCancelledError as e:
            # Catch cancellation from anywhere in the process
            logger.info(f"Batch processing cancelled by user: {e}")
            self.status_update.emit("キャンセルされました")
            self.log_message.emit(f"処理がユーザーによってキャンセルされました。 ({processed_count}件成功, {error_count}件エラー)")
            self.finished.emit(False, "処理がキャンセルされました。") 
            
        # <<< MODIFIED: Catch specific errors from CSV loading >>>
        except (FileNotFoundError, ValueError, IOError) as e:
            # Catch errors happening outside the loop (e.g., initial path validation OR CSV loading)
            logger.exception(f"バッチ処理中にエラーが発生しました（ファイル/形式）: {e}")
            error_msg = f"エラー: {e}"
            self.status_update.emit("エラー発生")
            self.log_message.emit(error_msg)
            self.finished.emit(False, error_msg)
        # <<< END MODIFIED >>>
        except Exception as e:
            # Catch other unexpected errors
            logger.exception(f"バッチ処理中に予期せぬエラーが発生しました: {e}")
            error_msg = f"予期せぬエラーが発生しました: {e}"
            self.status_update.emit("エラー発生")
            self.log_message.emit(error_msg)
            self.finished.emit(False, error_msg)

    def cancel(self):
        """Signals the worker to stop processing at the next check point."""
        self.log_message.emit("キャンセル要求を受信しました。現在の項目の完了後に停止します...")
        self._is_cancelled = True 