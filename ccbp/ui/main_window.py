from PySide6.QtWidgets import QMainWindow, QApplication, QTabWidget, QStatusBar, QMessageBox, QProgressDialog
from PySide6.QtCore import Slot, Qt, QTimer
from PySide6.QtGui import QAction # Import QAction
import logging # Import logging

# Import actual tab views
from .batch_tab import BatchTabView
from .crop_tab import CropTabView
from .settings_tab import SettingsTabView

# Import actual controllers using relative imports

# Import Help Viewer
from .help_view import HelpViewer # Import HelpViewer and helper

logger = logging.getLogger(__name__) # Setup logger for this module

class MainWindow(QMainWindow):
    def __init__(self):
        super().__init__()
        self.setWindowTitle("CapCut Batch Processor")
        self.setGeometry(100, 100, 800, 600) # Default size

        self.tab_widget = QTabWidget()
        self.setCentralWidget(self.tab_widget)

        # Add Status Bar
        self.status_bar = QStatusBar()
        self.setStatusBar(self.status_bar)
        # Display initial message or version (replace with dynamic version later)
        self.status_bar.showMessage("CapCut Batch Processor v1.0.0 - 準備完了") 

        # Initialize actual tabs (Views)
        self.batch_tab = BatchTabView(self)
        self.crop_tab = CropTabView(self)
        self.settings_tab = SettingsTabView(self)

        # Initialize controllers list (will be populated in init_controllers)
        self.controllers = [] # Initialize as empty list
        self.batch_controller = None
        self.crop_controller = None
        self.settings_controller = None
        self.previous_tab_index = -1
        self.loading_dialog: QProgressDialog | None = None # ローディングダイアログ用変数
        # --- Add Timer --- 
        self.loading_timer = QTimer(self)
        self.loading_timer.setInterval(500) # Update interval (ms)
        self.loading_timer.timeout.connect(self._update_loading_text)
        self._loading_dots = 0
        # --- End Timer ---

        self.init_ui()
        # Controllers are initialized after ConfigManager in main.py
        # self.init_controllers() # Removed from here

        self.setup_menu() # Call menu setup

    def init_ui(self):
        # Add tabs to the QTabWidget using the instantiated views
        self.tab_widget.addTab(self.batch_tab, "プロジェクト生成")
        self.tab_widget.addTab(self.crop_tab, "動画切り出し")
        self.tab_widget.addTab(self.settings_tab, "設定")

        # Connect tab change signal
        self.tab_widget.currentChanged.connect(self.on_tab_changed)

        # No need to add status bar here, it's set via self.setStatusBar
        pass

    def setup_menu(self):
        """Sets up the main menu bar."""
        menu_bar = self.menuBar()

        # File Menu (Example - Adjust as needed)
        file_menu = menu_bar.addMenu("ファイル")
        exit_action = QAction("終了", self)
        exit_action.triggered.connect(self.close)
        file_menu.addAction(exit_action)

        # Help Menu
        help_menu = menu_bar.addMenu("ヘルプ")

        help_action = QAction("ヘルプを表示", self)
        help_action.triggered.connect(self.show_help)
        help_menu.addAction(help_action)

        help_menu.addSeparator()

        batch_help_action = QAction("バッチ処理について", self)
        batch_help_action.triggered.connect(lambda: self.show_help_topic("topics/batch.html"))
        help_menu.addAction(batch_help_action)

        crop_help_action = QAction("クロップ処理について", self)
        crop_help_action.triggered.connect(lambda: self.show_help_topic("topics/crop.html"))
        help_menu.addAction(crop_help_action)

        license_help_action = QAction("ライセンスとトライアルについて", self)
        license_help_action.triggered.connect(lambda: self.show_help_topic("topics/license.html"))
        help_menu.addAction(license_help_action)

        help_menu.addSeparator()

        about_action = QAction("バージョン情報", self)
        about_action.triggered.connect(self.show_about)
        help_menu.addAction(about_action)

    def show_help(self):
        """メインヘルプページを表示"""
        try:
            # Use a new instance each time or manage a single instance
            self.help_viewer = HelpViewer(self, base_page="index.html")
            self.help_viewer.show()
        except Exception as e:
            logger.exception("ヘルプビューアの表示中にエラーが発生しました。")
            QMessageBox.critical(self, "ヘルプエラー", f"ヘルプを表示できませんでした: {e}")

    def show_help_topic(self, topic_page):
        """指定されたトピックページを表示"""
        try:
            self.help_viewer = HelpViewer(self, base_page=topic_page)
            self.help_viewer.show()
        except Exception as e:
            logger.exception(f"ヘルプビューアの表示中にエラーが発生しました (トピック: {topic_page})。")
            QMessageBox.critical(self, "ヘルプエラー", f"ヘルプトピック '{topic_page}' を表示できませんでした: {e}")

    def show_about(self):
        """バージョン情報ダイアログを表示"""
        # Consider reading version from a central place (e.g., config or __version__)
        app_version = "1.0.0" # Placeholder
        try:
            # Example: Read from a file if you store version there
            # version_file = get_resource_path("VERSION")
            # if os.path.exists(version_file):
            #     with open(version_file, 'r') as f:
            #         app_version = f.read().strip()
            pass # Implement actual version fetching if needed
        except Exception as e:
            logger.warning(f"バージョン情報の読み取りに失敗: {e}")
        
        QMessageBox.about(
            self,
            "CapCut Batch Processor について",
            f"バージョン: {app_version}\n"
            f"Copyright © 2025"
            # Add more info like links if desired
        )

    def set_controllers(self, batch_controller, crop_controller, settings_controller):
        """main.pyからコントローラーを設定し、シグナルを接続する"""
        self.batch_controller = batch_controller
        self.crop_controller = crop_controller
        self.settings_controller = settings_controller
        self.controllers = [batch_controller, crop_controller, settings_controller]

        # --- コントローラーにビューを設定 --- 
        if self.batch_controller and hasattr(self.batch_controller, 'set_view'):
            self.batch_controller.set_view(self.batch_tab)
        if self.crop_controller and hasattr(self.crop_controller, 'set_view'):
            self.crop_controller.set_view(self.crop_tab)
        if self.settings_controller and hasattr(self.settings_controller, 'set_view'):
            self.settings_controller.set_view(self.settings_tab)
        # --- ここまで --- 

        # --- SettingsControllerに他のコントローラー参照を渡す --- 
        if self.settings_controller and hasattr(self.settings_controller, 'set_other_controllers'):
            self.settings_controller.set_other_controllers(batch_controller, crop_controller)
        # --- ここまで --- 

        # --- SettingsController のシグナル接続 ---
        if self.settings_controller:
            self.settings_controller.authentication_started.connect(self._show_loading_dialog)
            self.settings_controller.authentication_finished.connect(self._hide_loading_dialog)
        # --- ここまで ---
        
        # Link views back to controllers using set_controller method if needed
        # Note: set_controller is often called within controller's set_view now
        # These might be redundant if set_view handles it.
        if hasattr(self.batch_tab, 'set_controller') and self.batch_controller:
             self.batch_tab.set_controller(self.batch_controller)
        if hasattr(self.crop_tab, 'set_controller') and self.crop_controller:
             self.crop_tab.set_controller(self.crop_controller)
        if hasattr(self.settings_tab, 'set_controller') and self.settings_controller:
             self.settings_tab.set_controller(self.settings_controller)

    @Slot()
    def _show_loading_dialog(self):
        """認証中のローディングダイアログ(QProgressDialog)を表示する"""
        if self.loading_dialog is None:
            self._loading_dots = 0 # Reset dots
            base_text = "ライセンスサーバーと通信中"
            self.loading_dialog = QProgressDialog(base_text, None, 0, 0, self)
            self.loading_dialog.setWindowTitle("認証確認")
            self.loading_dialog.setCancelButton(None)
            self.loading_dialog.setWindowModality(Qt.WindowModal)
            self.loading_dialog.setMinimumDuration(0)
        self.loading_dialog.show()
        # --- Start Timer --- 
        self.loading_timer.start()
        # --- End Start ---
        QApplication.processEvents()
        
    @Slot()
    def _update_loading_text(self):
        """Update the loading dialog text with cycling dots."""
        if self.loading_dialog:
            self._loading_dots = (self._loading_dots + 1) % 4 # Cycle 0, 1, 2, 3
            dots = "." * self._loading_dots
            # Ensure base text doesn't accumulate dots if timer fires rapidly
            base_text = "ライセンスサーバーと通信中"
            self.loading_dialog.setLabelText(base_text + dots)

    @Slot(str, bool)
    def _hide_loading_dialog(self, message: str, success: bool):
        """ローディングダイアログ(QProgressDialog)を非表示にし、結果をステータスバーに表示する"""
        # --- Stop Timer --- 
        self.loading_timer.stop()
        # --- End Stop ---
        if self.loading_dialog is not None:
            self.loading_dialog.close()
            self.loading_dialog = None

        # ステータスバーに結果メッセージを表示
        status_prefix = "認証成功" if success else "認証失敗"
        self.status_bar.showMessage(f"{status_prefix}: {message}", 5000) # 5秒表示

    def on_tab_changed(self, index):
        # Finalize the controller of the previously selected tab
        if 0 <= self.previous_tab_index < len(self.controllers):
            controller = self.controllers[self.previous_tab_index]
            if controller and hasattr(controller, 'finalize'):
                print(f"Finalizing controller for tab {self.previous_tab_index}") # Debug print
                try:
                    controller.finalize()
                except Exception as e:
                    print(f"Error finalizing controller for tab {self.previous_tab_index}: {e}") # Add error handling
        
        self.previous_tab_index = index
        # Potentially initialize or activate the new tab's controller here if needed

    def closeEvent(self, event):
        # Finalize all controllers before closing
        print("Main window closing, finalizing all controllers...") # Debug print
        for i, controller in enumerate(self.controllers):
            if controller and hasattr(controller, 'finalize'):
                try:
                    controller.finalize()
                except Exception as e:
                    print(f"Error finalizing controller for tab {i} during close: {e}") # Add error handling
        super().closeEvent(event)

    # --- UI Notification Methods --- 
    def show_info_message(self, title: str, message: str):
        QMessageBox.information(self, title, message)

    def show_warning_message(self, title: str, message: str):
        QMessageBox.warning(self, title, message)
    
    def show_error_message(self, title: str, message: str):
        QMessageBox.critical(self, title, message)
    # --- End UI Notification Methods --- 

# --- Removed __main__ block for direct execution --- 
# if __name__ == '__main__':
#    # ... (Removed code) 