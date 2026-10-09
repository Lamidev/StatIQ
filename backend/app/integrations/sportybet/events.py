import logging
import datetime
import asyncio
from typing import Dict, Any, List, Optional
from sqlalchemy.orm import Session
from sqlalchemy import select

from app.db.models import SportyBetEvent, SportyBetCompetition
from .client import SportyBetClient
from .normalizer import SportyBetNormalizer
from .markets import SportyBetMarketSyncService

logger = logging.getLogger("matchiq.integrations.sportybet.events")

class SportyBetEventSyncService:
    """
    Service for synchronizing the complete SportyBet football fixture feed.
    Performs exhaustive pagination across all active timelines (Today, Tomorrow, Upcoming).
    """

    def __init__(self, client: Optional[SportyBetClient] = None):
        self.client = client or SportyBetClient()
        self.market_service = SportyBetMarketSyncService(self.client)

    async def sync_all_upcoming_events(
        self,
        db: Session,
        deep_market_sync: bool = True
    ) -> Dict[str, Any]:
        """
        Ingests the entire active SportyBet football feed via exhaustive pagination.
        """
        logger.info("[EventSync] Starting complete SportyBet football feed sync...")
        now = datetime.datetime.now(datetime.timezone.utc)
        
        all_events_raw: List[Dict[str, Any]] = []
        seen_event_ids = set()

        # Phase 1: Exhaustive pagination over timelines (Today, +1d, +2d, +3d)
        timelines_to_crawl = [None, 1, 2, 3]  # None = todayGames
        for timeline in timelines_to_crawl:
            page = 1
            max_pages = 50  # Upper safety guard
            while page <= max_pages:
                data = await self.client.fetch_configurable_events(
                    sport_id="sr:sport:1",
                    page_num=page,
                    page_size=50,
                    today_games=(timeline is None),
                    timeline=timeline
                )
                tournaments = data.get("tournaments", [])
                if not tournaments:
                    break

                events_in_page = 0
                for tour in tournaments:
                    c_name = str(tour.get("categoryName") or "").strip()
                    t_name = str(tour.get("name") or "").strip()
                    c_id = str(tour.get("categoryId") or "").strip()
                    t_id = str(tour.get("id") or "").strip()

                    for ev in tour.get("events", []):
                        ev_id = str(ev.get("eventId") or ev.get("gameId") or "").strip()
                        if ev_id and ev_id not in seen_event_ids:
                            seen_event_ids.add(ev_id)
                            ev["sporty_tournament_id"] = t_id
                            ev["sporty_tournament_name"] = t_name
                            ev["sporty_category_name"] = c_name
                            all_events_raw.append(ev)
                            events_in_page += 1

                if events_in_page == 0:
                    break
                page += 1

        logger.info(f"[EventSync] Ingested {len(all_events_raw)} unique events across all SportyBet pages.")

        # Phase 2: Database Reconciliation & Market Extraction
        inserted_events = 0
        updated_events = 0
        total_markets = 0
        total_snapshots = 0

        # Build competition lookup map
        comp_records = db.execute(select(SportyBetCompetition)).scalars().all()
        comp_map = {c.sporty_competition_id: c.id for c in comp_records}

        for raw_ev in all_events_raw:
            t_id = raw_ev.get("sporty_tournament_id")
            comp_db_id = comp_map.get(t_id)

            norm_ev = SportyBetNormalizer.normalize_event(raw_ev, comp_id=comp_db_id)
            if not norm_ev:
                continue

            ev_id = norm_ev["sporty_event_id"]
            existing_ev = db.execute(
                select(SportyBetEvent).where(SportyBetEvent.sporty_event_id == ev_id)
            ).scalar_one_or_none()

            if existing_ev:
                existing_ev.sporty_game_id = norm_ev["sporty_game_id"]
                existing_ev.competition_id = norm_ev["competition_id"]
                existing_ev.home_team = norm_ev["home_team"]
                existing_ev.away_team = norm_ev["away_team"]
                existing_ev.start_time = norm_ev["start_time"]
                existing_ev.start_time_ms = norm_ev["start_time_ms"]
                existing_ev.status = norm_ev["status"]
                existing_ev.event_state = norm_ev["event_state"]
                existing_ev.raw_payload = norm_ev["raw_payload"]
                existing_ev.last_seen_at = now
                existing_ev.updated_at = now
                event_db_id = existing_ev.id
                updated_events += 1
            else:
                new_ev = SportyBetEvent(
                    sporty_event_id=ev_id,
                    sporty_game_id=norm_ev["sporty_game_id"],
                    competition_id=norm_ev["competition_id"],
                    home_team=norm_ev["home_team"],
                    away_team=norm_ev["away_team"],
                    start_time=norm_ev["start_time"],
                    start_time_ms=norm_ev["start_time_ms"],
                    status=norm_ev["status"],
                    event_state=norm_ev["event_state"],
                    raw_payload=norm_ev["raw_payload"],
                    first_seen_at=now,
                    last_seen_at=now,
                    updated_at=now
                )
                db.add(new_ev)
                db.flush()
                event_db_id = new_ev.id
                inserted_events += 1

            # Sync markets embedded in event payload or deep fetch
            embedded_markets = raw_ev.get("markets", [])
            if embedded_markets:
                m_res = await self.market_service.sync_event_markets(
                    db=db,
                    event_db_id=event_db_id,
                    sporty_event_id=ev_id,
                    raw_markets=embedded_markets
                )
                total_markets += m_res.get("markets_synced", 0)
                total_snapshots += m_res.get("snapshots_created", 0)

        # Automatically mark past events as FINISHED so they are never picked as upcoming
        from sqlalchemy import update
        db.execute(
            update(SportyBetEvent)
            .where(SportyBetEvent.start_time <= now, SportyBetEvent.status == "SCHEDULED")
            .values(status="FINISHED", event_state="ENDED", updated_at=now)
        )

        db.commit()
        logger.info(f"[EventSync] Sync complete: {inserted_events} new events, {updated_events} updated, {total_markets} markets.")

        return {
            "total_events_discovered": len(all_events_raw),
            "inserted_events": inserted_events,
            "updated_events": updated_events,
            "total_markets_synced": total_markets,
            "total_odds_snapshots": total_snapshots,
            "timestamp": now.isoformat()
        }
