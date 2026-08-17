from typing import Dict, Any
from app.evaluators.base import MatchStateContext, EvaluationResult

def evaluate_btts(market_def: Dict[str, Any], ctx: MatchStateContext) -> EvaluationResult:
    """
    Evaluates Both Teams to Score (GG / NG).
    """
    if ctx.home_score is None or ctx.away_score is None:
        return EvaluationResult(status="PENDING", result_text="--")

    sel = str(market_def.get("selection") or market_def.get("selection_name") or "YES").upper().strip()
    sel_clean = sel.replace("GG/NG —", "").replace("GG/NG -", "").replace("BTTS —", "").strip()

    is_no = sel_clean in ("NO", "NG", "FALSE", "NO GOAL", "BOTH TEAMS TO SCORE - NO", "BTTS - NO") or (sel_clean.startswith("NO") and "YES" not in sel_clean)
    is_yes = not is_no

    both_scored = ctx.home_score >= 1 and ctx.away_score >= 1

    if is_yes:
        if both_scored:
            return EvaluationResult(status="WON", result_text=f"{ctx.home_score} - {ctx.away_score}", is_early_settled=True)
        if ctx.is_concluded:
            return EvaluationResult(status="LOST", result_text=f"{ctx.home_score} - {ctx.away_score}")
        return EvaluationResult(status="PENDING", result_text="--")
    else: # NG / NO
        if both_scored:
            return EvaluationResult(status="LOST", result_text=f"{ctx.home_score} - {ctx.away_score}", is_early_settled=True)
        if ctx.is_concluded:
            return EvaluationResult(status="WON" if (ctx.home_score == 0 or ctx.away_score == 0) else "LOST", result_text=f"{ctx.home_score} - {ctx.away_score}")
        return EvaluationResult(status="PENDING", result_text="--")
