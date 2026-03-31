"""
app.py
Flask web dashboard for the Test Case Automator.
Provides a UI to enter URL + selector and streams live logs via SSE.
"""

import json
import logging
import os
import queue
import sys
import threading
import time
import uuid
from pathlib import Path

from flask import Flask, render_template, request, jsonify, Response, send_file

# ── PyInstaller compatibility ────────────────────────────────────────────────────
# When frozen as an .exe, static assets and templates are extracted to _MEIPASS.
# In development, they live next to this file.
_BASE_DIR = Path(getattr(sys, '_MEIPASS', Path(__file__).parent))

# ── Setup project imports ─────────────────────────────────────────────────────
from config import LOG_DIR, LOG_FILE, EXCEL_FILE_PATH, JIRA_CSS_SELECTOR
from scraper import scrape_section
from confluence_scraper import scrape_confluence_page
from prompt_template import generate_test_cases, generate_confluence_test_cases
from summary_prompt import generate_summary, generate_dependencies
from parser import parse_to_rows
from excel_handler import append_test_cases, append_summary_to_excel

app = Flask(
    __name__,
    template_folder=str(_BASE_DIR / "templates"),
    static_folder=str(_BASE_DIR / "static"),
)

# ── Job Management ────────────────────────────────────────────────────────────
# Each job has: { "id": str, "status": "running"|"success"|"error",
#                 "queue": Queue, "message": str, "test_count": int }
_jobs: dict[str, dict] = {}
_jobs_lock = threading.Lock()


class QueueLogHandler(logging.Handler):
    """Custom log handler that pushes formatted records into a queue."""

    def __init__(self, log_queue: queue.Queue):
        super().__init__()
        self.log_queue = log_queue

    def emit(self, record: logging.LogRecord):
        try:
            msg = self.format(record)
            self.log_queue.put({"type": "log", "data": msg, "level": record.levelname})
        except Exception:
            self.handleError(record)


def _setup_root_logging():
    """Setup base logging (file + console) once at startup."""
    Path(LOG_DIR).mkdir(parents=True, exist_ok=True)
    formatter = logging.Formatter(
        fmt="%(asctime)s [%(levelname)s] %(name)s – %(message)s",
        datefmt="%Y-%m-%d %H:%M:%S",
    )

    root = logging.getLogger()
    root.setLevel(logging.INFO)

    # Avoid duplicate handlers on reload
    if not any(isinstance(h, logging.FileHandler) for h in root.handlers):
        fh = logging.FileHandler(LOG_FILE, encoding="utf-8")
        fh.setLevel(logging.INFO)
        fh.setFormatter(formatter)
        root.addHandler(fh)

    if not any(isinstance(h, logging.StreamHandler) and h.stream == sys.stdout
               for h in root.handlers):
        # Use UTF-8 for console to avoid UnicodeEncodeError on Windows cp1252
        utf8_stdout = open(sys.stdout.fileno(), mode='w', encoding='utf-8',
                           closefd=False, errors='replace')
        ch = logging.StreamHandler(utf8_stdout)
        ch.setLevel(logging.INFO)
        ch.setFormatter(formatter)
        root.addHandler(ch)


logger = logging.getLogger(__name__)


def _run_pipeline(job_id: str, url: str, selector: str):
    """Run the full test-case pipeline in a background thread."""
    job = _jobs[job_id]
    log_queue = job["queue"]

    # Attach a queue handler to root logger for this job
    formatter = logging.Formatter(
        fmt="%(asctime)s [%(levelname)s] %(name)s – %(message)s",
        datefmt="%Y-%m-%d %H:%M:%S",
    )
    handler = QueueLogHandler(log_queue)
    handler.setLevel(logging.INFO)
    handler.setFormatter(formatter)

    root = logging.getLogger()
    root.addHandler(handler)

    try:
        log_queue.put({"type": "log", "data": f"🚀 Starting test case generation for: {url}", "level": "INFO"})
        log_queue.put({"type": "log", "data": f"   Selector: {selector}", "level": "INFO"})
        log_queue.put({"type": "log", "data": "═" * 60, "level": "INFO"})

        # Step 1 — Scrape
        log_queue.put({"type": "step", "data": "Step 1/4 — Scraping requirement text...", "level": "INFO"})
        scraped_text = scrape_section(url, selector, headless=True)

        # Step 2 — Generate via LLM
        log_queue.put({"type": "step", "data": "Step 2/4 — Generating test cases via AI...", "level": "INFO"})
        test_cases = generate_test_cases(scraped_text)

        # Step 3 — Parse to rows
        log_queue.put({"type": "step", "data": "Step 3/4 — Parsing test cases into rows...", "level": "INFO"})
        rows = parse_to_rows(test_cases)
        if not rows:
            raise RuntimeError("No rows produced — AI returned empty results.")

        # Step 4 — Write to Excel
        log_queue.put({"type": "step", "data": "Step 4/4 — Writing to Excel workbook...", "level": "INFO"})
        append_test_cases(rows)

        log_queue.put({"type": "log", "data": "═" * 60, "level": "INFO"})
        log_queue.put({
            "type": "log",
            "data": f"✅ Successfully generated {len(rows)} test case(s)!",
            "level": "INFO",
        })

        with _jobs_lock:
            job["status"] = "success"
            job["test_count"] = len(rows)
            job["message"] = f"Successfully generated {len(rows)} test case(s) and saved to Excel."

    except Exception as exc:
        logger.error("Pipeline failed: %s", exc)
        log_queue.put({
            "type": "log",
            "data": f"❌ Error: {exc}",
            "level": "ERROR",
        })
        with _jobs_lock:
            job["status"] = "error"
            job["message"] = str(exc)

    finally:
        # Signal end-of-stream
        log_queue.put({"type": "done", "data": job["status"], "level": "INFO"})
        root.removeHandler(handler)


def _run_confluence_pipeline(job_id: str, confluence_url: str):
    """Run the Confluence test-case pipeline in a background thread."""
    job = _jobs[job_id]
    log_queue = job["queue"]

    # Attach a queue handler to root logger for this job
    formatter = logging.Formatter(
        fmt="%(asctime)s [%(levelname)s] %(name)s – %(message)s",
        datefmt="%Y-%m-%d %H:%M:%S",
    )
    handler = QueueLogHandler(log_queue)
    handler.setLevel(logging.INFO)
    handler.setFormatter(formatter)

    root = logging.getLogger()
    root.addHandler(handler)

    try:
        log_queue.put({"type": "log", "data": f"📄 Starting Confluence test case generation for: {confluence_url}", "level": "INFO"})
        log_queue.put({"type": "log", "data": "   Source: Confluence Wiki Page", "level": "INFO"})
        log_queue.put({"type": "log", "data": "═" * 60, "level": "INFO"})

        # Step 1 — Scrape Confluence page
        log_queue.put({"type": "step", "data": "Step 1/4 — Scraping Confluence page content...", "level": "INFO"})
        scraped_text = scrape_confluence_page(confluence_url, headless=True)

        # Step 2 — Generate via LLM (Confluence-specific prompt)
        log_queue.put({"type": "step", "data": "Step 2/4 — Generating test cases via AI (Confluence mode)...", "level": "INFO"})
        test_cases = generate_confluence_test_cases(scraped_text)

        # Step 3 — Parse to rows
        log_queue.put({"type": "step", "data": "Step 3/4 — Parsing test cases into rows...", "level": "INFO"})
        rows = parse_to_rows(test_cases)
        if not rows:
            raise RuntimeError("No rows produced — AI returned empty results.")

        # Step 4 — Write to Excel
        log_queue.put({"type": "step", "data": "Step 4/4 — Writing to Excel workbook...", "level": "INFO"})
        append_test_cases(rows)

        log_queue.put({"type": "log", "data": "═" * 60, "level": "INFO"})
        log_queue.put({
            "type": "log",
            "data": f"✅ Successfully generated {len(rows)} test case(s) from Confluence!",
            "level": "INFO",
        })

        with _jobs_lock:
            job["status"] = "success"
            job["test_count"] = len(rows)
            job["message"] = f"Successfully generated {len(rows)} test case(s) from Confluence and saved to Excel."

    except Exception as exc:
        logger.error("Confluence pipeline failed: %s", exc)
        log_queue.put({
            "type": "log",
            "data": f"❌ Error: {exc}",
            "level": "ERROR",
        })
        with _jobs_lock:
            job["status"] = "error"
            job["message"] = str(exc)

    finally:
        # Signal end-of-stream
        log_queue.put({"type": "done", "data": job["status"], "level": "INFO"})
        root.removeHandler(handler)


def _run_summary_pipeline(job_id: str, url: str, selector: str):
    """Run the summary + dependencies pipeline in a background thread."""
    job = _jobs[job_id]
    log_queue = job["queue"]

    formatter = logging.Formatter(
        fmt="%(asctime)s [%(levelname)s] %(name)s – %(message)s",
        datefmt="%Y-%m-%d %H:%M:%S",
    )
    handler = QueueLogHandler(log_queue)
    handler.setLevel(logging.INFO)
    handler.setFormatter(formatter)

    root = logging.getLogger()
    root.addHandler(handler)

    try:
        is_confluence = "/wiki/" in url
        source_type = "Confluence" if is_confluence else "Jira"

        log_queue.put({"type": "log", "data": f"📋 Starting requirement analysis for: {url}", "level": "INFO"})
        log_queue.put({"type": "log", "data": f"   Source type: {source_type}", "level": "INFO"})
        log_queue.put({"type": "log", "data": "═" * 60, "level": "INFO"})

        # Step 1 — Scrape
        log_queue.put({"type": "step", "data": f"Step 1/3 — Scraping {source_type} page content...", "level": "INFO"})
        if is_confluence:
            scraped_text = scrape_confluence_page(url, headless=True)
        else:
            scraped_text = scrape_section(url, selector, headless=True)

        # Step 2 — Generate summary
        log_queue.put({"type": "step", "data": "Step 2/3 — Generating requirement summary via AI...", "level": "INFO"})
        summary_data = generate_summary(scraped_text)

        # Step 3 — Generate dependencies
        log_queue.put({"type": "step", "data": "Step 3/3 — Identifying testing dependencies via AI...", "level": "INFO"})
        deps_data = generate_dependencies(scraped_text)

        # Step 4 — Export to Excel
        log_queue.put({"type": "step", "data": "Step 4/4 — Exporting to Excel workbook...", "level": "INFO"})
        
        # Build base_name from url
        # Keep hyphens so Jira IDs like 'ALTV-113' stay intact
        base_name = url.split('/')[-1]
        base_name = base_name.split('?')[0].strip()
        if not base_name:
            base_name = "Jira Ticket"
            
        append_summary_to_excel(base_name, summary_data, deps_data)
        log_queue.put({"type": "log", "data": "✓ Saved summary data to Excel", "level": "INFO"})

        log_queue.put({"type": "log", "data": "═" * 60, "level": "INFO"})
        log_queue.put({
            "type": "log",
            "data": f"✅ Analysis complete! {len(summary_data.get('key_features', []))} features, {len(deps_data)} dependencies identified.",
            "level": "INFO",
        })

        with _jobs_lock:
            job["status"] = "success"
            job["message"] = f"Analysis complete. {len(deps_data)} dependencies identified."
            job["result"] = {
                "summary": summary_data,
                "dependencies": deps_data,
            }

    except Exception as exc:
        logger.error("Summary pipeline failed: %s", exc)
        log_queue.put({"type": "log", "data": f"❌ Error: {exc}", "level": "ERROR"})
        with _jobs_lock:
            job["status"] = "error"
            job["message"] = str(exc)

    finally:
        log_queue.put({"type": "done", "data": job["status"], "level": "INFO"})
        root.removeHandler(handler)


# ── Routes ────────────────────────────────────────────────────────────────────

@app.route("/api/status")
def api_status():
    """Health check — used by launcher.py to know Flask is ready."""
    return jsonify({"status": "ok", "version": "1.0.0"}), 200

@app.route("/")
def index():
    """Serve the dashboard page."""
    return render_template("index.html")


@app.route("/summary")
def summary_page():
    """Serve the summary & dependencies page."""
    return render_template("summary.html")


@app.route("/api/generate", methods=["POST"])
def api_generate():
    """Start a Jira test-case generation job. Returns a job_id for SSE subscription."""
    data = request.get_json(force=True)
    url = (data.get("url") or "").strip()
    # Use the hardcoded ALTV selector if none is supplied by the client.
    # To change the selector for all pages, update JIRA_CSS_SELECTOR in config.py.
    selector = (data.get("selector") or JIRA_CSS_SELECTOR).strip()

    if not url:
        return jsonify({"error": "URL is required."}), 400
    if not url.startswith(("http://", "https://")):
        return jsonify({"error": "URL must start with http:// or https://"}), 400

    job_id = uuid.uuid4().hex[:12]
    with _jobs_lock:
        _jobs[job_id] = {
            "id": job_id,
            "status": "running",
            "queue": queue.Queue(),
            "message": "",
            "test_count": 0,
        }

    thread = threading.Thread(target=_run_pipeline, args=(job_id, url, selector), daemon=True)
    thread.start()

    return jsonify({"job_id": job_id}), 202


@app.route("/api/generate-confluence", methods=["POST"])
def api_generate_confluence():
    """Start a Confluence test-case generation job. Returns a job_id for SSE subscription."""
    data = request.get_json(force=True)
    confluence_url = (data.get("confluence_url") or "").strip()

    if not confluence_url:
        return jsonify({"error": "Confluence Page URL is required."}), 400
    if not confluence_url.startswith(("http://", "https://")):
        return jsonify({"error": "URL must start with http:// or https://"}), 400

    job_id = uuid.uuid4().hex[:12]
    with _jobs_lock:
        _jobs[job_id] = {
            "id": job_id,
            "status": "running",
            "queue": queue.Queue(),
            "message": "",
            "test_count": 0,
        }

    thread = threading.Thread(target=_run_confluence_pipeline, args=(job_id, confluence_url), daemon=True)
    thread.start()

    return jsonify({"job_id": job_id}), 202


@app.route("/api/summarize", methods=["POST"])
def api_summarize():
    """Start a summary + dependencies job. Returns a job_id for SSE subscription."""
    data = request.get_json(force=True)
    url = (data.get("url") or "").strip()
    # Use the hardcoded ALTV selector if none is supplied by the client.
    # To change the selector for all pages, update JIRA_CSS_SELECTOR in config.py.
    selector = (data.get("selector") or JIRA_CSS_SELECTOR).strip()

    if not url:
        return jsonify({"error": "URL is required."}), 400
    if not url.startswith(("http://", "https://")):
        return jsonify({"error": "URL must start with http:// or https://"}), 400

    # Confluence doesn't need a selector
    is_confluence = "/wiki/" in url

    job_id = uuid.uuid4().hex[:12]
    with _jobs_lock:
        _jobs[job_id] = {
            "id": job_id,
            "status": "running",
            "queue": queue.Queue(),
            "message": "",
            "test_count": 0,
            "result": None,
        }

    thread = threading.Thread(target=_run_summary_pipeline, args=(job_id, url, selector), daemon=True)
    thread.start()

    return jsonify({"job_id": job_id}), 202


@app.route("/api/result/<job_id>")
def api_result(job_id: str):
    """Return the result data for a completed summary job."""
    if job_id not in _jobs:
        return jsonify({"error": "Job not found."}), 404
    job = _jobs[job_id]
    if job["status"] == "running":
        return jsonify({"status": "running"}), 202
    if job["status"] == "error":
        return jsonify({"status": "error", "message": job["message"]}), 200
    return jsonify({
        "status": "success",
        "result": job.get("result"),
    }), 200


@app.route("/api/logs/<job_id>")
def api_logs(job_id: str):
    """SSE endpoint — streams log lines for a given job."""
    if job_id not in _jobs:
        return jsonify({"error": "Job not found."}), 404

    def event_stream():
        job = _jobs[job_id]
        log_queue = job["queue"]

        while True:
            try:
                item = log_queue.get(timeout=120)  # 2-min timeout
            except queue.Empty:
                yield "event: ping\ndata: keep-alive\n\n"
                continue

            payload = json.dumps(item)
            yield f"data: {payload}\n\n"

            if item.get("type") == "done":
                # Send final summary
                summary = json.dumps({
                    "type": "summary",
                    "status": job["status"],
                    "message": job["message"],
                    "test_count": job.get("test_count", 0),
                })
                yield f"data: {summary}\n\n"
                break

    return Response(
        event_stream(),
        mimetype="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "X-Accel-Buffering": "no",
            "Connection": "keep-alive",
        },
    )


@app.route("/api/download")
def api_download():
    """Serve the generated test cases Excel file as a download attachment."""
    path = Path(EXCEL_FILE_PATH)
    if not path.exists():
        return jsonify({
            "error": "No test cases file found. Generate test cases first."
        }), 404
    return send_file(
        str(path.resolve()),
        as_attachment=True,
        download_name="test_cases.xlsx",
        mimetype="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
    )


@app.route("/api/download-summary")
def api_download_summary():
    """Serve the generated summary Excel file as a download attachment."""
    summary_path = Path(EXCEL_FILE_PATH).parent / "summary_requirements.xlsx"
    if not summary_path.exists():
        return jsonify({
            "error": "No summary file found. Generate a summary first."
        }), 404
    return send_file(
        str(summary_path.resolve()),
        as_attachment=True,
        download_name="summary_requirements.xlsx",
        mimetype="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
    )


# ── Main ──────────────────────────────────────────────────────────────────────

if __name__ == "__main__":
    _setup_root_logging()
    logger.info("Dashboard server starting on http://localhost:5000")
    app.run(debug=False, host="0.0.0.0", port=5000, threaded=True)
