"""
StatIQ SportyBet Feed Ingestion & Mirror Integration Package.
Provides client communication, dynamic discovery, generic market normalization,
tiered polling schedulers, and ticket validation.
"""

from .client import SportyBetClient
from .discovery import SportyBetDiscoveryService
from .events import SportyBetEventSyncService
from .normalizer import SportyBetNormalizer
from .validators import SportyBetValidator
from .scheduler import SportyBetFeedScheduler

__all__ = [
    "SportyBetClient",
    "SportyBetDiscoveryService",
    "SportyBetEventSyncService",
    "SportyBetNormalizer",
    "SportyBetValidator",
    "SportyBetFeedScheduler",
]
