import sys
import os
from PySide6.QtWidgets import QDialog, QVBoxLayout, QMessageBox
from PySide6.QtWebEngineWidgets import QWebEngineView
from PySide6.QtWebEngineCore import QWebEngineSettings
from PySide6.QtCore import QUrl, Qt
import logging

logger = logging.getLogger(__name__)

def get_resource_path(relative_path):
    """実行環境（開発/Nuitka）に関わらずリソースパスを解決"""
    if getattr(sys, 'frozen', False) and hasattr(sys, '_MEIPASS'):
        # Nuitkaでパッケージされた場合 (_MEIPASS が一時展開ディレクトリ)
        base_path = sys._MEIPASS
        logger.debug(f"Running in Nuitka bundle. MEIPASS: {base_path}")
    else:
        # 通常のPython環境 (開発環境)
        # このファイルの場所からプロジェクトルートを推定
        # ccbp/ui/help_view.py -> ccbp/ -> project root
        base_path = os.path.dirname(os.path.dirname(os.path.dirname(__file__)))
        logger.debug(f"Running in development mode. Base path: {base_path}")

    resource_path = os.path.join(base_path, relative_path)
    logger.debug(f"Resolved resource path for '{relative_path}': {resource_path}")
    return resource_path

class HelpViewer(QDialog):
    """HTML/CSSベースのヘルプドキュメントを表示するダイアログ"""

    def __init__(self, parent=None, base_page="index.html"):
        super().__init__(parent)
        self.setWindowTitle("CapCut Batch Processor ヘルプ")
        self.setWindowFlags(self.windowFlags() | Qt.WindowType.WindowMinMaxButtonsHint)
        self.resize(800, 600)

        self.help_base_path = get_resource_path("ccbp/resources/help")
        logger.info(f"Help base path: {self.help_base_path}")

        layout = QVBoxLayout(self)
        layout.setContentsMargins(5, 5, 5, 5)

        self.web_view = QWebEngineView()
        # Enable necessary features like local file access if needed (be cautious)
        settings = self.web_view.settings()
        settings.setAttribute(QWebEngineSettings.WebAttribute.LocalContentCanAccessFileUrls, True)
        settings.setAttribute(QWebEngineSettings.WebAttribute.LocalContentCanAccessRemoteUrls, False) # Usually false for security
        settings.setAttribute(QWebEngineSettings.WebAttribute.PluginsEnabled, False) # Disable plugins
        settings.setAttribute(QWebEngineSettings.WebAttribute.JavascriptEnabled, True) # Enable if help files use JS

        layout.addWidget(self.web_view)

        self.navigate_to(base_page)

    def navigate_to(self, page_name):
        """指定されたヘルプページ（ルート相対）に移動"""
        target_file = os.path.abspath(os.path.join(self.help_base_path, page_name))
        logger.info(f"Navigating to help file: {target_file}")

        if os.path.exists(target_file):
            url = QUrl.fromLocalFile(target_file)
            if url.isValid():
                self.web_view.load(url)
            else:
                logger.error(f"Invalid URL generated for local file: {target_file}")
                self._show_error(f"ヘルプファイルのURLが無効です: {page_name}")
        else:
            logger.error(f"Help file not found: {target_file}")
            self._show_error(f"ヘルプファイルが見つかりません: {page_name}")

    def _show_error(self, message):
        """エラーメッセージをWebビューに表示するか、MsgBoxで表示"""
        # Simple fallback: show error in message box
        QMessageBox.warning(self, "ヘルプエラー", message)
        # Alternative: Display error HTML in the web view itself
        # error_html = f"<html><body><h1>エラー</h1><p>{message}</p></body></html>"
        # self.web_view.setHtml(error_html)

    # Example navigation methods if needed from within HTML (using QWebChannel)
    # def open_topic(self, topic):
    #     self.navigate_to(f"topics/{topic}.html") 