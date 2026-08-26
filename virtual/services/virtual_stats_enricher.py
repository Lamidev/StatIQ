"""
VirtualStatsEnricher - Quantitative Form, Goal Expectancy & H2H Statistical Service for vFootball.
Computes rolling 5-10 match goal averages, draw frequencies, and eliminates cold 0-0 traps.
"""
import logging
from typing import Dict, Any, List, Optional
from datetime import datetime, timezone
from sqlalchemy.orm import Session
from sqlalchemy import or_, and_, desc

from virtual.models.virtual_models import VirtualMatchHistory

logger = logging.getLogger("statiq.virtual.stats_enricher")

class VirtualStatsEnricher:
    """
    Enriches vFootball fixtures with historical goal distributions,
    team form ratings, and head-to-head metrics.
    """

    @classmethod
    def record_match_result(
        cls,
        db: Session,
        game_id: str,
        league_name: str,
        home_team: str,
        away_team: str,
        home_score: int,
        away_score: int,
        kickoff_time: datetime
    ) -> Optional[VirtualMatchHistory]:
        """
        Saves a concluded match outcome to the historical database.
        """
        if not game_id:
            return None

        existing = db.query(VirtualMatchHistory).filter(VirtualMatchHistory.game_id == str(game_id)).first()
        if existing:
            return existing

        tot_goals = home_score + away_score
        res_1x2 = "1" if home_score > away_score else ("2" if away_score > home_score else "X")

        match = VirtualMatchHistory(
            game_id=str(game_id),
            league_name=league_name,
            home_team=home_team,
            away_team=away_team,
            home_score=home_score,
            away_score=away_score,
            total_goals=tot_goals,
            is_over_15=(tot_goals >= 2),
            is_over_25=(tot_goals >= 3),
            result_1x2=res_1x2,
            kickoff_time=kickoff_time,
            created_at=datetime.now(timezone.utc)
        )
        try:
            db.add(match)
            db.commit()
            db.refresh(match)
            return match
        except Exception as e:
            db.rollback()
            logger.warning(f"[StatsEnricher] Error recording match {game_id}: {e}")
            return None

    @classmethod
    def get_team_profile(cls, db: Session, team_name: str, league_name: Optional[str] = None, last_n: int = 10) -> Dict[str, Any]:
        """
        Calculates rolling performance metrics for a specific virtual team.
        """
        query = db.query(VirtualMatchHistory).filter(
            or_(VirtualMatchHistory.home_team == team_name, VirtualMatchHistory.away_team == team_name)
        )
        if league_name:
            query = query.filter(VirtualMatchHistory.league_name == league_name)

        matches = query.order_by(desc(VirtualMatchHistory.kickoff_time)).limit(last_n).all()

        if not matches:
            # Baseline league defaults if no history recorded yet
            return {
                "team": team_name,
                "matches_played": 0,
                "avg_goals_scored": 1.5,
                "avg_goals_conceded": 1.4,
                "avg_total_goals": 2.9,
                "over_15_rate": 0.80,
                "win_rate": 0.40,
                "draw_rate": 0.30,
                "loss_rate": 0.30,
                "form": []
            }

        total_gf = 0
        total_ga = 0
        total_match_goals = 0
        over_15_count = 0
        wins = 0
        draws = 0
        losses = 0
        form = []

        for m in matches:
            is_home = (m.home_team == team_name)
            gf = m.home_score if is_home else m.away_score
            ga = m.away_score if is_home else m.home_score
            tot = m.total_goals

            total_gf += gf
            total_ga += ga
            total_match_goals += tot

            if tot >= 2:
                over_15_count += 1

            if gf > ga:
                wins += 1
                form.append("W")
            elif gf == ga:
                draws += 1
                form.append("D")
            else:
                losses += 1
                form.append("L")

        count = len(matches)
        return {
            "team": team_name,
            "matches_played": count,
            "avg_goals_scored": round(total_gf / count, 2),
            "avg_goals_conceded": round(total_ga / count, 2),
            "avg_total_goals": round(total_match_goals / count, 2),
            "over_15_rate": round(over_15_count / count, 2),
            "win_rate": round(wins / count, 2),
            "draw_rate": round(draws / count, 2),
            "loss_rate": round(losses / count, 2),
            "form": form
        }

    @classmethod
    def evaluate_fixture_safety(
        cls, db: Session, home_team: str, away_team: str, league_name: str
    ) -> Dict[str, Any]:
        """
        Evaluates a scheduled match to determine:
        1. Combined Goal Expectancy (GF + GA)
        2. Cold trap risk (e.g. low-goal 0-0 grinder)
        3. Double Chance (1X / X2) safety score
        """
        h_prof = cls.get_team_profile(db, home_team, league_name, last_n=8)
        a_prof = cls.get_team_profile(db, away_team, league_name, last_n=8)

        # Combined expected match goals
        exp_goals = (h_prof["avg_goals_scored"] + a_prof["avg_goals_conceded"] + 
                     a_prof["avg_goals_scored"] + h_prof["avg_goals_conceded"]) / 2.0

        # Over 1.5 combined probability estimate
        over_15_prob = (h_prof["over_15_rate"] + a_prof["over_15_rate"]) / 2.0

        # Cold Trap: Both teams average under 2.0 total goals with < 60% Over 1.5 rate
        is_cold_trap = (exp_goals < 2.20 and over_15_prob < 0.65)

        # Double Chance 1X Safety (Home team win or draw rate vs Away win rate)
        dc_1x_safety = round(h_prof["win_rate"] + h_prof["draw_rate"], 2)
        # Double Chance X2 Safety (Away team win or draw rate vs Home win rate)
        dc_x2_safety = round(a_prof["win_rate"] + a_prof["draw_rate"], 2)

        return {
            "home_team": home_team,
            "away_team": away_team,
            "league_name": league_name,
            "expected_goals": round(exp_goals, 2),
            "over_15_prob": round(over_15_prob, 2),
            "is_cold_trap": is_cold_trap,
            "dc_1x_safety": dc_1x_safety,
            "dc_x2_safety": dc_x2_safety,
            "home_form": h_prof["form"][:5],
            "away_form": a_prof["form"][:5]
        }
