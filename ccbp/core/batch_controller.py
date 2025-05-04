# Placeholder for BatchController logic

from PySide6.QtCore import QObject, QThread, Slot, Qt, QTimer
from PySide6.QtWidgets import QLineEdit, QApplication
from .batch_worker import BatchWorker
from pathlib import Path
from PySide6.QtWidgets import QMessageBox, QFileDialog
from .config_manager import ConfigManager, \
    KEY_BATCH_CSV_FILE, \
    KEY_BATCH_TEMPLATE_DIR, \
    KEY_BATCH_TEMPLATE_MATERIAL_DIR, \
    KEY_BATCH_REPLACE_MATERIAL_DIR, \
    KEY_BATCH_OUTPUT_DIR, \
    KEY_BATCH_OUTPUT_CSV_DIR
import logging
import csv

# --- Import LicenseManager --- 
from .license_manager import LicenseManager
# --- End Import ---

class BatchController(QObject):
    def __init__(self, config_manager: ConfigManager, license_manager: LicenseManager, model=None, view=None):
        super().__init__()
        self.model = model
        self.view = view
        self.config_manager = config_manager
        self.license_manager = license_manager # Store LicenseManager
        self.worker = None
        self.worker_thread = None
        self.logger = logging.getLogger(__name__)
        self._last_batch_result: tuple | None = None
        self.logger.info("BatchController initialized")

    def set_view(self, view):
        """Sets the view and initializes connections."""
        self.view = view
        if self.view:
            self._init_connections()
            self.load_paths_from_config() # Load paths when view is set
        else:
            self.logger.warning("Attempted to set an invalid view for BatchController")

    def _init_connections(self):
        """Initialize signal-slot connections if view is available"""
        if self.view is None:
            self.logger.warning("View not provided to controller, cannot initialize connections.")
            return

        self.logger.info("Initializing batch controller connections")
        try:
            # Connect browse buttons using view's actual names to CONTROLLER slots
            if hasattr(self.view, 'browse_csv_button') and self.view.browse_csv_button:
                # Connect CSV button to controller's browse_csv_file slot
                self.view.browse_csv_button.clicked.connect(self.browse_csv_file)
            else:
                self.logger.warning("browse_csv_button not found or is None in the view.")

            if hasattr(self.view, 'browse_template_project_button') and self.view.browse_template_project_button:
                # Connect Template Project button to controller's browse_template_project slot
                self.view.browse_template_project_button.clicked.connect(self.browse_template_project)
            else:
                self.logger.warning("browse_template_project_button not found or is None in the view.")

            # Connect Template Material button to a new controller slot
            if hasattr(self.view, 'browse_template_material_button') and self.view.browse_template_material_button:
                self.view.browse_template_material_button.clicked.connect(self.browse_template_material_folder)
            else:
                self.logger.warning("browse_template_material_button not found or is None in the view.")

            # Connect Change Material button to a new controller slot
            if hasattr(self.view, 'browse_change_material_button') and self.view.browse_change_material_button:
                self.view.browse_change_material_button.clicked.connect(self.browse_change_material_folder)
            else:
                self.logger.warning("browse_change_material_button not found or is None in the view.")

            # Connect Output Projects button to a new controller slot
            if hasattr(self.view, 'browse_output_projects_button') and self.view.browse_output_projects_button:
                self.view.browse_output_projects_button.clicked.connect(self.browse_output_projects_folder)
            else:
                self.logger.warning("browse_output_projects_button not found or is None in the view.")

            # Connect Output CSV button to a new controller slot
            if hasattr(self.view, 'browse_output_csv_button') and self.view.browse_output_csv_button:
                self.view.browse_output_csv_button.clicked.connect(self.browse_output_csv_folder)
            else:
                self.logger.warning("browse_output_csv_button not found or is None in the view.")

            # Connect action buttons using view's actual names
            # Corrected name: run_batch_button
            if hasattr(self.view, 'run_batch_button') and self.view.run_batch_button:
                self.view.run_batch_button.clicked.connect(self.run_batch_processing)
            else:
                self.logger.warning("run_batch_button not found or is None in the view.")

            # Corrected name: cancel_batch_button
            if hasattr(self.view, 'cancel_batch_button') and self.view.cancel_batch_button:
                self.view.cancel_batch_button.clicked.connect(self.cancel_processing)
            else:
                self.logger.warning("cancel_batch_button not found or is None in the view.")

            # Connect path line edits (if needed for auto-saving or validation)
            # ...

            # --- Connect editingFinished signals for auto-save ---
            if hasattr(self.view, 'csv_path_edit'):
                self.view.csv_path_edit.editingFinished.connect(self._save_csv_path)
            if hasattr(self.view, 'template_project_path_edit'):
                self.view.template_project_path_edit.editingFinished.connect(self._save_template_project_path)
            if hasattr(self.view, 'template_material_base_edit'):
                self.view.template_material_base_edit.editingFinished.connect(self._save_template_material_path)
            if hasattr(self.view, 'change_material_base_edit'):
                self.view.change_material_base_edit.editingFinished.connect(self._save_change_material_path)
            if hasattr(self.view, 'output_projects_dir_edit'):
                self.view.output_projects_dir_edit.editingFinished.connect(self._save_output_projects_path)
            if hasattr(self.view, 'output_csv_dir_edit'):
                self.view.output_csv_dir_edit.editingFinished.connect(self._save_output_csv_path)
            # --- End Connect editingFinished ---

            self.logger.info("Batch view signals connected.")
        except Exception as e:
            self.logger.exception(f"Unexpected error connecting batch view signals: {e}")

    def load_paths_from_config(self):
        """Loads paths from config and updates the view."""
        self.logger.info("Loading batch paths from config...")
        if not self.view or not self.config_manager:
            self.logger.warning("Cannot load batch paths: View or ConfigManager not set.")
            return
        try:
            # Load paths using the correct widget names from BatchTabView
            self.view.csv_path_edit.setText(self.config_manager.get(KEY_BATCH_CSV_FILE, ""))
            self.view.template_project_path_edit.setText(self.config_manager.get(KEY_BATCH_TEMPLATE_DIR, ""))
            self.view.template_material_base_edit.setText(self.config_manager.get(KEY_BATCH_TEMPLATE_MATERIAL_DIR, ""))
            self.view.change_material_base_edit.setText(self.config_manager.get(KEY_BATCH_REPLACE_MATERIAL_DIR, ""))
            self.view.output_projects_dir_edit.setText(self.config_manager.get(KEY_BATCH_OUTPUT_DIR, ""))
            self.view.output_csv_dir_edit.setText(self.config_manager.get(KEY_BATCH_OUTPUT_CSV_DIR, ""))
            self.logger.info("Successfully loaded batch paths into view.")
        except AttributeError as e:
            self.logger.error(f"Error setting text on view widgets during load: {e}. Widget might be missing or named incorrectly.")
        except Exception as e:
            self.logger.exception(f"Unexpected error loading batch paths from config: {e}")

    def browse_csv_file(self):
        """Open a file dialog for CSV file and update view's LineEdit."""
        if not self.view:
            return
        start_dir = self.config_manager.get(KEY_BATCH_CSV_FILE, str(Path.home()))
        start_dir = str(Path(start_dir).parent) if Path(start_dir).is_file() else start_dir
        file_path, _ = QFileDialog.getOpenFileName(self.view, "CSVファイルを選択", start_dir, "CSV Files (*.csv)")
        if file_path:
            self.view.csv_path_edit.setText(file_path)
            self.config_manager.set(KEY_BATCH_CSV_FILE, file_path)
            self.config_manager.save()
            self.logger.info(f"CSV file selected and saved: {file_path}")

    def browse_template_project(self):
        """Open a directory dialog for CapCut project folder and update view's LineEdit."""
        if not self.view:
            return
        start_dir = self.config_manager.get(KEY_BATCH_TEMPLATE_DIR, str(Path.home()))
        dir_path = QFileDialog.getExistingDirectory(self.view, "テンプレートプロジェクトフォルダを選択", start_dir)
        if dir_path:
            self.view.template_project_path_edit.setText(dir_path)
            self.config_manager.set(KEY_BATCH_TEMPLATE_DIR, dir_path)
            self.config_manager.save()
            self.logger.info(f"Template folder selected and saved: {dir_path}")

    def browse_template_material_folder(self):
        """Open a directory dialog for template material base and update view."""
        if not self.view:
            return
        start_dir = self.config_manager.get(KEY_BATCH_TEMPLATE_MATERIAL_DIR, str(Path.home()))
        dir_path = QFileDialog.getExistingDirectory(self.view, "テンプレート素材フォルダを選択", start_dir)
        if dir_path:
            self.view.template_material_base_edit.setText(dir_path)
            self.config_manager.set(KEY_BATCH_TEMPLATE_MATERIAL_DIR, dir_path)
            self.config_manager.save()
            self.logger.info(f"Template material folder selected and saved: {dir_path}")

    def browse_change_material_folder(self):
        """Open a directory dialog for change material base and update view."""
        if not self.view:
            return
        start_dir = self.config_manager.get(KEY_BATCH_REPLACE_MATERIAL_DIR, str(Path.home()))
        dir_path = QFileDialog.getExistingDirectory(self.view, "リプレイス素材フォルダを選択", start_dir)
        if dir_path:
            self.view.change_material_base_edit.setText(dir_path)
            self.config_manager.set(KEY_BATCH_REPLACE_MATERIAL_DIR, dir_path)
            self.config_manager.save()
            self.logger.info(f"Replace material folder selected and saved: {dir_path}")

    def browse_output_projects_folder(self):
        """Open a directory dialog for project output and update view."""
        if not self.view:
            return
        start_dir = self.config_manager.get(KEY_BATCH_OUTPUT_DIR, str(Path.home()))
        dir_path = QFileDialog.getExistingDirectory(self.view, "出力プロジェクトフォルダを選択", start_dir)
        if dir_path:
            self.view.output_projects_dir_edit.setText(dir_path)
            self.config_manager.set(KEY_BATCH_OUTPUT_DIR, dir_path)
            self.config_manager.save()
            self.logger.info(f"Output folder selected and saved: {dir_path}")

    def browse_output_csv_folder(self):
        """Open a directory dialog for CSV report output and update view."""
        if not self.view:
            return
        start_dir = self.config_manager.get(KEY_BATCH_OUTPUT_CSV_DIR, str(Path.home()))
        dir_path = QFileDialog.getExistingDirectory(self.view, "出力CSVフォルダを選択", start_dir)
        if dir_path:
            self.view.output_csv_dir_edit.setText(dir_path)
            self.config_manager.set(KEY_BATCH_OUTPUT_CSV_DIR, dir_path)
            self.config_manager.save()
            self.logger.info(f"Output CSV folder selected and saved: {dir_path}")

    def run_batch_processing(self):
        """Handles the button click: Performs IMMEDIATE UI feedback and schedules worker start."""
        self.logger.debug("run_batch_processing clicked.")
        # --- IMMEDIATE UI Feedback ONLY --- 
        if hasattr(self.view, 'run_batch_button'):
            self.logger.debug("Disabling run button.")
            self.view.run_batch_button.setEnabled(False)
        if self.view:
            self.logger.debug("Updating status to 'リクエスト受付...'.")
            self.view.update_status("リクエスト受付...")
            QApplication.processEvents() # Force immediate UI update
        else:
            self.logger.warning("View not set when run_batch_processing clicked.")
            # Re-enable button if view is somehow missing at click time?
            if hasattr(self.view, 'run_batch_button'): self.view.run_batch_button.setEnabled(True)
            return
        # --- END IMMEDIATE UI Feedback ---

        # --- Schedule the actual worker start using QTimer --- 
        self.logger.debug("Scheduling _start_worker_thread with QTimer.singleShot(0).")
        QTimer.singleShot(0, self._start_worker_thread)

    def _start_worker_thread(self):
        """Prepares and starts the background worker thread. Called via QTimer."""
        self.logger.info("_start_worker_thread called.")
        # All checks and worker setup moved here
        
        # --- Pre-checks (moved from run_batch_processing) ---
        if not self.view: # Should theoretically not happen if check in run_batch_processing passed
            self.logger.error("Error: View is None in _start_worker_thread. Aborting.")
            # Reset UI just in case
            if hasattr(self.view, 'run_batch_button'): self.view.run_batch_button.setEnabled(True)
            if self.view: self.view.update_status("エラー")
            return
            
        if self.worker_thread and self.worker_thread.isRunning():
            self.logger.warning("Warning: Processing is already running (checked again in _start_worker_thread).")
            QMessageBox.warning(self.view, "処理中", "既にバッチ処理が実行中です。")
            # Reset UI state 
            if hasattr(self.view, 'run_batch_button'): self.view.run_batch_button.setEnabled(True)
            if self.view: self.view.update_status("準備完了")
            return
            
        if not self.license_manager:
            self.logger.error("LicenseManager is not available when creating BatchWorker!")
            QMessageBox.critical(self.view, "内部エラー", "ライセンス管理機能が見つかりません。")
            # Reset UI state
            if hasattr(self.view, 'run_batch_button'): self.view.run_batch_button.setEnabled(True) 
            if hasattr(self.view, 'cancel_batch_button'): self.view.cancel_batch_button.setEnabled(False)
            if self.view: self.view.update_status("準備完了")
            return
        # --- End Pre-checks ---
        
        paths = self.view.get_paths()
        csv_file_path = paths.get('csv_path')
        if not csv_file_path:
             self.logger.warning("CSV Path appears empty in view (checked in _start_worker_thread).")
             # Let worker handle the error if the path is truly invalid/missing after this point

        # --- Prepare and start the worker thread --- 
        if self.view:
            self.logger.debug("Updating status to '処理を開始しています...' and logging CSV path.")
            self.view.update_status("処理を開始しています...") 
            self.view.append_log(f"CSVファイルを読み込み開始: {csv_file_path if csv_file_path else '（パス未指定）'}") 
            QApplication.processEvents() # Update UI before potential blocking operations

        # Enable cancel button, reset progress bar
        if hasattr(self.view, 'cancel_batch_button'): self.view.cancel_batch_button.setEnabled(True)
        if hasattr(self.view, 'progress_bar'): self.view.progress_bar.setValue(0)

        self.logger.info("Creating and starting BatchWorker thread...")
        try:
            self.worker_thread = QThread()
            self.worker = BatchWorker(paths, self.license_manager)
            self.worker.moveToThread(self.worker_thread)
    
            # --- Connect Signals --- 
            self.worker.finished.connect(self._on_worker_finished)
            self.worker.status_update.connect(self._on_worker_status_update)
            self.worker.progress_updated.connect(self._on_worker_progress_update)
            self.worker.log_message.connect(self._on_worker_log_message) 
            self.worker_thread.started.connect(self.worker.run)
            self.worker.finished.connect(self.worker_thread.quit)
            self.worker.finished.connect(self.worker.deleteLater)
            self.worker_thread.finished.connect(self.worker_thread.deleteLater)
            self.worker_thread.finished.connect(self._reset_ui_on_cancel_or_finish) 
            self.worker_thread.finished.connect(self._clear_worker_references)
            # --- End Connect Signals --- 
    
            self.worker_thread.start()
            self.logger.info("BatchWorker thread started successfully.")
            
        except Exception as e:
            self.logger.exception("Error during worker thread creation/start")
            QMessageBox.critical(self.view, "スレッド開始エラー", f"バックグラウンド処理の開始に失敗しました:\n{e}")
            # Reset UI state fully if thread failed to start
            if hasattr(self.view, 'run_batch_button'): self.view.run_batch_button.setEnabled(True) 
            if hasattr(self.view, 'cancel_batch_button'): self.view.cancel_batch_button.setEnabled(False)
            if self.view: self.view.update_status("エラー")
            # Ensure references are cleared if worker/thread objects were partially created
            self.worker = None
            self.worker_thread = None
            
    def cancel_processing(self):
        print("Cancel processing requested")
        if self.worker:
            self.worker.cancel()
        else:
            print("Warning: No worker process to cancel.")
        
    # --- Slots for Worker Signals --- 
    @Slot(bool, str) # Added type hints for clarity
    def _on_worker_finished(self, success: bool, result_message: str):
        """Handles the finished signal from BatchWorker. Stores result for later alert."""
        self.logger.info(f"BatchWorker finished signal received. Success: {success}, Message: {result_message}")
        # Store the result to show alert AFTER UI reset
        self.logger.debug(f"Storing batch result: Success={success}, Message='{result_message}'") # ADD LOG
        self._last_batch_result = (success, result_message)
        self.logger.debug(f"Stored _last_batch_result: {self._last_batch_result}") # ADD LOG
        # Remove alert from here
        # if self.view: ... QMessageBox ...

        # Note: UI reset is now handled when the worker_thread finishes
        # self._reset_ui_on_cancel_or_finish() # Removed from here

    @Slot(str)
    def _on_worker_status_update(self, message):
        if self.view:
            self.view.update_status(message)

    def _on_worker_progress_update(self, value):
        if self.view:
            self.view.update_progress(value)

    def _on_worker_log_message(self, message):
        if self.view:
            self.view.append_log(message)
            
    # --- Helper Methods --- 
    def _clear_worker_references(self):
        """Clear references to worker and thread after thread finishes."""
        print("Clearing worker and thread references.")
        self.worker = None
        self.worker_thread = None

    def _reset_ui_on_cancel_or_finish(self):
        """Resets buttons and shows completion alert after processing ends or is cancelled."""
        self.logger.debug("--- _reset_ui_on_cancel_or_finish called ---")
        # self._close_processing_popup() # Removed call
        # --- Reset UI --- 
        self.logger.debug("Attempting to reset batch UI.")
        if self.view:
            self.view.set_buttons_enabled(run_enabled=True, cancel_enabled=False)
            if self._last_batch_result is None or self._last_batch_result[0] is True:
                 self.view.update_status("準備完了") 
            self.logger.debug("Batch UI elements reset.")
        else:
            self.logger.warning("Cannot reset batch UI, view is not set.")
        # --- Show pending completion alert --- 
        self.logger.debug(f"Checking if batch alert needs to be shown. _last_batch_result: {self._last_batch_result}") # ADD LOG
        if self._last_batch_result is not None:
            self.logger.debug("Proceeding to show batch completion alert.") # ADD LOG
            success, result_message = self._last_batch_result
            if self.view: # Check if view exists
                self.logger.debug("View exists, attempting to show QMessageBox for batch.") # ADD LOG
                if success:
                    msg = "バッチ処理が正常に完了しました。"
                    if result_message: # Append report path if provided
                        msg += f"\nレポートファイル: {result_message}"
                    self.logger.debug(f"Showing batch success alert: {msg}") # ADD LOG
                    QMessageBox.information(self.view, "バッチ処理完了", msg)
                else:
                    # Use the error message from the worker signal
                    alert_msg = f"バッチ処理中にエラーが発生しました。\n詳細はログを確認してください。\n({result_message})"
                    self.logger.debug(f"Showing batch warning alert: {alert_msg}") # ADD LOG
                    QMessageBox.warning(self.view, "バッチ処理エラー", alert_msg)
                self.logger.debug("Finished showing QMessageBox for batch.") # ADD LOG
            else:
                self.logger.warning("Cannot show batch completion alert because view is None.") # ADD LOG

            self._last_batch_result = None # Clear the stored result
            self.logger.debug("Cleared _last_batch_result.") # ADD LOG
        else:
            self.logger.debug("No batch result stored, skipping alert.") # ADD LOG
        # -------------------------------------------------------

    def cleanup_workers(self):
        """Stops and cleans up the worker and thread if they exist."""
        if self.worker_thread and self.worker_thread.isRunning():
            print("Cleaning up existing worker and thread...")
            if self.worker:
                print("Signalling worker to cancel...")
                self.worker.cancel() 
            
            print("Quitting thread...")
            self.worker_thread.quit()
            print("Waiting for thread to finish...")
            if not self.worker_thread.wait(2000): # Wait up to 2 seconds
                 print("Warning: Thread did not finish gracefully. Terminating.")
                 self.worker_thread.terminate() # Force terminate if doesn't quit
                 self.worker_thread.wait() # Wait after terminating
            print("Thread finished.")
        elif self.worker_thread: 
             print("Thread exists but is not running. Proceeding with cleanup.")
        else:
             print("No active thread to clean up.")
             return # Nothing to clean up

        # At this point, thread is finished or terminated
        # DeleteLater was scheduled via finished signal connection
        # Just clear references immediately after ensuring thread stopped
        self._clear_worker_references() 
        # self._close_processing_popup() # Removed call

    def finalize(self):
        """Called when the tab is changed or window is closed."""
        print("BatchController finalizing...")
        self.cleanup_workers() # Ensure workers are stopped
        # self._close_processing_popup() # Already called by cleanup_workers
        print("BatchController finalized")

    # --- Slots for editingFinished signals ---
    @Slot()
    def _save_csv_path(self):
        self._save_path_from_edit(self.view.csv_path_edit, KEY_BATCH_CSV_FILE, is_file=True)

    @Slot()
    def _save_template_project_path(self):
        self._save_path_from_edit(self.view.template_project_path_edit, KEY_BATCH_TEMPLATE_DIR, is_dir=True)

    @Slot()
    def _save_template_material_path(self):
        self._save_path_from_edit(self.view.template_material_base_edit, KEY_BATCH_TEMPLATE_MATERIAL_DIR, is_dir=True)

    @Slot()
    def _save_change_material_path(self):
        # Allow empty path for optional field
        self._save_path_from_edit(self.view.change_material_base_edit, KEY_BATCH_REPLACE_MATERIAL_DIR, is_dir=True, allow_empty=True)

    @Slot()
    def _save_output_projects_path(self):
        # Allow non-existent path for output dir (will be created)
        self._save_path_from_edit(self.view.output_projects_dir_edit, KEY_BATCH_OUTPUT_DIR, is_dir=True, check_exists=False)

    @Slot()
    def _save_output_csv_path(self):
        # Allow non-existent path for output dir (will be created)
        self._save_path_from_edit(self.view.output_csv_dir_edit, KEY_BATCH_OUTPUT_CSV_DIR, is_dir=True, check_exists=False)

    # --- Helper for saving paths from LineEdits ---
    def _save_path_from_edit(self, line_edit: QLineEdit, config_key: str, is_file: bool = False, is_dir: bool = False, allow_empty: bool = False, check_exists: bool = True):
        """Generic helper to save path from a QLineEdit on editingFinished."""
        if not line_edit or not self.config_manager:
            self.logger.warning(f"Cannot save path for {config_key}, View or ConfigManager not available.")
            return
        try:
            path_str = line_edit.text().strip()
            last_saved = self.config_manager.get(config_key, "")

            if not path_str:
                if allow_empty:
                    if path_str != last_saved: # Save only if changed to empty
                        self.config_manager.set(config_key, "")
                        self.config_manager.save()
                        self.logger.info(f"Saved empty path for optional key {config_key}.")
                    return # Path is empty, allowed, do nothing else or saved if needed
                else:
                    self.logger.warning(f"Attempted to save empty path for required key {config_key}. Reverting.")
                    line_edit.setText(last_saved) # Revert UI
                    return

            # --- Path Validation ---
            try:
                path_obj = Path(path_str)
                valid = True
                if check_exists:
                    if is_file and not path_obj.is_file():
                        self.logger.warning(f"Path for {config_key} is not a valid file: {path_str}. Reverting.")
                        valid = False
                    elif is_dir and not path_obj.is_dir():
                         # Special case for output dirs: allow non-existent but not files
                         if config_key in [KEY_BATCH_OUTPUT_DIR, KEY_BATCH_OUTPUT_CSV_DIR] and path_obj.is_file():
                              self.logger.warning(f"Path for output key {config_key} is a file, must be a directory: {path_str}. Reverting.")
                              valid = False
                         elif config_key not in [KEY_BATCH_OUTPUT_DIR, KEY_BATCH_OUTPUT_CSV_DIR]:
                              self.logger.warning(f"Path for {config_key} is not a valid directory: {path_str}. Reverting.")
                              valid = False
                         # If it's an output dir and doesn't exist, valid = True (will be created later)

                if valid and path_str != last_saved:
                    self.config_manager.set(config_key, path_str)
                    self.config_manager.save()
                    self.logger.info(f"Path for {config_key} saved via edit: {path_str}")
                elif not valid:
                    line_edit.setText(last_saved) # Revert UI if invalid

            except Exception as path_e: # Catch potential errors during Path() creation etc.
                self.logger.error(f"Error validating path '{path_str}' for {config_key}: {path_e}. Reverting.")
                line_edit.setText(last_saved)

        except Exception as e:
            self.logger.exception(f"Error saving path for {config_key} from edit: {e}")
            # Optionally revert UI on unexpected errors too
            last_saved = self.config_manager.get(config_key, "")
            line_edit.setText(last_saved)

    # --- Placeholder for license validation if needed
    # def validate_license_input(self):
    #     key = self.view.get_license_key()
    #     # ... validation logic ... 