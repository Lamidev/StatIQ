import time
import threading
import logging
from datetime import datetime, timezone

from virtual.core.db import SessionLocal
from virtual.core.config import virtual_config
from virtual.ingestion.event_collector import VirtualEventCollector

logger = logging.getLogger("statiq.virtual.ingestion_worker")

class VirtualIngestionWorker:
    """
    Autonomous Background Worker for Virtual Trader Data Ingestion.
    """
    _running: bool = False
    _thread: threading.Thread = None
    _last_run_time: float = 0.0
    _last_status: str = "OFFLINE"
    _total_runs: int = 0
    _consecutive_errors: int = 0

    @classmethod
    def start(cls):
        if cls._running:
            return
        cls._running = True
        cls._thread = threading.Thread(target=cls._run_loop, daemon=True, name="StatIQ-VirtualIngestionWorker")
        cls._thread.start()
        cls._last_status = "ONLINE"
        print("[VirtualIngestionWorker] Standalone Virtual Ingestion Worker active.")

    @classmethod
    def stop(cls):
        cls._running = False
        cls._last_status = "STOPPED"

    @classmethod
    def get_status(cls):
        return {
            "status": cls._last_status,
            "running": cls._running,
            "total_runs": cls._total_runs,
            "last_run_timestamp": cls._last_run_time,
            "consecutive_errors": cls._consecutive_errors,
            "agent_mode": virtual_config.AGENT_MODE,
            "poll_interval_seconds": virtual_config.POLL_INTERVAL_SECONDS
        }

    @classmethod
    def _run_loop(cls):
        time.sleep(3)
        while cls._running:
            try:
                db = SessionLocal()
                cls._last_run_time = time.time()
                cls._total_runs += 1

                res = VirtualEventCollector.collect_and_sync(db)
                cls._consecutive_errors = 0
                cls._last_status = "ONLINE"

                db.close()
            except Exception as e:
                cls._consecutive_errors += 1
                cls._last_status = f"ERROR: {str(e)[:50]}"
                logger.error(f"[VirtualIngestionWorker] Error in poll loop: {e}")

            time.sleep(virtual_config.POLL_INTERVAL_SECONDS)
