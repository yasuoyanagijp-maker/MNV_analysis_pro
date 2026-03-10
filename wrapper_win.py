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
import socket
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

# ── ログ設定 ───────────────────────────────────────────────────
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s [%(levelname)s] %(message)s',
    handlers=[logging.StreamHandler(sys.stdout)]
)
logger = logging.getLogger("ARIAKE_WIN")

def get_free_port() -> int:
    """
    OSが割り当てる空きポート(エフェメラルポート)を取得する。
    """
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
        s.bind(("127.0.0.1", 0))
        s.listen(1)
        return int(s.getsockname()[1])

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

def open_browser(target_port: int):
    """サーバー起動を待ってブラウザを開く"""
    time.sleep(5)
    url = f"http://localhost:{target_port}"
    logger.info(f"Opening browser: {url}")
    webbrowser.open(url)

def monitor_browser_connection(process: subprocess.Popen, target_port: int):
    """
    ブラウザからの接続状態を監視し、接続が途絶えたらプロセスを終了させる。
    Windows版: netstat -ano | findstr :<port> | findstr ESTABLISHED
    """
    logger.info("Connection monitor started. Waiting for initial browser connection...")
    time.sleep(15)  # アプリ起動・ブラウザ立ち上がりまでの猶予

    no_connection_seconds = 0
    timeout_threshold = 10  # 接続が完全に切れてから終了するまでの猶予(秒)

    while process.poll() is None:  # サブプロセスが生きている間ループ
        try:
            cmd = f'netstat -ano | findstr :{target_port} | findstr ESTABLISHED'
            result = subprocess.check_output(cmd, shell=True, stderr=subprocess.DEVNULL).decode(errors="ignore")
            if result.strip():
                no_connection_seconds = 0
            else:
                no_connection_seconds += 2
        except FileNotFoundError:
            logger.warning("netstat not found; connection monitor disabled.")
            return
        except subprocess.CalledProcessError:
            # findstrが何も見つけられなかった場合(エラーコード1)など
            no_connection_seconds += 2
        except Exception as e:
            # 監視スレッド側で予期せぬ例外が出ても、誤terminateしない
            logger.warning(f"Connection monitor error (ignored): {e}")

        if no_connection_seconds >= timeout_threshold:
            logger.info("Browser tab closed (no active connections). Shutting down...")
            try:
                process.terminate()
                process.wait(timeout=5)
            except Exception:
                try:
                    process.kill()
                except Exception:
                    pass
            kill_old_streamlit(str(target_port))
            break

        time.sleep(2)  # 2秒間隔でチェック

def run_streamlit_worker():
    """
    Streamlitを現在のプロセス内で実行するワーカー関数。
    PyInstallerで1つのEXEにまとめるために重要。
    """
    from streamlit.web import cli as stcli
    
    main_script = BASE_DIR / "mainstreamer.py"
    target_port = int(os.environ.get("ARIAKE_TARGET_PORT") or get_free_port())
    
    sys.argv = [
        "streamlit", "run", str(main_script),
        "--server.headless", "true",
        "--server.port", str(target_port),
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
    target_port = get_free_port()
    
    # 子プロセス（自分自身を worker モードで起動）の準備
    env = os.environ.copy()
    env["ARIAKE_IS_STREAMLIT_WORKER"] = "1"
    env["ARIAKE_TARGET_PORT"] = str(target_port)
    
    cmd = [sys.executable]
    if not getattr(sys, "frozen", False):
        cmd.append(str(Path(__file__).resolve()))
    
    logger.info(f"Starting Streamlit worker on port {target_port}...")
    
    # Windowsでは shell=True が安定し、また CREATE_NO_WINDOW を使うことで
    # console=False ビルド時に余計な窓が出るのを防ぐ
    creationflags = 0
    if getattr(sys, "frozen", False):
        import subprocess as sp
        creationflags = 0x08000000 # CREATE_NO_WINDOW
    
    process = subprocess.Popen(cmd, env=env, creationflags=creationflags)
    
    # ブラウザ起動スレッド
    threading.Thread(target=open_browser, args=(target_port,), daemon=True).start()

    # 接続監視スレッド
    threading.Thread(target=monitor_browser_connection, args=(process, target_port), daemon=True).start()
    
    try:
        process.wait()
    except KeyboardInterrupt:
        logger.info("Supervisor received KeyboardInterrupt. Terminating worker...")
        process.terminate()
        kill_old_streamlit(str(target_port))
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
