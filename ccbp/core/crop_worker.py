import time
import os
import re 
import subprocess 
import shutil 
import tempfile
from pathlib import Path
# Use PySide6 consistently
from PySide6.QtCore import QObject, QThread, Signal, Slot # Corrected import
from PySide6.QtGui import QImage, QPixmap # Corrected import
import logging # Import logging
import json
import platform

logger = logging.getLogger(__name__) # Setup logger for this module

SUPPORTED_VIDEO_EXTENSIONS = ['.mp4', '.mov', '.avi', '.mkv', '.wmv', '.flv']

# Custom Exception for cancellation
class OperationCancelledError(Exception):
    pass

# --- PreviewWorker (Keep as is for now) --- 
class PreviewWorker(QObject):
    finished = Signal(bool, QImage)
    error_occurred = Signal(str)
    status_update = Signal(str)
    log_message = Signal(str)

    def __init__(self, paths, ffmpeg_path, ffprobe_path, crop_params: dict, parent=None):
        super().__init__(parent)
        self._ffmpeg_path = str(ffmpeg_path)
        self._ffprobe_path = str(ffprobe_path) if ffprobe_path else None
        try:
            self._input_dir = Path(paths.get('input', ''))
        except TypeError:
             # Log the error before raising
             logger.error("Invalid path data received in PreviewWorker", exc_info=True)
             raise ValueError("Invalid path data received in PreviewWorker")
        self._crop_params = crop_params
        self._cancelled = False
        # logger.info("PreviewWorker initialized.") # Already logged by controller
        logger.debug(f"PreviewWorker initialized with input: {self._input_dir}, ffmpeg: {self._ffmpeg_path}, ffprobe: {self._ffprobe_path}, params: {self._crop_params}")

    def run(self):
        temp_image_file = None
        video_file = None # Define outside the loop
        logger.info("Preview generation started.")
        self.log_message.emit("プレビュー生成を開始します...") # UI message
        try:
            if not self._ffprobe_path:
                 raise ValueError("ffprobe path not provided to PreviewWorker.")
            
            self.status_update.emit("入力フォルダを検索中...")
            if not self._input_dir.is_dir():
                 logger.error(f"Input directory not found: {self._input_dir}")
                 raise FileNotFoundError(f"入力フォルダが見つかりません: {self._input_dir}")

            logger.info(f"Searching for video files in: {self._input_dir}")
            self.log_message.emit(f"フォルダ内の動画ファイルを検索: {self._input_dir}") # UI message
            for item in self._input_dir.iterdir():
                 if self._cancelled:
                     logger.info("Preview generation cancelled during file search.")
                     raise OperationCancelledError("Cancelled during file search")
                 if item.is_file() and item.suffix.lower() in SUPPORTED_VIDEO_EXTENSIONS:
                     video_file = item
                     logger.info(f"Video file found for preview: {video_file.name}")
                     self.log_message.emit(f"動画ファイル発見: {video_file.name}") # UI message
                     break
           
            if not video_file:
                logger.warning(f"No supported video files found in {self._input_dir}")
                raise FileNotFoundError(f"入力フォルダ内にサポートされている動画ファイルが見つかりません ({SUPPORTED_VIDEO_EXTENSIONS})")

            logger.info("Calculating crop coordinates for preview...")
            self.log_message.emit("クロップ座標を計算中...")
            dimensions = self._get_video_dimensions(video_file)
            if not dimensions or dimensions[0] is None or dimensions[1] is None:
                 raise ValueError(f"動画サイズを取得できませんでした: {video_file.name}")
            
            crop_w, crop_h, crop_x, crop_y = self._calculate_crop_coords(dimensions[0], dimensions[1])
            logger.info(f"Calculated crop for preview: W={crop_w}, H={crop_h}, X={crop_x}, Y={crop_y}")
            self.log_message.emit(f"計算されたクロップ座標: W={crop_w}, H={crop_h}, X={crop_x}, Y={crop_y}")
           
            self.status_update.emit(f"'{video_file.name}' からクロップしてフレームを抽出中...")
            logger.info(f"Extracting cropped frame from '{video_file.name}'...")
           
            # --- Frame extraction using FFmpeg --- 
            # Create a temporary file path using a context manager
            with tempfile.NamedTemporaryFile(suffix='.jpg', delete=False) as temp_file_obj:
                 temp_image_file = temp_file_obj.name
            logger.debug(f"Temporary file created: {temp_image_file}")
            self.log_message.emit(f"一時ファイルを作成: {temp_image_file}") # UI message
           
            vf_filter = f"crop={crop_w}:{crop_h}:{crop_x}:{crop_y}"
            cmd = [
                self._ffmpeg_path,
                '-ss', '1', # Seek to 1 second
                '-i', str(video_file),
                '-vf', vf_filter,
                '-vframes', '1',
                '-f', 'image2',
                '-q:v', '2',
                '-y',
                temp_image_file
            ]
           
            logger.info(f"Running FFmpeg command: {' '.join(cmd)}")
            self.log_message.emit(f"FFmpegコマンド実行: {' '.join(cmd)}") # UI message
            start_time = time.time()
            process = subprocess.run(cmd, capture_output=True, text=True, encoding='utf-8', 
                                     creationflags=subprocess.CREATE_NO_WINDOW if os.name == 'nt' else 0)
            elapsed_time = time.time() - start_time
                                    
            if self._cancelled:
                logger.info("Preview generation cancelled after FFmpeg execution.")
                raise OperationCancelledError("Cancelled after FFmpeg execution")

            if process.returncode != 0:
                # Log full ffmpeg output for debugging to logger
                logger.error(f"FFmpeg frame extraction failed (Code: {process.returncode}) in {elapsed_time:.2f}s")
                logger.debug(f"FFmpeg stderr: {process.stderr}")
                logger.debug(f"FFmpeg stdout: {process.stdout}")
                # Send concise error to UI log
                self.log_message.emit(f"FFmpeg stderr: {process.stderr.splitlines()[0] if process.stderr else 'N/A'}...")
                raise RuntimeError(f"FFmpegフレーム抽出エラー (コード: {process.returncode})")
            else:
                 logger.info(f"FFmpeg frame extraction successful in {elapsed_time:.2f}s.")
                 # +++ Add detailed logging +++
                 logger.debug(f"FFmpeg frame extraction stdout: {process.stdout}")
                 # +++ End added logging +++
           
            # --- Load image from temp file ---           
            logger.info(f"Loading image from temporary file: {temp_image_file}")
            self.log_message.emit("一時画像ファイルを読み込み中...") # UI message
            preview_image = QImage()
            load_success = preview_image.load(temp_image_file)
            if not load_success:
                 logger.warning(f"QImage.load failed for {temp_image_file}. Trying QPixmap fallback.")
                 pixmap = QPixmap()
                 if pixmap.load(temp_image_file):
                     preview_image = pixmap.toImage()
                     if preview_image.isNull():
                          logger.error(f"Conversion from QPixmap to QImage failed for {temp_image_file}")
                          raise ValueError(f"一時ファイルからQPixmap経由でQImageへの変換失敗: {temp_image_file}")
                     else:
                         logger.info("Successfully loaded image via QPixmap fallback.")
                         load_success = True
                 else:
                     logger.error(f"QPixmap.load also failed for {temp_image_file}")
                     raise ValueError(f"一時画像ファイルの読み込み失敗 (Pixmap): {temp_image_file}")
           
            if not load_success or preview_image.isNull(): # Check again after potential fallback
                 logger.error(f"Failed to load image from {temp_image_file} even after fallback.")
                 raise ValueError(f"一時画像ファイルの読み込み失敗 (Image): {temp_image_file}")
           
            logger.info("Preview image loaded successfully.")
            self.status_update.emit("プレビュー生成完了")
            self.log_message.emit("プレビュー画像の生成が完了しました。") # UI message
            self.finished.emit(True, preview_image)

        except OperationCancelledError:
            logger.info("Preview generation operation cancelled.")
            self.status_update.emit("キャンセルされました")
            self.log_message.emit("プレビュー生成がキャンセルされました。") # UI message
            self.finished.emit(False, QImage())
           
        except (FileNotFoundError, ValueError, RuntimeError) as e:
            error_msg = f"Error during preview generation: {e}"
            logger.error(error_msg) # Log error to file/console
            ui_error_msg = f"プレビュー生成中にエラーが発生しました: {e}" # User-friendly message
            self.status_update.emit("エラー発生")
            self.log_message.emit(ui_error_msg) # UI message
            self.error_occurred.emit(ui_error_msg) # Emit user-friendly error
            self.finished.emit(False, QImage())
        except Exception as e: # Catch unexpected errors
            error_msg = f"Unexpected error during preview generation: {e}"
            logger.exception(error_msg) # Log full traceback
            ui_error_msg = f"プレビュー生成中に予期せぬエラーが発生しました: {e}"
            self.status_update.emit("エラー発生")
            self.log_message.emit(ui_error_msg)
            self.error_occurred.emit(ui_error_msg)
            self.finished.emit(False, QImage())

    def cancel(self):
        logger.info("PreviewWorker cancel requested.")
        self.log_message.emit("プレビュー生成のキャンセル要求を受信しました。") # UI message
        self._cancelled = True

    def _get_video_dimensions(self, video_path: Path) -> tuple[int | None, int | None]:
        """Gets video width and height using ffprobe."""
        if not self._ffprobe_path:
            logger.error("ffprobe path is not set in PreviewWorker.")
            return None, None
        # +++ Add detailed logging +++
        logger.debug(f"Getting dimensions for: {video_path} using ffprobe: {self._ffprobe_path}")
        # +++ End added logging +++
        command = [
            self._ffprobe_path,
            '-v', 'error',
            '-select_streams', 'v:0', # Select only the first video stream
            '-show_entries', 'stream=width,height',
            '-of', 'csv=p=0:s=x', # Output as widthxheight
            str(video_path)
        ]
        logger.debug(f"Running ffprobe for dimensions: {' '.join(command)}")
        try:
            # +++ Add detailed logging +++
            logger.debug(f"Executing subprocess for dimensions: {command}")
            # +++ End added logging +++
            process = subprocess.run(command, capture_output=True, text=True, encoding='utf-8', check=True,
                                     creationflags=subprocess.CREATE_NO_WINDOW if os.name == 'nt' else 0)
            output = process.stdout.strip()
            logger.debug(f"ffprobe dimension output: '{output}'")
            match = re.match(r'(\d+)x(\d+)', output)
            if match:
                width = int(match.group(1))
                height = int(match.group(2))
                logger.info(f"Video dimensions for {video_path.name}: {width}x{height}")
                return width, height
            else:
                logger.error(f"Could not parse dimensions from ffprobe output: '{output}'")
                return None, None
        except FileNotFoundError:
            logger.error(f"ffprobe not found at: {self._ffprobe_path}")
            return None, None
        except subprocess.CalledProcessError as e:
            logger.error(f"ffprobe failed for {video_path.name} (Return code: {e.returncode})")
            logger.error(f"ffprobe command was: {' '.join(e.cmd)}")
            logger.error(f"ffprobe stderr: {e.stderr}")
            logger.error(f"ffprobe stdout: {e.stdout}")
            return None, None
        except Exception as e:
            logger.exception(f"Error getting video dimensions for {video_path.name}: {e}")
            return None, None

    def _calculate_crop_coords(self, video_w: int, video_h: int) -> tuple[int, int, int, int]:
        """Calculates crop coordinates based on stored parameters and video dimensions."""
        target_w = self._crop_params.get('w')
        target_h = self._crop_params.get('h')
        target_x_param = self._crop_params.get('x')
        target_y_param = self._crop_params.get('y')

        if not all([isinstance(target_w, int), isinstance(target_h, int)]):
             raise ValueError("Crop dimensions (w, h) must be integers.")

        # Calculate X coordinate
        if target_x_param == 'center':
            crop_x = max(0, (video_w - target_w) // 2)
        elif isinstance(target_x_param, int):
            crop_x = max(0, target_x_param)
        else:
            raise ValueError(f"Invalid crop X parameter: {target_x_param}. Must be 'center' or int.")

        # Calculate Y coordinate
        if target_y_param == 'center':
            crop_y = max(0, (video_h - target_h) // 2)
        elif isinstance(target_y_param, int):
            crop_y = max(0, target_y_param)
        else:
            raise ValueError(f"Invalid crop Y parameter: {target_y_param}. Must be 'center' or int.")

        # Ensure calculated coords don't exceed video bounds (though ffmpeg handles this, it's good practice)
        if crop_x + target_w > video_w:
            crop_x = max(0, video_w - target_w) # Adjust X if crop goes out of bounds right
        if crop_y + target_h > video_h:
             crop_y = max(0, video_h - target_h) # Adjust Y if crop goes out of bounds bottom
             
        return target_w, target_h, crop_x, crop_y

# --- CropWorker Implementation using FFmpeg --- 
class CropWorker(QObject):
    finished = Signal(bool, int, int) # overall_success, success_count, error_count
    progress_updated = Signal(int) # percentage
    status_update = Signal(str)
    log_message = Signal(str)
    error_occurred = Signal(str) 

    # Accept specific arguments
    def __init__(self, input_dir: Path, output_dir: Path, ffmpeg_path: str, crop_params: dict, parent=None):
        super().__init__(parent)
        self._ffmpeg_path = ffmpeg_path
        self._input_dir = input_dir
        self._output_dir = output_dir
        
        # Remove the validation call here, as 'center' is valid now
        # if not self._validate_crop_params(crop_params):
        #     raise ValueError(f"無効なクロップパラメータ: {crop_params}")
        self._crop_params = crop_params 
             
        self._cancelled = False
        self._process = None # Process handle for potential cancellation
        logger.debug(f"CropWorker initialized with params: {self._crop_params}")

    @Slot()
    def run(self):
        logger.info("Crop processing started.")
        # Use f-string for easier formatting
        self.log_message.emit(f"クロップ処理を開始します... (FFmpeg: {self._ffmpeg_path})")
        processed_files = 0
        success_count = 0
        error_count = 0
        videos_to_process = []
        
        try:
            logger.info(f"Searching for input videos in: {self._input_dir}")
            self.log_message.emit(f"入力フォルダを検索: {self._input_dir}") 
            if not self._input_dir.is_dir():
                logger.error(f"Input directory not found: {self._input_dir}")
                raise FileNotFoundError(f"入力フォルダが見つかりません: {self._input_dir}")
            
            if not self._output_dir.exists():
                logger.info(f"Output directory not found. Creating: {self._output_dir}")
                self.log_message.emit(f"出力フォルダを作成: {self._output_dir}") 
                self._output_dir.mkdir(parents=True, exist_ok=True)
            elif not self._output_dir.is_dir():
                 logger.error(f"Specified output path is not a directory: {self._output_dir}")
                 raise NotADirectoryError(f"指定された出力パスはフォルダではありません: {self._output_dir}")

            videos_to_process = [item for item in self._input_dir.iterdir() if item.is_file() and item.suffix.lower() in SUPPORTED_VIDEO_EXTENSIONS]
            if not videos_to_process:
                logger.warning(f"No supported video files found in {self._input_dir}. Supported: {SUPPORTED_VIDEO_EXTENSIONS}")
                # It's not an error if no files are found, just finish successfully with 0 counts
                self.log_message.emit("処理対象の動画ファイルが見つかりませんでした。")
                self.status_update.emit("完了 (ファイルなし)")
                self.finished.emit(True, 0, 0)
                return # Exit run method
            
            total_videos = len(videos_to_process)
            logger.info(f"Found {total_videos} video files to process.")
            self.log_message.emit(f"{total_videos} 件の動画ファイルを処理します。")
            self.progress_updated.emit(0)

            for i, input_video_path in enumerate(videos_to_process):
                file_num = i + 1
                if self._cancelled:
                    logger.info(f"Crop processing cancelled before starting video {file_num}/{total_videos} ({input_video_path.name}).")
                    raise OperationCancelledError("User cancelled operation")
                
                # Use .mp4 extension for output regardless of input extension
                output_video_name = f"{input_video_path.stem}_cropped.mp4" 
                output_video_path = self._output_dir / output_video_name

                logger.info(f"--- Processing video {file_num}/{total_videos}: {input_video_path.name} -> {output_video_path.name} ---")
                self.status_update.emit(f"動画 {file_num}/{total_videos}: {input_video_path.name} を処理中...")
                self.log_message.emit(f"--- 動画 {file_num}: {input_video_path.name} --- 開始 --- ({output_video_path.name})") 
                
                # --- Calculate actual crop coordinates if 'center' is specified --- 
                w = self._crop_params.get('w')
                h = self._crop_params.get('h')
                x_param = self._crop_params.get('x')
                y_param = self._crop_params.get('y')
                
                if x_param == 'center' or y_param == 'center':
                     logger.debug(f"Centering required for {input_video_path.name}. Getting video dimensions...")
                     input_w, input_h = self._get_video_dimensions(input_video_path)
                     if input_w is None or input_h is None:
                          # Raise specific error for UI
                          raise ValueError(f"'{input_video_path.name}' の解像度を取得できませんでした。ログを確認してください。") 
                      
                     target_w = w
                     target_h = h
                     # Calculate coordinates, default to 0 if param is not 'center' but centering was triggered (should not happen)
                     x = round((input_w - target_w) / 2) if x_param == 'center' else int(x_param if x_param != 'center' else 0) 
                     y = round((input_h - target_h) / 2) if y_param == 'center' else int(y_param if y_param != 'center' else 0) 
                     
                     # Validate calculated coordinates
                     if x < 0 or y < 0 or target_w <= 0 or target_h <= 0 or x + target_w > input_w or y + target_h > input_h:
                         logger.error(f"Invalid calculated crop coordinates for {input_video_path.name}: W={target_w}, H={target_h}, X={x}, Y={y} (Input: {input_w}x{input_h})")
                         # Raise specific error for UI
                         raise ValueError(f"'{input_video_path.name}' の計算されたクロップ座標が無効です (入力={input_w}x{input_h}, 計算結果=W:{target_w},H:{target_h},X:{x},Y:{y})。ログを確認してください。") 
                     logger.info(f"Calculated center crop for {input_video_path.name}: W={target_w}, H={target_h}, X={x}, Y={y}")
                     crop_filter = f"crop={target_w}:{target_h}:{x}:{y}"
                else:
                    # This block should ideally not be reached with fixed params
                    logger.warning(f"Crop parameters for {input_video_path.name} do not specify 'center', using directly: {self._crop_params}")
                    try:
                        x = int(x_param)
                        y = int(y_param)
                        if w <= 0 or h <= 0 or x < 0 or y < 0:
                             raise ValueError("Invalid non-center parameters")
                        crop_filter = f"crop={w}:{h}:{x}:{y}"
                    except (TypeError, ValueError) as e:
                        logger.error(f"Invalid non-center crop parameters for {input_video_path.name}: {self._crop_params}")
                        raise ValueError(f"'{input_video_path.name}' のクロップパラメータが無効です: {self._crop_params}") from e
                # ---------------------------------------------------------------------

                # --- Build and run FFmpeg command --- 
                cmd = [
                    self._ffmpeg_path, 
                    '-i', str(input_video_path),
                    '-y', # Overwrite output without asking
                    '-vf', crop_filter,
                    '-c:v', 'libx264', # Explicitly set video codec
                    '-crf', '23', # Constant Rate Factor (adjust quality/size)
                    '-preset', 'fast', # Encoding speed preset
                    '-c:a', 'aac', # Set audio codec to AAC (common compatibility)
                    '-b:a', '128k', # Set audio bitrate
                    str(output_video_path)
                ]
                
                logger.info(f"Running FFmpeg command: {' '.join(cmd)}")
                # +++ Add detailed logging +++
                logger.debug(f"Executing subprocess for crop: {cmd}")
                # +++ End added logging +++
                # Use shorter message for UI log
                self.log_message.emit(f"[{file_num}/{total_videos}] FFmpeg 実行中: {input_video_path.name} -> {output_video_path.name}") 
                start_time = time.time()
                success = False
                try:
                    # Using subprocess.run
                    self._process = subprocess.run(cmd, capture_output=True, text=True, encoding='utf-8', check=False,
                                                 creationflags=subprocess.CREATE_NO_WINDOW if os.name == 'nt' else 0)
                    
                    elapsed_time = time.time() - start_time
                    if self._cancelled:
                        logger.warning(f"Cancellation detected after ffmpeg finished for {input_video_path.name}. Cleaning up.")
                        self.log_message.emit(f"[{file_num}/{total_videos}] 処理中にキャンセル: {input_video_path.name}") 
                        if output_video_path.exists():
                             try: 
                                 output_video_path.unlink()
                                 logger.debug(f"Removed partial output file: {output_video_path}")
                             except OSError as e:
                                 logger.warning(f"Failed to remove partial output file {output_video_path}: {e}")
                        # Re-raise to exit the loop cleanly
                        raise OperationCancelledError("User cancelled operation after ffmpeg run") 

                    if self._process.returncode == 0:
                        logger.info(f"Video {file_num} processed successfully in {elapsed_time:.2f}s: {output_video_path.name}")
                        self.log_message.emit(f"[{file_num}/{total_videos}] 成功 ({elapsed_time:.2f}秒): {output_video_path.name}") 
                        success_count += 1
                        success = True
                    else: 
                        error_msg = f"Video {file_num} processing failed (Code: {self._process.returncode}) in {elapsed_time:.2f}s: {input_video_path.name}"
                        logger.error(error_msg)
                        logger.debug(f"[ffmpeg stderr for {input_video_path.name}]:\n{self._process.stderr}") 
                        logger.debug(f"[ffmpeg stdout for {input_video_path.name}]:\n{self._process.stdout}")
                        ui_error_msg = f"[{file_num}/{total_videos}] エラー (Code:{self._process.returncode}): {input_video_path.name}"
                        self.log_message.emit(ui_error_msg) 
                        # Emit only first few lines to UI log to prevent flooding
                        stderr_lines = self._process.stderr.splitlines()
                        self.log_message.emit("[ffmpeg stderr]:")
                        for line_idx, line in enumerate(stderr_lines):
                             if line_idx >= 5:
                                 break
                             self.log_message.emit(f"  {line}")
                        if len(stderr_lines) > 5:
                            self.log_message.emit("  ... (詳細はログファイルを確認)")
                        self.error_occurred.emit(ui_error_msg) # Emit concise error for potential popups
                        error_count += 1
                
                except OperationCancelledError: # Catch re-raised cancellation
                     raise # Propagate to outer handler
                except Exception as e: 
                    # Catch other exceptions during the subprocess run or calculation
                    if self._cancelled:
                         raise OperationCancelledError("Cancelled during exception handling") 
                    error_msg = f"Unexpected error during processing video {file_num} ({input_video_path.name}): {e}"
                    logger.exception(error_msg) # Log full traceback
                    ui_error_msg = f"[{file_num}/{total_videos}] 予期せぬエラー: {input_video_path.name} - {e}"
                    self.log_message.emit(ui_error_msg) 
                    self.error_occurred.emit(ui_error_msg)
                    error_count += 1
                finally:
                    self._process = None # Clear process handle
                    processed_files += 1
                    progress = int((processed_files / total_videos) * 100)
                    self.progress_updated.emit(progress)
                    result_str = '成功' if success else '失敗'
                    logger.info(f"--- Finished video {file_num}/{total_videos}: {input_video_path.name} --- Result: {result_str} ---")
                    # Shorter UI message
                    self.log_message.emit(f"[{file_num}/{total_videos}] 完了 ({result_str}): {input_video_path.name}") 
                    QThread.msleep(50) # Small delay for UI responsiveness

            # --- Loop finished --- 
            final_message = f"全 {total_videos} 件の処理完了。成功: {success_count}, 失敗: {error_count}。"
            logger.info(final_message)
            self.log_message.emit("--- 処理結果 ---")
            self.log_message.emit(f"成功: {success_count} 件")
            self.log_message.emit(f"失敗: {error_count} 件")
            self.status_update.emit("完了")
            self.finished.emit(error_count == 0, success_count, error_count)

        except OperationCancelledError:
            # Log final counts upon cancellation
            final_message = f"処理はキャンセルされました。完了: {success_count}, 失敗: {error_count} (残り {total_videos - processed_files} 件未処理)。"
            logger.info(final_message)
            self.log_message.emit("--- 処理結果 (キャンセル) ---")
            self.log_message.emit(f"完了済み (成功): {success_count} 件")
            self.log_message.emit(f"完了済み (失敗): {error_count} 件")
            self.log_message.emit(f"未処理: {total_videos - processed_files} 件")
            self.status_update.emit("キャンセル済")
            # Overall success is false if cancelled
            self.finished.emit(False, success_count, error_count) 
        except (FileNotFoundError, NotADirectoryError, ValueError) as e:
            # Handle specific setup or per-file errors that halt processing
            error_msg = f"処理停止エラー: {e}"
            logger.error(error_msg, exc_info=True) # Log traceback for these errors
            ui_error_msg = f"エラー: {e}" # User-friendly message
            self.log_message.emit(f"!!! {ui_error_msg} !!!") # UI message
            self.error_occurred.emit(ui_error_msg)
            self.status_update.emit("エラー発生")
            # Count remaining files as errors if processing halted prematurely
            error_count += (total_videos - processed_files)
            self.finished.emit(False, success_count, error_count)
        except Exception as e:
            # Catch any other unexpected errors
            error_msg = f"Unexpected error during crop processing loop: {e}"
            logger.exception(error_msg) # Log full traceback
            ui_error_msg = f"クロップ処理中に予期せぬエラーが発生しました: {e}"
            self.log_message.emit(f"!!! {ui_error_msg} !!!") # UI message
            self.error_occurred.emit(ui_error_msg)
            self.status_update.emit("エラー発生")
            error_count += (total_videos - processed_files)
            self.finished.emit(False, success_count, error_count)
        finally:
             self._process = None # Ensure process handle is cleared
             logger.info("Crop processing run method finished.") # Log end of run

    @Slot()
    def cancel(self):
        logger.info("CropWorker cancel requested.")
        self.log_message.emit("クロップ処理のキャンセル要求を受信しました。")
        self._cancelled = True
        # --- Cancellation Logic (Best effort with subprocess.run) --- 
        # If _process held a Popen object, we could terminate/kill.
        # With subprocess.run, the process completes before returning.
        # The flag self._cancelled is the primary mechanism to stop processing *between* files.
        # We could potentially add a check *during* ffmpeg by using Popen and monitoring, 
        # but that adds significant complexity.
        # -----------------------------------------------------------
        # if self._process: # self._process is None after subprocess.run finishes
        #      logger.debug("Attempting to terminate FFmpeg process...")
        #      # self._process.terminate() # Or kill()

    # --- Helper to get video dimensions (needed for centering) --- 
    def _get_video_dimensions(self, video_path: Path) -> tuple[int | None, int | None]:
        """Gets the width and height of the first video stream."""
        # Try finding ffprobe next to ffmpeg first, then PATH
        ffprobe_path = None
        try:
            ffmpeg_dir = Path(self._ffmpeg_path).parent
            ffprobe_name = "ffprobe.exe" if platform.system() == "Windows" else "ffprobe"
            potential_ffprobe = ffmpeg_dir / ffprobe_name
            if potential_ffprobe.is_file():
                ffprobe_path = str(potential_ffprobe)
                logger.debug(f"Found ffprobe next to ffmpeg: {ffprobe_path}")
        except Exception as e: 
            logger.warning(f"Could not determine ffmpeg directory: {e}")

        if not ffprobe_path:
            ffprobe_path = shutil.which("ffprobe.exe" if platform.system() == "Windows" else "ffprobe")
            if ffprobe_path:
                 logger.debug(f"Found ffprobe in PATH: {ffprobe_path}")
            else:
                 logger.error("ffprobe executable not found next to ffmpeg or in PATH.")
                 # Raise error or return None? Returning None is handled by caller.
                 return None, None 
        
        command = [
            ffprobe_path,
            '-v', 'error',
            '-select_streams', 'v:0',
            '-show_entries', 'stream=width,height',
            '-of', 'json',
            str(video_path)
        ]
        logger.debug(f"Running ffprobe command: {' '.join(command)}")
        try:
            # +++ Add detailed logging +++
            logger.debug(f"Executing subprocess for dimensions (CropWorker): {command}")
            # +++ End added logging +++
            # Increased timeout slightly
            process = subprocess.run(command, capture_output=True, text=True, encoding='utf-8', check=False, timeout=15, 
                                     creationflags=subprocess.CREATE_NO_WINDOW if os.name == 'nt' else 0)
            if process.returncode != 0:
                logger.error(f"ffprobe failed for {video_path.name} (Code: {process.returncode}): {process.stderr}")
                return None, None
            # Add extra check for empty stdout
            if not process.stdout.strip():
                 logger.error(f"ffprobe returned success but stdout is empty for {video_path.name}")
                 return None, None
            data = json.loads(process.stdout)
            if data and 'streams' in data and data['streams']:
                width = data['streams'][0].get('width')
                height = data['streams'][0].get('height')
                if isinstance(width, int) and isinstance(height, int):
                     logger.debug(f"Dimensions for {video_path.name}: {width}x{height}")
                     return width, height
                else:
                     logger.error(f"Parsed dimensions are not integers for {video_path.name}: w={width}, h={height}")
                     return None, None # Treat non-integer as error
            logger.error(f"Could not parse dimensions from ffprobe output for {video_path.name}: {data}")
            return None, None
        except subprocess.TimeoutExpired:
            logger.error(f"ffprobe timed out getting dimensions for {video_path.name}")
            return None, None
        except (json.JSONDecodeError, FileNotFoundError, Exception) as e:
            logger.exception(f"Error getting video dimensions for {video_path.name}: {e}")
            return None, None

# ... (PreviewWorker might need similar logging/error handling improvements) ...
