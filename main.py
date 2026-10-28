# -*- coding: utf-8 -*-
"""
音檔轉 MP3 桌面應用程式 (Audio to MP3 Converter)
支援格式包含：.m4a, .aac, .wav, .flac, .ogg, .wma, .m4b, .opus, .aiff, .ape, .mp3 等。
"""

import sys
import os
import subprocess
from pathlib import Path

# --- 自動切換虛擬環境 (防止使用者直接用系統全局 Python 執行時缺少套件閃退) ---
try:
    import PyQt6
    import imageio_ffmpeg
except ImportError:
    current_dir = os.path.dirname(os.path.abspath(__file__))
    venv_python = os.path.join(current_dir, "venv", "Scripts", "python.exe")
    if os.path.exists(venv_python) and os.path.abspath(sys.executable).lower() != os.path.abspath(venv_python).lower():
        ret = subprocess.call([venv_python] + sys.argv)
        sys.exit(ret)
    else:
        print("【錯誤】未找到虛擬環境或套件未安裝。請使用: .\\venv\\Scripts\\python.exe main.py 執行。")
        input("請按 Enter 鍵結束...")
        sys.exit(1)

import imageio_ffmpeg
FFMPEG_EXE = imageio_ffmpeg.get_ffmpeg_exe()

from PyQt6.QtWidgets import (
    QApplication, QMainWindow, QWidget, QVBoxLayout, QHBoxLayout,
    QPushButton, QFileDialog, QScrollArea, QLabel, QProgressBar,
    QMessageBox, QCheckBox, QFrame
)
from PyQt6.QtCore import Qt, QThread, pyqtSignal
from PyQt6.QtGui import QFont

# 支援的音訊副檔名清單 (皆為小寫)
SUPPORTED_EXTENSIONS = {
    '.m4a', '.aac', '.mp3', '.wav', '.flac', '.ogg',
    '.wma', '.m4b', '.opus', '.aiff', '.ape'
}


def format_file_size(size_in_bytes: int) -> str:
    """將位元組轉換為易讀的檔案大小格式 (KB, MB)"""
    if size_in_bytes < 1024:
        return f"{size_in_bytes} B"
    elif size_in_bytes < 1024 * 1024:
        return f"{size_in_bytes / 1024:.1f} KB"
    else:
        return f"{size_in_bytes / (1024 * 1024):.2f} MB"


class ConvertWorker(QThread):
    """背景轉檔工作執行緒，以原音質模式 (VBR 0 / 最高保真) 進行轉換"""
    item_started = pyqtSignal(int)          # 正在處理第 index 個項目
    item_finished = pyqtSignal(int, str)    # 完成第 index 個項目，傳回輸出路徑
    item_failed = pyqtSignal(int, str)      # 第 index 個項目失敗，傳回錯誤訊息
    progress_updated = pyqtSignal(int, int) # 當前進度 (完成數, 總數)
    all_finished = pyqtSignal()             # 全部處理完畢

    def __init__(self, tasks, auto_rename=True):
        super().__init__()
        self.tasks = tasks                  # list of dict: [{'index': int, 'input_path': str}]
        self.auto_rename = auto_rename      # 若已存在同名檔案是否自動編號
        self._is_cancelled = False

    def cancel(self):
        self._is_cancelled = True

    def run(self):
        total = len(self.tasks)
        completed_count = 0

        for task in self.tasks:
            if self._is_cancelled:
                break

            idx = task['index']
            input_path = task['input_path']
            self.item_started.emit(idx)

            try:
                # 決定輸出路徑：放在原檔案所在資料夾下
                dir_name = os.path.dirname(input_path)
                file_stem = Path(input_path).stem
                out_path = os.path.join(dir_name, f"{file_stem}.mp3")

                # 若原檔案本身就是 .mp3，避免覆蓋自身
                if os.path.abspath(input_path).lower() == os.path.abspath(out_path).lower():
                    out_path = os.path.join(dir_name, f"{file_stem}_converted.mp3")

                # 若同目錄下已有同名檔案，依設定處理
                if os.path.exists(out_path) and self.auto_rename:
                    counter = 1
                    while os.path.exists(out_path):
                        out_path = os.path.join(dir_name, f"{file_stem}_{counter}.mp3")
                        counter += 1

                # 原音質轉檔核心命令：
                # -vn: 忽略視訊軌
                # -c:a libmp3lame: MP3 編碼器
                # -q:a 0: LAME 原生最高品質 VBR (動態最高保真，忠實保留原檔所有音訊細節，不需使用者手動調整)
                # -map_metadata 0: 保留原始標籤 ID3 metadata
                cmd = [
                    FFMPEG_EXE,
                    "-y",
                    "-i", input_path,
                    "-vn",
                    "-c:a", "libmp3lame",
                    "-q:a", "0",
                    "-map_metadata", "0",
                    "-id3v2_version", "3",
                    out_path
                ]

                # 隱藏 Windows 控制台黑視窗
                creationflags = subprocess.CREATE_NO_WINDOW if sys.platform == "win32" else 0

                result = subprocess.run(
                    cmd,
                    stdout=subprocess.PIPE,
                    stderr=subprocess.PIPE,
                    text=True,
                    encoding='utf-8',
                    errors='ignore',
                    creationflags=creationflags
                )

                if result.returncode == 0 and os.path.exists(out_path):
                    self.item_finished.emit(idx, out_path)
                else:
                    err_msg = result.stderr if result.stderr else "轉檔失敗"
                    self.item_failed.emit(idx, err_msg)

            except Exception as e:
                self.item_failed.emit(idx, str(e))

            completed_count += 1
            self.progress_updated.emit(completed_count, total)

        self.all_finished.emit()


class AudioItemCard(QFrame):
    """單一音檔卡片元件，包含檔名、大小、路徑、狀態與個別關閉按鈕"""
    remove_requested = pyqtSignal(object)

    def __init__(self, file_path: str):
        super().__init__()
        self.file_path = file_path
        self.output_path = None
        self.status = "waiting"

        self.init_ui()

    def init_ui(self):
        self.setObjectName("AudioItemCard")
        self.setStyleSheet("""
            #AudioItemCard {
                background-color: #ffffff;
                border: 1px solid #dcdfe6;
                border-radius: 8px;
                padding: 6px;
            }
            #AudioItemCard:hover {
                border: 1px solid #409eff;
            }
        """)

        layout = QHBoxLayout(self)
        layout.setContentsMargins(12, 10, 12, 10)
        layout.setSpacing(12)

        # 格式徽章 (例如 M4A, AAC)
        ext = Path(self.file_path).suffix.upper().replace('.', '')
        self.badge_label = QLabel(ext)
        self.badge_label.setFixedSize(52, 28)
        self.badge_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.badge_label.setStyleSheet("""
            background-color: #ecf5ff;
            color: #409eff;
            font-weight: bold;
            font-size: 13px;
            border-radius: 4px;
            border: 1px solid #d9ecff;
        """)
        layout.addWidget(self.badge_label)

        # 檔案資訊 (檔名與路徑)
        info_layout = QVBoxLayout()
        info_layout.setSpacing(3)

        file_name = os.path.basename(self.file_path)
        self.name_label = QLabel(file_name)
        self.name_label.setStyleSheet("font-size: 14px; font-weight: bold; color: #303133;")
        self.name_label.setToolTip(self.file_path)

        dir_path = os.path.dirname(self.file_path)
        try:
            size_str = format_file_size(os.path.getsize(self.file_path))
        except Exception:
            size_str = "未知大小"

        self.detail_label = QLabel(f"大小: {size_str}  |  目錄: {dir_path}")
        self.detail_label.setStyleSheet("font-size: 12px; color: #909399;")
        self.detail_label.setToolTip(dir_path)

        info_layout.addWidget(self.name_label)
        info_layout.addWidget(self.detail_label)
        layout.addLayout(info_layout, stretch=1)

        # 狀態標籤
        self.status_label = QLabel("待轉換")
        self.status_label.setFixedWidth(85)
        self.status_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.status_label.setStyleSheet("""
            color: #606266;
            background-color: #f4f4f5;
            padding: 4px 8px;
            border-radius: 4px;
            font-size: 12px;
        """)
        layout.addWidget(self.status_label)

        # 開啟資料夾按鈕 (轉檔完成後顯示)
        self.open_dir_btn = QPushButton("開啟資料夾")
        self.open_dir_btn.setFixedHeight(30)
        self.open_dir_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        self.open_dir_btn.setStyleSheet("""
            QPushButton {
                background-color: #f0f9eb;
                color: #67c23a;
                border: 1px solid #c2e7b0;
                border-radius: 4px;
                padding: 0 10px;
                font-size: 12px;
            }
            QPushButton:hover {
                background-color: #67c23a;
                color: #ffffff;
            }
        """)
        self.open_dir_btn.clicked.connect(self.open_in_explorer)
        self.open_dir_btn.setVisible(False)
        layout.addWidget(self.open_dir_btn)

        # 個別關閉/移除按鈕
        self.remove_btn = QPushButton("✕")
        self.remove_btn.setFixedSize(30, 30)
        self.remove_btn.setToolTip("自清單中移除此檔案")
        self.remove_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        self.remove_btn.setStyleSheet("""
            QPushButton {
                background-color: #fee;
                color: #f56c6c;
                border: 1px solid #fde2e2;
                border-radius: 15px;
                font-weight: bold;
                font-size: 14px;
            }
            QPushButton:hover {
                background-color: #f56c6c;
                color: #ffffff;
            }
        """)
        self.remove_btn.clicked.connect(lambda: self.remove_requested.emit(self))
        layout.addWidget(self.remove_btn)

    def set_converting(self):
        self.status = "converting"
        self.remove_btn.setEnabled(False)
        self.status_label.setText("轉檔中...")
        self.status_label.setStyleSheet("""
            color: #e6a23c;
            background-color: #fdf6ec;
            padding: 4px 8px;
            border-radius: 4px;
            font-size: 12px;
            font-weight: bold;
        """)

    def set_done(self, output_path: str):
        self.status = "done"
        self.output_path = output_path
        self.remove_btn.setEnabled(True)
        self.status_label.setText("已完成 ✓")
        self.status_label.setStyleSheet("""
            color: #67c23a;
            background-color: #f0f9eb;
            padding: 4px 8px;
            border-radius: 4px;
            font-size: 12px;
            font-weight: bold;
        """)
        self.open_dir_btn.setVisible(True)

    def set_failed(self, error_msg: str):
        self.status = "error"
        self.remove_btn.setEnabled(True)
        self.status_label.setText("失敗 ✗")
        self.status_label.setToolTip(error_msg)
        self.status_label.setStyleSheet("""
            color: #f56c6c;
            background-color: #fef0f0;
            padding: 4px 8px;
            border-radius: 4px;
            font-size: 12px;
            font-weight: bold;
        """)

    def open_in_explorer(self):
        target = self.output_path if self.output_path and os.path.exists(self.output_path) else self.file_path
        if sys.platform == "win32":
            subprocess.run(f'explorer /select,"{os.path.normpath(target)}"')
        else:
            folder = os.path.dirname(target)
            os.system(f'start "" "{folder}"')


class MainWindow(QMainWindow):
    def __init__(self):
        super().__init__()
        self.setWindowTitle("音檔轉 MP3 轉換工具 (Audio to MP3 Converter)")
        self.resize(920, 680)
        self.setAcceptDrops(True)

        self.cards = []
        self.worker_thread = None

        self.init_ui()

    def init_ui(self):
        main_widget = QWidget()
        self.setCentralWidget(main_widget)
        main_layout = QVBoxLayout(main_widget)
        main_layout.setContentsMargins(18, 18, 18, 18)
        main_layout.setSpacing(14)

        # 頂部控制列
        top_bar = QHBoxLayout()
        top_bar.setSpacing(10)

        self.add_files_btn = QPushButton("📂 加入音訊檔案")
        self.add_files_btn.setFixedHeight(38)
        self.add_files_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        self.add_files_btn.setStyleSheet("""
            QPushButton {
                background-color: #409eff;
                color: white;
                font-size: 14px;
                font-weight: bold;
                border-radius: 5px;
                padding: 0 15px;
            }
            QPushButton:hover {
                background-color: #66b1ff;
            }
        """)
        self.add_files_btn.clicked.connect(self.select_files)
        top_bar.addWidget(self.add_files_btn)

        self.add_folder_btn = QPushButton("📁 加入資料夾")
        self.add_folder_btn.setFixedHeight(38)
        self.add_folder_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        self.add_folder_btn.setStyleSheet("""
            QPushButton {
                background-color: #ecf5ff;
                color: #409eff;
                font-size: 14px;
                font-weight: bold;
                border: 1px solid #b3d8ff;
                border-radius: 5px;
                padding: 0 15px;
            }
            QPushButton:hover {
                background-color: #d9ecff;
            }
        """)
        self.add_folder_btn.clicked.connect(self.select_folder)
        top_bar.addWidget(self.add_folder_btn)

        self.clear_btn = QPushButton("🧹 清空清單")
        self.clear_btn.setFixedHeight(38)
        self.clear_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        self.clear_btn.setStyleSheet("""
            QPushButton {
                background-color: #ffffff;
                color: #606266;
                font-size: 14px;
                border: 1px solid #dcdfe6;
                border-radius: 5px;
                padding: 0 12px;
            }
            QPushButton:hover {
                background-color: #f4f4f5;
                color: #f56c6c;
                border-color: #fbc4c4;
            }
        """)
        self.clear_btn.clicked.connect(self.clear_all)
        top_bar.addWidget(self.clear_btn)

        top_bar.addStretch()

        # 原音質自動轉換說明標籤（免手動設定）
        mode_label = QLabel("✨ 模式：原音質最佳轉換 (自動匹配)")
        mode_label.setStyleSheet("font-size: 13px; color: #409eff; font-weight: bold; background-color: #f0f7ff; padding: 6px 12px; border-radius: 4px;")
        top_bar.addWidget(mode_label)

        # 同名自動更名選項
        self.auto_rename_cb = QCheckBox("同名時自動編號")
        self.auto_rename_cb.setChecked(True)
        self.auto_rename_cb.setToolTip("若原資料夾下已存在同名 .mp3，自動於檔名後方加上 _1, _2 等序號")
        top_bar.addWidget(self.auto_rename_cb)

        main_layout.addLayout(top_bar)

        # 中間滾動清單區域
        self.scroll_area = QScrollArea()
        self.scroll_area.setWidgetResizable(True)
        self.scroll_area.setStyleSheet("""
            QScrollArea {
                border: 2px dashed #c0c4cc;
                border-radius: 8px;
                background-color: #fafafa;
            }
        """)

        self.scroll_content = QWidget()
        self.scroll_content.setStyleSheet("background-color: transparent;")
        self.list_layout = QVBoxLayout(self.scroll_content)
        self.list_layout.setAlignment(Qt.AlignmentFlag.AlignTop)
        self.list_layout.setSpacing(8)
        self.list_layout.setContentsMargins(10, 10, 10, 10)

        # 拖曳提示標籤
        self.empty_hint = QLabel("可拖曳單個/複數音檔或資料夾至此處\n支援格式：M4A, AAC, WAV, FLAC, OGG, WMA, MP3 等\n\n轉換後的 MP3 將以原音質直接儲存在各自的原檔資料夾下")
        self.empty_hint.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.empty_hint.setStyleSheet("font-size: 15px; color: #909399; line-height: 1.8;")
        self.list_layout.addWidget(self.empty_hint)

        self.scroll_area.setWidget(self.scroll_content)
        main_layout.addWidget(self.scroll_area, stretch=1)

        # 底部動作列
        bottom_box = QVBoxLayout()
        bottom_box.setSpacing(8)

        status_bar = QHBoxLayout()
        self.status_label = QLabel("就緒，等待加入檔案...")
        self.status_label.setStyleSheet("font-size: 13px; color: #606266;")
        status_bar.addWidget(self.status_label)

        status_bar.addStretch()

        self.file_count_label = QLabel("清單音檔數：0 個")
        self.file_count_label.setStyleSheet("font-size: 13px; font-weight: bold; color: #409eff;")
        status_bar.addWidget(self.file_count_label)
        bottom_box.addLayout(status_bar)

        self.progress_bar = QProgressBar()
        self.progress_bar.setFixedHeight(12)
        self.progress_bar.setVisible(False)
        self.progress_bar.setTextVisible(False)
        self.progress_bar.setStyleSheet("""
            QProgressBar {
                border: none;
                border-radius: 6px;
                background-color: #ebeef5;
            }
            QProgressBar::chunk {
                border-radius: 6px;
                background-color: #67c23a;
            }
        """)
        bottom_box.addWidget(self.progress_bar)

        self.convert_btn = QPushButton("🚀 開始全部轉換為 MP3 (原音質輸出至原檔資料夾)")
        self.convert_btn.setFixedHeight(46)
        self.convert_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        self.convert_btn.setStyleSheet("""
            QPushButton {
                background-color: #67c23a;
                color: #ffffff;
                font-size: 16px;
                font-weight: bold;
                border-radius: 6px;
            }
            QPushButton:hover {
                background-color: #85ce61;
            }
            QPushButton:disabled {
                background-color: #c0c4cc;
            }
        """)
        self.convert_btn.clicked.connect(self.start_conversion)
        bottom_box.addWidget(self.convert_btn)

        main_layout.addLayout(bottom_box)

    def dragEnterEvent(self, event):
        if event.mimeData().hasUrls():
            event.acceptProposedAction()
            self.scroll_area.setStyleSheet("""
                QScrollArea {
                    border: 2px dashed #409eff;
                    border-radius: 8px;
                    background-color: #ecf5ff;
                }
            """)

    def dragLeaveEvent(self, event):
        self.scroll_area.setStyleSheet("""
            QScrollArea {
                border: 2px dashed #c0c4cc;
                border-radius: 8px;
                background-color: #fafafa;
            }
        """)

    def dropEvent(self, event):
        self.scroll_area.setStyleSheet("""
            QScrollArea {
                border: 2px dashed #c0c4cc;
                border-radius: 8px;
                background-color: #fafafa;
            }
        """)
        urls = event.mimeData().urls()
        raw_paths = [url.toLocalFile() for url in urls if url.isLocalFile()]
        self.import_paths(raw_paths)

    def select_files(self):
        filter_str = "音訊檔案 (*.m4a *.aac *.mp3 *.wav *.flac *.ogg *.wma *.m4b *.opus *.aiff);;所有檔案 (*.*)"
        files, _ = QFileDialog.getOpenFileNames(self, "選擇音訊檔案 (可複選)", "", filter_str)
        if files:
            self.import_paths(files)

    def select_folder(self):
        folder = QFileDialog.getExistingDirectory(self, "選擇包含音訊的資料夾")
        if folder:
            self.import_paths([folder])

    def import_paths(self, paths: list[str]):
        candidate_files = []
        for path in paths:
            if not os.path.exists(path):
                continue
            if os.path.isdir(path):
                for root, _, files in os.walk(path):
                    for file in files:
                        candidate_files.append(os.path.join(root, file))
            elif os.path.isfile(path):
                candidate_files.append(path)

        supported_to_add = []
        unsupported_files = []
        existing_paths = {card.file_path for card in self.cards}

        for file_path in candidate_files:
            ext = Path(file_path).suffix.lower()
            if ext in SUPPORTED_EXTENSIONS:
                if file_path not in existing_paths and file_path not in supported_to_add:
                    supported_to_add.append(file_path)
            else:
                unsupported_files.append(file_path)

        # 不支援格式彈出警告並不匯入
        if unsupported_files:
            file_names = [os.path.basename(f) for f in unsupported_files]
            if len(file_names) > 8:
                preview = "\n".join([f"• {name}" for name in file_names[:8]])
                msg = f"偵測到 {len(file_names)} 個不支援的檔案格式，已略過不匯入：\n\n{preview}\n...以及其餘 {len(file_names) - 8} 個檔案"
            else:
                preview = "\n".join([f"• {name}" for name in file_names])
                msg = f"偵測到以下不支援的檔案格式，已略過不匯入：\n\n{preview}"

            QMessageBox.warning(self, "格式不支援警告", msg)

        for file_path in supported_to_add:
            self.add_audio_card(file_path)

        self.update_ui_state()

    def add_audio_card(self, file_path: str):
        card = AudioItemCard(file_path)
        card.remove_requested.connect(self.remove_audio_card)
        self.cards.append(card)
        self.list_layout.addWidget(card)

    def remove_audio_card(self, card: AudioItemCard):
        if card in self.cards:
            self.cards.remove(card)
            self.list_layout.removeWidget(card)
            card.deleteLater()
            self.update_ui_state()

    def clear_all(self):
        if not self.cards:
            return
        for card in list(self.cards):
            self.list_layout.removeWidget(card)
            card.deleteLater()
        self.cards.clear()
        self.update_ui_state()

    def update_ui_state(self):
        count = len(self.cards)
        self.empty_hint.setVisible(count == 0)
        self.file_count_label.setText(f"清單音檔數：{count} 個")
        self.convert_btn.setEnabled(count > 0)
        if count == 0:
            self.status_label.setText("就緒，等待加入檔案...")

    def start_conversion(self):
        if not self.cards:
            QMessageBox.information(self, "提示", "清單中目前沒有可轉換的音訊檔案。")
            return

        auto_rename = self.auto_rename_cb.isChecked()
        tasks = [{'index': i, 'input_path': card.file_path} for i, card in enumerate(self.cards)]

        self.set_controls_enabled(False)
        self.progress_bar.setVisible(True)
        self.progress_bar.setMaximum(len(tasks))
        self.progress_bar.setValue(0)
        self.status_label.setText("正在轉檔中，請稍候...")

        self.worker_thread = ConvertWorker(tasks, auto_rename=auto_rename)
        self.worker_thread.item_started.connect(self.on_item_started)
        self.worker_thread.item_finished.connect(self.on_item_finished)
        self.worker_thread.item_failed.connect(self.on_item_failed)
        self.worker_thread.progress_updated.connect(self.on_progress_updated)
        self.worker_thread.all_finished.connect(self.on_all_finished)
        self.worker_thread.start()

    def set_controls_enabled(self, enabled: bool):
        self.add_files_btn.setEnabled(enabled)
        self.add_folder_btn.setEnabled(enabled)
        self.clear_btn.setEnabled(enabled)
        self.auto_rename_cb.setEnabled(enabled)
        self.convert_btn.setEnabled(enabled)

    def on_item_started(self, index: int):
        if index < len(self.cards):
            self.cards[index].set_converting()

    def on_item_finished(self, index: int, output_path: str):
        if index < len(self.cards):
            self.cards[index].set_done(output_path)

    def on_item_failed(self, index: int, error_msg: str):
        if index < len(self.cards):
            self.cards[index].set_failed(error_msg)

    def on_progress_updated(self, completed: int, total: int):
        self.progress_bar.setValue(completed)
        self.status_label.setText(f"正在以原音質轉檔中... ({completed}/{total})")

    def on_all_finished(self):
        self.set_controls_enabled(True)
        self.progress_bar.setVisible(False)
        self.status_label.setText("全部轉檔作業已完成！")

        success_count = sum(1 for c in self.cards if c.status == "done")
        total_count = len(self.cards)

        QMessageBox.information(
            self,
            "轉檔完成",
            f"所有音檔已以原音質處理完畢！\n成功：{success_count} 個\n失敗：{total_count - success_count} 個\n\n轉換後的 MP3 檔案均已存放於各原檔案所在的資料夾中。"
        )


if __name__ == '__main__':
    app = QApplication(sys.argv)
    app.setStyle("Fusion")
    font = QFont("Microsoft JhengHei UI", 9)
    app.setFont(font)

    window = MainWindow()
    window.show()
    sys.exit(app.exec())
