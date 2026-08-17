import re
from typing import Dict, Any, Optional
from app.evaluators.base import MatchStateContext, EvaluationResult
from app.evaluators.combo import evaluate_combo
from app.evaluators.win_either_half import evaluate_win_either_half
from app.evaluators.total_goals import evaluate_total_goals
from app.evaluators.team_goals import evaluate_team_goals
from app.evaluators.double_chance import evaluate_double_chance
from app.evaluators.match_result import evaluate_match_result
from app.evaluators.btts import evaluate_btts
from app.evaluators.handicap import evaluate_handicap
from app.evaluators.corners import evaluate_corners

class SettlementRouter:
    """
    StatIQ V2.0 Central Settlement Dispatcher.
    Maps structured market definitions or inferable market types to dedicated evaluators.
    """

    @classmethod
    def evaluate(
        cls,
        market_type: str,
        market_def: Dict[str, Any],
        ctx: MatchStateContext
    ) -> EvaluationResult:
        mtype = (market_type or "").upper().strip()

        if mtype in ("COMBO_OR", "COMBO_AND", "COMBO_SAFETY"):
            return evaluate_combo(market_def, ctx)

        if mtype in ("WIN_EITHER_HALF", "WEH"):
            return evaluate_win_either_half(market_def, ctx)

        if mtype in ("OVER_UNDER_GOALS", "TOTAL_GOALS", "MATCH_TOTAL_GOALS"):
            return evaluate_total_goals(market_def, ctx)

        if mtype in ("TEAM_TOTAL_GOALS", "TEAM_GOALS"):
            return evaluate_team_goals(market_def, ctx)

        if mtype in ("DOUBLE_CHANCE", "DC"):
            return evaluate_double_chance(market_def, ctx)

        if mtype in ("MATCH_RESULT", "1X2"):
            return evaluate_match_result(market_def, ctx)

        if mtype in ("BTTS", "BOTH_TEAMS_TO_SCORE", "GG_NG"):
            return evaluate_btts(market_def, ctx)

        if mtype in ("ASIAN_HANDICAP", "HANDICAP"):
            return evaluate_handicap(market_def, ctx)

        if mtype in ("TOTAL_CORNERS", "TEAM_CORNERS", "CORNERS"):
            return evaluate_corners(market_def, ctx)

        # Fallback to inference if market_type is generic
        return cls._infer_and_evaluate(market_def, ctx)

    @classmethod
    def _infer_and_evaluate(cls, market_def: Dict[str, Any], ctx: MatchStateContext) -> EvaluationResult:
        sel_name = str(market_def.get("selection_name") or market_def.get("selection") or "").strip().lower()
        mkt_name = str(market_def.get("market_name") or market_def.get("market_type") or "").strip().lower()
        combined = f"{mkt_name} — {sel_name}"

        # 1. Combo Market
        if any(k in combined for k in ("or over", "win or over", "team or over", "& over")) and "both halve" not in combined:
            m_ov = re.search(r"over\s*(\d+\.?\d*)", combined)
            line = float(m_ov.group(1)) if m_ov else 2.5
            is_away = "away" in sel_name or (ctx.away_team and ctx.away_team.lower() in sel_name and ctx.home_team.lower() not in sel_name)
            target = "AWAY" if is_away else "HOME"
            return evaluate_combo({"combo_type": "OR", "target_team": target, "over_line": line}, ctx)

        # 2. Win Either Half
        if "win either half" in combined or "weh" in combined:
            is_away = "away" in sel_name or (ctx.away_team and ctx.away_team.lower() in sel_name and ctx.home_team.lower() not in sel_name)
            target = "AWAY" if is_away else "HOME"
            return evaluate_win_either_half({"target_team": target}, ctx)

        # 3. Corners
        if "corner" in combined:
            m_ov = re.search(r"over\s*(\d+\.?\d*)", combined)
            m_un = re.search(r"under\s*(\d+\.?\d*)", combined)
            direction = "OVER" if m_ov else "UNDER"
            line = float(m_ov.group(1)) if m_ov else (float(m_un.group(1)) if m_un else 7.5)
            target = "HOME" if "home" in combined else ("AWAY" if "away" in combined else None)
            return evaluate_corners({"direction": direction, "line": line, "target_team": target}, ctx)

        # 4. BTTS / GG-NG
        if "both teams to score" in mkt_name or "btts" in mkt_name or "gg/ng" in mkt_name or "gg_ng" in mkt_name or "goal / no goal" in mkt_name:
            is_no = sel_name in ("no", "ng", "false", "no goal") or (sel_name.startswith("no") and "yes" not in sel_name)
            return evaluate_btts({"selection": "NO" if is_no else "YES"}, ctx)

        # 5. Over / Under Goals
        m_ov = re.search(r"over\s*(\d+\.?\d*)", combined)
        m_un = re.search(r"under\s*(\d+\.?\d*)", combined)
        if (m_ov or m_un) and not any(k in combined for k in ("double chance", "1x", "x2", "handicap")):
            direction = "OVER" if m_ov else "UNDER"
            line = float(m_ov.group(1)) if m_ov else float(m_un.group(1))
            return evaluate_total_goals({"direction": direction, "line": line}, ctx)

        # 6. Double Chance (including 1st Half / 2nd Half Double Chance)
        if any(k in combined for k in ("double chance", "(1x)", "(x2)", "(12)", "home or draw", "away or draw", "home or away", "1x", "x2", "12")):
            sel = "1X"
            if any(k in sel_name for k in ("x2", "away or draw", "2 or draw", "draw or away", "away/draw")): sel = "X2"
            elif any(k in sel_name for k in ("12", "home or away", "1 or 2", "home/away")): sel = "12"
            elif any(k in sel_name for k in ("1x", "home or draw", "1 or draw", "home/draw")): sel = "1X"
            return evaluate_double_chance({"selection": sel, "market_name": mkt_name}, ctx)

        # 7. Handicap
        if "handicap" in combined or "(+" in combined or "(-" in combined:
            m_val = re.search(r"([+-]?\d+\.?\d*)", combined)
            hcp = float(m_val.group(1)) if m_val else 1.5
            is_away = "away" in sel_name or (ctx.away_team and ctx.away_team.lower() in sel_name and ctx.home_team.lower() not in sel_name)
            return evaluate_handicap({"target_team": "AWAY" if is_away else "HOME", "handicap": hcp}, ctx)

        # 8. 1X2 Match Result
        if "1x2" in mkt_name or "match result" in mkt_name or mkt_name in ("1x2", "match_result", "") or ctx.is_concluded:
            if sel_name in ("draw", "x", "tie", "draw win") or "draw" in sel_name:
                return evaluate_match_result({"selection": "X"}, ctx)
            is_away = sel_name in ("2", "away", "away win") or (ctx.away_team and ctx.away_team.lower() in sel_name)
            return evaluate_match_result({"selection": "2" if is_away else "1"}, ctx)

        return EvaluationResult(status="PENDING", result_text="--")
