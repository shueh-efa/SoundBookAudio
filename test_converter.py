# -*- coding: utf-8 -*-
"""
測試音檔轉 MP3 核心邏輯與轉檔輸出
"""
import os
import subprocess
import tempfile
import shutil
from pathlib import Path
import imageio_ffmpeg

FFMPEG_EXE = imageio_ffmpeg.get_ffmpeg_exe()

def create_dummy_audio(out_path: str, format_codec: str):
    """使用 ffmpeg 產生 1 秒的正弦波音訊檔案"""
    cmd = [
        FFMPEG_EXE,
        "-y",
        "-f", "lavfi",
        "-i", "sine=frequency=1000:duration=1",
    ]
    if format_codec == "m4a":
        cmd += ["-c:a", "aac", out_path]
    elif format_codec == "aac":
        cmd += ["-c:a", "aac", out_path]
    elif format_codec == "wav":
        cmd += ["-c:a", "pcm_s16le", out_path]
    else:
        cmd += [out_path]

    creationflags = 0
    if os.name == "nt":
        creationflags = subprocess.CREATE_NO_WINDOW

    res = subprocess.run(cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE, creationflags=creationflags)
    assert res.returncode == 0, f"產生測試音檔失敗: {res.stderr.decode('utf-8', errors='ignore')}"

def test_conversion_flow():
    test_dir = os.path.join(tempfile.gettempdir(), "test_audio_mp3_conv")
    if os.path.exists(test_dir):
        shutil.rmtree(test_dir)
    os.makedirs(test_dir, exist_ok=True)

    folder_a = os.path.join(test_dir, "folder_a")
    folder_b = os.path.join(test_dir, "folder_b")
    os.makedirs(folder_a, exist_ok=True)
    os.makedirs(folder_b, exist_ok=True)

    # 建立 m4a 檔案在 folder_a
    m4a_path = os.path.join(folder_a, "sample1.m4a")
    create_dummy_audio(m4a_path, "m4a")
    print(f"[OK] 建立測試 m4a: {m4a_path}")

    # 建立 aac 檔案在 folder_b
    aac_path = os.path.join(folder_b, "sample2.aac")
    create_dummy_audio(aac_path, "aac")
    print(f"[OK] 建立測試 aac: {aac_path}")

    # 建立不支援的檔案 (txt)
    txt_path = os.path.join(folder_a, "readme.txt")
    with open(txt_path, "w", encoding="utf-8") as f:
        f.write("這是文字檔案")
    print(f"[OK] 建立測試 txt (不支援格式): {txt_path}")

    # 測試轉檔功能
    # 1. 轉 sample1.m4a 成 mp3
    dir_name_a = os.path.dirname(m4a_path)
    file_stem_a = Path(m4a_path).stem
    out_a = os.path.join(dir_name_a, f"{file_stem_a}.mp3")

    cmd = [
        FFMPEG_EXE,
        "-y",
        "-i", m4a_path,
        "-vn",
        "-c:a", "libmp3lame",
        "-b:a", "320k",
        out_a
    ]
    res = subprocess.run(cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE)
    assert res.returncode == 0, "m4a 轉 mp3 失敗"
    assert os.path.exists(out_a), f"找不到輸出 mp3: {out_a}"
    assert os.path.getsize(out_a) > 0, "輸出 mp3 檔案為空"
    print(f"[PASS] m4a 成功轉成 MP3 並存放於原資料夾: {out_a} (大小: {os.path.getsize(out_a)} bytes)")

    # 2. 轉 sample2.aac 成 mp3
    dir_name_b = os.path.dirname(aac_path)
    file_stem_b = Path(aac_path).stem
    out_b = os.path.join(dir_name_b, f"{file_stem_b}.mp3")

    cmd = [
        FFMPEG_EXE,
        "-y",
        "-i", aac_path,
        "-vn",
        "-c:a", "libmp3lame",
        "-b:a", "320k",
        out_b
    ]
    res = subprocess.run(cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE)
    assert res.returncode == 0, "aac 轉 mp3 失敗"
    assert os.path.exists(out_b), f"找不到輸出 mp3: {out_b}"
    assert os.path.getsize(out_b) > 0, "輸出 mp3 檔案為空"
    print(f"[PASS] aac 成功轉成 MP3 並存放於原資料夾: {out_b} (大小: {os.path.getsize(out_b)} bytes)")

    print("\n所有轉換測試通過！")

if __name__ == "__main__":
    test_conversion_flow()
