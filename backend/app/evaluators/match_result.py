from typing import Dict, Any
from app.evaluators.base import MatchStateContext, EvaluationResult

def evaluate_match_result(market_def: Dict[str, Any], ctx: MatchStateContext) -> EvaluationResult:
    """
    Evaluates 1X2 Match Result (Home, Draw, Away).
    """
    if ctx.home_score is None or ctx.away_score is None or not ctx.is_concluded:
        return EvaluationResult(status="PENDING", result_text="--")

    pick = str(market_def.get("selection", "1")).upper()

    if pick in ("1", "HOME", "HOME_TEAM"):
        is_won = ctx.home_score > ctx.away_score
    elif pick in ("2", "AWAY", "AWAY_TEAM"):
        is_won = ctx.away_score > ctx.home_score
    elif pick in ("X", "DRAW"):
        is_won = ctx.home_score == ctx.away_score
    else:
        is_won = ctx.home_score > ctx.away_score

    return EvaluationResult(status="WON" if is_won else "LOST", result_text="Passed" if is_won else "Failed")
