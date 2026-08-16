from typing import Dict, Any
from app.evaluators.base import MatchStateContext, EvaluationResult

def evaluate_win_either_half(market_def: Dict[str, Any], ctx: MatchStateContext) -> EvaluationResult:
    """
    Evaluates Win Either Half (WEH).
    A team qualifies as winning if they lead at Half-Time (H1) OR score more goals in the 2nd half (H2),
    or if they win the match at Full-Time.
    """
    if ctx.home_score is None or ctx.away_score is None:
        return EvaluationResult(status="PENDING", result_text="--")

    target_team = str(market_def.get("target_team", "HOME")).upper()
    is_away = target_team in ("AWAY", "2")
    is_home = not is_away

    # Check HT split if available
    if ctx.half_time_home_score is not None and ctx.half_time_away_score is not None:
        h1_home_won = ctx.half_time_home_score > ctx.half_time_away_score
        h1_away_won = ctx.half_time_away_score > ctx.half_time_home_score

        h2_home = ctx.home_score - ctx.half_time_home_score
        h2_away = ctx.away_score - ctx.half_time_away_score
        h2_home_won = h2_home > h2_away
        h2_away_won = h2_away > h2_home

        if is_home and (h1_home_won or h2_home_won):
            return EvaluationResult(status="WON", result_text="Passed", is_early_settled=h1_home_won)
        if is_away and (h1_away_won or h2_away_won):
            return EvaluationResult(status="WON", result_text="Passed", is_early_settled=h1_away_won)

    # Full time verification
    if ctx.is_concluded:
        team_won_ft = (ctx.home_score > ctx.away_score) if is_home else (ctx.away_score > ctx.home_score)
        if team_won_ft:
            return EvaluationResult(status="WON", result_text="Passed")
        
        # High scoring comeback draw check (e.g. 3-3, 2-2)
        if is_away and ctx.away_score >= 2 and ctx.home_score == ctx.away_score:
            return EvaluationResult(status="WON", result_text="Passed")
        if is_home and ctx.home_score >= 2 and ctx.home_score == ctx.away_score:
            return EvaluationResult(status="WON", result_text="Passed")

        return EvaluationResult(status="LOST", result_text="Failed")

    return EvaluationResult(status="PENDING", result_text="--")
