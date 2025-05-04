from PySide6.QtWidgets import (
    QWidget, QVBoxLayout, QGridLayout, QLabel, QLineEdit, QPushButton, QMessageBox,
    QGroupBox, QHBoxLayout, QSpacerItem, QSizePolicy
)
from PySide6.QtCore import Slot, Signal, QSize
from ccbp.core.config_manager import (
    KEY_WORKING_DIRECTORY,
    KEY_LICENSE_KEY,
    # Add other keys from ConfigManager that should be editable here
    # KEY_CROP_INPUT_DIR,
    # KEY_CROP_OUTPUT_DIR,
    # KEY_PREVIEW_SAVE_DIR
)
import logging
# Import common style
from .styles import BUTTON_STYLE

class SettingsTabView(QWidget):
    """UI View for the Settings Tab."""
    # Define signals for controller interaction
    # Signal emitted when the license check button is clicked
    check_license_requested = Signal()

    def __init__(self, parent=None):
        super().__init__(parent)
        self.logger = logging.getLogger(__name__)
        self.controller = None # Controller will be set externally

        self.setup_ui()

    def set_controller(self, controller):
        """Sets the controller for this view."""
        self.controller = controller
        self._connect_signals()

    def setup_ui(self):
        """Initializes the user interface components."""
        main_layout = QVBoxLayout(self)

        # --- Settings Group ---
        settings_group = QGroupBox("アプリケーション設定")
        grid_layout = QGridLayout()
        grid_layout.setSpacing(10)

        # Working Directory (Row 0, Row 1)
        self.working_dir_label = QLabel("作業ディレクトリ:")
        self.working_dir_edit = QLineEdit()
        self.working_dir_edit.setPlaceholderText("作業用のベースフォルダを選択")
        self.browse_working_dir_button = QPushButton("参照...")
        self.browse_working_dir_button.setStyleSheet(BUTTON_STYLE) # Apply style
        self.browse_working_dir_button.setFixedSize(QSize(100, 32)) # Set fixed size
        self.create_folders_button = QPushButton("デフォルトフォルダ作成")
        self.create_folders_button.setStyleSheet(BUTTON_STYLE) # Apply style
        self.create_folders_button.setFixedSize(QSize(160, 32)) # Set fixed size
        self.create_folders_button.setEnabled(False) # Initially disabled

        grid_layout.addWidget(self.working_dir_label, 0, 0)
        grid_layout.addWidget(self.working_dir_edit, 0, 1)
        grid_layout.addWidget(self.browse_working_dir_button, 0, 2)
        grid_layout.addWidget(self.create_folders_button, 1, 1, 1, 2) # Row 1, Col 1, Span 2 cols

        # --- Add Vertical Spacer (Row 2) ---
        # Add 10px vertical space across all columns
        grid_layout.addItem(QSpacerItem(20, 10, QSizePolicy.Policy.Minimum, QSizePolicy.Policy.Fixed), 2, 0, 1, grid_layout.columnCount())
        # --- End Spacer ---

        # License Key (Start from row 3 now)
        self.license_key_label = QLabel("ライセンスキー:")
        self.license_key_edit = QLineEdit()
        self.license_key_edit.setPlaceholderText("ライセンスキーを入力")
        self.license_key_edit.setEchoMode(QLineEdit.EchoMode.Password)
        self.check_license_button = QPushButton("認証確認")
        self.check_license_button.setStyleSheet(BUTTON_STYLE) # Apply style
        self.check_license_button.setFixedSize(QSize(100, 32)) # Change size to match browse button
        self.license_status_label = QLabel("状態: 未確認")
        self.progress_label = QLabel("認証中...") # Added progress label
        self.progress_label.setVisible(False) # Initially hidden
        self.progress_label.setStyleSheet("color: gray;") # Style for progress

        grid_layout.addWidget(self.license_key_label, 3, 0)       # Row index updated to 3
        grid_layout.addWidget(self.license_key_edit, 3, 1)       # Row index updated to 3
        grid_layout.addWidget(self.check_license_button, 3, 2)   # Row index updated to 3
        grid_layout.addWidget(self.license_status_label, 4, 1)  # Row index updated to 4
        grid_layout.addWidget(self.progress_label, 4, 2)         # Row index updated to 4

        # --- Set column stretch for the input field --- 
        grid_layout.setColumnStretch(1, 1) # Ensure input field takes available space

        settings_group.setLayout(grid_layout)
        main_layout.addWidget(settings_group)

        # --- Button Layout ---
        button_layout = QHBoxLayout()
        self.reset_button = QPushButton("設定リセット")
        self.reset_button.setStyleSheet(BUTTON_STYLE) # Apply style
        self.reset_button.setFixedSize(QSize(160, 32)) # Set fixed size
        self.clear_license_button = QPushButton("ライセンス情報クリア")
        self.clear_license_button.setStyleSheet(BUTTON_STYLE) # Apply style
        self.clear_license_button.setFixedSize(QSize(160, 32)) # Set fixed size
        # --- Remove Save Button --- 
        # self.save_button = QPushButton("設定を保存")
        # --- End Remove ---

        button_layout.addWidget(self.reset_button)
        button_layout.addWidget(self.clear_license_button)
        button_layout.addStretch()
        # --- Remove Save Button from layout --- 
        # button_layout.addWidget(self.save_button)
        # --- End Remove ---

        main_layout.addLayout(button_layout)
        main_layout.addStretch() # Push elements to the top

        self.setLayout(main_layout)

    def _connect_signals(self):
        """Connect UI signals to controller slots."""
        self.logger.debug(f"_connect_signals called for {self}")
        if not self.controller:
            self.logger.warning("Controller not set, cannot connect signals.")
            return
        try:
            # Disconnect existing connections to prevent duplicates
            self.browse_working_dir_button.clicked.disconnect()
            self.create_folders_button.clicked.disconnect()
            self.reset_button.clicked.disconnect()
            self.clear_license_button.clicked.disconnect()
            self.working_dir_edit.textChanged.disconnect()
            self.check_license_button.clicked.disconnect()
            self.check_license_requested.disconnect()
            # --- Remove Save Button disconnect ---
            # self.save_button.clicked.disconnect()
            # --- End Remove ---
            self.logger.debug("Attempted to disconnect existing signals before reconnecting.")
        except (TypeError, RuntimeError) as e:
            # Ignore errors if signals were not connected previously
            self.logger.debug(f"Error during signal disconnection (likely first time): {e}")
            pass
        try:
            # Connect new buttons
            self.browse_working_dir_button.clicked.connect(self.controller.browse_working_directory)
            self.create_folders_button.clicked.connect(self.controller.create_default_folders)
            self.reset_button.clicked.connect(self.controller.reset_settings)
            self.clear_license_button.clicked.connect(self.controller.clear_license)
            # Connect text changed to enable/disable create button
            self.working_dir_edit.textChanged.connect(self._update_create_button_state)
            # Connect the new check license button to emit the signal
            self.check_license_button.clicked.connect(self.check_license_requested.emit)
            # Connect the signal to the controller's slot - Use the correct method name
            self.check_license_requested.connect(self.controller.validate_license_key) # CORRECTED: Was check_license_key
            # --- Remove Save Button connect ---
            # self.save_button.clicked.connect(self.controller.save_settings)
            # --- End Remove ---
            self.logger.info("Settings view signals connected.")
        except AttributeError as e:
            self.logger.error(f"Error connecting settings signals: Missing attribute in controller or view? - {e}")
        except Exception as e:
             self.logger.exception(f"Unexpected error connecting settings signals: {e}")

    @Slot(str)
    def _update_create_button_state(self, text: str):
        """Enable create folders button only if path is entered."""
        self.create_folders_button.setEnabled(bool(text.strip()))

    # --- Methods to Update UI --- #

    @Slot(dict)
    def load_settings(self, settings: dict):
        """Loads setting values into the UI fields."""
        self.working_dir_edit.setText(settings.get(KEY_WORKING_DIRECTORY, ""))
        # Don't set license key directly, rely on set_license_status
        # self.license_key_edit.setText(settings.get(KEY_LICENSE_KEY, ""))
        # Removed crop settings
        # self.crop_input_edit.setText(settings.get(KEY_CROP_INPUT_DIR, ""))
        # self.crop_output_edit.setText(settings.get(KEY_CROP_OUTPUT_DIR, ""))
        # self.preview_save_edit.setText(settings.get(KEY_PREVIEW_SAVE_DIR, ""))
        # Trigger button state update after loading
        self._update_create_button_state(self.working_dir_edit.text())
        # Load other settings into their respective widgets
        self.logger.info("Settings loaded into view (excluding license key and crop defaults). Call set_license_status separately.")

    def get_settings(self) -> dict:
        """Retrieves the current values from the UI fields."""
        settings = {
            KEY_WORKING_DIRECTORY: self.working_dir_edit.text().strip(),
            KEY_LICENSE_KEY: self.license_key_edit.text().strip(),
            # Removed crop settings
            # KEY_CROP_INPUT_DIR: self.crop_input_edit.text().strip(),
            # KEY_CROP_OUTPUT_DIR: self.crop_output_edit.text().strip(),
            # KEY_PREVIEW_SAVE_DIR: self.preview_save_edit.text().strip(),
            # Get values from other widgets
        }
        return settings

    @Slot(str, bool)
    def set_license_status(self, status: str, is_valid: bool | None = None):
        """Updates the license status label and its appearance."""
        self.license_status_label.setText(f"状態: {status}") # Keep "状態:" prefix
        if is_valid is True:
            # Green color for valid status - Changed to LimeGreen for visibility
            self.license_status_label.setStyleSheet("font-weight: bold; color: #32CD32;") # LimeGreen
        elif is_valid is False:
            # Red color for invalid status - Changed to Gold for visibility
            self.license_status_label.setStyleSheet("font-weight: bold; color: #FFD700;") # Gold
        else: # Default/unknown/checking status
            # Keep orange for intermediate/unknown states
            self.license_status_label.setStyleSheet("font-weight: bold; color: orange;")

    # Add method similar to old view's set_license_entry_state if needed
    # This controls enabled state and potentially masks the key
    @Slot(bool, str, str)
    def set_license_entry_state(self, is_valid: bool, display_text: str = "", status_text: str = "N/A"):
        """Updates the license key field and status label based on validity."""
        self.license_key_edit.setText(display_text)
        self.license_key_edit.setEnabled(not is_valid)
        self.set_license_status(status_text, is_valid=is_valid) # Pass validity for coloring
        # Enable/disable clear button based on validity
        self.clear_license_button.setEnabled(is_valid)

    @Slot(str, str)
    def show_message(self, title: str, message: str, type: str = "info"):
        """Shows a message box (info, warning, critical)."""
        if type == "info":
            QMessageBox.information(self, title, message)
        elif type == "warning":
            QMessageBox.warning(self, title, message)
        elif type == "critical":
            QMessageBox.critical(self, title, message)
        else:
             QMessageBox.information(self, title, message)

    def set_working_directory(self, path: str):
        """Sets the text of the working directory line edit."""
        self.working_dir_edit.setText(path)

    def get_working_directory(self) -> str:
        """Returns the current text from the working directory line edit."""
        return self.working_dir_edit.text()

    def set_license_key(self, key: str):
        """Sets the text of the license key line edit."""
        self.license_key_edit.setText(key)

    def get_license_key(self) -> str:
        """Returns the current text from the license key line edit."""
        return self.license_key_edit.text()

    def connect_signals(self):
         """Connects view signals to controller slots (called by controller)."""
         if self.controller:
            # Connect browse button
            self.browse_working_dir_button.clicked.connect(self.controller.browse_working_directory)
            # Connect create folders button
            self.create_folders_button.clicked.connect(self.controller.create_workspace_folders)
            # Connect LineEdit editingFinished for saving
            self.working_dir_edit.editingFinished.connect(self.controller.save_working_directory)
            
            # Connect License related signals
            self.license_key_edit.editingFinished.connect(self.controller.save_license_key) # Save on edit finished
            self.check_license_button.clicked.connect(self.check_license_requested.emit) # Emit signal on click
            # Connect the signal to the controller's slot - Use the correct method name
            self.check_license_requested.connect(self.controller.validate_license_key) # CORRECTED: Was check_license_key
            self.clear_license_button.clicked.connect(self.controller.clear_license) # Connect clear button

            # Connect other buttons if they exist
            if hasattr(self, 'reset_button'):
                self.reset_button.clicked.connect(self.controller.reset_settings)
            if hasattr(self, 'save_button'):
                self.save_button.clicked.connect(self.controller.save_settings)

            self.logger.info("Settings view signals connected.")
         else:
            self.logger.warning("Settings Controller not set, cannot connect signals.") 