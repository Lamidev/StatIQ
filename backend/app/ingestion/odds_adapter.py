import datetime
from typing import List, Dict, Any, Optional
from sqlalchemy import select, and_
from app.db.models import Fixture, MarketOdds

class OddsProviderAdapter:
    """
    Phase 8.5 Bookmaker Odds Ingestion Adapter.
    Ingests and normalizes decimal market odds from external providers/feeds.
    Strictly decoupled from prediction engine mathematics.
    """
    def __init__(self, session):
        self.session = session

    def ingest_odds_for_fixture(self, fixture: Fixture, odds_dict: Dict[str, Dict[str, float]], bookmaker: str = "Consensus") -> List[MarketOdds]:
        """
        Persists market odds for a given fixture.
        odds_dict format:
        {
            "1X2": {"HOME": 2.10, "DRAW": 3.40, "AWAY": 3.20},
            "OVER_UNDER_2_5": {"OVER": 1.85, "UNDER": 1.95},
            "BTTS": {"YES": 1.75, "NO": 2.05}
        }
        """
        stored_odds = []
        now = datetime.datetime.now(datetime.timezone.utc)

        for mkt, selections in odds_dict.items():
            for sel, price in selections.items():
                if price <= 1.01:
                    continue  # Invalid odds

                m_odds = MarketOdds(
                    fixture_id=fixture.id,
                    bookmaker=bookmaker,
                    market=mkt,
                    selection=sel,
                    odds=price,
                    timestamp=now
                )
                self.session.add(m_odds)
                stored_odds.append(m_odds)

        self.session.commit()
        return stored_odds

    def get_latest_odds_for_fixture(self, fixture_id: int) -> List[MarketOdds]:
        stmt = select(MarketOdds).where(MarketOdds.fixture_id == fixture_id).order_by(MarketOdds.timestamp.desc())
        return list(self.session.execute(stmt).scalars().all())
