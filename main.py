import sys
import os
import logging # Import logging
from dotenv import load_dotenv
# --- PySide6 Imports ---
from PySide6.QtWidgets import QApplication, QMessageBox
from PySide6.QtGui import QPalette, QColor
# --- CCBP Imports ---
from ccbp.ui.main_window import MainWindow
from ccbp.utils.logging_config import setup_logging, get_logger
from ccbp.core.config_manager import ConfigManager
from ccbp.core.license_manager import LicenseManager
from ccbp.core.crop_controller import CropController
from ccbp.core.batch_controller import BatchController
from ccbp.core.settings_controller import SettingsController

# アプリケーション全体のログレベルをここで一元管理
LOG_LEVEL = logging.INFO  # 全体のログレベル
CONFIG_MANAGER_LOG_LEVEL = logging.INFO  # config_manager特有のログレベル

# Add the project root directory to the Python path
project_root = os.path.dirname(os.path.abspath(__file__))
if project_root not in sys.path:
    sys.path.insert(0, project_root)
    # Optional: for debugging
    # print(f"Added project root to sys.path: {project_root}")

# --- Initialize logging ---
logger = None # Initialize logger to None
try:
    setup_logging(level=LOG_LEVEL)  # セットアップ時にレベルを渡す
    logger = get_logger(__name__)
    # config_managerのログレベルを特別に設定
    logging.getLogger("ccbp.core.config_manager").setLevel(CONFIG_MANAGER_LOG_LEVEL)
    # capcut_handler のログレベルも INFO に設定
    logging.getLogger("ccbp.core.capcut_handler").setLevel(logging.INFO)
except Exception as log_e:
    print(f"Error setting up logging: {log_e}", file=sys.stderr)
    # logger remains None

# --- Load .env ---
dotenv_path_str = '.env'
if os.path.exists(dotenv_path_str):
    load_dotenv(dotenv_path=dotenv_path_str)
    if logger: 
        logger.info(f"Loaded environment variables from: {dotenv_path_str}")
    else: 
        print(f"Loaded environment variables from: {dotenv_path_str}")
else:
    if logger: 
        logger.info(".env file not found.")
    else: 
        print(".env file not found.")

def main_gui(): # Renamed original main
    if logger: # Check if logger was successfully initialized
        logger.setLevel(LOG_LEVEL)  # グローバル変数を使用
    else:
        # Fallback basic logging if setup failed
        logging.basicConfig(level=LOG_LEVEL, format='%(levelname)s: %(message)s')  # グローバル変数を使用
        logging.warning("Basic logging configured because setup_logging failed.")
        # config_managerのログレベルを特別に設定
        logging.getLogger("ccbp.core.config_manager").setLevel(CONFIG_MANAGER_LOG_LEVEL)

    app = QApplication(sys.argv)

    # --- ダークモード強制適用 ---
    app.setStyle("Fusion")
    dark_palette = QPalette()
    dark_palette.setColor(QPalette.Window, QColor(53, 53, 53))
    dark_palette.setColor(QPalette.WindowText, QColor(220, 220, 220))
    dark_palette.setColor(QPalette.Base, QColor(35, 35, 35))
    dark_palette.setColor(QPalette.AlternateBase, QColor(53, 53, 53))
    dark_palette.setColor(QPalette.ToolTipBase, QColor(220, 220, 220))
    dark_palette.setColor(QPalette.ToolTipText, QColor(220, 220, 220))
    dark_palette.setColor(QPalette.Text, QColor(220, 220, 220))
    dark_palette.setColor(QPalette.Button, QColor(53, 53, 53))
    dark_palette.setColor(QPalette.ButtonText, QColor(220, 220, 220))
    dark_palette.setColor(QPalette.BrightText, QColor(255, 0, 0))
    dark_palette.setColor(QPalette.Link, QColor(42, 130, 218))
    dark_palette.setColor(QPalette.Highlight, QColor(42, 130, 218))
    dark_palette.setColor(QPalette.HighlightedText, QColor(35, 35, 35))
    app.setPalette(dark_palette)
    app.setStyleSheet("QToolTip { color: #dddddd; background-color: #222222; border: 1px solid #666666; }")

    # --- Initialize Managers ---
    config_manager = None
    license_manager = None
    try:
        config_manager = ConfigManager()
    except Exception as e:
        log_msg = f"Failed to initialize ConfigManager: {e}"
        if logger: 
            logger.exception(log_msg)
        else: 
            print(log_msg, file=sys.stderr)
        QMessageBox.critical(None, "設定エラー", f"設定マネージャーの初期化に失敗しました: {e}")
        sys.exit(1)

    try:
        license_manager = LicenseManager(config_manager)
        license_manager.initialize_trial_if_needed()
    except Exception as e:
        log_msg = f"Failed to initialize LicenseManager: {e}"
        if logger: 
            logger.exception(log_msg)
        else: 
            print(log_msg, file=sys.stderr)
        QMessageBox.critical(None, "ライセンスエラー", f"ライセンス管理機能の初期化に失敗しました: {e}")
        sys.exit(1)

    # --- Initialize Controllers ---
    batch_controller = None
    crop_controller = None
    settings_controller = None
    try:
        batch_controller = BatchController(config_manager=config_manager, license_manager=license_manager)
        crop_controller = CropController(config_manager=config_manager, license_manager=license_manager)
        settings_controller = SettingsController(config_manager=config_manager, license_manager=license_manager)
    except Exception as e:
        log_msg = f"Failed to initialize one or more controllers: {e}"
        if logger: 
            logger.exception(log_msg)
        else: 
            print(log_msg, file=sys.stderr)
        QMessageBox.critical(None, "初期化エラー", f"コントローラーの初期化に失敗しました: {e}")
        sys.exit(1)

    # --- Initialize MainWindow ---
    main_window = None
    try:
        main_window = MainWindow()
        main_window.set_controllers(batch_controller, crop_controller, settings_controller)
    except Exception as e:
        log_msg = f"Failed to initialize MainWindow: {e}"
        if logger: 
            logger.exception(log_msg)
        else: 
            print(log_msg, file=sys.stderr)
        QMessageBox.critical(None, "初期化エラー", f"メインウィンドウの初期化に失敗しました: {e}")
        sys.exit(1)

    # --- Check Trial Status ---
    try:
        trial_status = license_manager.get_trial_status()
        if logger: 
            logger.info(f"Startup trial status: {trial_status}")
        if trial_status['tampered']:
            main_window.show_warning_message("日付警告", "システムの日付が不正に変更された可能性があります。トライアル期間が正しく計算されない場合があります。")
        if trial_status['restricted']:
            main_window.show_warning_message(
                "制限モード",
                "トライアル期間が終了しました。バッチ処理は1日5件まで、クロップ機能は使用できません。ライセンスをご購入ください。"
            )
        elif trial_status['in_trial']:
            days_left = trial_status['days_left']
            if days_left <= 3:
                main_window.show_info_message(
                    "トライアル期間", 
                    f"トライアル期間は残り{days_left}日です。終了後は一部機能が制限されます。"
                )
    except Exception: # Keep bare except if we don't use the exception variable
        if logger: 
            logger.exception("トライアルステータスの確認中にエラーが発生しました。")
        main_window.show_error_message("起動エラー", "トライアル状態の確認中に問題が発生しました。")

    # --- Run Application ---
    main_window.show() 
    exit_code = app.exec()

    # --- Save Config on Exit ---
    if logger: 
        logger.info("Application exiting. Saving configuration...")
    try:
        if config_manager: # Ensure config_manager was initialized
            config_manager.save()
            if logger: 
                logger.info("Configuration saved.")
    except Exception as e:
        log_msg = f"Error saving configuration on exit: {e}"
        if logger: 
            logger.exception(log_msg)
        else: 
            print(log_msg, file=sys.stderr)

    sys.exit(exit_code)

# # --- New Test Code --- 
# import csv
# import logging
# import shutil
# from pathlib import Path
# from ccbp.core.capcut_handler import CapcutHandler
# from ccbp.core.file_system_handler import FileSystemHandler
# from ccbp.utils.logging_config import setup_logging # Import setup_logging

# # Configure logging for the test
# setup_logging(level=logging.DEBUG) # Enable DEBUG level logging
# logger = logging.getLogger(__name__)
# # logging.getLogger("ccbp.core.file_system_handler").setLevel(logging.DEBUG)
# # logging.getLogger("ccbp.core.capcut_handler").setLevel(logging.DEBUG)

# def run_single_test():
#     logger.info("--- Starting CapcutHandler Single Test ---")
    
#     # --- User Paths (Use absolute paths provided) ---
#     TEMPLATE_PROJECT_PATH = "/Users/mbp/Movies/CapCut/User Data/Projects/com.lveditor.draft/TemplateA"
#     TEMPLATE_MATERIAL_BASE = "/Users/mbp/Movies/CapCut/CCBP_WorkSpace/TemplateMaterial/TemplateA" 
#     CHANGE_MATERIAL_BASE = "/Users/mbp/Movies/CapCut/CCBP_WorkSpace/ChangeMaterial"
#     CSV_DATA_PATH = "/Users/mbp/Movies/CapCut/sample_batch_sheet.csv"
#     TEST_OUTPUT_BASE_DIR = Path("validation_output/main_test_output") # Temporary output
#     TEST_OUTPUT_BASE_DIR.mkdir(parents=True, exist_ok=True)
#     logger.info(f"Test output base directory: {TEST_OUTPUT_BASE_DIR}")

#     # --- Read first data row from CSV ---
#     first_row = None
#     try:
#         with open(CSV_DATA_PATH, 'r', newline='', encoding='utf-8-sig') as csvfile:
#             reader = csv.DictReader(csvfile)
#             first_row = next(reader, None) # Get the first row
#     except FileNotFoundError:
#         logger.error(f"CSV file not found: {CSV_DATA_PATH}")
#         return
#     except Exception as e:
#         logger.error(f"Error reading CSV file {CSV_DATA_PATH}: {e}", exc_info=True)
#         return
        
#     if not first_row:
#         logger.error("CSV file is empty or has no data rows.")
#         return
#     logger.info(f"Loaded first data row from CSV: {first_row.get('ProjectName', 'N/A')}")

#     # --- Prepare output directory ---
#     project_name = first_row.get("ProjectName", "TestProject")
#     # Create a unique subfolder for this test run within the temp output
#     output_project_dir_str = str(TEST_OUTPUT_BASE_DIR / project_name)
#     logger.info(f"Copying template project '{TEMPLATE_PROJECT_PATH}' to '{output_project_dir_str}'...")
    
#     # Use FileSystemHandler to copy the template project
#     copied_project_path = FileSystemHandler.copy_template_project(TEMPLATE_PROJECT_PATH, str(TEST_OUTPUT_BASE_DIR), project_name)
    
#     if not copied_project_path:
#         logger.error("Failed to copy template project. Aborting test.")
#         return

#     logger.info(f"Template project copied successfully to: {copied_project_path}")

#     # --- Run CapcutHandler ---
#     try:
#         logger.info(f"Initializing CapcutHandler for copied project: {copied_project_path}")
#         # Initialize with the COPIED project path
#         handler = CapcutHandler(project_path=copied_project_path)
        
#         # Update paths and text using the first CSV row
#         logger.info("Calling handler.update_material_paths()...")
#         success = handler.update_material_paths(
#             csv_row_data=first_row,
#             template_material_base=TEMPLATE_MATERIAL_BASE,
#             change_material_base=CHANGE_MATERIAL_BASE
#         )
        
#         if success:
#             logger.info("handler.update_material_paths() completed successfully.")
#             # Optionally save the result
#             # logger.info("Calling handler.save_changes()...")
#             # save_success = handler.save_changes()
#             # logger.info(f"handler.save_changes() result: {save_success}")
#         else:
#             logger.error("handler.update_material_paths() failed.")
            
#     except Exception as e:
#         logger.error(f"Error during CapcutHandler execution: {e}", exc_info=True)
        
# if __name__ == "__main__":
#     run_single_test()

if __name__ == "__main__":
    main_gui() # Call the GUI function
