from dataclasses import dataclass, field
from typing import List, Dict, Any, Optional

@dataclass
class ExternalSelection:
    external_fixture_id: Optional[str] = None
    external_market_id: Optional[str] = None
    external_market_name: Optional[str] = None
    home_team: Optional[str] = None
    away_team: Optional[str] = None
    kickoff_datetime_str: Optional[str] = None
    market: str = "1X2"
    selection: str = "HOME"
    odds: Optional[float] = None

@dataclass
class ParsedExternalCode:
    provider: str
    raw_code: str
    parse_status: str  # PARSED, PARTIALLY_PARSED, UNSUPPORTED, INVALID
    selections: List[ExternalSelection] = field(default_factory=list)
    message: Optional[str] = None

class ExternalCodeParser:
    """
    Phase 11 External Booking Code Parser.
    Delegates to SportyBetAdapter for SportyBet codes via direct public web API endpoints.
    """
    def parse_external_code(self, code: str, provider: str = "UNKNOWN", session=None) -> ParsedExternalCode:
        code_str = code.strip().upper()
        if not code_str or len(code_str) < 3:
            return ParsedExternalCode(
                provider=provider,
                raw_code=code,
                parse_status="INVALID",
                message="Code string too short or empty"
            )

        # 1. Native MatchIQ structured codes
        if code_str.startswith("MATCHIQ-") or code_str.startswith("SLIP-"):
            return ParsedExternalCode(
                provider="MATCHIQ_NATIVE",
                raw_code=code,
                parse_status="PARSED",
                selections=[]
            )

        # 2. SportyBet Codes
        if provider.upper() == "SPORTYBET" or code_str.startswith("BC") or len(code_str) in [6, 7]:
            from app.adapters.bookmaker_adapter import SportyBetAdapter
            adapter = SportyBetAdapter(session)
            res = adapter.fetch_booking_code_details(code_str)
            
            ext_selections = []
            for item in res.get("selections", []):
                ext_selections.append(ExternalSelection(
                    external_fixture_id=item.get("external_fixture_id"),
                    home_team=item.get("home_team"),
                    away_team=item.get("away_team"),
                    market=item.get("market_name", "1X2"),
                    selection=item.get("selection_name", "HOME"),
                    odds=item.get("odds", 1.0)
                ))

            return ParsedExternalCode(
                provider="SPORTYBET",
                raw_code=code_str,
                parse_status="PARSED",
                selections=ext_selections,
                message=f"Successfully decoded SportyBet booking code {code_str} via direct Web API adapter."
            )

        # 3. Unsupported generic codes
        return ParsedExternalCode(
            provider=provider,
            raw_code=code,
            parse_status="UNSUPPORTED",
            message="No authorized mapping endpoint exists for opaque booking code. MatchIQ canonical fixture/market input required."
        )
