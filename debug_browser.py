import os
import subprocess
import time
import socket
import logging
import sys
from pathlib import Path

# Setup logging
logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")
logger = logging.getLogger("debug_browser")

# Path to Edge
EDGE_PATH = r"C:\Program Files (x86)\Microsoft\Edge\Application\msedge.exe"
USER_DATA_DIR = str(Path.home() / "EdgeDebug")
PORT = 9222

def is_port_in_use(port: int) -> bool:
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
        s.settimeout(1.0)
        return s.connect_ex(('127.0.0.1', port)) == 0

def launch_edge():
    if is_port_in_use(PORT):
        logger.info(f"Port {PORT} is already in use. Assuming Edge is running.")
        return None
    
    logger.info("Launching Edge with remote debugging...")
    cmd = [
        EDGE_PATH,
        f"--remote-debugging-port={PORT}",
        f"--user-data-dir={USER_DATA_DIR}",
        "--no-first-run",
        "--no-default-browser-check"
    ]
    # Launch in background
    process = subprocess.Popen(cmd)
    
    # Wait for port to open
    for _ in range(10):
        if is_port_in_use(PORT):
            logger.info("Edge is now listening on port 9222.")
            return process
        time.sleep(1)
    
    logger.error("Timed out waiting for Edge to start listening.")
    return process

def test_connection():
    logger.info("Testing connection logic from scraper.py...")
    # Add absolute path to the scraper module
    sys.path.append(os.getcwd())
    try:
        from scraper import _build_driver, _safe_close_driver
        
        logger.info("--- ATTEMPT 1 ---")
        driver, is_attached = _build_driver(headless=True)
        logger.info(f"Connected: {is_attached}")
        logger.info(f"Current URL: {driver.current_url}")
        
        # Detach
        _safe_close_driver(driver, is_attached)
        logger.info("Detached successfully.")
        
        time.sleep(2)
        
        logger.info("--- ATTEMPT 2 ---")
        driver2, is_attached2 = _build_driver(headless=True)
        logger.info(f"Connected: {is_attached2}")
        logger.info(f"Current URL: {driver2.current_url}")
        _safe_close_driver(driver2, is_attached2)
        logger.info("Test complete.")
        
    except ImportError as e:
        logger.error(f"Could not import scraper: {e}")
    except Exception as e:
        logger.exception(f"Error during test: {e}")

if __name__ == "__main__":
    edge_proc = launch_edge()
    try:
        test_connection()
    finally:
        # We don't want to kill the browser if we are simulating the user's manual start
        # but for this script we might want to clean up.
        # However, to debug why it CLOSES, we should see if it stays alive.
        logger.info("Script finished. Check if Edge window is still open.")
