from typing import Dict, Any
from app.evaluators.base import MatchStateContext, EvaluationResult

def evaluate_total_goals(market_def: Dict[str, Any], ctx: MatchStateContext) -> EvaluationResult:
    """
    Evaluates Match Total Goals (Over/Under).
    """
    if ctx.home_score is None or ctx.away_score is None:
        return EvaluationResult(status="PENDING", result_text="--")

    total = ctx.home_score + ctx.away_score
    line = float(market_def.get("line", 2.5))
    direction = str(market_def.get("direction", "OVER")).upper()

    if direction == "OVER":
        if total > line:
            return EvaluationResult(status="WON", result_text="Passed", is_early_settled=True)
        if ctx.is_concluded:
            return EvaluationResult(status="LOST", result_text="Failed")
        return EvaluationResult(status="PENDING", result_text="--")

    elif direction == "UNDER":
        if total > line:
            return EvaluationResult(status="LOST", result_text="Failed", is_early_settled=True)
        if ctx.is_concluded:
            return EvaluationResult(status="WON" if total < line else "LOST", result_text="Passed" if total < line else "Failed")
        return EvaluationResult(status="PENDING", result_text="--")

    return EvaluationResult(status="PENDING", result_text="--")
