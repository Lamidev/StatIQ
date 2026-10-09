import asyncio
import logging
import datetime
from typing import Dict, Any, Optional
from sqlalchemy.orm import Session

from app.db.session import SessionLocal
from .client import SportyBetClient
from .discovery import SportyBetDiscoveryService
from .events import SportyBetEventSyncService

logger = logging.getLogger("matchiq.integrations.sportybet.scheduler")

class SportyBetFeedScheduler:
    """
    Tiered Background Polling Daemon for SportyBet Mirror Synchronization.
    Controls discovery intervals, event polling, and feed health monitoring.
    """

    def __init__(
        self,
        competition_interval_sec: int = 180,  # 3 minutes
        event_interval_sec: int = 45,        # 45 seconds
        client: Optional[SportyBetClient] = None
    ):
        self.competition_interval = competition_interval_sec
        self.event_interval = event_interval_sec
        self.client = client or SportyBetClient()
        self.discovery_service = SportyBetDiscoveryService(self.client)
        self.event_service = SportyBetEventSyncService(self.client)
        self._is_running = False
        self._task: Optional[asyncio.Task] = None

        # Health metrics
        self.last_competition_sync: Optional[datetime.datetime] = None
        self.last_event_sync: Optional[datetime.datetime] = None
        self.last_error: Optional[str] = None
        self.sync_cycle_count = 0
        self.total_errors = 0

    def start(self):
        if not self._is_running:
            self._is_running = True
            self._task = asyncio.create_task(self._run_loop())
            logger.info("[FeedScheduler] SportyBet feed ingestion scheduler started.")

    async def stop(self):
        self._is_running = False
        if self._task and not self._task.done():
            self._task.cancel()
            try:
                await self._task
            except asyncio.CancelledError:
                pass
        await self.client.close()
        logger.info("[FeedScheduler] SportyBet feed ingestion scheduler stopped.")

    async def _run_loop(self):
        last_comp_time = 0.0

        while self._is_running:
            now_ts = asyncio.get_event_loop().time()
            db: Session = SessionLocal()
            try:
                # 1. Discover competitions if interval elapsed
                if (now_ts - last_comp_time) >= self.competition_interval:
                    await self.discovery_service.discover_and_sync_competitions(db)
                    self.last_competition_sync = datetime.datetime.now(datetime.timezone.utc)
                    last_comp_time = now_ts

                # 2. Synchronize all events & markets
                sync_res = await self.event_service.sync_all_upcoming_events(db)
                self.last_event_sync = datetime.datetime.now(datetime.timezone.utc)
                self.sync_cycle_count += 1

            except Exception as e:
                self.total_errors += 1
                self.last_error = str(e)
                logger.error(f"[FeedScheduler] Error in sync loop: {e}")
            finally:
                db.close()

            await asyncio.sleep(self.event_interval)

    def get_health_status(self) -> Dict[str, Any]:
        """
        Returns live feed health telemetry.
        """
        now = datetime.datetime.now(datetime.timezone.utc)
        event_lag_sec = (now - self.last_event_sync).total_seconds() if self.last_event_sync else None

        return {
            "status": "HEALTHY" if self._is_running and (event_lag_sec is not None and event_lag_sec < 180) else "INITIALIZING",
            "is_running": self._is_running,
            "sync_cycles_completed": self.sync_cycle_count,
            "total_errors": self.total_errors,
            "last_competition_sync": self.last_competition_sync.isoformat() if self.last_competition_sync else None,
            "last_event_sync": self.last_event_sync.isoformat() if self.last_event_sync else None,
            "event_lag_seconds": round(event_lag_sec, 1) if event_lag_sec else None,
            "last_error": self.last_error,
            "poller_intervals": {
                "competitions_seconds": self.competition_interval,
                "events_seconds": self.event_interval
            }
        }
