import logging
import datetime
from typing import Dict, Any, List, Optional
from sqlalchemy.orm import Session
from sqlalchemy import select

from app.db.models import SportyBetCompetition
from .client import SportyBetClient
from .normalizer import SportyBetNormalizer

logger = logging.getLogger("matchiq.integrations.sportybet.discovery")

class SportyBetDiscoveryService:
    """
    Service for discovering and synchronizing all SportyBet football competitions & tournaments.
    Eliminates hardcoded league lists by dynamically extracting categories and tournaments from feed events.
    """

    def __init__(self, client: Optional[SportyBetClient] = None):
        self.client = client or SportyBetClient()

    async def discover_and_sync_competitions(self, db: Session) -> Dict[str, Any]:
        """
        Discovers all currently active tournaments across SportyBet and updates sportybet_competitions.
        """
        logger.info("[Discovery] Starting dynamic SportyBet competition discovery...")
        now = datetime.datetime.now(datetime.timezone.utc)

        # 1. Fetch configurable events board for today & upcoming days
        tournaments_discovered: Dict[str, Dict[str, Any]] = {}

        # Scan today and next 3 days
        for timeline_val in [None, 1, 2, 3]:
            page = 1
            while page <= 10:
                data = await self.client.fetch_configurable_events(
                    sport_id="sr:sport:1",
                    page_num=page,
                    page_size=50,
                    today_games=(timeline_val is None),
                    timeline=timeline_val
                )
                t_list = data.get("tournaments", [])
                if not t_list:
                    break

                for t in t_list:
                    t_id = str(t.get("id") or "").strip()
                    if t_id and t_id not in tournaments_discovered:
                        tournaments_discovered[t_id] = t

                page += 1

        logger.info(f"[Discovery] Discovered {len(tournaments_discovered)} unique SportyBet tournaments.")

        # 2. Synchronize into database
        inserted_count = 0
        updated_count = 0

        for t_id, raw_t in tournaments_discovered.items():
            norm = SportyBetNormalizer.normalize_competition(raw_t)
            
            existing = db.execute(
                select(SportyBetCompetition).where(SportyBetCompetition.sporty_competition_id == t_id)
            ).scalar_one_or_none()

            if existing:
                existing.name = norm["name"]
                existing.country = norm["country"]
                existing.category = norm["category"]
                existing.status = "ACTIVE"
                existing.raw_payload = norm["raw_payload"]
                existing.last_seen_at = now
                existing.updated_at = now
                updated_count += 1
            else:
                new_comp = SportyBetCompetition(
                    sporty_competition_id=norm["sporty_competition_id"],
                    name=norm["name"],
                    country=norm["country"],
                    category=norm["category"],
                    status="ACTIVE",
                    raw_payload=norm["raw_payload"],
                    first_seen_at=now,
                    last_seen_at=now,
                    updated_at=now
                )
                db.add(new_comp)
                inserted_count += 1

        db.commit()
        logger.info(f"[Discovery] Synced competitions: {inserted_count} new, {updated_count} updated.")

        return {
            "total_discovered": len(tournaments_discovered),
            "inserted": inserted_count,
            "updated": updated_count,
            "timestamp": now.isoformat()
        }
