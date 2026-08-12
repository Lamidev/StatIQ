from abc import ABC, abstractmethod
from typing import Dict, Any, List, Optional

class SportsbookProvider(ABC):
    """
    Generic Sportsbook Provider Abstract Base Class.
    Decouples StatIQ's quantitative engine from provider-specific APIs (SportyBet, 1xBet, Bet9ja).
    """

    @abstractmethod
    async def get_upcoming_events(self, region: str = "NG", sport_id: str = "sr:sport:1") -> List[Dict[str, Any]]:
        """
        Fetch upcoming fixtures for a specific sport and region.
        """
        pass

    @abstractmethod
    async def get_event_markets(self, event_id: str, region: str = "NG") -> List[Dict[str, Any]]:
        """
        Fetch live markets and outcome odds for a given event ID.
        """
        pass

    @abstractmethod
    async def create_booking(self, selections: List[Dict[str, Any]], region: str = "NG") -> Dict[str, Any]:
        """
        Submit a booking payload to the provider and retrieve a share code.
        """
        pass

    @abstractmethod
    async def get_booking(self, booking_code: str, region: str = "NG") -> Dict[str, Any]:
        """
        Retrieve existing booking details by code for independent reconciliation.
        """
        pass
