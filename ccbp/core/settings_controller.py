# Placeholder for SettingsController logic

from PySide6.QtCore import QObject, Slot, Signal, QThread # QThread added
from PySide6.QtWidgets import QMessageBox, QFileDialog # Corrected import
from ccbp.core.config_manager import (
    ConfigManager,
    KEY_WORKING_DIRECTORY,
    KEY_LICENSE_KEY,
    # Removed crop specific keys from imports as they are no longer used here
    # KEY_CROP_INPUT_DIR,
    # KEY_CROP_OUTPUT_DIR,
    # KEY_PREVIEW_SAVE_DIR
    # --- Import Cache Keys --- 
    KEY_LICENSE_STATUS,
    KEY_LICENSE_EXPIRES,
    KEY_LICENSE_VALIDATED_AT,
    KEY_LICENSE_LAST_MESSAGE,
    KEY_BATCH_CSV_FILE,
    KEY_BATCH_TEMPLATE_DIR,
    KEY_BATCH_TEMPLATE_MATERIAL_DIR,
    KEY_BATCH_REPLACE_MATERIAL_DIR,
    KEY_BATCH_OUTPUT_DIR,
    KEY_BATCH_OUTPUT_CSV_DIR,
    # --- Import Crop Keys needed for reset --- 
    KEY_CROP_INPUT_DIR,
    KEY_CROP_OUTPUT_DIR
    # --- End Import --- 
)
from ccbp.core.license_manager import LicenseManager # LicenseWorker removed
from ccbp.core.workers.license_worker import LicenseWorker # Import LicenseWorker
import logging
from pathlib import Path # Import Path for validation

class SettingsController(QObject):
    """Controller for the Settings Tab logic."""
    # --- ローディング表示用シグナル ---
    authentication_started = Signal()
    authentication_finished = Signal(str, bool) # message, success_flag

    # --- Modify __init__ to accept license_manager ---
    def __init__(self, config_manager: ConfigManager, license_manager: LicenseManager, model=None, view=None):
        super().__init__()
        self.model = model # Keep model if needed for future expansion
        self.view = None # View will be set via set_view
        self.config_manager = config_manager
        self.license_manager = license_manager # Use passed-in instance
        self._validated_full_key = None # Added: Store the last successfully validated full key
        self.logger = logging.getLogger(__name__)
        # --- Add references for other controllers ---
        self.batch_controller_ref = None
        self.crop_controller_ref = None
        # --- End Add references ---
        self.license_worker = None
        self.license_thread = None

        # --- Worker Thread and Worker setup removed --- 
        self.logger.info("SettingsController initialized (synchronous validation mode).")
        # Do not load settings here, wait for view to be set

    def set_other_controllers(self, batch_controller, crop_controller):
        """Store references to other controllers for cross-tab updates."""
        self.logger.debug("Setting references to Batch and Crop controllers.")
        self.batch_controller_ref = batch_controller
        self.crop_controller_ref = crop_controller

    def set_view(self, view):
        """Sets the view, loads initial cache, and updates license display."""
        self.view = view
        if not self.view:
            self.logger.error("Attempted to set an invalid view for SettingsController")
            return

        # Set the controller reference in the view
        if hasattr(self.view, 'set_controller'):
            self.view.set_controller(self)
        else:
            self.logger.warning("View does not have a 'set_controller' method.")

        self.load_settings_to_view()
        
        # --- Load cached license status FIRST --- 
        self.logger.info("Loading cached license status...")
        try:
            cached_msg, is_valid, _ = self.license_manager.get_cached_status_message()
            license_key = self.config_manager.get(KEY_LICENSE_KEY, "")
            display_text = self.license_manager.get_masked_key(license_key) if is_valid else license_key
            if hasattr(self.view, 'set_license_entry_state'):
                self.view.set_license_entry_state(bool(is_valid), display_text, cached_msg)
                self.logger.info(f"Displayed cached license status: {cached_msg} (Valid: {is_valid})")
            else:
                self.logger.error("View has no set_license_entry_state method for cache display.")
        except Exception as e:
             self.logger.exception(f"Error displaying cached license status: {e}")
             if hasattr(self.view, 'set_license_entry_state'):
                  self.view.set_license_entry_state(False, "", "キャッシュ表示エラー")
        # --- End cache loading --- 

        # Optionally trigger a background validation check here if needed later
        self.logger.info("SettingsController view has been set and initial settings loaded.")

    def load_settings_to_view(self):
        """Loads settings from ConfigManager and populates the view."""
        if not self.view or not self.config_manager:
            self.logger.warning("Cannot load settings, View or ConfigManager not available.")
            return

        # Prepare settings dict from ConfigManager
        settings_to_load = {
            KEY_WORKING_DIRECTORY: self.config_manager.get(KEY_WORKING_DIRECTORY, ""),
            # License key is loaded separately via validate_license_key
            # Removed crop keys
            # KEY_CROP_INPUT_DIR: self.config_manager.get(KEY_CROP_INPUT_DIR, ""),
            # KEY_CROP_OUTPUT_DIR: self.config_manager.get(KEY_CROP_OUTPUT_DIR, ""),
            # KEY_PREVIEW_SAVE_DIR: self.config_manager.get(KEY_PREVIEW_SAVE_DIR, ""),
            # Add other keys if any
        }

        # Call the view's method to load settings
        if hasattr(self.view, 'load_settings'):
            self.view.load_settings(settings_to_load)
        else:
            self.logger.error("View does not have a 'load_settings' method.")

    @Slot()
    def browse_working_directory(self):
        """Opens a dialog to select the working directory and saves immediately."""
        if not self.view:
            return
        current_path = self.view.working_dir_edit.text() or str(Path.home())
        dir_path = QFileDialog.getExistingDirectory(self.view, "作業ディレクトリを選択", current_path)
        if dir_path:
            self.view.working_dir_edit.setText(dir_path)
            self.config_manager.set(KEY_WORKING_DIRECTORY, dir_path)
            self.config_manager.save()
            self.logger.info(f"Working directory selected and saved: {dir_path}")

    @Slot()
    def create_default_folders(self):
        """Creates default subfolders within the selected working directory."""
        if not self.view:
            return
        base_path_str = self.view.working_dir_edit.text().strip()
        if not base_path_str:
            if hasattr(self.view, 'show_message'):
                self.view.show_message("エラー", "作業ディレクトリが指定されていません。", type="warning")
            return

        base_path = Path(base_path_str)
        workspace_name = "CCBP_WorkSpace" # Or make this configurable
        workspace_path = base_path / workspace_name

        # Check if base path exists
        if not base_path.is_dir():
            reply = QMessageBox.question(self.view, "確認",
                                         f"指定された基本パスが見つかりません:\n{base_path}\n作成しますか？",
                                         QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
                                         QMessageBox.StandardButton.No)
            if reply == QMessageBox.StandardButton.Yes:
                try:
                    base_path.mkdir(parents=True, exist_ok=True)
                except Exception as e:
                    self.logger.error(f"Failed to create base directory {base_path}: {e}")
                    if hasattr(self.view, 'show_message'):
                        self.view.show_message("エラー", f"基本ディレクトリの作成に失敗しました: {e}", type="critical")
                    return
            else:
                return # User cancelled

        # Define folders to create within workspace - Use names based on old controller
        folders_to_create = [
            "01_TemplateMaterial",
            "02_ReplaceMaterial",
            "03_CropInput",
            "04_CropOutput",
            "05_ReportCsvOutput",
            "06_Logs"
        ]

        created_folders = []
        skipped_folders = []
        errors = []

        try:
            self.logger.info(f"Creating workspace folders in: {workspace_path}")
            workspace_path.mkdir(exist_ok=True)  # Create the main workspace folder

            for folder_name in folders_to_create:
                folder_path = workspace_path / folder_name
                try:
                    if not folder_path.exists():
                        folder_path.mkdir()
                        self.logger.info(f"Created folder: {folder_path}")
                        created_folders.append(folder_name)
                    else:
                        self.logger.info(f"Folder already exists, skipping: {folder_path}")
                        skipped_folders.append(folder_name)
                except Exception as e:
                    self.logger.error(f"Error creating subfolder {folder_path}: {e}")
                    errors.append(f"{folder_name}: {e}")

            # --- Report results --- #
            message = f"ワークスペースフォルダ ({workspace_name}) の確認/作成完了\n場所: {workspace_path}\n"
            if created_folders:
                message += f"\n作成されたフォルダ: {', '.join(created_folders)}"
            if skipped_folders:
                message += f"\n既存のためスキップ: {', '.join(skipped_folders)}"
            if errors:
                message += "\nエラーが発生したフォルダ:\n" + "\n".join(errors)
                msg_type = "warning"
            else:
                msg_type = "info"

            if hasattr(self.view, 'show_message'):
                self.view.show_message("フォルダ作成結果", message, type=msg_type)

        except Exception as e:
            self.logger.exception(f"Error creating workspace structure in {workspace_path}: {e}")
            if hasattr(self.view, 'show_message'):
                self.view.show_message("エラー", f"ワークスペースフォルダの作成中にエラーが発生しました: {e}", type="critical")

    @Slot()
    def reset_settings(self):
        """Resets settings including license cache."""
        """Resets ALL settings (excluding license) to defaults after confirmation."""
        if not self.view or not self.config_manager:
            return

        reply = QMessageBox.question(self.view, "確認",
                                     "ライセンス情報を除く全てのパス設定などをデフォルト値にリセットしますか？\n（バッチ処理タブ、クロップ処理タブの設定もリセットされます）",
                                     QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No, 
                                     QMessageBox.StandardButton.No)
        
        if reply == QMessageBox.StandardButton.Yes:
            try:
                defaults = self.config_manager._get_default_config()
                
                # --- Define keys to reset (EXCLUDE license keys) ---
                keys_to_reset = [
                    KEY_WORKING_DIRECTORY,
                    # Batch keys
                    KEY_BATCH_CSV_FILE,
                    KEY_BATCH_TEMPLATE_DIR,
                    KEY_BATCH_TEMPLATE_MATERIAL_DIR,
                    KEY_BATCH_REPLACE_MATERIAL_DIR,
                    KEY_BATCH_OUTPUT_DIR,
                    KEY_BATCH_OUTPUT_CSV_DIR,
                    # Crop keys
                    KEY_CROP_INPUT_DIR,
                    KEY_CROP_OUTPUT_DIR,
                    # Add other non-license keys here if they exist
                ]
                # --- End Define keys ---
                
                self.logger.info(f"Resetting the following keys to default: {keys_to_reset}")
                
                # --- Reset specified keys --- 
                for key in keys_to_reset:
                    if key in defaults:
                        self.config_manager.set(key, defaults[key])
                    else:
                        self.logger.warning(f"Key '{key}' not found in default config during reset, skipping.")
                # --- End Reset ---

                # --- Save and Reload ALL Views --- 
                self.config_manager.save()
                self.logger.info("Non-license settings reset to defaults and saved.")
                
                # Reload settings into the current (Settings) view
                self.load_settings_to_view() 
                
                # --- Reload Batch Tab View --- 
                if self.batch_controller_ref and hasattr(self.batch_controller_ref, 'load_paths_from_config'):
                    self.logger.debug("Reloading Batch tab paths.")
                    self.batch_controller_ref.load_paths_from_config()
                else:
                    self.logger.warning("Batch controller reference not set or missing load_paths_from_config method.")
                    
                # --- Reload Crop Tab View --- 
                if self.crop_controller_ref and hasattr(self.crop_controller_ref, 'load_paths_from_config'):
                    self.logger.debug("Reloading Crop tab paths.")
                    self.crop_controller_ref.load_paths_from_config()
                else:
                    self.logger.warning("Crop controller reference not set or missing load_paths_from_config method.")
                # --- End Reload ALL Views ---
                
                # --- DO NOT re-validate license here ---
                # self.validate_license_key() # REMOVED
                
                if hasattr(self.view, 'show_message'):
                    self.view.show_message("リセット完了", "ライセンス情報を除く設定がデフォルト値にリセットされました。", type="info")
            except Exception as e:
                self.logger.exception(f"Error resetting settings: {e}")
                if hasattr(self.view, 'show_message'):
                    self.view.show_message("エラー", f"設定のリセット中にエラーが発生しました: {e}", type="critical")

    @Slot()
    def save_working_directory(self):
        """Saves the working directory when the line edit loses focus."""
        if not self.view or not self.config_manager:
            self.logger.warning("Cannot save working directory, View or ConfigManager not available.")
            return
        try:
            working_dir = self.view.get_working_directory().strip()
            if working_dir and Path(working_dir).is_dir():
                self.config_manager.set(KEY_WORKING_DIRECTORY, working_dir)
                self.config_manager.save()
                self.logger.info(f"Working directory saved: {working_dir}")
            elif working_dir:
                # Path exists but is not a directory or path is invalid syntactically
                self.logger.warning(f"Attempted to save invalid working directory: {working_dir}")
                # Optionally show a message, but might be annoying on every focus lost
                # Revert to the last saved value?
                last_saved = self.config_manager.get(KEY_WORKING_DIRECTORY, "")
                self.view.set_working_directory(last_saved) # Revert UI
        except Exception as e:
            self.logger.exception(f"Error saving working directory: {e}")

    @Slot()
    def save_license_key_from_edit(self):
        """Saves the license key when the line edit loses focus, if it's valid."""
        if not self.view or not self.config_manager:
            self.logger.warning("Cannot save license key, View or ConfigManager not available.")
            return
        try:
            license_key = self.view.get_license_key().strip()
            # Perform validation using LicenseManager
            is_valid = self.license_manager.is_valid(license_key)

            if is_valid or not license_key: # Allow saving valid keys or empty key
                self.config_manager.set(KEY_LICENSE_KEY, license_key)
                self.config_manager.save()
                self.logger.info(f"License key updated and saved (valid: {is_valid}).")
                # Update the display after saving
                self.validate_license_key()
            else:
                # Handle invalid key entered - maybe just log and don't save?
                self.logger.warning(f"Invalid license key entered in field, not saving: {license_key[:5]}...")
                # Optionally revert the view to the last saved valid key
                self.validate_license_key() # This will reload the state based on config

        except Exception as e:
            self.logger.exception(f"Error saving license key from edit: {e}")

    @Slot()
    def clear_license(self):
        """Clears the license key from settings and view after confirmation."""
        if not self.view or not self.config_manager:
            return

        reply = QMessageBox.question(self.view, "確認",
                                     "保存されているライセンスキーをクリアしますか？",
                                     QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No, 
                                     QMessageBox.StandardButton.No)
                                     
        if reply == QMessageBox.StandardButton.Yes:
            try:
                self.config_manager.set(KEY_LICENSE_KEY, "")
                # --- Reset Cache Keys ---
                defaults = self.config_manager._get_default_config()
                self.config_manager.set(KEY_LICENSE_STATUS, defaults.get(KEY_LICENSE_STATUS))
                self.config_manager.set(KEY_LICENSE_EXPIRES, defaults.get(KEY_LICENSE_EXPIRES))
                self.config_manager.set(KEY_LICENSE_VALIDATED_AT, defaults.get(KEY_LICENSE_VALIDATED_AT))
                self.config_manager.set(KEY_LICENSE_LAST_MESSAGE, defaults.get(KEY_LICENSE_LAST_MESSAGE))
                # --- End Reset ---
                self.config_manager.save()
                self.logger.info("License key and cache cleared and settings saved.")
                self._validated_full_key = None # Clear the temporary key as well

                # --- Explicitly clear the view's line edit ---
                if self.view and hasattr(self.view, 'set_license_key'):
                    self.view.set_license_key("")
                    self.logger.debug("Cleared license key text in the view.")
                # --- End explicit clear ---

                # Update the view (display status etc.)
                # load_settings_to_view() doesn't load license key, so we rely on validate_license_key
                self.validate_license_key() # Should now validate an empty string

                if hasattr(self.view, 'show_message'):
                    self.view.show_message("クリア完了", "ライセンスキーがクリアされました。", type="info")
            except Exception as e:
                self.logger.exception("Error clearing license key: {e}")
                if hasattr(self.view, 'show_message'):
                    self.view.show_message("エラー", f"ライセンスキーのクリア中にエラーが発生しました: {e}", type="critical")

    @Slot()
    def validate_license_key(self):
        """Validates the license key entered in the view (ASYNCHRONOUSLY). Handles empty key."""
        if not self.view:
            return
        key = self.view.get_license_key().strip()

        # --- Handle Empty Key Explicitly (remains synchronous) ---
        if not key:
            self.logger.info("License key is empty. Resetting view to 'Not Entered' state.")
            # Update cache to reflect empty state (optional but good practice)
            # Use None for validation_data and a specific error message for cache update
            self.license_manager._update_license_cache("", None, error_message="未入力")
            # Directly update view to 'Not Entered' state
            self._update_view_with_validation_result("", status_override="未入力")
            # Emit finished signal for consistency, although no API call happened
            self.authentication_finished.emit("ライセンスキーが入力されていません。", False)
            return
        # --- End Empty Key Handling ---

        # --- Proceed with ASYNCHRONOUS validation for non-empty key ---
        # --- Check if worker is already running ---
        if self.license_thread and self.license_thread.isRunning():
            self.logger.warning("License validation is already in progress.")
            QMessageBox.information(self.view, "処理中", "ライセンス認証処理が実行中です。")
            return
        # --- End Check ---
            
        self.logger.info(f"Triggering license validation ASYNCHRONOUSLY for key: '{key[:5]}...'")

        # --- Clean up previous thread/worker if they exist but aren't running ---
        self._cleanup_license_worker() # Add cleanup call
        # --- End Cleanup ---

        # --- Create Worker and Thread --- 
        self.license_thread = QThread()
        self.license_worker = LicenseWorker(key, self.license_manager) # Pass key and manager
        self.license_worker.moveToThread(self.license_thread)

        # --- Connect Signals --- 
        # Worker signals to controller slots
        self.license_worker.finished.connect(self._on_validation_finished)
        self.license_worker.error.connect(self._on_validation_error) # Optional: more specific error handling
        # Thread signals
        self.license_thread.started.connect(self.license_worker.run)
        self.license_worker.finished.connect(self.license_thread.quit)
        # Cleanup after thread finishes
        self.license_worker.finished.connect(self.license_worker.deleteLater)
        self.license_thread.finished.connect(self.license_thread.deleteLater)
        self.license_thread.finished.connect(self._clear_license_worker_references)
        # --- End Connect --- 

        # --- Emit start signal (for progress dialog) --- 
        self.logger.debug("Emitting authentication_started signal (async)")
        self.authentication_started.emit()
        # QApplication.processEvents() # Not needed when starting a thread

        # --- Start Thread --- 
        self.license_thread.start()
        # --- End Start ---
        
    # --- Slot for Worker Finished Signal --- 
    @Slot(dict)
    def _on_validation_finished(self, result_data: dict):
        self.logger.info(f"LicenseWorker finished signal received. Result data: {result_data}")
        
        # Use helper to generate message and determine success
        message, success = self.license_manager.get_status_message_from_data(result_data)
        license_key = result_data.get('license_key', '') # Get potentially full key
            
        if success:
            self._validated_full_key = license_key # Store full key if validation was successful
            self._update_view_with_validation_result(license_key)
        else:
            self._validated_full_key = None
            # Get the key the user *entered* for display if validation failed
            input_key = self.view.get_license_key().strip() if self.view else ""
            self._update_view_with_validation_result(input_key, status_override=message)

        self.logger.debug(f"Emitting authentication_finished signal (async success) with message: '{message}', success: {success}")
        self.authentication_finished.emit(message, success)

    # --- Slot for Worker Error Signal (Optional but good practice) --- 
    @Slot(str)
    def _on_validation_error(self, error_message: str):
        self.logger.error(f"LicenseWorker error signal received: {error_message}")
        # Update cache with error state
        input_key = self.view.get_license_key().strip() if self.view else ""
        self.license_manager._update_license_cache(input_key, None, error_message=f"Workerエラー: {error_message}")
        
        # Update UI to show error
        cached_msg, _, _ = self.license_manager.get_cached_status_message()
        self._update_view_with_validation_result(input_key, status_override=cached_msg)
        
        self.logger.debug(f"Emitting authentication_finished signal (async error) with message: '{cached_msg}', success: False")
        self.authentication_finished.emit(cached_msg, False)

    # --- Helper Methods for Cleanup --- 
    def _cleanup_license_worker(self):
        """Ensures any existing license worker/thread is stopped and cleaned up."""
        if self.license_thread:
            self.logger.debug("Cleaning up existing license worker/thread...")
            if self.license_thread.isRunning():
                self.logger.warning("License validation thread was still running during cleanup. Requesting quit.")
                # Optionally signal worker to cancel if applicable
                self.license_thread.quit()
                if not self.license_thread.wait(1000): # Wait briefly
                    self.logger.error("License thread did not finish gracefully. Terminating.")
                    self.license_thread.terminate()
                    self.license_thread.wait() # Wait after terminate

            # Disconnect signals and schedule deletion regardless of running state
            try:
                if self.license_worker:
                    self.license_worker.finished.disconnect()
                # --- Disconnect error signal too --- 
                if self.license_worker:
                    self.license_worker.error.disconnect()
                # --- End Disconnect ---
                if self.license_thread:
                    self.license_thread.finished.disconnect()
                # --- Disconnect started signal too --- 
                if self.license_thread:
                    self.license_thread.started.disconnect()
                # --- End Disconnect ---
            except (TypeError, RuntimeError) as e:
                self.logger.debug(f"Ignoring error during signal disconnection: {e}")
                pass # Ignore if already disconnected or other errors
                
            if self.license_worker:
                self.license_worker.deleteLater()
            if self.license_thread:
                self.license_thread.deleteLater()
            self._clear_license_worker_references()
            self.logger.debug("Finished cleaning up license worker/thread.")
        else:
            self.logger.debug("No existing license worker/thread to clean up.")

    def _clear_license_worker_references(self):
        """Clears references to the worker and thread objects."""
        self.logger.debug("Clearing license worker and thread references.")
        self.license_worker = None
        self.license_thread = None

    def _update_view_with_validation_result(self, license_key: str, status_override: str | None = None):
        """Helper method to update the UI based on a license key and its validation status."""
        if not self.view or not self.license_manager:
            self.logger.warning("Cannot update view, dependencies missing.")
            return
            
        try:
            self.logger.debug(f"Updating view for license key: '{license_key[:5]}...'")
            is_valid = False # Default
            status_msg = "エラー"
            if status_override:
                 status_msg = status_override
                 is_valid = False 
                 self.logger.debug("Using status override.")
            else:
                 # --- Get status from CACHE after worker runs --- 
                 cached_msg, validity, _ = self.license_manager.get_cached_status_message()
                 status_msg = cached_msg
                 is_valid = validity if validity is not None else False # Handle None case
                 self.logger.debug(f"Using cached status after worker: {status_msg}, is_valid: {is_valid}")

            # Determine text to display in the input field
            display_text = self.license_manager.get_masked_key(license_key) if is_valid else license_key
            self.logger.debug(f"Determined display_text: '{display_text[:5]}...'")

            # Update the view using set_license_entry_state
            if hasattr(self.view, 'set_license_entry_state'):
                self.view.set_license_entry_state(
                    is_valid=bool(is_valid),
                    display_text=display_text,
                    status_text=status_msg
                )
                self.logger.info(f"License status updated in view: {status_msg} (Valid: {is_valid})")
            else:
                 self.logger.error("View does not have 'set_license_entry_state' method.")

        except Exception as e:
            self.logger.exception(f"Error updating view with validation result: {e}")
            # Update view to show error state
            if hasattr(self.view, 'set_license_entry_state'):
                 self.view.set_license_entry_state(is_valid=False, display_text="", status_text="表示エラー")
            self._validated_full_key = None # Clear validated key on error

    def finalize(self):
        """Cleans up resources including the worker thread."""
        self.logger.info("Finalizing SettingsController.")
        # --- Ensure worker thread is stopped --- 
        if self.license_thread and self.license_thread.isRunning():
            self.logger.warning("License validation thread still running during finalize. Requesting quit.")
            self.license_thread.quit()
            if not self.license_thread.wait(1000): # Wait briefly
                 self.logger.error("License thread did not finish gracefully during finalize. Terminating.")
                 self.license_thread.terminate()
        self._cleanup_license_worker() # Final cleanup
        # --- End Ensure --- 
        self.logger.info("SettingsController finalized")