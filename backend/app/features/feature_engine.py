import datetime
import hashlib
import json
from typing import Dict, Any, List
from sqlalchemy import select, and_, or_
from app.db.models import Fixture, FeatureSnapshot

class PointInTimeFeatureEngine:
    """
    Point-in-Time Feature Engine for MatchIQ.
    Strictly enforces temporal boundaries: only retrieves historical matches
    played BEFORE the target fixture's kickoff_datetime.
    """
    def __init__(self, session):
        self.session = session

    def compute_features_for_fixture(self, fixture: Fixture) -> Dict[str, Any]:
        target_time = fixture.kickoff_datetime
        home_id = fixture.home_team_id
        away_id = fixture.away_team_id

        # 1. Fetch prior matches for Home Team strictly before target_time
        stmt_home = (
            select(Fixture)
            .where(
                and_(
                    or_(Fixture.home_team_id == home_id, Fixture.away_team_id == home_id),
                    Fixture.kickoff_datetime < target_time,
                    Fixture.status == "FINISHED",
                    Fixture.home_score.isnot(None)
                )
            )
            .order_by(Fixture.kickoff_datetime.desc())
            .limit(15)
        )
        res_home = self.session.execute(stmt_home)
        home_prior_matches = list(res_home.scalars().all())

        # 2. Fetch prior matches for Away Team strictly before target_time
        stmt_away = (
            select(Fixture)
            .where(
                and_(
                    or_(Fixture.home_team_id == away_id, Fixture.away_team_id == away_id),
                    Fixture.kickoff_datetime < target_time,
                    Fixture.status == "FINISHED",
                    Fixture.home_score.isnot(None)
                )
            )
            .order_by(Fixture.kickoff_datetime.desc())
            .limit(15)
        )
        res_away = self.session.execute(stmt_away)
        away_prior_matches = list(res_away.scalars().all())

        # Compute overall stats for Home & Away teams
        home_stats = self._calculate_team_rolling_stats(home_id, home_prior_matches)
        away_stats = self._calculate_team_rolling_stats(away_id, away_prior_matches)

        # 3. Fetch Home-only prior matches for Home team
        home_only_matches = [m for m in home_prior_matches if m.home_team_id == home_id][:5]
        # 4. Fetch Away-only prior matches for Away team
        away_only_matches = [m for m in away_prior_matches if m.away_team_id == away_id][:5]

        home_only_stats = self._calculate_team_rolling_stats(home_id, home_only_matches)
        away_only_stats = self._calculate_team_rolling_stats(away_id, away_only_matches)


        # 5. Fetch Head-to-Head (H2H) historical matches between home and away teams strictly before target_time
        stmt_h2h = (
            select(Fixture)
            .where(
                and_(
                    or_(
                        and_(Fixture.home_team_id == home_id, Fixture.away_team_id == away_id),
                        and_(Fixture.home_team_id == away_id, Fixture.away_team_id == home_id)
                    ),
                    Fixture.kickoff_datetime < target_time,
                    Fixture.status == "FINISHED",
                    Fixture.home_score.isnot(None)
                )
            )
            .order_by(Fixture.kickoff_datetime.desc())
            .limit(10)
        )
        res_h2h = self.session.execute(stmt_h2h)
        h2h_matches = list(res_h2h.scalars().all())

        h2h_stats = self._calculate_h2h_stats(home_id, away_id, h2h_matches)

        # Calculate 15-match long-term structural team capability metrics
        home_longterm = self._calculate_longterm_structural_stats(home_id, home_prior_matches)
        away_longterm = self._calculate_longterm_structural_stats(away_id, away_prior_matches)

        # Composite Squad Capability Index Differential
        # Combines 15-match PPG difference, long-term goal ratio difference, and H2H dominance
        ppg_diff_15 = home_longterm["ppg_15"] - away_longterm["ppg_15"]
        goal_ratio_diff_15 = home_longterm["goal_ratio_15"] - away_longterm["goal_ratio_15"]
        squad_capability_diff = (0.50 * ppg_diff_15) + (0.30 * goal_ratio_diff_15) + (0.20 * h2h_stats["h2h_dominance_home"])

        # Rest days calculation
        home_rest_days = self._calculate_rest_days(target_time, home_prior_matches)
        away_rest_days = self._calculate_rest_days(target_time, away_prior_matches)

        # 14-day match density
        home_density = sum(1 for m in home_prior_matches if (target_time - m.kickoff_datetime).total_seconds() <= 14 * 86400)
        away_density = sum(1 for m in away_prior_matches if (target_time - m.kickoff_datetime).total_seconds() <= 14 * 86400)

        is_uefa = 1.0 if fixture.competition_code in ["CL", "EL", "KL"] else 0.0

        feature_vector = {
            "fixture_id": fixture.id,
            "kickoff_datetime": target_time.isoformat(),
            "competition_code": fixture.competition_code,
            "is_uefa_competition": is_uefa,
            "matchday": fixture.matchday or 1,
            # Home Overall Stats
            "home_form_5": home_stats["form_5"],
            "home_goals_scored_avg_5": home_stats["goals_scored_avg_5"],
            "home_goals_conceded_avg_5": home_stats["goals_conceded_avg_5"],
            "home_win_ratio_10": home_stats["win_ratio_10"],
            "home_ppg_15": home_longterm["ppg_15"],
            "home_goal_ratio_15": home_longterm["goal_ratio_15"],
            "home_rest_days": home_rest_days,
            "home_match_density_14": home_density,
            "home_only_form_5": home_only_stats["form_5"],
            # Away Overall Stats
            "away_form_5": away_stats["form_5"],
            "away_goals_scored_avg_5": away_stats["goals_scored_avg_5"],
            "away_goals_conceded_avg_5": away_stats["goals_conceded_avg_5"],
            "away_win_ratio_10": away_stats["win_ratio_10"],
            "away_ppg_15": away_longterm["ppg_15"],
            "away_goal_ratio_15": away_longterm["goal_ratio_15"],
            "away_rest_days": away_rest_days,
            "away_match_density_14": away_density,
            "away_only_form_5": away_only_stats["form_5"],
            # Head-to-Head (H2H) Historical Metrics
            "h2h_matches_count": h2h_stats["h2h_count"],
            "h2h_home_win_ratio": h2h_stats["h2h_home_win_ratio"],
            "h2h_away_win_ratio": h2h_stats["h2h_away_win_ratio"],
            "h2h_draw_ratio": h2h_stats["h2h_draw_ratio"],
            "h2h_avg_goal_diff": h2h_stats["h2h_avg_goal_diff"],
            "h2h_dominance_home": h2h_stats["h2h_dominance_home"],
            # Structural Team Tier & Squad Capability Differentials
            "form_diff_5": home_stats["form_5"] - away_stats["form_5"],
            "attack_diff_5": home_stats["goals_scored_avg_5"] - away_stats["goals_scored_avg_5"],
            "defense_diff_5": away_stats["goals_conceded_avg_5"] - home_stats["goals_conceded_avg_5"],
            "ppg_diff_15": ppg_diff_15,
            "goal_ratio_diff_15": goal_ratio_diff_15,
            "squad_capability_diff": squad_capability_diff,
            "rest_diff": home_rest_days - away_rest_days,
            "density_diff": home_density - away_density,
        }

        return feature_vector


    def create_immutable_snapshot(self, fixture: Fixture, feature_vector: Dict[str, Any]) -> FeatureSnapshot:
        vector_str = json.dumps(feature_vector, sort_keys=True)
        vector_hash = hashlib.sha256(vector_str.encode("utf-8")).hexdigest()

        snapshot = FeatureSnapshot(
            fixture_id=fixture.id,
            as_of_timestamp=fixture.kickoff_datetime,
            feature_vector=feature_vector,
            hash=vector_hash
        )
        self.session.add(snapshot)
        self.session.flush()
        return snapshot


    def _calculate_team_rolling_stats(self, team_id: int, matches: List[Fixture]) -> Dict[str, float]:
        if not matches:
            return {
                "form_5": 1.0,  # Default neutral form (1 pt/game)
                "goals_scored_avg_5": 1.0,
                "goals_conceded_avg_5": 1.0,
                "win_ratio_10": 0.33
            }

        last_5 = matches[:5]
        points = 0
        scored = 0
        conceded = 0

        for m in last_5:
            is_home = (m.home_team_id == team_id)
            team_score = m.home_score if is_home else m.away_score
            opp_score = m.away_score if is_home else m.home_score

            scored += team_score or 0
            conceded += opp_score or 0

            if team_score > opp_score:
                points += 3
            elif team_score == opp_score:
                points += 1

        n_5 = max(len(last_5), 1)

        # 10-match win ratio
        last_10 = matches[:10]
        wins = 0
        for m in last_10:
            is_home = (m.home_team_id == team_id)
            team_score = m.home_score if is_home else m.away_score
            opp_score = m.away_score if is_home else m.home_score
            if team_score > opp_score:
                wins += 1

        n_10 = max(len(last_10), 1)

        return {
            "form_5": points / n_5,
            "goals_scored_avg_5": scored / n_5,
            "goals_conceded_avg_5": conceded / n_5,
            "win_ratio_10": wins / n_10
        }

    def _calculate_rest_days(self, target_time: datetime.datetime, matches: List[Fixture]) -> float:
        if not matches:
            return 7.0  # Default standard 7 days rest
        last_match_time = matches[0].kickoff_datetime
        diff = (target_time - last_match_time).total_seconds() / 86400.0
        return min(max(diff, 1.0), 21.0)  # Cap between 1 and 21 days

    def _calculate_h2h_stats(self, home_id: int, away_id: int, h2h_matches: List[Fixture]) -> Dict[str, float]:
        if not h2h_matches:
            return {
                "h2h_count": 0.0,
                "h2h_home_win_ratio": 0.33,
                "h2h_away_win_ratio": 0.33,
                "h2h_draw_ratio": 0.33,
                "h2h_avg_goal_diff": 0.0,
                "h2h_dominance_home": 0.0
            }

        n = len(h2h_matches)
        home_wins = 0
        away_wins = 0
        draws = 0
        total_goal_diff = 0

        for m in h2h_matches:
            is_home = (m.home_team_id == home_id)
            h_s = m.home_score if is_home else m.away_score
            a_s = m.away_score if is_home else m.home_score

            h_s = h_s or 0
            a_s = a_s or 0

            diff = h_s - a_s
            total_goal_diff += diff

            if diff > 0:
                home_wins += 1
            elif diff < 0:
                away_wins += 1
            else:
                draws += 1

        h_ratio = home_wins / n
        a_ratio = away_wins / n
        d_ratio = draws / n
        avg_diff = total_goal_diff / n

        # Home dominance metric: range [-1.0, 1.0]
        dominance = h_ratio - a_ratio

        return {
            "h2h_count": float(n),
            "h2h_home_win_ratio": round(h_ratio, 3),
            "h2h_away_win_ratio": round(a_ratio, 3),
            "h2h_draw_ratio": round(d_ratio, 3),
            "h2h_avg_goal_diff": round(avg_diff, 3),
            "h2h_dominance_home": round(dominance, 3)
        }

    def _calculate_longterm_structural_stats(self, team_id: int, matches: List[Fixture]) -> Dict[str, float]:
        if not matches:
            return {
                "ppg_15": 1.0,
                "goal_ratio_15": 1.0
            }

        last_15 = matches[:15]
        n = max(len(last_15), 1)

        points = 0
        scored = 0
        conceded = 0

        for m in last_15:
            is_home = (m.home_team_id == team_id)
            team_score = m.home_score if is_home else m.away_score
            opp_score = m.away_score if is_home else m.home_score

            s = team_score or 0
            c = opp_score or 0

            scored += s
            conceded += c

            if s > c:
                points += 3
            elif s == c:
                points += 1

        ppg = points / n
        goal_ratio = (scored + 1.0) / (conceded + 1.0)  # Laplace smoothed ratio

        return {
            "ppg_15": round(ppg, 3),
            "goal_ratio_15": round(goal_ratio, 3)
        }

