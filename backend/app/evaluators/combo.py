from typing import Dict, Any
from app.evaluators.base import MatchStateContext, EvaluationResult

def evaluate_combo(market_def: Dict[str, Any], ctx: MatchStateContext) -> EvaluationResult:
    """
    Evaluates COMBO_OR and COMBO_AND markets (e.g. Udinese Win OR Over 2.5 Goals, Draw/Away & Over 1.5).
    """
    if ctx.home_score is None or ctx.away_score is None:
        return EvaluationResult(status="PENDING", result_text="--")

    total_goals = ctx.home_score + ctx.away_score
    combo_type = str(market_def.get("combo_type", "AND")).upper()
    
    target_team = str(market_def.get("target_team", "HOME")).upper()
    goal_line = float(market_def.get("goal_line") or market_def.get("over_line") or 1.5)
    goal_direction = str(market_def.get("goal_direction", "OVER")).upper()
    
    if goal_direction == "UNDER":
        goals_satisfied = total_goals < goal_line
    else:
        goals_satisfied = total_goals > goal_line
    
    # Team condition
    if target_team in ("HOME", "1"):
        team_won = ctx.home_score > ctx.away_score
    elif target_team in ("AWAY", "2"):
        team_won = ctx.away_score > ctx.home_score
    elif target_team in ("DRAW", "X"):
        team_won = ctx.home_score == ctx.away_score
    elif target_team in ("1X", "HOME/DRAW", "HOME_OR_DRAW", "DRAW/HOME", "DRAW_OR_HOME"):
        team_won = ctx.home_score >= ctx.away_score
    elif target_team in ("X2", "DRAW/AWAY", "DRAW_OR_AWAY", "AWAY/DRAW", "AWAY_OR_DRAW"):
        team_won = ctx.away_score >= ctx.home_score
    elif target_team in ("12", "HOME/AWAY", "HOME_OR_AWAY"):
        team_won = ctx.home_score != ctx.away_score
    else:
        team_won = ctx.home_score != ctx.away_score

    if combo_type == "OR":
        # Early win check for OR combos
        if goals_satisfied or team_won:
            return EvaluationResult(status="WON", result_text="Passed", is_early_settled=goals_satisfied)
        if ctx.is_concluded:
            return EvaluationResult(status="LOST", result_text="Failed")
        return EvaluationResult(status="PENDING", result_text="--")
        
    elif combo_type in ("AND", "COMBO"):
        if ctx.is_concluded:
            is_won = team_won and goals_satisfied
            return EvaluationResult(status="WON" if is_won else "LOST", result_text="Passed" if is_won else "Failed")
        # For live matches in AND combos, cannot settle WON until match concludes
        # but if UNDER goals is already exceeded, it's definitively LOST
        if goal_direction == "UNDER" and total_goals >= goal_line:
            return EvaluationResult(status="LOST", result_text="Failed")
        return EvaluationResult(status="PENDING", result_text="--")

    return EvaluationResult(status="PENDING", result_text="--")
