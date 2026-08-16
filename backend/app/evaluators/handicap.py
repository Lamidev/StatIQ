from typing import Dict, Any
from app.evaluators.base import MatchStateContext, EvaluationResult

def evaluate_handicap(market_def: Dict[str, Any], ctx: MatchStateContext) -> EvaluationResult:
    """
    Evaluates Asian & European Handicap (e.g. Union Brescia +1.5).
    """
    if ctx.home_score is None or ctx.away_score is None or not ctx.is_concluded:
        return EvaluationResult(status="PENDING", result_text="--")

    target_team = str(market_def.get("target_team", "HOME")).upper()
    handicap_val = float(market_def.get("handicap", 1.5))

    if target_team in ("AWAY", "2"):
        adj_score = ctx.away_score + handicap_val
        is_won = adj_score > ctx.home_score
        is_push = adj_score == ctx.home_score
    else:
        adj_score = ctx.home_score + handicap_val
        is_won = adj_score > ctx.away_score
        is_push = adj_score == ctx.away_score

    if is_push:
        return EvaluationResult(status="VOID", result_text="Void/Refunded")

    return EvaluationResult(status="WON" if is_won else "LOST", result_text="Passed" if is_won else "Failed")
