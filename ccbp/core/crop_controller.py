from PySide6.QtCore import QObject, QThread, Signal, Slot
from PySide6.QtGui import QImage
from PySide6.QtWidgets import QMessageBox, QFileDialog, QLineEdit
from pathlib import Path
import platform
import shutil
from .config_manager import (
    ConfigManager, KEY_CROP_INPUT_DIR, KEY_CROP_OUTPUT_DIR, 
    # Remove crop default keys as they are no longer configurable
    # KEY_CROP_DEFAULT_W, KEY_CROP_DEFAULT_H, KEY_CROP_DEFAULT_X, KEY_CROP_DEFAULT_Y
)
import logging
from .crop_worker import CropWorker, PreviewWorker 
import json
import subprocess
import sys
from .license_manager import LicenseManager
import os

# --- Import get_resource_path --- 
# Assuming get_resource_path is defined in a utility module like help_view
logger = logging.getLogger(__name__)
try:
    from ..ui.help_view import get_resource_path
except ImportError as e:
    logger.error(f"CRITICAL: Failed to import get_resource_path from ccbp.ui.help_view: {e}", exc_info=True)
    def get_resource_path(relative_path):
        logger.error("get_resource_path fallback used - resource loading will likely fail.")
        return relative_path # Incorrect, but prevents NameError
# --- End Import --- 

# Define fixed crop parameters
FIXED_CROP_PARAMS = {
    'w': 1080,
    'h': 1920,
    'x': 'center', # Use 'center' to indicate centering to the worker
    'y': 'center'
}

class CropController(QObject):
    preview_finished = Signal(bool, QImage)
    crop_finished = Signal(bool, int, int)
    error_occurred = Signal(str)
    status_update = Signal(str)
    progress_update = Signal(int)
    log_message = Signal(str)
    preview_generated = Signal(QImage) 
    crop_params_calculated = Signal(dict)

    def __init__(self, config_manager: ConfigManager, license_manager: LicenseManager, model=None, view=None):
        super().__init__()
        self.model = model
        self.view = None 
        self.config_manager = config_manager 
        self.license_manager = license_manager
        self.ffmpeg_path: str | None = None
        self.ffprobe_path: str | None = None
        self.preview_worker: PreviewWorker | None = None
        self.preview_thread: QThread | None = None
        self.crop_worker: CropWorker | None = None
        self.crop_thread: QThread | None = None
        self._last_crop_result: tuple | None = None 
        self.last_crop_params: dict | None = None

        self.ffmpeg_path, self.ffprobe_path = self._find_ffmpeg_and_ffprobe()
        
        if not self.ffmpeg_path:
             logger.error("FFmpeg executable not found.")
        if not self.ffprobe_path:
             logger.error("ffprobe executable not found.")

        logger.info(f"CropController initialized. FFmpeg: {self.ffmpeg_path}, FFprobe: {self.ffprobe_path}")

    def generate_preview(self):
        logger.info("Generate preview requested.")
        if not self.view:
            logger.error("View not set in CropController, cannot generate preview.")
            return
        if not self.ffmpeg_path:
            msg = "FFmpeg実行ファイルが見つかりません。プレビューを生成できません。"
            logger.error(f"{msg} (Path not set)")
            QMessageBox.critical(self.view, "FFmpegエラー", msg)
            return
        if not self.ffprobe_path:
            msg = "ffprobe実行ファイルが見つかりません。プレビューを生成できません。"
            logger.error(f"{msg} (Path not set)")
            QMessageBox.critical(self.view, "ffprobeエラー", msg)
            return
        if self.preview_thread and self.preview_thread.isRunning():
            msg = "既にプレビュー生成処理が実行中です。"
            logger.warning(f"Preview generation requested while already running. {msg}")
            return
        if self.crop_thread and self.crop_thread.isRunning():
            msg = "クロップ処理中はプレビューを生成できません。"
            logger.warning(f"Preview generation requested during crop processing. {msg}")
            return

        paths = self.view.get_paths()
        logger.info(f"Preview generation paths: {paths}")
        if not paths or not paths.get('input'):
             msg = "入力フォルダが指定されていません。"
             logger.warning(f"Preview generation failed: {msg}")
             QMessageBox.warning(self.view, "パスエラー", msg)
             return
        input_path = Path(paths['input'])
        if not input_path.is_dir():
             msg = f"指定された入力パスは有効なフォルダではありません: {input_path}"
             logger.warning(f"Preview generation failed: {msg}")
             QMessageBox.warning(self.view, "パスエラー", msg)
             return

        logger.debug("Setting UI state for preview generation.")
        self.view.set_buttons_enabled(preview_gen=False, crop=False, cancel=True)
        self.view.update_status("プレビュー生成開始...")
        self.view.append_log("プレビュー生成を開始します...")
        self.view.update_progress(0)

        logger.info("Preparing PreviewWorker thread.")
        if not self.cleanup_workers(): 
             logger.warning("Cleanup prevented starting new preview worker.")
             self._check_and_reset_ui() 
             return

        self.preview_thread = QThread()
        try:
            self.preview_worker = PreviewWorker(
                paths=paths, 
                ffmpeg_path=self.ffmpeg_path, 
                ffprobe_path=self.ffprobe_path,
                crop_params=FIXED_CROP_PARAMS,
                parent=None)
        except (ValueError, TypeError) as e:
             msg = f"プレビュー処理の準備中にエラーが発生しました:\n{e}"
             logger.error(f"Failed to initialize PreviewWorker: {e}")
             QMessageBox.critical(self.view, "初期化エラー", msg)
             self._check_and_reset_ui() 
             self.preview_thread = None 
             return
        except Exception as e:
             msg = f"予期せぬエラーが発生しました: {e}"
             logger.exception(f"Unexpected error initializing PreviewWorker: {e}")
             QMessageBox.critical(self.view, "予期せぬエラー", msg)
             self._check_and_reset_ui() 
             self.preview_thread = None 
             return

        self.preview_worker.moveToThread(self.preview_thread)
        logger.debug("Connecting PreviewWorker signals...")
        self.preview_worker.finished.connect(self._on_preview_finished)
        self.preview_worker.error_occurred.connect(self._on_worker_error)
        self.preview_worker.status_update.connect(self._on_worker_status_update)
        self.preview_worker.log_message.connect(self._on_worker_log_message)
        self.preview_worker.finished.connect(self.preview_thread.quit)
        self.preview_thread.started.connect(self.preview_worker.run)
        self.preview_thread.finished.connect(self.preview_worker.deleteLater)
        self.preview_thread.finished.connect(self._check_and_reset_ui)
        self.preview_thread.finished.connect(self._clear_preview_worker_references)

        logger.info("Starting PreviewWorker thread execution.")
        self.preview_thread.start()

    def run_cropping(self):
        if not self.license_manager:
            self.logger.error("LicenseManager not set in CropController")
            if self.view and hasattr(self.view.parent(), 'show_error_message'):
                 self.view.parent().show_error_message("内部エラー", "ライセンス管理機能が初期化されていません。")
            elif self.view:
                 QMessageBox.critical(self.view, "内部エラー", "ライセンス管理機能が初期化されていません。")
            return
            
        can_use, message = self.license_manager.can_use_crop()
        if not can_use:
             self.logger.warning(f"Crop processing blocked: {message}")
             if self.view and hasattr(self.view.parent(), 'show_warning_message'):
                 self.view.parent().show_warning_message("処理制限", message)
             elif self.view:
                 QMessageBox.warning(self.view, "処理制限", message)
             return
        
        logger.info("Run cropping requested (using fixed 1080x1920 center crop).")
        logger.debug("Checking view...")
        if not self.view:
            logger.error("View not set in CropController, cannot run cropping.")
            return
        logger.debug("Checking ffmpeg path...")
        if not self.ffmpeg_path:
             msg = "FFmpeg実行ファイルが見つかりません。クロップ処理を実行できません。"
             logger.error(f"{msg} (Path not set)")
             QMessageBox.critical(self.view, "FFmpegエラー", msg)
             return
        logger.debug(f"Checking running preview thread: {self.preview_thread.isRunning() if self.preview_thread else 'None'}")
        if self.preview_thread and self.preview_thread.isRunning():
            msg = "プレビュー生成中はクロップ処理を開始できません。"
            logger.warning(f"Crop processing requested during preview generation. {msg}")
            QMessageBox.warning(self.view, "処理中", msg)
            return
        logger.debug(f"Checking running crop thread: {self.crop_thread.isRunning() if self.crop_thread else 'None'}")
        if self.crop_thread and self.crop_thread.isRunning():
             msg = "既にクロップ処理が実行中です。"
             logger.warning(f"Crop processing requested while already running. {msg}")
             QMessageBox.warning(self.view, "処理中", msg)
             return

        logger.debug("Getting paths from view...")
        paths = self.view.get_paths()
        # Use fixed crop parameters directly
        crop_params = FIXED_CROP_PARAMS 
        logger.info(f"Run cropping paths: {paths}, params: {crop_params} (Fixed)")

        logger.debug("Validating crop paths...")
        if not self._validate_crop_paths(paths): 
             logger.warning("Crop path validation failed. Aborting run_cropping.")
             return
        # Remove parameter validation call
        # logger.debug("Validating crop params...")
        # if not self._validate_crop_params(crop_params): 
        #      msg = "クロップ設定の値 (幅・高さ・XY座標) が正しくありません。" # This message is now irrelevant
        #      logger.warning("Crop param validation failed. Aborting run_cropping.")
        #      QMessageBox.warning(self.view, "パラメータエラー", msg)
        #      return

        logger.debug("Setting UI state for crop processing.")
        self.view.set_buttons_enabled(preview_gen=False, crop=False, cancel=True)
        self.view.update_status("クロップ処理開始...")
        self.view.append_log("クロップ処理を開始します (1080x1920 中央揃え)...")
        self.view.update_progress(0)

        logger.info("Preparing CropWorker thread.")
        logger.debug("Calling cleanup_workers before starting CropWorker...")
        cleanup_successful = self.cleanup_workers() 
        logger.debug(f"cleanup_workers result: {cleanup_successful}")
        if not cleanup_successful: 
            logger.warning("Cleanup failed or prevented starting new crop worker. Aborting.")
            self._check_and_reset_ui() 
            return

        logger.debug("Cleanup successful, proceeding to create CropWorker thread.")
        self.crop_thread = QThread()
        try:
            input_dir_path = Path(paths.get('input'))
            output_dir_path = Path(paths.get('output'))
            # Pass the fixed crop_params
            self.crop_worker = CropWorker(
                input_dir=input_dir_path, output_dir=output_dir_path,
                ffmpeg_path=self.ffmpeg_path, crop_params=crop_params, parent=None
            )
        except (ValueError, TypeError) as e:
             msg = f"クロップ処理の準備中にエラーが発生しました:\n{e}"
             logger.error(f"Failed to initialize CropWorker: {e}")
             QMessageBox.critical(self.view, "初期化エラー", msg)
             self._check_and_reset_ui() 
             self.crop_thread = None 
             return
        except Exception as e:
             msg = f"予期せぬエラーが発生しました: {e}"
             logger.exception(f"Unexpected error initializing CropWorker: {e}")
             QMessageBox.critical(self.view, "予期せぬエラー", msg)
             self._check_and_reset_ui() 
             self.crop_thread = None 
             return

        self.crop_worker.moveToThread(self.crop_thread)
        logger.debug("Connecting CropWorker signals...")
        self.crop_worker.finished.connect(self._on_crop_finished)
        self.crop_worker.status_update.connect(self._on_worker_status_update)
        self.crop_worker.progress_updated.connect(self._on_worker_progress_update)
        self.crop_worker.log_message.connect(self._on_worker_log_message)
        self.crop_worker.finished.connect(self.crop_thread.quit)
        self.crop_thread.started.connect(self.crop_worker.run)
        self.crop_thread.finished.connect(self.crop_worker.deleteLater)
        self.crop_thread.finished.connect(self.crop_thread.deleteLater)
        self.crop_thread.finished.connect(self._check_and_reset_ui)
        self.crop_thread.finished.connect(self._clear_crop_worker_references)
        
        logger.info("Starting CropWorker thread execution.")
        self.crop_thread.start()

    def cancel_processing(self):
        logger.info("Cancel processing requested by user.")
        cancelled = False
        if self.preview_thread and self.preview_thread.isRunning() and self.preview_worker:
            logger.info("Requesting cancellation of PreviewWorker.")
            self.preview_worker.cancel() 
            self.view.update_status("プレビュー生成をキャンセル中...")
            cancelled = True
        elif self.crop_thread and self.crop_thread.isRunning() and self.crop_worker:
            logger.info("Requesting cancellation of CropWorker.")
            self.crop_worker.cancel() 
            self.view.update_status("クロップ処理をキャンセル中...")
            cancelled = True

        if not cancelled:
             logger.info("No running process to cancel.")

    @Slot(bool, QImage) 
    def _on_preview_finished(self, success: bool, image: QImage):
        logger.info(f"PreviewWorker finished signal received. Success: {success}")
        if success and not image.isNull():
            self.preview_generated.emit(image)
        elif not success:
            logger.warning("Preview generation failed or was cancelled (received finish signal).")
        else: 
             msg = "プレビュー画像の生成には成功しましたが、画像データが空でした。"
             logger.error(f"PreviewWorker reported success but returned a null image. {msg}")
             self.preview_generated.emit(QImage()) 
             QMessageBox.warning(self.view, "プレビューエラー", msg)

    @Slot(bool, int, int)
    def _on_crop_finished(self, overall_success: bool, success_count: int, error_count: int):
        logger.info(f"CropWorker finished signal received. Overall Success: {overall_success}, Success Count: {success_count}, Error Count: {error_count}")
        logger.debug(f"Storing crop result: Success={overall_success}, Count={success_count}, Errors={error_count}")
        self._last_crop_result = (overall_success, success_count, error_count)
        logger.debug(f"Stored _last_crop_result: {self._last_crop_result}")

    @Slot(str)
    def _on_worker_error(self, message):
        logger.error(f"Received worker error signal for UI: {message}")
        if self.view:
            QMessageBox.warning(self.view, "処理エラー", message)
            self.view.append_log(f"エラー: {message}")
            self.view.update_status("エラーが発生しました")

    @Slot(str)
    def _on_worker_status_update(self, message):
        logger.debug(f"Worker Status Update: {message}")
        if self.view:
            self.view.update_status(message)

    @Slot(int)
    def _on_worker_progress_update(self, value):
        logger.debug(f"Worker Progress Update: {value}%" )
        if self.view:
            self.view.update_progress(value)

    @Slot(str)
    def _on_worker_log_message(self, message):
        logger.debug(f"Appending message to UI log: {message}") 
        if self.view:
            self.view.append_log(message)

    def cleanup_workers(self) -> bool:
        logger.debug("--- cleanup_workers requested ---")
        cleanup_ok = True
        # Preview Thread
        logger.debug(f"Checking preview thread. Instance: {self.preview_thread}, Running: {self.preview_thread.isRunning() if self.preview_thread else 'N/A'}")
        if self.preview_thread:
             current_thread = self.preview_thread
             current_worker = self.preview_worker
             if current_thread and current_thread.isRunning():
                 logger.info("Cleaning up active preview thread...")
                 if current_worker:
                     logger.debug("Requesting PreviewWorker cancellation.")
                     current_worker.cancel()
                 else:
                     logger.warning("Preview thread running but worker reference is None.")
                 logger.debug("Attempting preview thread quit()...")
                 current_thread.quit()
                 logger.debug("Waiting for preview thread to finish (max 5s)... ")
                 wait_result = current_thread.wait(5000) 
                 logger.debug(f"Preview thread wait result: {wait_result}")
                 if not wait_result:
                     logger.error("Preview thread did not quit gracefully after 5 seconds. Terminating.")
                     current_thread.terminate() 
                     logger.debug("Waiting for preview thread after termination...")
                     current_thread.wait() 
                     logger.debug("Preview thread finished after termination.")
                     cleanup_ok = False 
                 else:
                     logger.info("Preview thread finished gracefully.")
             elif current_thread:
                 logger.debug("Preview thread exists but is not running. Scheduling for deletion.")
                 if current_worker:
                     current_worker.deleteLater()
                 current_thread.deleteLater()
             logger.debug("Clearing controller references for preview thread/worker.")
             self.preview_thread = None
             self.preview_worker = None
        # Crop Thread (Similar)
        logger.debug(f"Checking crop thread. Instance: {self.crop_thread}, Running: {self.crop_thread.isRunning() if self.crop_thread else 'N/A'}")
        if self.crop_thread:
             current_thread = self.crop_thread
             current_worker = self.crop_worker
             if current_thread and current_thread.isRunning():
                 logger.info("Cleaning up active crop thread...")
                 if current_worker:
                     logger.debug("Requesting CropWorker cancellation.")
                     current_worker.cancel()
                 else:
                     logger.warning("Crop thread running but worker reference is None.")
                 logger.debug("Attempting crop thread quit()...")
                 current_thread.quit()
                 logger.debug("Waiting for crop thread to finish (max 5s)... ")
                 wait_result = current_thread.wait(5000)
                 logger.debug(f"Crop thread wait result: {wait_result}")
                 if not wait_result:
                     logger.error("Crop thread did not quit gracefully after 5 seconds. Terminating.")
                     current_thread.terminate()
                     logger.debug("Waiting for crop thread after termination...")
                     current_thread.wait()
                     logger.debug("Crop thread finished after termination.")
                     cleanup_ok = False
                 else:
                     logger.info("Crop thread finished gracefully.")
             elif current_thread:
                 logger.debug("Crop thread exists but is not running. Scheduling for deletion.")
                 if current_worker:
                     current_worker.deleteLater()
                 current_thread.deleteLater()
             logger.debug("Clearing controller references for crop thread/worker.")
             self.crop_thread = None
             self.crop_worker = None

        logger.debug(f"--- cleanup_workers finished. Returning: {cleanup_ok} ---")
        return cleanup_ok

    def _check_and_reset_ui(self):
        logger.debug("--- _check_and_reset_ui called ---") 
        if self.view:
            logger.debug("Attempting to reset crop UI elements.")
            self.view.set_buttons_enabled(preview_gen=True, crop=True, cancel=False)
            self.view.update_status("準備完了") 
            self.view.update_progress(0) 
            logger.debug("Crop UI elements reset.")
        else:
            logger.warning("Cannot reset crop UI, view is not set.")

        logger.debug(f"Checking if crop alert needs to be shown. _last_crop_result: {self._last_crop_result}")
        if self._last_crop_result is not None:
            logger.debug("Proceeding to show crop completion alert.")
            success, success_count, error_count = self._last_crop_result
            if self.view:
                logger.debug("View exists, attempting to show QMessageBox for crop.")
                if success:
                    msg = f"クロップ処理が完了しました。\n成功: {success_count}件, 失敗: {error_count}件"
                    logger.debug(f"Showing crop success alert: {msg}")
                    QMessageBox.information(self.view, "クロップ処理完了", msg)
                else:
                    alert_msg = f"クロップ処理中にエラーが発生しました。\n成功: {success_count}件, 失敗: {error_count}件\n詳細はログを確認してください。"
                    logger.debug(f"Showing crop warning alert: {alert_msg}")
                    QMessageBox.warning(self.view, "クロップ処理エラー", alert_msg)
                logger.debug("Finished showing QMessageBox for crop.")
            else:
                logger.warning("Cannot show crop completion alert because view is None.")

            self._last_crop_result = None 
            logger.debug("Cleared _last_crop_result.")
        else:
            logger.debug("No crop result stored, skipping alert.")

    def _validate_crop_paths(self, paths):
        input_path_str = paths.get('input')
        output_path_str = paths.get('output')
        valid = True
        error_messages = []
        logger.debug(f"Validating input path string: '{input_path_str}'") 
        if not input_path_str:
             msg = "エラー: 入力フォルダが指定されていません。"
             logger.warning("Crop Path validation failed (input): No path provided.") 
             error_messages.append(msg)
             valid = False
        else:
            try:
                input_path_obj = Path(input_path_str)
                if not input_path_obj.is_dir():
                     msg = "エラー: 指定された入力パスは有効なフォルダではありません。"
                     logger.warning(f"Crop Path validation failed (input): Path '{input_path_str}' is not a directory.") 
                     error_messages.append(msg)
                     valid = False
            except Exception as e:
                 msg = f"エラー: 入力パスの検証中に予期せぬエラーが発生しました: {input_path_str}"
                 logger.exception(f"Crop Path validation failed (input): Unexpected error checking path '{input_path_str}': {e}")
                 error_messages.append(msg)
                 valid = False
        
        logger.debug(f"Validating output path string: '{output_path_str}'") 
        if not output_path_str: 
            msg = "エラー: 出力フォルダが指定されていません。"
            logger.warning("Crop Path validation failed (output): No path provided.") 
            error_messages.append(msg)
            valid = False
        else:
            try:
                output_path = Path(output_path_str)
                if output_path.is_file():
                    msg = "エラー: 指定された出力パスはファイルです。フォルダを指定してください。"
                    logger.warning(f"Crop Path validation failed (output): Path '{output_path_str}' is a file.") 
                    error_messages.append(msg)
                    valid = False
                elif not output_path.exists():
                     logger.info(f"Output directory does not exist, will be created by worker: {output_path_str}")
                     pass # Assume worker will create it
                elif not output_path.is_dir():
                     msg = f"エラー: 出力パスは有効なフォルダではありません: {output_path_str}"
                     logger.warning(f"Crop Path validation failed (output): Path '{output_path_str}' exists but is not a directory.") 
                     error_messages.append(msg)
                     valid = False
            except Exception as e:
                 msg = f"エラー: 出力パスの検証中に予期せぬエラーが発生しました: {output_path_str}"
                 logger.exception(f"Crop Path validation failed (output): Unexpected error checking path '{output_path_str}': {e}")
                 error_messages.append(msg)
                 valid = False
            
            if valid and input_path_str and output_path_str:
                try:
                    if Path(input_path_str).resolve() == Path(output_path_str).resolve(): 
                        msg = "エラー: 入力フォルダと出力フォルダを同じにすることはできません。"
                        logger.warning(f"Crop Path validation failed: Input and Output paths are the same ('{input_path_str}').") 
                        error_messages.append(msg)
                        valid = False
                except Exception as e:
                    logger.warning(f"Could not resolve paths to compare input and output: {e}", exc_info=True) 

        if not valid and self.view:
            QMessageBox.warning(self.view, "パスエラー", "\n".join(error_messages))
        logger.debug(f"_validate_crop_paths result: {valid}") 
        return valid

    def set_view(self, view):
        self.view = view
        if not self.view:
            logger.error("Attempted to set an invalid view for CropController")
            return
        logger.info("CropController view has been set.")
        self.load_paths_from_config()
        self._connect_view_signals() 
        
    def _connect_view_signals(self):
        if not self.view:
            logger.warning("Cannot connect signals, view is not set.")
            return
        try:
            if hasattr(self.view, 'preview_gen_button') and self.view.preview_gen_button:
                self.view.preview_gen_button.clicked.connect(self.generate_preview)
            else:
                logger.warning("preview_gen_button not found or is None in the view. Signal not connected.")

            if hasattr(self.view, 'crop_button') and self.view.crop_button:
                self.view.crop_button.clicked.connect(self.run_cropping)
            else:
                logger.warning("crop_button not found or is None in the view. Signal not connected.")

            if hasattr(self.view, 'cancel_button') and self.view.cancel_button:
                self.view.cancel_button.clicked.connect(self.cancel_processing)
            else:
                logger.warning("cancel_button not found or is None in the view. Signal not connected.")

            if hasattr(self.view, 'browse_input_button') and self.view.browse_input_button:
                self.view.browse_input_button.clicked.connect(self._browse_input_folder)
            if hasattr(self.view, 'browse_output_button') and self.view.browse_output_button:
                self.view.browse_output_button.clicked.connect(self._browse_output_folder)

            if hasattr(self.view, 'input_folder_edit'):
                self.view.input_folder_edit.editingFinished.connect(self._save_input_path)
            if hasattr(self.view, 'output_folder_edit'):
                self.view.output_folder_edit.editingFinished.connect(self._save_output_path)

            logger.info("Crop view signals connected.")

        except AttributeError as e:
            logger.exception(f"Error connecting crop view signals: Missing attribute in view - {e}")
        except Exception as e:
            logger.exception(f"Unexpected error connecting crop view signals: {e}")

            
    def load_paths_from_config(self):
        if not self.view or not self.config_manager:
            logger.warning("View or ConfigManager not available for loading paths.")
            return
        try:
            input_dir = self.config_manager.get(KEY_CROP_INPUT_DIR, "")
            output_dir = self.config_manager.get(KEY_CROP_OUTPUT_DIR, "")
            
            if hasattr(self.view, 'input_folder_edit'):
                self.view.input_folder_edit.setText(input_dir)
            if hasattr(self.view, 'output_folder_edit'):
                self.view.output_folder_edit.setText(output_dir)

            logger.info(f"Loaded paths from config: Input='{input_dir}', Output='{output_dir}'")
        except Exception as e:
            logger.exception(f"Error loading paths from config: {e}")


    def _browse_input_folder(self):
        if not self.view or not self.config_manager: 
            logger.warning("Cannot browse input folder: View or ConfigManager not set.")
            return
        current_path = self.config_manager.get(KEY_CROP_INPUT_DIR, str(Path.home()))
        logger.debug(f"Browsing for input folder, starting from: {current_path}")
        dir_path = QFileDialog.getExistingDirectory(self.view, "入力フォルダを選択", current_path)
        if dir_path:
            logger.info(f"Input folder selected: {dir_path}")
            if hasattr(self.view, 'update_paths'):
                self.view.update_paths(input_dir=dir_path)
            self.config_manager.set(KEY_CROP_INPUT_DIR, dir_path)
            self.config_manager.save() # Save immediately on change
            if hasattr(self.view, 'append_log'):
                self.view.append_log(f"入力フォルダを設定: {dir_path}")
        else:
            logger.debug("Input folder selection cancelled.")
            
    def _browse_output_folder(self):
        if not self.view or not self.config_manager: 
            logger.warning("Cannot browse output folder: View or ConfigManager not set.")
            return
        current_path = self.config_manager.get(KEY_CROP_OUTPUT_DIR, str(Path.home()))
        logger.debug(f"Browsing for output folder, starting from: {current_path}")
        dir_path = QFileDialog.getExistingDirectory(self.view, "出力フォルダを選択", current_path)
        if dir_path:
            logger.info(f"Output folder selected: {dir_path}")
            if hasattr(self.view, 'update_paths'):
                self.view.update_paths(output_dir=dir_path)
            self.config_manager.set(KEY_CROP_OUTPUT_DIR, dir_path)
            self.config_manager.save() # Save immediately on change
            if hasattr(self.view, 'append_log'):
                self.view.append_log(f"出力フォルダを設定: {dir_path}")
        else:
            logger.debug("Output folder selection cancelled.")

    def _find_ffmpeg_and_ffprobe(self) -> tuple[str | None, str | None]:
        ffmpeg_name = "ffmpeg.exe" if platform.system() == "Windows" else "ffmpeg"
        ffprobe_name = "ffprobe.exe" if platform.system() == "Windows" else "ffprobe"
        
        ffmpeg_path_obj = None
        ffprobe_path_obj = None
        
        # --- Nuitka/PyInstaller バンドル環境のチェック ---
        if hasattr(sys, '_MEIPASS'):
            # バンドル環境の場合、_MEIPASS を基点とする
            base_path = Path(sys._MEIPASS)
            logger.info(f"Running in bundled environment (_MEIPASS): {base_path}")
        else:
            # 通常の実行環境の場合、__file__ を基点とする (開発用)
            try:
                # Assuming crop_controller.py is in ccbp/core/
                base_path = Path(__file__).resolve().parent.parent 
                logger.info(f"Running in development environment, base path: {base_path}")
            except NameError:
                logger.error("__file__ not defined, cannot determine base path in dev environment.")
                base_path = Path.cwd() # Fallback to current working directory
                logger.warning(f"Falling back to CWD for base path: {base_path}")
        # --- ここまで変更 ---

        # --- assets 内の検索 (プラットフォームサブディレクトリ考慮) ---
        platform_subdir = "win" if platform.system() == "Windows" else "mac"
        assets_dir = base_path / "assets" / "ffmpeg" / platform_subdir
        logger.info(f"Searching for tools in expected assets path: {assets_dir}")

        if assets_dir.is_dir():
            potential_ffmpeg = assets_dir / ffmpeg_name
            potential_ffprobe = assets_dir / ffprobe_name
            if potential_ffmpeg.is_file():
                ffmpeg_path_obj = potential_ffmpeg
                logger.info(f"Found {ffmpeg_name} in assets: {ffmpeg_path_obj}")
            if potential_ffprobe.is_file():
                ffprobe_path_obj = potential_ffprobe
                logger.info(f"Found {ffprobe_name} in assets: {ffprobe_path_obj}")
        # --- ここまで assets 内検索ロジック --- 

        # --- PATH の検索 (Fallback) ---
        if not ffmpeg_path_obj:
            logger.warning(f"{ffmpeg_name} not found in assets ({assets_dir}). Trying PATH.")
            path_ffmpeg = shutil.which(ffmpeg_name)
            if path_ffmpeg:
                ffmpeg_path_obj = Path(path_ffmpeg)
                logger.info(f"Found {ffmpeg_name} in PATH: {ffmpeg_path_obj}")
            else:
                logger.error(f"{ffmpeg_name} not found in assets or PATH.")
                 
        if not ffprobe_path_obj:
            logger.warning(f"{ffprobe_name} not found in assets ({assets_dir}). Trying PATH.")
            path_ffprobe = shutil.which(ffprobe_name)
            if path_ffprobe:
                ffprobe_path_obj = Path(path_ffprobe)
                logger.info(f"Found {ffprobe_name} in PATH: {ffprobe_path_obj}")
            else: 
                logger.error(f"{ffprobe_name} not found in assets or PATH.")
        # --- ここまで PATH 検索 --- 

        # --- 実行権限の確認・付与 (macOS/Linux) ---
        if platform.system() != "Windows":
            if ffmpeg_path_obj and not os.access(ffmpeg_path_obj, os.X_OK):
                logger.warning(f"Adding execute permission to: {ffmpeg_path_obj}")
                try:
                    # Add execute permission for user, group, others (+x)
                    os.chmod(ffmpeg_path_obj, os.stat(ffmpeg_path_obj).st_mode | 0o111) 
                except Exception as e:
                     logger.error(f"Failed to set execute permission for {ffmpeg_path_obj}: {e}")
            if ffprobe_path_obj and not os.access(ffprobe_path_obj, os.X_OK):
                 logger.warning(f"Adding execute permission to: {ffprobe_path_obj}")
                 try:
                     # Add execute permission for user, group, others (+x)
                     os.chmod(ffprobe_path_obj, os.stat(ffprobe_path_obj).st_mode | 0o111)
                 except Exception as e:
                     logger.error(f"Failed to set execute permission for {ffprobe_path_obj}: {e}")
        # --- ここまで権限付与 --- 

        return (str(ffmpeg_path_obj) if ffmpeg_path_obj else None,
                str(ffprobe_path_obj) if ffprobe_path_obj else None)

    def _run_ffprobe_json(self, command: list[str]) -> dict | None:
        logger.debug(f"Running ffprobe command: {' '.join(command)}")
        if not self.ffprobe_path:
            logger.error("ffprobe path is not set, cannot run command.")
            return None
        try:
            # +++ Add detailed logging +++
            logger.debug(f"Executing subprocess: {command}")
            env = os.environ.copy() # Capture environment for logging if needed
            logger.debug(f"Subprocess environment (first few vars): { {k: env[k] for k in list(env)[:5]} }...")
            # +++ End added logging +++
            process = subprocess.run(
                command,
                capture_output=True,
                text=True,
                encoding='utf-8',
                check=False, 
                creationflags=subprocess.CREATE_NO_WINDOW if sys.platform == 'nt' else 0
            )
            if process.returncode != 0:
                logger.error(f"ffprobe command failed with code {process.returncode}.")
                logger.debug(f"ffprobe stderr: {process.stderr}")
                logger.debug(f"ffprobe stdout: {process.stdout}")
                return None
            
            logger.debug(f"ffprobe stdout: {process.stdout}")
            return json.loads(process.stdout)
            
        except FileNotFoundError:
            logger.error(f"ffprobe executable not found at: {command[0]}", exc_info=True)
            # +++ Add detailed logging +++
            logger.error(f"Attempted ffprobe path: {self.ffprobe_path}")
            # +++ End added logging +++
            return None
        except json.JSONDecodeError as e:
            logger.error(f"Failed to decode ffprobe JSON output: {e}", exc_info=True)
            logger.debug(f"Invalid JSON string was: {process.stdout}") 
            return None
        except Exception as e:
            logger.exception(f"An unexpected error occurred running ffprobe: {e}")
            return None

    @Slot()
    def _clear_preview_worker_references(self):
        logger.debug("Clearing preview worker references.")
        self.preview_worker = None
        self.preview_thread = None

    @Slot()
    def _clear_crop_worker_references(self):
        logger.debug("Clearing crop worker references.")
        self.crop_worker = None
        self.crop_thread = None

    @Slot()
    def _save_input_path(self):
        self._save_path_from_edit(self.view.input_folder_edit, KEY_CROP_INPUT_DIR, is_dir=True)

    @Slot()
    def _save_output_path(self):
        if not self._save_path_from_edit(self.view.output_folder_edit, KEY_CROP_OUTPUT_DIR, is_dir=True, check_exists=False):
             return
        input_path_str = self.config_manager.get(KEY_CROP_INPUT_DIR, "")
        output_path_str = self.config_manager.get(KEY_CROP_OUTPUT_DIR, "")
        if input_path_str and output_path_str and Path(input_path_str).resolve() == Path(output_path_str).resolve():
            self.logger.warning("Input and Output folders cannot be the same. Reverting output folder.")
            self.view.output_folder_edit.setText("") 
            self.config_manager.set(KEY_CROP_OUTPUT_DIR, "")
            self.config_manager.save()
            if hasattr(self.view, 'show_message'):
                QMessageBox.warning(self.view, "パスエラー", "入力フォルダと出力フォルダを同じにすることはできません。出力フォルダをクリアしました。")
            
    def _save_path_from_edit(self, line_edit: QLineEdit, config_key: str, is_file: bool = False, is_dir: bool = False, allow_empty: bool = False, check_exists: bool = True) -> bool:
        if not line_edit or not self.config_manager:
            self.logger.warning(f"Cannot save path for {config_key}, View or ConfigManager not available.")
            return False
        try:
            path_str = line_edit.text().strip()
            last_saved = self.config_manager.get(config_key, "")

            if not path_str:
                if allow_empty:
                    if path_str != last_saved:
                        self.config_manager.set(config_key, "")
                        self.config_manager.save()
                        self.logger.info(f"Saved empty path for optional key {config_key}.")
                    return True
                else:
                    self.logger.warning(f"Attempted to save empty path for required key {config_key}. Reverting.")
                    line_edit.setText(last_saved)
                    return False

            try:
                path_obj = Path(path_str)
                valid = True
                if check_exists:
                    if is_file and not path_obj.is_file():
                        self.logger.warning(f"Path for {config_key} is not a valid file: {path_str}. Reverting.")
                        valid = False
                    elif is_dir and not path_obj.is_dir():
                         if config_key == KEY_CROP_OUTPUT_DIR and path_obj.is_file():
                             self.logger.warning(f"Output path {config_key} is a file: {path_str}. Reverting.")
                             valid = False
                         elif config_key != KEY_CROP_OUTPUT_DIR:
                              self.logger.warning(f"Input path {config_key} is not a valid directory: {path_str}. Reverting.")
                              valid = False

                if valid and path_str != last_saved:
                    self.config_manager.set(config_key, path_str)
                    self.config_manager.save()
                    self.logger.info(f"Path for {config_key} saved via edit: {path_str}")
                    return True
                elif not valid:
                    line_edit.setText(last_saved)
                    return False
                else: 
                    return True

            except Exception as path_e:
                self.logger.error(f"Error validating path '{path_str}' for {config_key}: {path_e}. Reverting.")
                line_edit.setText(last_saved)
                return False

        except Exception as e:
            self.logger.exception(f"Error saving path for {config_key} from edit: {e}")
            last_saved = self.config_manager.get(config_key, "")
            line_edit.setText(last_saved)
            return False

    def finalize(self):
        self.cleanup_workers()
        logger.info("CropController finalized.")

    # ... (Rest of the CropController methods) ...
        pass

    # ... (Other private methods like cleanup remain the same) ...
    pass 