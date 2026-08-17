from typing import Dict, Any
from app.evaluators.base import MatchStateContext, EvaluationResult

def evaluate_match_result(market_def: Dict[str, Any], ctx: MatchStateContext) -> EvaluationResult:
    """
    Evaluates 1X2 Match Result (Home, Draw, Away).
    """
    if ctx.home_score is None or ctx.away_score is None or not ctx.is_concluded:
        return EvaluationResult(status="PENDING", result_text="--")

    pick = str(market_def.get("selection") or market_def.get("selection_name") or "1").upper().strip()
    sel_clean = pick.replace("1X2 —", "").replace("1X2 -", "").strip()

    if sel_clean in ("1", "HOME", "HOME_TEAM", "HOME WIN", "1X2 — HOME") or (ctx.home_team and ctx.home_team.upper() in sel_clean and "AWAY" not in sel_clean):
        is_won = ctx.home_score > ctx.away_score
    elif sel_clean in ("2", "AWAY", "AWAY_TEAM", "AWAY WIN", "1X2 — AWAY") or (ctx.away_team and ctx.away_team.upper() in sel_clean and "HOME" not in sel_clean):
        is_won = ctx.away_score > ctx.home_score
    elif sel_clean in ("X", "DRAW", "TIE", "1X2 — DRAW", "1X2 — X", "DRAW WIN") or "DRAW" in sel_clean:
        is_won = ctx.home_score == ctx.away_score
    else:
        is_won = ctx.home_score > ctx.away_score

    return EvaluationResult(status="WON" if is_won else "LOST", result_text=f"{ctx.home_score} - {ctx.away_score}")
