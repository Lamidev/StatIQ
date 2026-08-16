from dataclasses import dataclass
from typing import Optional, Dict, Any

@dataclass
class MatchStateContext:
    home_score: Optional[int]
    away_score: Optional[int]
    is_concluded: bool
    is_live: bool = False
    half_time_home_score: Optional[int] = None
    half_time_away_score: Optional[int] = None
    total_corners: Optional[int] = None
    home_corners: Optional[int] = None
    away_corners: Optional[int] = None
    home_team: str = ""
    away_team: str = ""

@dataclass
class EvaluationResult:
    status: str           # "WON", "LOST", "VOID", "EARLY_WON", "EARLY_LOST", "PENDING"
    result_text: str      # e.g. "Passed", "2 - 1", "Failed", "Yes", "No"
    is_early_settled: bool = False
