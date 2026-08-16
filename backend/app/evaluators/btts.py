from typing import Dict, Any
from app.evaluators.base import MatchStateContext, EvaluationResult

def evaluate_btts(market_def: Dict[str, Any], ctx: MatchStateContext) -> EvaluationResult:
    """
    Evaluates Both Teams to Score (GG / NG).
    """
    if ctx.home_score is None or ctx.away_score is None:
        return EvaluationResult(status="PENDING", result_text="--")

    is_yes = str(market_def.get("selection", "YES")).upper() in ("YES", "GG", "TRUE")
    both_scored = ctx.home_score >= 1 and ctx.away_score >= 1

    if is_yes:
        if both_scored:
            return EvaluationResult(status="WON", result_text="Passed", is_early_settled=True)
        if ctx.is_concluded:
            return EvaluationResult(status="LOST", result_text="Failed")
        return EvaluationResult(status="PENDING", result_text="--")
    else: # NG / NO
        if both_scored:
            return EvaluationResult(status="LOST", result_text="Failed", is_early_settled=True)
        if ctx.is_concluded:
            return EvaluationResult(status="WON" if (ctx.home_score == 0 or ctx.away_score == 0) else "LOST", result_text="Passed")
        return EvaluationResult(status="PENDING", result_text="--")
