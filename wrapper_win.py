"""
wrapper_win.py — ARIAKE_CVI Windows
Mac版の「Supervisor/Worker」ロジックを継承し、Windowsのプロセス管理とパス解決に最適化。
"""
import sys
import os
import time
import subprocess
import threading
import webbrowser
import signal
import multiprocessing
import logging
from pathlib import Path

# ── パス解決 & 環境設定 ──────────────────────────────────────────
if getattr(sys, "frozen", False):
    BASE_DIR = Path(sys._MEIPASS)
else:
    BASE_DIR = Path(__file__).resolve().parent

# src ディレクトリを検索パスに追加 (mainstreamer.py のインポート用)
SRC_DIR = BASE_DIR / "src"
if str(BASE_DIR) not in sys.path:
    sys.path.insert(0, str(BASE_DIR))
if str(SRC_DIR) not in sys.path:
    sys.path.insert(0, str(SRC_DIR))

# 環境変数のデフォルト設定
os.environ.setdefault("ARIAKE_ACCESS_KEY", "ariake2024")
os.environ.setdefault("ARIAKE_LOG_LEVEL", "ERROR")
os.environ.setdefault("STREAMLIT_GLOBAL_DEVELOPMENT_MODE", "false")
os.environ.setdefault("PYTHONPATH", f"{BASE_DIR};{SRC_DIR};" + os.environ.get("PYTHONPATH", ""))

TARGET_PORT = "8501"

# ── ログ設定 ───────────────────────────────────────────────────
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s [%(levelname)s] %(message)s',
    handlers=[logging.StreamHandler(sys.stdout)]
)
logger = logging.getLogger("ARIAKE_WIN")

def kill_old_streamlit(port):
    """指定ポートを占有している既存のStreamlitプロセスを強制終了する"""
    logger.info(f"Checking for processes on port {port}...")
    try:
        # netstat で PID を特定
        find_cmd = f'netstat -aon | findstr :{port}'
        result = subprocess.check_output(find_cmd, shell=True).decode()
        pids = set()
        for line in result.splitlines():
            parts = line.split()
            if len(parts) > 4 and f":{port}" in parts[1]:
                pids.add(parts[-1])
        
        for pid in pids:
            logger.info(f"Killing old process PID: {pid}")
            subprocess.run(f'taskkill /F /PID {pid}', shell=True, capture_output=True)
    except subprocess.CalledProcessError:
        # ポートが使われていない場合はここに来る
        pass
    except Exception as e:
        logger.error(f"Error while killing old processes: {e}")

def open_browser():
    """サーバー起動を待ってブラウザを開く"""
    time.sleep(5)
    url = f"http://localhost:{TARGET_PORT}"
    logger.info(f"Opening browser: {url}")
    webbrowser.open(url)

def run_streamlit_worker():
    """
    Streamlitを現在のプロセス内で実行するワーカー関数。
    PyInstallerで1つのEXEにまとめるために重要。
    """
    from streamlit.web import cli as stcli
    
    main_script = BASE_DIR / "mainstreamer.py"
    
    sys.argv = [
        "streamlit", "run", str(main_script),
        "--server.headless", "true",
        "--server.port", TARGET_PORT,
        "--server.enableCORS", "false",
        "--server.enableXsrfProtection", "false",
        "--global.developmentMode", "false",
        "--browser.gatherUsageStats", "false",
        "--server.fileWatcherType", "none",
        "--logger.level", "error"
    ]
    stcli.main()

def main_supervisor():
    """メイン監視プロセス"""
    kill_old_streamlit(TARGET_PORT)
    
    # 子プロセス（自分自身を worker モードで起動）の準備
    env = os.environ.copy()
    env["ARIAKE_IS_STREAMLIT_WORKER"] = "1"
    
    cmd = [sys.executable]
    if not getattr(sys, "frozen", False):
        cmd.append(str(Path(__file__).resolve()))
    
    logger.info(f"Starting Streamlit worker on port {TARGET_PORT}...")
    
    # Windowsでは shell=True が安定し、また CREATE_NO_WINDOW を使うことで
    # console=False ビルド時に余計な窓が出るのを防ぐ
    creationflags = 0
    if getattr(sys, "frozen", False):
        import subprocess as sp
        creationflags = 0x08000000 # CREATE_NO_WINDOW
    
    process = subprocess.Popen(cmd, env=env, creationflags=creationflags)
    
    # ブラウザ起動スレッド
    threading.Thread(target=open_browser, daemon=True).start()
    
    try:
        process.wait()
    except KeyboardInterrupt:
        logger.info("Supervisor received KeyboardInterrupt. Terminating worker...")
        process.terminate()
        kill_old_streamlit(TARGET_PORT)
    except Exception as e:
        logger.error(f"Supervisor encountered an error: {e}")
        process.terminate()

if __name__ == "__main__":
    # Windowsバイナリでマルチプロセッシングを正しく動作させるために必須
    multiprocessing.freeze_support()
    
    if os.environ.get("ARIAKE_IS_STREAMLIT_WORKER") == "1":
        run_streamlit_worker()
    else:
        main_supervisor()
