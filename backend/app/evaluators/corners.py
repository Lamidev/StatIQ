from typing import Dict, Any
from app.evaluators.base import MatchStateContext, EvaluationResult

def evaluate_corners(market_def: Dict[str, Any], ctx: MatchStateContext) -> EvaluationResult:
    """
    Evaluates Corner markets (Total Corners Over/Under, Team Corners).
    """
    c_val = ctx.total_corners
    target_team = market_def.get("target_team")
    if target_team == "HOME" and ctx.home_corners is not None:
        c_val = ctx.home_corners
    elif target_team == "AWAY" and ctx.away_corners is not None:
        c_val = ctx.away_corners

    if c_val is None:
        return EvaluationResult(status="PENDING", result_text="--")

    line = float(market_def.get("line", 7.5))
    direction = str(market_def.get("direction", "OVER")).upper()

    if direction == "OVER":
        if c_val > line:
            return EvaluationResult(status="WON", result_text=f"{c_val} Corners", is_early_settled=True)
        if ctx.is_concluded:
            return EvaluationResult(status="LOST", result_text=f"{c_val} Corners")
        return EvaluationResult(status="PENDING", result_text=f"{c_val} Corners")
    elif direction == "UNDER":
        if c_val > line:
            return EvaluationResult(status="LOST", result_text=f"{c_val} Corners", is_early_settled=True)
        if ctx.is_concluded:
            return EvaluationResult(status="WON" if c_val < line else "LOST", result_text=f"{c_val} Corners")
        return EvaluationResult(status="PENDING", result_text=f"{c_val} Corners")

    return EvaluationResult(status="PENDING", result_text="--")
