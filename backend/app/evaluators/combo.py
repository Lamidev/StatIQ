from typing import Dict, Any
from app.evaluators.base import MatchStateContext, EvaluationResult

def evaluate_combo(market_def: Dict[str, Any], ctx: MatchStateContext) -> EvaluationResult:
    """
    Evaluates COMBO_OR and COMBO_AND markets (e.g. Udinese Win OR Over 2.5 Goals).
    """
    if ctx.home_score is None or ctx.away_score is None:
        return EvaluationResult(status="PENDING", result_text="--")

    total_goals = ctx.home_score + ctx.away_score
    combo_type = market_def.get("combo_type", "OR").upper()
    
    target_team = str(market_def.get("target_team", "HOME")).upper()
    over_line = float(market_def.get("over_line", 2.5))
    
    over_satisfied = total_goals > over_line
    
    # Team win condition
    if target_team in ("HOME", "1"):
        team_won = ctx.home_score > ctx.away_score
    elif target_team in ("AWAY", "2"):
        team_won = ctx.away_score > ctx.home_score
    else:
        team_won = ctx.home_score != ctx.away_score

    if combo_type == "OR":
        # Early win check
        if over_satisfied or team_won:
            return EvaluationResult(status="WON", result_text="Passed", is_early_settled=over_satisfied)
        if ctx.is_concluded:
            return EvaluationResult(status="LOST", result_text="Failed")
        return EvaluationResult(status="PENDING", result_text="--")
        
    elif combo_type == "AND":
        if ctx.is_concluded:
            is_won = team_won and over_satisfied
            return EvaluationResult(status="WON" if is_won else "LOST", result_text="Passed" if is_won else "Failed")
        return EvaluationResult(status="PENDING", result_text="--")

    return EvaluationResult(status="PENDING", result_text="--")
