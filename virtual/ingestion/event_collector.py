import time
import logging
from datetime import datetime, timezone
from typing import List, Dict, Any
from sqlalchemy.orm import Session

from virtual.models.virtual_models import VirtualLeague, VirtualEvent, VirtualOddsSnapshot
from virtual.ingestion.virtual_sportybet_client import VirtualSportyBetClient

logger = logging.getLogger("statiq.virtual.event_collector")

class VirtualEventCollector:
    """
    Normalizes upcoming virtual football events and odds into the Virtual database.
    """

    @classmethod
    def collect_and_sync(cls, db: Session) -> Dict[str, Any]:
        raw_events = VirtualSportyBetClient.fetch_upcoming_virtual_events()
        new_events_count = 0
        updated_events_count = 0
        odds_snapshots_count = 0

        cls._ensure_default_leagues(db)

        for ev in raw_events:
            provider_event_id = str(ev.get("eventId") or ev.get("gameId") or "")
            if not provider_event_id:
                continue

            # vFootball API format:
            #   sport.name = "vFootball"
            #   sport.category.name = "England" (the league country)
            #   sport.category.id = "sv:category:202120001"
            #   sport.category.tournament.name = "Virtual" (generic)
            sport_info = ev.get("sport", {})
            cat_info = sport_info.get("category", {}) if isinstance(sport_info, dict) else {}
            cat_name = cat_info.get("name", "") if isinstance(cat_info, dict) else ""

            # Use category name as the league name (England/Spain/Italy etc.)
            league_name = f"{cat_name} Virtual" if cat_name else "Virtual Football"
            # Use category ID as the unique league code
            league_code = str(cat_info.get("id") or f"v_{cat_name.lower()}" if cat_name else "v_league_default")

            league = db.query(VirtualLeague).filter(VirtualLeague.league_code == league_code).first()
            if not league:
                league = VirtualLeague(
                    league_code=league_code,
                    name=league_name,
                    country=cat_name or "Virtual"
                )
                db.add(league)
                db.flush()

            start_ms = ev.get("estimateStartTime") or ev.get("startTime") or 0
            sched_dt = datetime.fromtimestamp(start_ms / 1000.0, tz=timezone.utc) if start_ms > 0 else datetime.now(timezone.utc)

            home_team = str(ev.get("homeTeamName") or "Home")
            away_team = str(ev.get("awayTeamName") or "Away")
            game_id = str(ev.get("gameId") or "")

            canonical = db.query(VirtualEvent).filter(
                VirtualEvent.provider == "sportybet",
                VirtualEvent.provider_event_id == provider_event_id
            ).first()

            now = datetime.now(timezone.utc)
            if not canonical:
                canonical = VirtualEvent(
                    provider="sportybet",
                    provider_event_id=provider_event_id,
                    provider_game_id=game_id,
                    league_id=league.id,
                    home_team=home_team,
                    away_team=away_team,
                    scheduled_time=sched_dt,
                    status=str(ev.get("status") or "UPCOMING").upper(),
                    source_timestamp=now,
                    last_seen_at=now
                )
                db.add(canonical)
                db.flush()
                new_events_count += 1
            else:
                canonical.last_seen_at = now
                canonical.status = str(ev.get("status") or canonical.status).upper()
                updated_events_count += 1

            markets = ev.get("markets", [])
            odds_added = cls._extract_and_store_odds(db, canonical.id, markets)
            odds_snapshots_count += odds_added

        try:
            db.commit()
        except Exception as e:
            db.rollback()
            logger.error(f"[VirtualEventCollector] Commit error: {e}")
            return {"status": "error", "message": str(e)}

        return {
            "status": "success",
            "events_discovered": len(raw_events),
            "new_events": new_events_count,
            "updated_events": updated_events_count,
            "odds_snapshots_created": odds_snapshots_count
        }

    @classmethod
    def _extract_and_store_odds(cls, db: Session, event_id: int, markets: List[Dict[str, Any]]) -> int:
        snapshots_added = 0
        now = datetime.now(timezone.utc)

        for m in markets:
            desc = str(m.get("desc") or m.get("name") or "").upper()
            outcomes = m.get("outcomes", [])
            
            if "1X2" in desc or "3 WAY" in desc or desc == "1X2":
                odds_1, odds_x, odds_2 = None, None, None
                for oc in outcomes:
                    desc_oc = str(oc.get("desc") or "").upper()
                    val = float(oc.get("odds") or 0.0)
                    if desc_oc in ["1", "HOME", "HOME WIN"]:
                        odds_1 = val
                    elif desc_oc in ["X", "DRAW"]:
                        odds_x = val
                    elif desc_oc in ["2", "AWAY", "AWAY WIN"]:
                        odds_2 = val

                if odds_1 or odds_x or odds_2:
                    snapshot = VirtualOddsSnapshot(
                        event_id=event_id,
                        market_type="1X2",
                        odds_home=odds_1,
                        odds_draw=odds_x,
                        odds_away=odds_2,
                        observed_at=now,
                        raw_payload=m
                    )
                    db.add(snapshot)
                    snapshots_added += 1

            elif "OVER/UNDER" in desc or "O/U" in desc or "GOALS" in desc:
                param = str(m.get("specifier") or m.get("specifiers") or "2.5")
                odds_over, odds_under = None, None
                for oc in outcomes:
                    desc_oc = str(oc.get("desc") or "").upper()
                    val = float(oc.get("odds") or 0.0)
                    if "OVER" in desc_oc:
                        odds_over = val
                    elif "UNDER" in desc_oc:
                        odds_under = val

                if odds_over or odds_under:
                    snapshot = VirtualOddsSnapshot(
                        event_id=event_id,
                        market_type="OVER_UNDER",
                        market_param=param,
                        odds_over=odds_over,
                        odds_under=odds_under,
                        observed_at=now,
                        raw_payload=m
                    )
                    db.add(snapshot)
                    snapshots_added += 1

        return snapshots_added

    @classmethod
    def _ensure_default_leagues(cls, db: Session):
        # League codes match the confirmed vFootball API category IDs
        defaults = [
            ("sv:category:202120001", "England Virtual", "England"),
            ("sv:category:202120002", "Spain Virtual", "Spain"),
            ("sv:category:202120003", "Italy Virtual", "Italy"),
            ("sv:category:202120004", "Germany Virtual", "Germany"),
            ("sv:category:202120005", "France Virtual", "France"),
            ("sv:category:202120006", "Turkey Virtual", "Turkey"),
        ]
        for code, name, country in defaults:
            exists = db.query(VirtualLeague).filter(VirtualLeague.league_code == code).first()
            if not exists:
                db.add(VirtualLeague(league_code=code, name=name, country=country))
        db.flush()
