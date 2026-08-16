from typing import Dict, Any
from app.evaluators.base import MatchStateContext, EvaluationResult

def evaluate_double_chance(market_def: Dict[str, Any], ctx: MatchStateContext) -> EvaluationResult:
    """
    Evaluates Double Chance (1X, X2, 12).
    """
    if ctx.home_score is None or ctx.away_score is None:
        return EvaluationResult(status="PENDING", result_text="--")

    pick = str(market_def.get("selection", "1X")).upper()

    if not ctx.is_concluded:
        return EvaluationResult(status="PENDING", result_text="--")

    if "1X" in pick or "HOME_OR_DRAW" in pick or "1 OR DRAW" in pick:
        is_won = ctx.home_score >= ctx.away_score
    elif "X2" in pick or "AWAY_OR_DRAW" in pick or "2 OR DRAW" in pick or "DRAW OR AWAY" in pick:
        is_won = ctx.away_score >= ctx.home_score
    elif "12" in pick or "HOME_OR_AWAY" in pick:
        is_won = ctx.home_score != ctx.away_score
    else:
        is_won = ctx.home_score >= ctx.away_score

    return EvaluationResult(status="WON" if is_won else "LOST", result_text="Passed" if is_won else "Failed")
