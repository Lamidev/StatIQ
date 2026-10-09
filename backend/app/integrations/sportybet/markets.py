import logging
import datetime
from typing import Dict, Any, List, Optional
from sqlalchemy.orm import Session
from sqlalchemy import select

from app.db.models import SportyBetMarket, SportyBetOutcome, SportyBetOddsSnapshot, SportyBetEvent
from .client import SportyBetClient
from .normalizer import SportyBetNormalizer

logger = logging.getLogger("matchiq.integrations.sportybet.markets")

class SportyBetMarketSyncService:
    """
    Service for synchronizing all SportyBet markets and capturing historical odds snapshots.
    Operates generically: stores every market and outcome returned by SportyBet.
    """

    def __init__(self, client: Optional[SportyBetClient] = None):
        self.client = client or SportyBetClient()

    async def sync_event_markets(
        self,
        db: Session,
        event_db_id: int,
        sporty_event_id: str,
        raw_markets: Optional[List[Dict[str, Any]]] = None
    ) -> Dict[str, Any]:
        """
        Synchronizes all available markets and outcomes for a single SportyBet event.
        If raw_markets is not provided, fetches full details from pcEventDetails.
        """
        now = datetime.datetime.now(datetime.timezone.utc)

        if raw_markets is None:
            details = await self.client.fetch_event_details(sporty_event_id)
            raw_markets = details.get("markets") or details.get("market") or []

        if not raw_markets:
            return {"markets_synced": 0, "outcomes_synced": 0, "snapshots_created": 0}

        markets_count = 0
        outcomes_count = 0
        snapshots_count = 0

        for raw_m in raw_markets:
            norm_m, norm_outcomes = SportyBetNormalizer.normalize_market(raw_m, event_db_id)
            m_id = norm_m["sporty_market_id"]
            spec = norm_m["specifier"]

            # 1. Upsert market record
            query = select(SportyBetMarket).where(
                SportyBetMarket.event_id == event_db_id,
                SportyBetMarket.sporty_market_id == m_id
            )
            if spec:
                query = query.where(SportyBetMarket.specifier == spec)

            existing_m = db.execute(query).scalar_one_or_none()

            if existing_m:
                existing_m.market_name = norm_m["market_name"]
                existing_m.market_type = norm_m["market_type"]
                existing_m.line = norm_m["line"]
                existing_m.status = norm_m["status"]
                existing_m.raw_payload = norm_m["raw_payload"]
                existing_m.last_seen_at = now
                existing_m.updated_at = now
                market_db_id = existing_m.id
            else:
                new_m = SportyBetMarket(
                    sporty_market_id=m_id,
                    event_id=event_db_id,
                    market_type=norm_m["market_type"],
                    market_name=norm_m["market_name"],
                    line=norm_m["line"],
                    specifier=spec,
                    status=norm_m["status"],
                    raw_payload=norm_m["raw_payload"],
                    first_seen_at=now,
                    last_seen_at=now,
                    updated_at=now
                )
                db.add(new_m)
                db.flush()
                market_db_id = new_m.id

            markets_count += 1

            # 2. Upsert outcomes & log odds drift snapshots
            for norm_o in norm_outcomes:
                o_id = norm_o["sporty_outcome_id"]
                existing_o = db.execute(
                    select(SportyBetOutcome).where(
                        SportyBetOutcome.market_id == market_db_id,
                        SportyBetOutcome.sporty_outcome_id == o_id
                    )
                ).scalar_one_or_none()

                new_odds = norm_o["odds"]
                odds_changed = False

                if existing_o:
                    if abs(existing_o.odds - new_odds) > 0.001:
                        odds_changed = True
                    existing_o.label = norm_o["label"]
                    existing_o.selection = norm_o["selection"]
                    existing_o.odds = new_odds
                    existing_o.probability = norm_o["probability"]
                    existing_o.status = norm_o["status"]
                    existing_o.raw_payload = norm_o["raw_payload"]
                    existing_o.last_seen_at = now
                    existing_o.updated_at = now
                    outcome_db_id = existing_o.id
                else:
                    new_o = SportyBetOutcome(
                        market_id=market_db_id,
                        sporty_outcome_id=o_id,
                        label=norm_o["label"],
                        selection=norm_o["selection"],
                        odds=new_odds,
                        probability=norm_o["probability"],
                        status=norm_o["status"],
                        raw_payload=norm_o["raw_payload"],
                        first_seen_at=now,
                        last_seen_at=now,
                        updated_at=now
                    )
                    db.add(new_o)
                    db.flush()
                    outcome_db_id = new_o.id
                    odds_changed = True  # Initial price capture

                outcomes_count += 1

                # 3. Create append-only odds snapshot if price changed or newly discovered
                if odds_changed and new_odds >= 1.01:
                    snapshot = SportyBetOddsSnapshot(
                        event_id=event_db_id,
                        market_id=market_db_id,
                        outcome_id=outcome_db_id,
                        odds=new_odds,
                        captured_at=now
                    )
                    db.add(snapshot)
                    snapshots_count += 1

        db.commit()
        return {
            "markets_synced": markets_count,
            "outcomes_synced": outcomes_count,
            "snapshots_created": snapshots_count
        }
