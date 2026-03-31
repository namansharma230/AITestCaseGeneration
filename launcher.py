"""
launcher.py
===========
Desktop application entry point for Test Case Automator.

What it does:
  1. Sets the output directory to ~/Documents/TestCaseAutomator/
  2. Starts the Flask server on http://127.0.0.1:5000 in a background thread
  3. Polls /api/status until the server is ready (up to 30 seconds)
  4. Opens http://127.0.0.1:5000 in the user's default browser
  5. Keeps running until the user closes the window / presses Ctrl+C

PyInstaller notes:
  - When frozen (.exe), sys._MEIPASS points to the temp extraction folder
    where templates/ and static/ are unpacked.
  - The Flask app is already configured to read _BASE_DIR from sys._MEIPASS.
  - Excel output always goes to ~/Documents/TestCaseAutomator/
"""

import os
import sys
import time
import threading
import webbrowser
from pathlib import Path


# ── Resolve base directory ────────────────────────────────────────────────────
# In dev:        the folder containing launcher.py
# In .exe:       the temp folder PyInstaller extracts assets to
if getattr(sys, "frozen", False):
    _BASE_DIR = Path(sys._MEIPASS)
    # Also add the .exe's own directory to sys.path so config/scraper etc. load
    _EXE_DIR = Path(sys.executable).parent
    sys.path.insert(0, str(_EXE_DIR))
else:
    _BASE_DIR = Path(__file__).parent

# Ensure our own package is importable
sys.path.insert(0, str(_BASE_DIR))

# ── Set output directory BEFORE importing config ──────────────────────────────
_output_dir = Path.home() / "Documents" / "TestCaseAutomator"
_output_dir.mkdir(parents=True, exist_ok=True)
os.environ.setdefault("TESTCASE_OUTPUT_DIR", str(_output_dir))


# ── Wait for server helper ────────────────────────────────────────────────────
def _wait_for_server(url: str, timeout: int = 30) -> bool:
    """Poll *url* until it responds 200 or *timeout* seconds pass."""
    import urllib.request
    import urllib.error

    deadline = time.time() + timeout
    while time.time() < deadline:
        try:
            with urllib.request.urlopen(url, timeout=2):
                return True
        except Exception:
            time.sleep(0.4)
    return False


# ── Flask thread ──────────────────────────────────────────────────────────────
def _run_flask():
    """Import and start the Flask app (blocking, runs in a daemon thread)."""
    from app import app, _setup_root_logging
    _setup_root_logging()
    app.run(
        host="127.0.0.1",
        port=5000,
        debug=False,
        use_reloader=False,
        threaded=True,
    )


# ── Main ──────────────────────────────────────────────────────────────────────
def main():
    # Start Flask in a background daemon thread
    flask_thread = threading.Thread(target=_run_flask, daemon=True)
    flask_thread.start()

    # Wait until the server is accepting connections
    status_url = "http://127.0.0.1:5000/api/status"
    if _wait_for_server(status_url, timeout=30):
        webbrowser.open("http://127.0.0.1:5000")
    else:
        # Server failed to start — nothing we can do silently in windowed mode
        # Write an error file the user can inspect
        err_file = _output_dir / "startup_error.txt"
        err_file.write_text(
            "Test Case Automator failed to start its internal server.\n"
            "Please check that no other app is using port 5000 and try again.\n"
        )
        return

    # Keep the process alive until Flask thread exits (it won't, it's a daemon)
    # This loop also allows Ctrl+C in console mode to shut things down
    try:
        flask_thread.join()
    except KeyboardInterrupt:
        pass


if __name__ == "__main__":
    main()
