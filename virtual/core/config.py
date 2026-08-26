import os
from pydantic import BaseModel
from typing import List

class VirtualConfig(BaseModel):
    """
    Central Configuration for the Standalone StatIQ Virtual Trader Service.
    """
    AGENT_MODE: str = os.getenv("VIRTUAL_AGENT_MODE", "RESEARCH")  # RESEARCH, PAPER, LIVE
    PORT: int = int(os.getenv("VIRTUAL_PORT", "8001"))
    HOST: str = os.getenv("VIRTUAL_HOST", "0.0.0.0")
    
    DATABASE_URL: str = os.getenv(
        "VIRTUAL_DATABASE_URL",
        f"sqlite:///{os.path.abspath(os.path.join(os.path.dirname(__file__), '..', 'virtual.db'))}"
    )
    
    POLL_INTERVAL_SECONDS: int = int(os.getenv("VIRTUAL_POLL_INTERVAL_SECONDS", "60"))
    ODDS_STALE_THRESHOLD_SECONDS: int = int(os.getenv("VIRTUAL_ODDS_STALE_THRESHOLD_SECONDS", "60"))
    
    SPORTYBET_VIRTUAL_BASE_URL: str = "https://www.sportybet.com/api/ng/factsCenter"
    
    ENABLED_LEAGUES: List[str] = [
        "England Virtual",
        "Spain Virtual",
        "Italy Virtual",
        "Germany Virtual",
        "France Virtual"
    ]
    
    # Risk Limits
    MAX_DAILY_LOSS_PCT: float = float(os.getenv("VIRTUAL_MAX_DAILY_LOSS_PCT", "5.0"))
    MAX_SINGLE_STAKE_PCT: float = float(os.getenv("VIRTUAL_MAX_SINGLE_STAKE_PCT", "1.0"))
    MAX_CONSECUTIVE_LOSSES: int = int(os.getenv("VIRTUAL_MAX_CONSECUTIVE_LOSSES", "5"))
    MAX_OPEN_EXPOSURE_PCT: float = float(os.getenv("VIRTUAL_MAX_OPEN_EXPOSURE_PCT", "3.0"))
    
    MIN_SAMPLE_SIZE_FOR_QUALIFICATION: int = int(os.getenv("VIRTUAL_MIN_SAMPLE_SIZE", "1000"))
    MIN_EDGE_THRESHOLD: float = float(os.getenv("VIRTUAL_MIN_EDGE_THRESHOLD", "0.03"))
    
    MAX_ODDS_DRIFT_TOLERANCE: float = 0.08
    EXECUTION_DEADLINE_BUFFER_SECONDS: int = 15
    KILL_SWITCH_ACTIVE: bool = os.getenv("VIRTUAL_KILL_SWITCH", "false").lower() == "true"
    
    INITIAL_PAPER_BANKROLL: float = float(os.getenv("VIRTUAL_INITIAL_BANKROLL", "100000.0"))

virtual_config = VirtualConfig()
