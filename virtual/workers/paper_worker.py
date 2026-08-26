"""
PaperTradingWorker — Background daemon that drives the live paper trading loop.

Runs two tasks on a schedule:
  1. fire_bets_for_upcoming_events() — every FIRE_INTERVAL seconds
  2. settle_open_bets()             — every SETTLE_INTERVAL seconds

This worker is started once at service startup alongside the ingestion worker.
"""
import time
import threading
import logging
from datetime import datetime, timezone

from virtual.core.db import SessionLocal
from virtual.core.config import virtual_config
from virtual.paper.paper_trader import PaperTrader

logger = logging.getLogger("statiq.virtual.paper_worker")


class PaperTradingWorker:
    """
    Autonomous background worker for paper bet firing and settlement.
    """

    FIRE_INTERVAL: int = 30      # seconds between firing cycles
    SETTLE_INTERVAL: int = 15    # seconds between settlement scans

    _running: bool = False
    _thread: threading.Thread = None
    _last_fire_time: float = 0.0
    _last_settle_time: float = 0.0
    _last_fire_result: dict = {}
    _last_settle_result: dict = {}
    _total_bets_placed: int = 0
    _total_bets_settled: int = 0
    _last_status: str = "OFFLINE"
    _consecutive_errors: int = 0

    @classmethod
    def start(cls):
        if cls._running:
            return
        cls._running = True
        cls._thread = threading.Thread(
            target=cls._run_loop,
            daemon=True,
            name="StatIQ-PaperTradingWorker"
        )
        cls._thread.start()
        cls._last_status = "ONLINE"
        print("[PaperTradingWorker] Paper Trading Worker active.")

    @classmethod
    def stop(cls):
        cls._running = False
        cls._last_status = "STOPPED"

    @classmethod
    def get_status(cls) -> dict:
        return {
            "status": cls._last_status,
            "running": cls._running,
            "total_bets_placed": cls._total_bets_placed,
            "total_bets_settled": cls._total_bets_settled,
            "last_fire_result": cls._last_fire_result,
            "last_settle_result": cls._last_settle_result,
            "last_fire_timestamp": cls._last_fire_time,
            "last_settle_timestamp": cls._last_settle_time,
            "consecutive_errors": cls._consecutive_errors,
        }

    @classmethod
    def _run_loop(cls):
        # Brief startup delay to let ingestion worker seed some data first
        time.sleep(10)
        last_fire = 0.0
        last_settle = 0.0

        while cls._running:
            now = time.time()

            try:
                db = SessionLocal()

                # Settlement runs more frequently than firing
                if now - last_settle >= cls.SETTLE_INTERVAL:
                    result = PaperTrader.settle_open_bets(db)
                    cls._last_settle_result = result
                    cls._last_settle_time = now
                    cls._total_bets_settled += result.get("won", 0) + result.get("lost", 0)
                    last_settle = now

                # Bet firing
                if now - last_fire >= cls.FIRE_INTERVAL:
                    result = PaperTrader.fire_bets_for_upcoming_events(db)
                    cls._last_fire_result = result
                    cls._last_fire_time = now
                    cls._total_bets_placed += result.get("placed", 0)
                    last_fire = now

                db.close()
                cls._consecutive_errors = 0
                cls._last_status = "ONLINE"

            except Exception as e:
                cls._consecutive_errors += 1
                cls._last_status = f"ERROR: {str(e)[:60]}"
                logger.error(f"[PaperTradingWorker] Error: {e}")

            time.sleep(5)
