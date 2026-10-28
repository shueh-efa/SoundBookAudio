# 此檔案為先前開發之音量調整程式備份
# 原始路徑：main.py (備份時間：2026-10-15)

import sys
import os
import numpy as np
from pydub import AudioSegment
import imageio_ffmpeg

# 設定 pydub 使用 imageio-ffmpeg 內建的 ffmpeg 執行檔
# 這樣打包成 EXE 後，到任何電腦都不需要另外安裝 ffmpeg
AudioSegment.converter = imageio_ffmpeg.get_ffmpeg_exe()

from PyQt6.QtWidgets import (QApplication, QMainWindow, QWidget, QVBoxLayout, 
                             QHBoxLayout, QPushButton, QFileDialog, QScrollArea, 
                             QLabel, QDoubleSpinBox, QProgressBar, QMessageBox)
from PyQt6.QtCore import Qt, QThread, pyqtSignal, QPointF
from PyQt6.QtGui import QPainter, QColor, QPolygonF, QPen, QBrush

class AudioLoaderThread(QThread):
    finished_signal = pyqtSignal(str, float, np.ndarray, np.ndarray, float)
    error_signal = pyqtSignal(str, str)

    def __init__(self, file_path):
        super().__init__()
        self.file_path = file_path

    def run(self):
        try:
            audio = AudioSegment.from_file(self.file_path)
            current_dbfs = audio.dBFS
            max_possible = audio.max_possible_amplitude
            
            mono = audio.set_channels(1)
            samples = np.array(mono.get_array_of_samples())
            
            N = 1000
            if len(samples) < N:
                mins = samples
                maxs = samples
            else:
                chunk_size = len(samples) // N
                truncated_len = chunk_size * N
                samples_trunc = samples[:truncated_len].reshape(N, chunk_size)
                mins = np.min(samples_trunc, axis=1)
                maxs = np.max(samples_trunc, axis=1)
                
            self.finished_signal.emit(self.file_path, current_dbfs, mins, maxs, max_possible)
        except Exception as e:
            self.error_signal.emit(self.file_path, str(e))

class AudioSaverThread(QThread):
    progress_signal = pyqtSignal(int, int)
    finished_signal = pyqtSignal()
    error_signal = pyqtSignal(str, str)

    def __init__(self, files_info, target_dbfs, output_dir):
        super().__init__()
        self.files_info = files_info
        self.target_dbfs = target_dbfs
        self.output_dir = output_dir

    def run(self):
        total = len(self.files_info)
        for i, info in enumerate(self.files_info):
            file_path = info['path']
            current_dbfs = info['dbfs']
            try:
                audio = AudioSegment.from_file(file_path)
                change_in_dbfs = self.target_dbfs - current_dbfs
                
                adjusted_audio = audio.apply_gain(change_in_dbfs)
                
                base_name = os.path.basename(file_path)
                out_path = os.path.join(self.output_dir, base_name)
                
                counter = 1
                name, ext = os.path.splitext(base_name)
                while os.path.exists(out_path):
                    out_path = os.path.join(self.output_dir, f"{name}_{counter}{ext}")
                    counter += 1
                
                export_format = ext.lower().replace('.', '')
                if export_format not in ['mp3', 'wav', 'ogg', 'flv', 'mp4', 'wma', 'aac']:
                    export_format = 'mp3'
                    
                adjusted_audio.export(out_path, format=export_format)
                self.progress_signal.emit(i + 1, total)
                
            except Exception as e:
                self.error_signal.emit(file_path, str(e))
                
        self.finished_signal.emit()

class WaveformWidget(QWidget):
    def __init__(self, mins, maxs, max_possible):
        super().__init__()
        self.mins = mins
        self.maxs = maxs
        self.max_possible = max_possible if max_possible > 0 else 32768
        self.target_scale = 1.0 # 目標音量的縮放比例

        # 我們不寫死最小高度，而是讓它跟隨容器
        self.setSizePolicy(self.sizePolicy().Policy.Expanding, self.sizePolicy().Policy.Expanding)

    def set_target_scale(self, scale):
        self.target_scale = scale
        self.update() # 觸發重繪

    def paintEvent(self, event):
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)
        
        rect = self.rect()
        w = rect.width()
        h = rect.height()
        
        painter.fillRect(rect, QColor(25, 25, 25))
        
        if len(self.mins) == 0:
            return

        # 使用檔案本身的理論最大值作為 Y 軸縮放基準
        # 這樣才能真實反映音量大小，以及是否會破音 (超出視窗)
        amp_ref = self.max_possible
        
        num_points = len(self.mins)
        
        # 建立原始波形
        poly_orig = QPolygonF()
        for i in range(num_points):
            x = (i / num_points) * w
            y = (h / 2) - (self.maxs[i] / amp_ref) * (h / 2)
            poly_orig.append(QPointF(x, y))
        for i in range(num_points - 1, -1, -1):
            x = (i / num_points) * w
            y = (h / 2) - (self.mins[i] / amp_ref) * (h / 2)
            poly_orig.append(QPointF(x, y))
            
        # 建立目標波形 (預覽)
        poly_target = QPolygonF()
        for i in range(num_points):
            x = (i / num_points) * w
            val = self.maxs[i] * self.target_scale
            y = (h / 2) - (val / amp_ref) * (h / 2)
            poly_target.append(QPointF(x, y))
        for i in range(num_points - 1, -1, -1):
            x = (i / num_points) * w
            val = self.mins[i] * self.target_scale
            y = (h / 2) - (val / amp_ref) * (h / 2)
            poly_target.append(QPointF(x, y))

        painter.setPen(Qt.PenStyle.NoPen)

        # 繪製目標預覽波形 (藍色，可能比較大也可能比較小)
        painter.setBrush(QColor(0, 150, 255, 180))
        painter.drawPolygon(poly_target)

        # 繪製原始波形 (半透明白色，疊加在上面作為對比)
        painter.setBrush(QColor(255, 255, 255, 120))
        painter.drawPolygon(poly_orig)

        # 繪製 0dB 中心線
        painter.setPen(QPen(QColor(255, 255, 255, 100), 1))
        painter.drawLine(0, h // 2, w, h // 2)
        
        # 繪製破音警告線 (最頂部與最底部)
        painter.setPen(QPen(QColor(255, 0, 0, 150), 1, Qt.PenStyle.DashLine))
        painter.drawLine(0, 0, w, 0)
        painter.drawLine(0, h, w, h)

class AudioItemWidget(QWidget):
    removed_signal = pyqtSignal(object)

    def __init__(self, file_path, current_dbfs, mins, maxs, max_possible):
        super().__init__()
        self.file_path = file_path
        self.current_dbfs = current_dbfs
        
        layout = QHBoxLayout(self)
        layout.setContentsMargins(5, 5, 5, 5)
        
        info_layout = QVBoxLayout()
        name_label = QLabel(os.path.basename(file_path))
        name_label.setStyleSheet("font-weight: bold; font-size: 14px;")
        
        dbfs_text = f"原始音量: {current_dbfs:.1f} dB\n"
        self.dbfs_label = QLabel(dbfs_text)
        
        info_layout.addWidget(name_label)
        info_layout.addWidget(self.dbfs_label)
        info_layout.addStretch()
        
        info_widget = QWidget()
        info_widget.setLayout(info_layout)
        info_widget.setFixedWidth(200)
        
        self.waveform = WaveformWidget(mins, maxs, max_possible)
        
        remove_btn = QPushButton("X")
        remove_btn.setFixedSize(30, 30)
        remove_btn.setStyleSheet("background-color: #ff4444; color: white; font-weight: bold; border-radius: 5px;")
        remove_btn.clicked.connect(self.on_remove)
        
        layout.addWidget(info_widget)
        layout.addWidget(self.waveform, stretch=1)
        layout.addWidget(remove_btn)
        
        self.setStyleSheet("AudioItemWidget { border: 1px solid #aaa; border-radius: 8px; background-color: #f9f9f9; }")
        
    def update_target_dbfs(self, target_dbfs):
        delta_db = target_dbfs - self.current_dbfs
        # 計算線性的振幅放大/縮小倍率
        scale = 10 ** (delta_db / 20.0)
        self.waveform.set_target_scale(scale)
        
        if delta_db >= 0:
            color = "green"
            sign = "+"
        else:
            color = "red"
            sign = ""
        self.dbfs_label.setText(f"原始音量: {self.current_dbfs:.1f} dB\n調整: <span style='color:{color};'>{sign}{delta_db:.1f} dB</span>")

    def on_remove(self):
        self.removed_signal.emit(self)

class MainWindow(QMainWindow):
    def __init__(self):
        super().__init__()
        self.setWindowTitle("有聲書音量調整程式 (Volume Normalizer)")
        self.resize(900, 700)
        self.setAcceptDrops(True)
        
        self.files_info = []
        self.loading_threads = []
        self.active_loading_count = 0
        
        self.init_ui()
        
    def init_ui(self):
        main_widget = QWidget()
        self.setCentralWidget(main_widget)
        main_layout = QVBoxLayout(main_widget)
        
        top_layout = QHBoxLayout()
        add_file_btn = QPushButton("加入檔案")
        add_file_btn.setMinimumHeight(40)
        add_file_btn.clicked.connect(self.add_files)
        add_folder_btn = QPushButton("加入資料夾")
        add_folder_btn.setMinimumHeight(40)
        add_folder_btn.clicked.connect(self.add_folder)
        
        top_layout.addWidget(add_file_btn)
        top_layout.addWidget(add_folder_btn)
        
        top_layout.addSpacing(20)
        top_layout.addWidget(QLabel("統一目標音量 (dBFS):"))
        self.target_dbfs_spin = QDoubleSpinBox()
        self.target_dbfs_spin.setRange(-50.0, 5.0)
        self.target_dbfs_spin.setValue(-14.0)
        self.target_dbfs_spin.setSingleStep(1.0)
        self.target_dbfs_spin.setMinimumHeight(40)
        self.target_dbfs_spin.setStyleSheet("font-size: 16px; font-weight: bold;")
        self.target_dbfs_spin.valueChanged.connect(self.on_target_dbfs_changed)
        top_layout.addWidget(self.target_dbfs_spin)
        
        top_layout.addStretch()
        
        save_all_btn = QPushButton("全部儲存匯出")
        save_all_btn.setMinimumHeight(40)
        save_all_btn.setStyleSheet("background-color: #4CAF50; color: white; font-weight: bold; font-size: 16px; padding: 5px 20px; border-radius: 5px;")
        save_all_btn.clicked.connect(self.save_all)
        top_layout.addWidget(save_all_btn)
        
        main_layout.addLayout(top_layout)
        
        # 色例說明
        legend_layout = QHBoxLayout()
        legend_layout.addWidget(QLabel("<span style='color: #888;'>■</span> 原始音量"))
        legend_layout.addWidget(QLabel("<span style='color: #0096FF;'>■</span> 調整後音量預覽"))
        legend_layout.addWidget(QLabel("<i>(若藍色波形超出上下紅色虛線，代表匯出後會破音，請調低目標音量)</i>"))
        legend_layout.addStretch()
        main_layout.addLayout(legend_layout)
        
        self.scroll_area = QScrollArea()
        self.scroll_area.setWidgetResizable(True)
        self.scroll_content = QWidget()
        self.list_layout = QVBoxLayout(self.scroll_content)
        self.list_layout.setAlignment(Qt.AlignmentFlag.AlignTop)
        # 加上一點間距
        self.list_layout.setSpacing(10)
        self.scroll_area.setWidget(self.scroll_content)
        main_layout.addWidget(self.scroll_area, stretch=1)
        
        bottom_layout = QHBoxLayout()
        self.status_label = QLabel("請拖曳檔案或資料夾至視窗中...")
        self.progress_bar = QProgressBar()
        self.progress_bar.setVisible(False)
        bottom_layout.addWidget(self.status_label)
        bottom_layout.addWidget(self.progress_bar)
        main_layout.addLayout(bottom_layout)

    def resizeEvent(self, event):
        super().resizeEvent(event)
        self.update_items_height()

    def update_items_height(self):
        # 高度自適應介面的大小，每筆音檔高度為介面的 1/4 高度
        # 扣掉頂端控制列等雜項，我們取 scroll_area 的 1/4 或 window 的 1/4
        target_height = max(100, self.height() // 4)
        for info in self.files_info:
            info['widget'].setFixedHeight(target_height)

    def on_target_dbfs_changed(self, value):
        for info in self.files_info:
            info['widget'].update_target_dbfs(value)

    def dragEnterEvent(self, event):
        if event.mimeData().hasUrls():
            event.acceptProposedAction()
            self.setStyleSheet("QMainWindow { background-color: #e0f7fa; }")

    def dragLeaveEvent(self, event):
        self.setStyleSheet("")

    def dropEvent(self, event):
        self.setStyleSheet("")
        urls = event.mimeData().urls()
        for url in urls:
            path = url.toLocalFile()
            if os.path.isdir(path):
                self.process_folder(path)
            elif path.lower().endswith(('.mp3', '.wav', '.m4a', '.aac', '.ogg')):
                self.load_file(path)

    def add_files(self):
        files, _ = QFileDialog.getOpenFileNames(
            self, "選擇音訊檔案", "", 
            "Audio Files (*.mp3 *.wav *.m4a *.aac *.ogg);;All Files (*)"
        )
        for f in files:
            self.load_file(f)

    def add_folder(self):
        folder = QFileDialog.getExistingDirectory(self, "選擇資料夾")
        if folder:
            self.process_folder(folder)

    def process_folder(self, folder):
        for root, dirs, files in os.walk(folder):
            for file in files:
                if file.lower().endswith(('.mp3', '.wav', '.m4a', '.aac', '.ogg')):
                    self.load_file(os.path.join(root, file))

    def load_file(self, file_path):
        for info in self.files_info:
            if info['path'] == file_path:
                return
                
        self.active_loading_count += 1
        self.update_status(f"載入中... 剩餘 {self.active_loading_count} 個")
        
        thread = AudioLoaderThread(file_path)
        thread.finished_signal.connect(self.on_load_finished)
        thread.error_signal.connect(self.on_load_error)
        self.loading_threads.append(thread)
        thread.start()

    def on_load_finished(self, file_path, current_dbfs, mins, maxs, max_possible):
        self.active_loading_count -= 1
        self.update_status(f"載入中... 剩餘 {self.active_loading_count} 個" if self.active_loading_count > 0 else "就緒")
        
        item = AudioItemWidget(file_path, current_dbfs, mins, maxs, max_possible)
        item.removed_signal.connect(self.remove_item)
        
        # 套用目前設定的目標音量
        item.update_target_dbfs(self.target_dbfs_spin.value())
        
        self.list_layout.addWidget(item)
        self.files_info.append({
            'path': file_path,
            'dbfs': current_dbfs,
            'widget': item
        })
        
        self.update_items_height()

    def on_load_error(self, file_path, error_msg):
        self.active_loading_count -= 1
        self.update_status(f"載入中... 剩餘 {self.active_loading_count} 個" if self.active_loading_count > 0 else "就緒")
        QMessageBox.warning(self, "載入失敗", f"無法載入檔案: {file_path}\n錯誤: {error_msg}")

    def remove_item(self, item_widget):
        self.list_layout.removeWidget(item_widget)
        item_widget.deleteLater()
        self.files_info = [info for info in self.files_info if info['widget'] != item_widget]
        self.update_status(f"已移除，目前共 {len(self.files_info)} 個音檔")

    def update_status(self, text):
        self.status_label.setText(text)

    def save_all(self):
        if not self.files_info:
            QMessageBox.information(self, "提示", "沒有任何音檔可儲存。")
            return
            
        output_dir = QFileDialog.getExistingDirectory(self, "選擇儲存資料夾")
        if not output_dir:
            return
            
        target_dbfs = self.target_dbfs_spin.value()
        
        self.progress_bar.setVisible(True)
        self.progress_bar.setMaximum(len(self.files_info))
        self.progress_bar.setValue(0)
        self.update_status("正在處理並匯出...")
        
        self.setEnabled(False)
        
        self.saver_thread = AudioSaverThread(self.files_info, target_dbfs, output_dir)
        self.saver_thread.progress_signal.connect(self.on_save_progress)
        self.saver_thread.finished_signal.connect(self.on_save_finished)
        self.saver_thread.error_signal.connect(self.on_save_error)
        self.saver_thread.start()

    def on_save_progress(self, current, total):
        self.progress_bar.setValue(current)
        self.update_status(f"匯出中... {current}/{total}")

    def on_save_finished(self):
        self.setEnabled(True)
        self.progress_bar.setVisible(False)
        self.update_status("匯出完成！")
        QMessageBox.information(self, "成功", "所有音檔已成功匯出。")

    def on_save_error(self, file_path, error_msg):
        QMessageBox.warning(self, "匯出失敗", f"處理檔案時發生錯誤: {file_path}\n{error_msg}")

if __name__ == '__main__':
    app = QApplication(sys.argv)
    app.setStyle("Fusion")
    window = MainWindow()
    window.show()
    sys.exit(app.exec())
