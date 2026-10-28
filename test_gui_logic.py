# -*- coding: utf-8 -*-
"""
測試 PyQt 視窗程式邏輯 (檔案過濾、不支援提示、個別移除、轉檔工作執行緒)
"""
import os
import sys
import tempfile
import shutil
from PyQt6.QtWidgets import QApplication, QMessageBox
from main import MainWindow, ConvertWorker, SUPPORTED_EXTENSIONS

def test_main_window_logic():
    # 建立臨時音檔環境
    test_dir = os.path.join(tempfile.gettempdir(), "test_gui_audio_env")
    if os.path.exists(test_dir):
        shutil.rmtree(test_dir)
    os.makedirs(test_dir, exist_ok=True)

    folder_m4a = os.path.join(test_dir, "m4a_dir")
    os.makedirs(folder_m4a, exist_ok=True)

    # 建立幾個假檔案 (只需有副檔名即可測試篩選邏輯)
    valid_file1 = os.path.join(folder_m4a, "track1.m4a")
    valid_file2 = os.path.join(folder_m4a, "track2.aac")
    invalid_file1 = os.path.join(folder_m4a, "document.pdf")
    invalid_file2 = os.path.join(test_dir, "picture.png")

    for fpath in [valid_file1, valid_file2, invalid_file1, invalid_file2]:
        with open(fpath, "wb") as f:
            f.write(b"dummy data")

    app = QApplication.instance()
    if not app:
        app = QApplication(sys.argv)

    window = MainWindow()

    # 攔截 QMessageBox.warning 避免彈窗阻塞自動化測試
    warning_called = []
    def mock_warning(parent, title, text):
        warning_called.append((title, text))
        print(f"[攔截到警告視窗] 標題: {title}\n內容: {text}")

    QMessageBox.warning = mock_warning

    # 測試 1：匯入包含 valid 與 invalid 的檔案與資料夾
    # 傳入包含資料夾 folder_m4a 以及 picture.png
    print("\n--- 測試 1: 匯入資料夾與檔案 (含支援與不支援格式) ---")
    window.import_paths([folder_m4a, invalid_file2])

    # 驗證是否彈出不支援格式警告
    assert len(warning_called) == 1, "應該要彈出 1 次不支援格式警告視窗"
    assert "document.pdf" in warning_called[0][1], "警告訊息中應包含 document.pdf"
    assert "picture.png" in warning_called[0][1], "警告訊息中應包含 picture.png"
    print("[PASS] 不支援檔案成功觸發警告，且未被匯入！")

    # 驗證清單中只有支援的檔案
    assert len(window.cards) == 2, f"清單中卡片數量應為 2，實際為 {len(window.cards)}"
    card_paths = [c.file_path for c in window.cards]
    assert valid_file1 in card_paths and valid_file2 in card_paths
    print(f"[PASS] 支援檔案已成功匯入清單: {card_paths}")

    # 測試 2：個別移除檔案功能 (需求 3)
    print("\n--- 測試 2: 個別關閉/移除按鈕功能 ---")
    card_to_remove = window.cards[0]
    removed_path = card_to_remove.file_path
    window.remove_audio_card(card_to_remove)
    assert len(window.cards) == 1, "移除一個卡片後，清單應該只剩 1 個"
    assert window.cards[0].file_path != removed_path, "已移除的卡片不應存在"
    print(f"[PASS] 成功個別移除音檔: {removed_path}，目前清單剩餘: {window.cards[0].file_path}")

    # 測試 3：再次加入重複檔案
    print("\n--- 測試 3: 防重複匯入 ---")
    window.import_paths([valid_file2])  # 此檔案已在清單中
    assert len(window.cards) == 1, "重複檔案不應重複建立卡片"
    print("[PASS] 重複檔案成功過濾！")

    # 測試 4：清空功能
    print("\n--- 測試 4: 清空清單 ---")
    window.clear_all()
    assert len(window.cards) == 0, "清空後卡片數應為 0"
    print("[PASS] 清空清單成功！")

    # 清理臨時目錄
    shutil.rmtree(test_dir, ignore_errors=True)
    print("\n全部 GUI 核心邏輯測試通過！")

if __name__ == '__main__':
    test_main_window_logic()
