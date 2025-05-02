# -*- coding: utf-8 -*-
from PySide6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QGridLayout, QGroupBox, 
    QLabel, QLineEdit, QPushButton, QProgressBar, QTextEdit, 
    QApplication, QFileDialog # SizePolicy removed
)
# Qt removed
# from PySide6.QtCore import Qt

# Assuming KEY constants are defined in config_manager, 
# but the view itself doesn't need direct access to them.
# Keys used here are for the dictionary returned by get_paths()

class BatchTabView(QWidget):
    """View component for the Batch Processing tab."""
    def __init__(self, parent=None):
        super().__init__(parent)
        self.controller = None # Controller will be set later
        self._init_ui()

    # No set_controller needed, main application will link controller and view
    # The controller will connect its slots to the view's widgets/signals

    def _init_ui(self):
        main_layout = QVBoxLayout(self)

        # --- Paths Group --- 
        path_group = QGroupBox("バッチ処理パス設定")
        path_layout = QGridLayout()

        # Widgets for each path (Label, LineEdit, Button)
        self.csv_path_label = QLabel("CSVファイル:")
        self.csv_path_edit = QLineEdit()
        self.browse_csv_button = QPushButton("参照...")

        self.template_project_path_label = QLabel("テンプレートプロジェクト:")
        self.template_project_path_edit = QLineEdit()
        self.browse_template_project_button = QPushButton("参照...")

        self.template_material_base_label = QLabel("テンプレート素材ベース:")
        self.template_material_base_edit = QLineEdit()
        self.browse_template_material_button = QPushButton("参照...")

        self.change_material_base_label = QLabel("差し替え素材ベース (オプション):")
        self.change_material_base_edit = QLineEdit()
        self.browse_change_material_button = QPushButton("参照...")

        self.output_projects_dir_label = QLabel("プロジェクト出力先:")
        self.output_projects_dir_edit = QLineEdit()
        self.browse_output_projects_button = QPushButton("参照...")

        self.output_csv_dir_label = QLabel("レポートCSV出力先:")
        self.output_csv_dir_edit = QLineEdit()
        self.browse_output_csv_button = QPushButton("参照...")

        # Add widgets to grid layout
        row = 0
        path_layout.addWidget(self.csv_path_label, row, 0)
        path_layout.addWidget(self.csv_path_edit, row, 1)
        path_layout.addWidget(self.browse_csv_button, row, 2)
        row += 1
        path_layout.addWidget(self.template_project_path_label, row, 0)
        path_layout.addWidget(self.template_project_path_edit, row, 1)
        path_layout.addWidget(self.browse_template_project_button, row, 2)
        row += 1
        path_layout.addWidget(self.template_material_base_label, row, 0)
        path_layout.addWidget(self.template_material_base_edit, row, 1)
        path_layout.addWidget(self.browse_template_material_button, row, 2)
        row += 1
        path_layout.addWidget(self.change_material_base_label, row, 0)
        path_layout.addWidget(self.change_material_base_edit, row, 1)
        path_layout.addWidget(self.browse_change_material_button, row, 2)
        row += 1
        path_layout.addWidget(self.output_projects_dir_label, row, 0)
        path_layout.addWidget(self.output_projects_dir_edit, row, 1)
        path_layout.addWidget(self.browse_output_projects_button, row, 2)
        row += 1
        path_layout.addWidget(self.output_csv_dir_label, row, 0)
        path_layout.addWidget(self.output_csv_dir_edit, row, 1)
        path_layout.addWidget(self.browse_output_csv_button, row, 2)

        path_layout.setColumnStretch(1, 1) # Make LineEdit column expandable
        path_group.setLayout(path_layout)
        main_layout.addWidget(path_group)

        # --- Action Buttons --- 
        action_layout = QHBoxLayout()
        self.run_batch_button = QPushButton("バッチ処理実行")
        self.cancel_batch_button = QPushButton("中止")
        self.cancel_batch_button.setEnabled(False) # Initially disabled
        action_layout.addStretch(1)
        action_layout.addWidget(self.cancel_batch_button)
        action_layout.addWidget(self.run_batch_button)
        main_layout.addLayout(action_layout)

        # --- Progress & Log --- 
        status_group = QGroupBox("進捗・ログ")
        status_layout = QVBoxLayout()
        self.progress_bar = QProgressBar()
        self.progress_bar.setValue(0)
        self.status_label = QLabel("待機中")
        self.log_edit = QTextEdit()
        self.log_edit.setReadOnly(True)

        status_layout.addWidget(self.progress_bar)
        status_layout.addWidget(self.status_label)
        status_layout.addWidget(self.log_edit)
        status_layout.setStretchFactor(self.log_edit, 1)
        status_group.setLayout(status_layout)
        main_layout.addWidget(status_group)
        main_layout.setStretchFactor(status_group, 1)
        
        self.setLayout(main_layout)

    # --- Methods for Controller Interaction --- 

    def get_paths(self) -> dict:
        """Returns a dictionary containing the paths entered in the UI."""
        return {
            'csv_path': self.csv_path_edit.text().strip(),
            'template_project_path': self.template_project_path_edit.text().strip(),
            'template_material_base': self.template_material_base_edit.text().strip(),
            'change_material_base': self.change_material_base_edit.text().strip(), # Optional
            'output_projects_dir': self.output_projects_dir_edit.text().strip(),
            'output_csv_dir': self.output_csv_dir_edit.text().strip()
        }

    # --- Slots for Controller Updates --- 

    def update_status(self, message: str):
        """Updates the status label text."""
        self.status_label.setText(message)
        # QApplication.processEvents() # Avoid frequent processEvents here

    def update_progress(self, value: int):
        """Updates the progress bar value."""
        self.progress_bar.setValue(value)

    def append_log(self, message: str):
        """Appends a message to the log text edit."""
        self.log_edit.append(message)
        # Ensure the UI updates reasonably often, especially for logs
        QApplication.processEvents() 

    def set_buttons_enabled(self, run_enabled: bool, cancel_enabled: bool):
        """Enables or disables the Run and Cancel buttons."""
        self.run_batch_button.setEnabled(run_enabled)
        self.cancel_batch_button.setEnabled(cancel_enabled)

    # --- Browse Button Slots --- (Implementations using QFileDialog) ---
    def _browse_csv_file(self):
        file_path, _ = QFileDialog.getOpenFileName(self, "CSVファイルを選択", "", "CSV Files (*.csv);;All Files (*)")
        if file_path:
            self.csv_path_edit.setText(file_path)

    def _browse_template_file(self):
        file_path, _ = QFileDialog.getOpenFileName(self, "テンプレートプロジェクトを選択", "", "CapCut Project Files (*.ccp);;All Files (*)")
        if file_path:
            self.template_project_path_edit.setText(file_path)

    def _browse_template_material_folder(self):
        dir_path = QFileDialog.getExistingDirectory(self, "テンプレート素材フォルダを選択")
        if dir_path:
            self.template_material_base_edit.setText(dir_path)
            
    def _browse_replace_material_folder(self):
        dir_path = QFileDialog.getExistingDirectory(self, "差し替え素材フォルダを選択")
        if dir_path:
            self.change_material_base_edit.setText(dir_path)

    def _browse_output_folder(self):
        dir_path = QFileDialog.getExistingDirectory(self, "出力先フォルダを選択")
        if dir_path:
            self.output_projects_dir_edit.setText(dir_path)

    def _browse_output_csv_folder(self):
        dir_path = QFileDialog.getExistingDirectory(self, "レポートCSV出力先を選択")
        if dir_path:
            self.output_csv_dir_edit.setText(dir_path) 