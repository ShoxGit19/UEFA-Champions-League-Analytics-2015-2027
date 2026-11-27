"""Resilient Railway worker for scheduled UCL prediction refreshes."""
import json
import logging
import os
import smtplib
import subprocess
import sys
import threading
import time
import urllib.parse
import urllib.request
from email.message import EmailMessage
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

ROOT = Path(__file__).resolve().parent
MIN_INTERVAL_MINUTES = 5
INTERVAL_MINUTES = max(MIN_INTERVAL_MINUTES, int(os.getenv("SYNC_INTERVAL_MINUTES", "5")))
MAX_RETRIES = max(1, int(os.getenv("SYNC_MAX_RETRIES", "3")))
RETRY_BACKOFF_SECONDS = max(5, int(os.getenv("SYNC_RETRY_BACKOFF_SECONDS", "30")))
STATE = {"status": "starting", "last_success_at": None, "last_failure_at": None,
         "last_error": None, "last_duration_seconds": None, "runs": 0}
LOCK = threading.Lock()
logging.basicConfig(level=os.getenv("LOG_LEVEL", "INFO"), format="%(asctime)s %(levelname)s %(message)s")
log = logging.getLogger("ucl-worker")


def set_state(**values):
    with LOCK:
        STATE.update(values)


def notify(message):
    """Optional Telegram and SMTP alerts; alert failures never stop the worker."""
    try:
        token, chat_id = os.getenv("TELEGRAM_BOT_TOKEN"), os.getenv("TELEGRAM_CHAT_ID")
        if token and chat_id:
            data = urllib.parse.urlencode({"chat_id": chat_id, "text": message}).encode()
            urllib.request.urlopen(urllib.request.Request(f"https://api.telegram.org/bot{token}/sendMessage", data=data), timeout=15).read()
        host, user, password, recipient = (os.getenv(k) for k in ("SMTP_HOST", "SMTP_USER", "SMTP_PASSWORD", "ALERT_EMAIL_TO"))
        if host and recipient:
            msg = EmailMessage(); msg["Subject"] = "UCL Railway worker alert"; msg["From"] = user or "ucl-worker"; msg["To"] = recipient; msg.set_content(message)
            with smtplib.SMTP(host, int(os.getenv("SMTP_PORT", "587")), timeout=15) as smtp:
                smtp.starttls()
                if user and password: smtp.login(user, password)
                smtp.send_message(msg)
    except Exception as exc:
        log.warning("notification_failed error=%s", exc)


class HealthHandler(BaseHTTPRequestHandler):
    def do_GET(self):
        if self.path not in ("/", "/health", "/healthz"):
            self.send_response(404); self.end_headers(); return
        with LOCK: payload = dict(STATE)
        payload["interval_minutes"] = INTERVAL_MINUTES
        body = json.dumps(payload).encode()
        self.send_response(200 if payload["status"] in ("healthy", "starting") else 503)
        self.send_header("Content-Type", "application/json"); self.send_header("Content-Length", str(len(body))); self.end_headers(); self.wfile.write(body)

    def log_message(self, *_):
        return


def start_health_server():
    port = int(os.getenv("PORT", "8080"))
    server = ThreadingHTTPServer(("0.0.0.0", port), HealthHandler)
    threading.Thread(target=server.serve_forever, daemon=True).start()
    log.info("health_server_started port=%s", port)


def run_prediction():
    return subprocess.run([sys.executable, "-B", "main.py"], cwd=ROOT / "ucl_prediction_center", check=False).returncode


def run_with_retry():
    started = time.monotonic()
    with LOCK: run_no = STATE["runs"] + 1
    set_state(status="running", runs=run_no)
    for attempt in range(1, MAX_RETRIES + 1):
        try:
            code = run_prediction()
            if code != 0: raise RuntimeError(f"prediction exited with code {code}")
            duration = round(time.monotonic() - started, 2)
            set_state(status="healthy", last_success_at=time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()), last_error=None, last_duration_seconds=duration)
            log.info("prediction_sync_success attempt=%s duration_seconds=%s", attempt, duration)
            return True
        except Exception as exc:
            log.exception("prediction_sync_failed attempt=%s/%s", attempt, MAX_RETRIES)
            if attempt < MAX_RETRIES:
                time.sleep(RETRY_BACKOFF_SECONDS * attempt)
            else:
                set_state(status="failed", last_failure_at=time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()), last_error=str(exc), last_duration_seconds=round(time.monotonic() - started, 2))
                notify(f"UCL sync failed after {MAX_RETRIES} attempts: {exc}")
    return False


def main():
    start_health_server()
    while True:
        run_with_retry()
        time.sleep(INTERVAL_MINUTES * 60)


if __name__ == "__main__":
    main()
