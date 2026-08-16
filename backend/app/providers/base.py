from abc import ABC, abstractmethod
from dataclasses import dataclass
from datetime import datetime
from typing import Optional, List, Dict, Any

@dataclass
class NormalizedFixtureState:
    fixture_id: str                          # Canonical fixture ID (fx_...)
    provider: str                            # API_FOOTBALL, SPORTYBET, etc.
    status: str                              # SCHEDULED, PREMATCH, LIVE, HALFTIME, SECOND_HALF, FINISHED, POSTPONED, CANCELLED
    is_live: bool
    is_finished: bool
    minute: Optional[int] = None
    match_clock: Optional[str] = None        # e.g. "73' H2", "HT", "FT"
    home_score: Optional[int] = None
    away_score: Optional[int] = None
    half_time_home_score: Optional[int] = None
    half_time_away_score: Optional[int] = None
    total_corners: Optional[int] = None
    home_corners: Optional[int] = None
    away_corners: Optional[int] = None
    updated_at: datetime = datetime.utcnow()
    raw_payload: Optional[Dict[str, Any]] = None

class BaseProvider(ABC):
    @abstractmethod
    def get_provider_name(self) -> str:
        pass

    @abstractmethod
    def fetch_fixture_state(self, provider_event_id: Optional[str] = None, provider_game_id: Optional[str] = None) -> Optional[NormalizedFixtureState]:
        """Fetch current normalized state for a single fixture using its provider ID."""
        pass

    @abstractmethod
    def search_fixtures(self, date_str: str, competition: Optional[str] = None) -> List[Dict[str, Any]]:
        """Search available fixtures for mapping."""
        pass
