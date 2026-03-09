"""
wrapper.py — ARIAKE OCTA
Streamlit のラッパー兼、ゾンビプロセス監視プロセス。
"""
import sys
import os
import time
import threading
import webbrowser
import signal
import subprocess
import multiprocessing
import logging
from pathlib import Path

# ── DYNAMIC PATH ADJUSTMENT ───────────────────────────────────────────
if getattr(sys, "frozen", False):
    MEIPASS = Path(sys._MEIPASS)
    # Resources is parallel to Frameworks/Contents in BUNDLE
    RESOURCES_DIR = MEIPASS.parent / "Resources"
    
    if RESOURCES_DIR.exists():
        BASE_DIR = RESOURCES_DIR
    else:
        BASE_DIR = MEIPASS
else:
    BASE_DIR = Path(__file__).resolve().parent

# IMPORTANT: Ensure the detected BASE_DIR (Resources) is at the very front of sys.path
# This MUST happen before multiprocessing.freeze_support() so child processes can import
if str(BASE_DIR) not in sys.path:
    sys.path.insert(0, str(BASE_DIR))
if str(BASE_DIR / "src") not in sys.path:
    sys.path.insert(0, str(BASE_DIR / "src"))

# macOS needs spawn method for multiprocessing
if sys.platform == "darwin":
    multiprocessing.set_start_method("spawn", force=True)

# ── 環境変数の設定 ────────────────────────────────────────────────────
os.environ.setdefault("ARIAKE_ACCESS_KEY", "ariake2024")
os.environ.setdefault("ARIAKE_LOG_LEVEL", "ERROR")
os.environ.setdefault("ARIAKE_SAVE_STAGES", "false")
os.environ.setdefault("ARIAKE_ENABLE_ROI_REFINEMENT", "false")

TARGET_PORT = "8501"

def open_browser():
    """5秒後にブラウザを起動する"""
    time.sleep(5)
    webbrowser.open(f"http://localhost:{TARGET_PORT}")

def run_streamlit_worker():
    """Streamlitを実行するワーカープロセス。"""
    from streamlit.web import cli as stcli
    
    sys.argv = [
        "streamlit", "run",
        str(BASE_DIR / "mainstreamer.py"),
        "--server.headless", "true",
        "--server.enableCORS", "false",
        "--server.enableXsrfProtection", "false",
        "--logger.level", "error",
        "--server.fileWatcherType", "none",
        "--browser.gatherUsageStats", "false",
        "--browser.serverAddress", "localhost",
        "--server.port", TARGET_PORT,
        "--global.developmentMode", "false",
    ]
    stcli.main()

def main_supervisor():
    """メインアプリ（Supervisor）。ブラウザを開き、終了シグナルを受信したら子プロセスを安全にキルする。"""
    # 子プロセスが使う環境変数にSTREAMLIT_WORKERフラグをセット
    env = os.environ.copy()
    env["ARIAKE_IS_STREAMLIT_WORKER"] = "1"
    
    # 実行コマンドの構築
    cmd = [sys.executable]
    if not getattr(sys, "frozen", False):
        cmd.append(str(Path(__file__).resolve()))

    print(f"[Supervisor] Spawning Streamlit worker on port {TARGET_PORT}...", file=sys.stderr)
    process = subprocess.Popen(cmd, env=env)
    
    # ブラウザを開くスレッドを起動
    threading.Thread(target=open_browser, daemon=True).start()
    
    # 終了シグナルハンドラ（macOSからのSIGTERM / SIGINT をハンドルして子プロセスに伝播させる）
    def terminate_child(signum, frame):
        print(f"\n[Supervisor] Received termination signal {signum}. Terminating Streamlit worker...", file=sys.stderr)
        process.terminate()
        try:
            process.wait(timeout=5)
        except subprocess.TimeoutExpired:
            print("[Supervisor] Worker did not terminate gracefully. Killing it.", file=sys.stderr)
            process.kill()
        sys.exit(0)
        
    signal.signal(signal.SIGINT, terminate_child)
    signal.signal(signal.SIGTERM, terminate_child)
    
    # 子プロセスが終了するまで待機
    try:
        process.wait()
    except KeyboardInterrupt:
        process.terminate()
        process.wait()

if __name__ == "__main__":
    # PyInstaller + Multiprocessing (spawn / forkserver) のフリーズ解除処理。
    # 子プロセス（ワーカー）として呼ばれた場合はここで処理を横取りして終了する。
    multiprocessing.freeze_support()
    
    if os.environ.get("ARIAKE_IS_STREAMLIT_WORKER") == "1":
        # Streamlit実体として起動
        run_streamlit_worker()
    else:
        # Popenで起動する上位のSupervisorとして動作
        main_supervisor()