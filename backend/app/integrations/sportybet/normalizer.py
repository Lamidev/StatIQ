import logging
import datetime
from typing import Dict, Any, List, Optional, Tuple

logger = logging.getLogger("matchiq.integrations.sportybet.normalizer")

class SportyBetNormalizer:
    """
    Normalizes raw SportyBet JSON payloads into standardized StatIQ domain records.
    Extracts competitions, fixtures, generic markets, and outcome pricing.
    """

    @staticmethod
    def normalize_competition(raw_tour: Dict[str, Any]) -> Dict[str, Any]:
        """
        Normalizes competition/tournament metadata from SportyBet tournament payload.
        """
        t_id = str(raw_tour.get("id") or "").strip()
        t_name = str(raw_tour.get("name") or "Football Tournament").strip()
        c_name = str(raw_tour.get("categoryName") or "").strip()
        c_id = str(raw_tour.get("categoryId") or "").strip()

        return {
            "sporty_competition_id": t_id,
            "name": t_name,
            "country": c_name or None,
            "category": c_name or None,
            "status": "ACTIVE",
            "raw_payload": raw_tour
        }

    @staticmethod
    def normalize_event(raw_event: Dict[str, Any], comp_id: Optional[int] = None) -> Optional[Dict[str, Any]]:
        """
        Normalizes event fixture metadata.
        """
        event_id = str(raw_event.get("eventId") or raw_event.get("id") or "").strip()
        if not event_id:
            return None

        game_id = str(raw_event.get("gameId") or "").strip() or None
        home_team = str(raw_event.get("homeTeamName") or raw_event.get("home_team") or "Home").strip()
        away_team = str(raw_event.get("awayTeamName") or raw_event.get("away_team") or "Away").strip()

        start_ms = raw_event.get("estimateStartTime") or raw_event.get("startTime") or 0
        try:
            start_ms = int(start_ms)
        except (ValueError, TypeError):
            start_ms = 0

        if start_ms > 0:
            start_dt = datetime.datetime.fromtimestamp(start_ms / 1000.0, tz=datetime.timezone.utc)
        else:
            start_dt = datetime.datetime.now(datetime.timezone.utc)

        # Status normalization
        st_val = raw_event.get("status")
        ms_str = str(raw_event.get("matchStatus") or raw_event.get("match_status") or "").strip().upper()

        status = "SCHEDULED"
        event_state = "NOT_STARTED"

        if ms_str in ["LIVE", "STARTED", "1H", "2H", "HT"] or st_val == 1:
            status = "LIVE"
            event_state = "IN_PLAY"
        elif ms_str in ["FINISHED", "ENDED", "FT", "CONCLUDED"] or st_val == 2:
            status = "FINISHED"
            event_state = "ENDED"
        elif ms_str in ["CANCELLED", "POSTPONED", "ABANDONED", "INTERRUPTED", "DELAYED"]:
            status = "CANCELLED"
            event_state = ms_str

        return {
            "sporty_event_id": event_id,
            "sporty_game_id": game_id,
            "competition_id": comp_id,
            "home_team": home_team,
            "away_team": away_team,
            "start_time": start_dt,
            "start_time_ms": start_ms,
            "status": status,
            "event_state": event_state,
            "raw_payload": raw_event
        }

    @staticmethod
    def normalize_market(raw_market: Dict[str, Any], event_db_id: int) -> Tuple[Dict[str, Any], List[Dict[str, Any]]]:
        """
        Normalizes a SportyBet market and all its associated outcomes generically.
        Returns (market_dict, list_of_outcome_dicts).
        """
        m_id = str(raw_market.get("id") or "").strip()
        m_desc = str(raw_market.get("desc") or raw_market.get("name") or f"Market {m_id}").strip()
        specifier = str(raw_market.get("specifier") or "").strip() or None
        
        # Extract line if present (e.g. total=2.5 or hcp=0:1)
        line = None
        if specifier:
            if "total=" in specifier:
                line = specifier.split("total=")[-1].split("&")[0]
            elif "hcp=" in specifier:
                line = specifier.split("hcp=")[-1].split("&")[0]

        market_dict = {
            "sporty_market_id": m_id,
            "event_id": event_db_id,
            "market_type": m_desc.upper(),
            "market_name": m_desc,
            "line": line,
            "specifier": specifier,
            "status": "ACTIVE",
            "raw_payload": raw_market
        }

        outcomes_list = []
        raw_outcomes = raw_market.get("outcomes", [])
        if isinstance(raw_outcomes, dict):
            raw_outcomes = list(raw_outcomes.values())

        for oc in raw_outcomes:
            o_id = str(oc.get("id") or oc.get("outcome_id") or "").strip()
            o_desc = str(oc.get("desc") or oc.get("name") or f"Outcome {o_id}").strip()
            
            try:
                odds_val = float(oc.get("odds") or oc.get("oddsValue") or oc.get("price") or 0.0)
            except (ValueError, TypeError):
                odds_val = 0.0

            prob = oc.get("probability")
            try:
                prob_val = float(prob) if prob else (1.0 / odds_val if odds_val > 0 else None)
            except (ValueError, TypeError):
                prob_val = None

            outcomes_list.append({
                "sporty_outcome_id": o_id,
                "label": o_desc,
                "selection": o_desc,
                "odds": odds_val,
                "probability": prob_val,
                "status": "ACTIVE" if odds_val >= 1.01 else "SUSPENDED",
                "raw_payload": oc
            })

        return market_dict, outcomes_list
