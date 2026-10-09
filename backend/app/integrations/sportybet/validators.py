import logging
import datetime
from typing import Dict, Any, List, Optional, Tuple
from sqlalchemy.orm import Session
from sqlalchemy import select

from app.db.models import SportyBetEvent, SportyBetMarket, SportyBetOutcome
from .client import SportyBetClient

logger = logging.getLogger("matchiq.integrations.sportybet.validators")

class SportyBetValidator:
    """
    Real-Time Pre-Execution Validation Engine.
    Strictly verifies that:
    1. The event exists and has not kicked off (kickoff > 3 minutes away).
    2. The exact market ID and outcome ID still exist on SportyBet.
    3. The odds drift does not exceed the allowed tolerance (e.g. max 5% drift).
    4. Zero random or fuzzy fallbacks — fails closed with VALIDATION_FAILED.
    """

    def __init__(self, client: Optional[SportyBetClient] = None):
        self.client = client or SportyBetClient()

    async def validate_selection(
        self,
        db: Session,
        sporty_event_id: str,
        sporty_market_id: str,
        sporty_outcome_id: str,
        expected_odds: float,
        specifier: Optional[str] = None,
        max_odds_drift_pct: float = 0.08
    ) -> Tuple[bool, str, Optional[float]]:
        """
        Validates a single selection against local mirror and live SportyBet data.
        Returns: (is_valid, reason, current_odds)
        """
        # 1. Check local mirror
        ev = db.execute(
            select(SportyBetEvent).where(SportyBetEvent.sporty_event_id == sporty_event_id)
        ).scalar_one_or_none()

        if not ev:
            return False, f"Event {sporty_event_id} not found in SportyBet catalogue", None

        # Pre-match cutoff: event must be upcoming in the future
        now_utc = datetime.datetime.now(datetime.timezone.utc)
        if ev.start_time <= (now_utc + datetime.timedelta(minutes=3)):
            return False, f"Event {sporty_event_id} has started or is within 3-minute pre-match cutoff", None

        if ev.status not in ["SCHEDULED", "PREMATCH", "NOT_STARTED"]:
            return False, f"Event status is {ev.status} (must be SCHEDULED)", None

        # 2. Revalidate live against SportyBet API
        details = await self.client.fetch_event_details(sporty_event_id)
        if not details:
            return False, "Failed to reach live SportyBet endpoint for real-time verification", None

        markets = details.get("markets") or details.get("market") or []
        target_m = None
        for m in markets:
            if str(m.get("id")) == str(sporty_market_id):
                if specifier:
                    if str(m.get("specifier") or "") == str(specifier):
                        target_m = m
                        break
                else:
                    target_m = m
                    break

        if not target_m:
            return False, f"Market {sporty_market_id} is no longer offered for event {sporty_event_id}", None

        # 3. Verify outcome & check odds drift
        outcomes = target_m.get("outcomes", [])
        if isinstance(outcomes, dict):
            outcomes = list(outcomes.values())

        target_o = None
        for oc in outcomes:
            if str(oc.get("id") or oc.get("outcome_id")) == str(sporty_outcome_id):
                target_o = oc
                break

        if not target_o:
            return False, f"Outcome {sporty_outcome_id} is no longer available in market {sporty_market_id}", None

        try:
            live_odds = float(target_o.get("odds") or target_o.get("oddsValue") or 0.0)
        except (ValueError, TypeError):
            live_odds = 0.0

        if live_odds < 1.01:
            return False, f"Outcome {sporty_outcome_id} is suspended (odds < 1.01)", None

        if expected_odds > 0:
            drift = abs(live_odds - expected_odds) / expected_odds
            if drift > max_odds_drift_pct:
                return False, f"Odds drifted by {round(drift * 100, 1)}% (expected {expected_odds}, live {live_odds})", live_odds

        return True, "VALIDATED", live_odds

    async def validate_ticket_selections(
        self,
        db: Session,
        selections: List[Dict[str, Any]]
    ) -> Dict[str, Any]:
        """
        Validates all selections for a multi-leg ticket before booking code generation.
        """
        validation_results = []
        all_valid = True

        for leg in selections:
            ev_id = str(leg.get("sporty_event_id") or leg.get("event_id") or "")
            m_id = str(leg.get("sporty_market_id") or leg.get("market_id") or "")
            o_id = str(leg.get("sporty_outcome_id") or leg.get("outcome_id") or "")
            exp_odds = float(leg.get("odds") or 0.0)
            spec = leg.get("specifier")

            is_valid, reason, current_odds = await self.validate_selection(
                db=db,
                sporty_event_id=ev_id,
                sporty_market_id=m_id,
                sporty_outcome_id=o_id,
                expected_odds=exp_odds,
                specifier=spec
            )

            validation_results.append({
                "sporty_event_id": ev_id,
                "sporty_market_id": m_id,
                "sporty_outcome_id": o_id,
                "is_valid": is_valid,
                "reason": reason,
                "live_odds": current_odds
            })

            if not is_valid:
                all_valid = False

        return {
            "all_valid": all_valid,
            "status": "APPROVED" if all_valid else "VALIDATION_FAILED",
            "legs": validation_results
        }
