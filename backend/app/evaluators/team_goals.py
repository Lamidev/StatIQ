from typing import Dict, Any
from app.evaluators.base import MatchStateContext, EvaluationResult

def evaluate_team_goals(market_def: Dict[str, Any], ctx: MatchStateContext) -> EvaluationResult:
    """
    Evaluates individual Team Total Goals (e.g. Udinese Over 1.5 Goals).
    """
    if ctx.home_score is None or ctx.away_score is None:
        return EvaluationResult(status="PENDING", result_text="--")

    target_team = str(market_def.get("target_team", "HOME")).upper()
    direction = str(market_def.get("direction", "OVER")).upper()
    line = float(market_def.get("line", 0.5))

    target_score = ctx.away_score if target_team in ("AWAY", "2") else ctx.home_score

    if direction == "OVER":
        if target_score > line:
            return EvaluationResult(status="WON", result_text="Passed", is_early_settled=True)
        if ctx.is_concluded:
            return EvaluationResult(status="LOST", result_text="Failed")
        return EvaluationResult(status="PENDING", result_text="--")
    elif direction == "UNDER":
        if target_score > line:
            return EvaluationResult(status="LOST", result_text="Failed", is_early_settled=True)
        if ctx.is_concluded:
            return EvaluationResult(status="WON" if target_score < line else "LOST", result_text="Passed")
        return EvaluationResult(status="PENDING", result_text="--")

    return EvaluationResult(status="PENDING", result_text="--")
