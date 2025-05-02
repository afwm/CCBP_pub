from PySide6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QGridLayout, QGroupBox,
    QLabel, QLineEdit, QPushButton, QProgressBar, QTextEdit,
    QSizePolicy, QApplication
    )
from PySide6.QtCore import Qt, QSize
from PySide6.QtGui import QPixmap, QImage
import logging

logger = logging.getLogger(__name__)

class CropTabView(QWidget):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.controller = None
        self._setup_ui()

    def set_controller(self, controller):
        self.controller = controller
        if not self.controller:
            logger.warning("Attempted to set an invalid controller for CropTabView")
            return
        # Connect signals from controller to view slots
        self.controller.preview_generated.connect(self.update_preview_image)
        # Connect button signals to controller slots (already done in controller.set_view)
        # self.browse_input_button.clicked.connect(self.controller._browse_input_folder)
        # self.browse_output_button.clicked.connect(self.controller._browse_output_folder)
        # self.preview_gen_button.clicked.connect(self.controller.generate_preview)
        # self.crop_button.clicked.connect(self.controller.run_cropping)
        # self.cancel_button.clicked.connect(self.controller.cancel_processing)
        # Remove connection to non-existent auto_calculate_crop_params
        # if hasattr(self.controller, 'auto_calculate_crop_params'): # Check prevents error if method removed
        #    self.auto_calc_button.clicked.connect(self.controller.auto_calculate_crop_params)
        # else:
        #    logger.warning("controller does not have auto_calculate_crop_params method. Signal not connected.")
            
        # Connect controller's calculated params signal to view slot (Remove this too)
        # self.controller.crop_params_calculated.connect(self.update_crop_parameters)

        logger.info("CropTabView controller set and signals connected.")

    def _setup_ui(self):
        # Main layout for the entire tab (remains QVBoxLayout)
        main_layout = QVBoxLayout(self)

        # --- Top level horizontal layout --- 
        top_layout = QHBoxLayout()

        # --- Left Panel (Paths, Actions, Status) --- 
        left_panel_widget = QWidget() # Container widget for the left panel
        left_panel_layout = QVBoxLayout(left_panel_widget) # Layout for the left panel
        left_panel_layout.setContentsMargins(0,0,0,0) # Remove margins if needed

        # --- Path Settings Grid (goes into left_panel_layout) ---
        path_group = QGroupBox("パス設定")
        path_layout = QGridLayout()
        self.input_folder_label = QLabel("入力フォルダ:")
        self.input_folder_edit = QLineEdit()
        self.browse_input_button = QPushButton("参照...")
        self.output_folder_label = QLabel("出力フォルダ:")
        self.output_folder_edit = QLineEdit()
        self.browse_output_button = QPushButton("参照...")
        path_layout.addWidget(self.input_folder_label, 0, 0)
        path_layout.addWidget(self.input_folder_edit, 0, 1)
        path_layout.addWidget(self.browse_input_button, 0, 2)
        path_layout.addWidget(self.output_folder_label, 1, 0)
        path_layout.addWidget(self.output_folder_edit, 1, 1)
        path_layout.addWidget(self.browse_output_button, 1, 2)
        path_layout.setColumnStretch(1, 1)
        path_group.setLayout(path_layout)
        left_panel_layout.addWidget(path_group) # Add path_group to left panel

        # --- Action Buttons (goes into left_panel_layout) ---        
        action_layout = QHBoxLayout()
        self.crop_button = QPushButton("クロップ処理実行")
        self.cancel_button = QPushButton("中止")
        self.cancel_button.setEnabled(False)
        action_layout.addStretch(1)
        action_layout.addWidget(self.cancel_button)
        action_layout.addWidget(self.crop_button)
        left_panel_layout.addLayout(action_layout) # Add action_layout to left panel

        # --- Progress & Log (goes into left_panel_layout) ---        
        status_group = QGroupBox("進捗・ログ")
        status_layout = QVBoxLayout()
        self.progress_bar = QProgressBar()
        self.status_label = QLabel("待機中")
        self.log_edit = QTextEdit()
        self.log_edit.setReadOnly(True)
        # Remove fixed height to allow expansion
        # self.log_edit.setFixedHeight(100) 
        status_layout.addWidget(self.progress_bar)
        status_layout.addWidget(self.status_label)
        status_layout.addWidget(self.log_edit)
        status_layout.setStretchFactor(self.log_edit, 1) # Make log edit expand within status layout
        status_group.setLayout(status_layout)
        left_panel_layout.addWidget(status_group) # Add status_group to left panel
        left_panel_layout.setStretchFactor(status_group, 1) # Allow status group to expand in left panel

        # --- Preview Area (Right Panel) ---        
        preview_group = QGroupBox("プレビュー")
        preview_layout = QVBoxLayout()
        self.preview_label = QLabel("プレビュー画像を生成してください")
        self.preview_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.preview_label.setMinimumSize(QSize(200, 112)) # Adjust minimum size if needed for 1/4 width
        self.preview_label.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Expanding)
        self.preview_label.setFrameShape(QLabel.Shape.StyledPanel)
        self.preview_label.setStyleSheet("background-color: #404040; border: 1px solid #555555; color: white;")
        self.preview_gen_button = QPushButton("プレビュー生成")
        preview_button_layout = QHBoxLayout()
        preview_button_layout.addStretch(1)
        preview_button_layout.addWidget(self.preview_gen_button)
        preview_button_layout.addStretch(1)
        preview_layout.addWidget(self.preview_label, 1)
        preview_layout.addLayout(preview_button_layout)
        preview_group.setLayout(preview_layout)
        # Make preview group expand vertically if possible
        preview_group.setSizePolicy(QSizePolicy.Policy.Preferred, QSizePolicy.Policy.Expanding)

        # --- Assemble Top Layout --- 
        top_layout.addWidget(left_panel_widget) # Add left panel widget
        top_layout.addWidget(preview_group)   # Add preview group

        # Set stretch factors for horizontal ratio (3:1)
        top_layout.setStretchFactor(left_panel_widget, 3)
        top_layout.setStretchFactor(preview_group, 1)

        # Add the top horizontal layout to the main vertical layout
        main_layout.addLayout(top_layout)
        
        # Set main layout for the tab widget
        self.setLayout(main_layout)

    # --- UI Update Methods (called by Controller) --- 
    def update_status(self, message):
        self.status_label.setText(message)

    def update_progress(self, value):
        self.progress_bar.setValue(value)

    def append_log(self, message):
        self.log_edit.append(message)
        QApplication.processEvents() # Ensure UI updates during logging

    def update_preview_image(self, image: QImage):
        if image and not image.isNull():
            pixmap = QPixmap.fromImage(image)
            scaled_pixmap = pixmap.scaled(self.preview_label.size(), 
                                          Qt.AspectRatioMode.KeepAspectRatio, 
                                          Qt.TransformationMode.SmoothTransformation)
            self.preview_label.setPixmap(scaled_pixmap)
        else:
            self.preview_label.setText("プレビュー生成失敗 or 画像なし")
            self.preview_label.setPixmap(QPixmap()) # Clear existing pixmap

    def set_buttons_enabled(self, preview_gen, crop, cancel):
        self.preview_gen_button.setEnabled(preview_gen)
        self.crop_button.setEnabled(crop)
        self.cancel_button.setEnabled(cancel)

    # --- Method to update path LineEdits (called by Controller) ---
    def update_paths(self, input_dir=None, output_dir=None):
        """Updates the path LineEdit widgets with the provided values."""
        if input_dir is not None:
            self.input_folder_edit.setText(input_dir)
        if output_dir is not None:
            self.output_folder_edit.setText(output_dir)
        # Log that paths were updated (optional)
        # print(f"CropTabView paths updated: input={input_dir}, output={output_dir}") 

    def get_paths(self):
        return {
            "input": self.input_folder_edit.text(),
            "output": self.output_folder_edit.text(),
        }
        
    # --- Removed unused file dialog methods and commented out code --- 
    # def _browse_input_folder(self):
    #    ...
    # def _browse_output_folder(self):
    #    ...
    # --- Removed crop parameter methods --- 
    # def get_crop_parameters(self):
    #    ...
    # @Slot(dict)
    # def _update_crop_params_display(self, params: dict):
    #    ...
    # --- Removed error handling slot --- 
    # @Slot(str)
    # def _handle_controller_error(self, message):
    #    ...
    # --- End removals --- 