from typing import Dict, Any
from app.evaluators.base import MatchStateContext, EvaluationResult

def evaluate_double_chance(market_def: Dict[str, Any], ctx: MatchStateContext) -> EvaluationResult:
    """
    Evaluates Double Chance (1X, X2, 12) including 1st Half and 2nd Half Double Chance.
    """
    if ctx.home_score is None or ctx.away_score is None:
        return EvaluationResult(status="PENDING", result_text="--")

    if not ctx.is_concluded:
        return EvaluationResult(status="PENDING", result_text="--")

    mkt = str(market_def.get("market_name") or market_def.get("market_type") or "").upper()
    pick = str(market_def.get("selection") or market_def.get("selection_name") or "1X").upper().strip()

    is_2nd_half = "2ND HALF" in mkt or "2ND HALF" in pick or "SECOND HALF" in mkt
    is_1st_half = "1ST HALF" in mkt or "1ST HALF" in pick or "FIRST HALF" in mkt

    h_score = ctx.home_score
    a_score = ctx.away_score

    if is_2nd_half and ctx.half_time_home_score is not None and ctx.half_time_away_score is not None:
        h_score = ctx.home_score - ctx.half_time_home_score
        a_score = ctx.away_score - ctx.half_time_away_score
    elif is_1st_half and ctx.half_time_home_score is not None and ctx.half_time_away_score is not None:
        h_score = ctx.half_time_home_score
        a_score = ctx.half_time_away_score

    if "1X" in pick or "HOME_OR_DRAW" in pick or "1 OR DRAW" in pick or "HOME OR DRAW" in pick:
        is_won = h_score >= a_score
    elif "X2" in pick or "AWAY_OR_DRAW" in pick or "2 OR DRAW" in pick or "DRAW OR AWAY" in pick or "AWAY OR DRAW" in pick:
        is_won = a_score >= h_score
    elif "12" in pick or "HOME_OR_AWAY" in pick or "HOME OR AWAY" in pick:
        is_won = h_score != a_score
    else:
        is_won = h_score >= a_score

    return EvaluationResult(status="WON" if is_won else "LOST", result_text=f"{ctx.home_score} - {ctx.away_score}")
