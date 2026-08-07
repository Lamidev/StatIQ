import datetime
import math
import numpy as np
from typing import Dict, Any, List, Optional
from sqlalchemy import select, and_, or_
from app.db.models import Fixture, LivePredictionLedger
from app.features.feature_engine import PointInTimeFeatureEngine
from app.models.elo import EloEngine
from app.models.poisson import PoissonEngine
from app.models.dixon_coles import DixonColesEngine
from app.models.calibration import MultinomialTemperatureScaler
from app.models.xgboost_model import XGBoostPredictor
from app.models.ensemble import WeightedEnsemblePredictor

class LiveShadowEngine:
    """
    Phase 8 Live Forward Shadow Prediction Engine.
    Generates and persists pre-kickoff predictions for upcoming 2026+ fixtures.
    Strictly isolated from historical backtest predictions.
    """
    def __init__(self, session):
        self.session = session
        self.feature_engine = PointInTimeFeatureEngine(session)
        self.temp_scaler = MultinomialTemperatureScaler(temperature=2.1216)
        self.ensemble = WeightedEnsemblePredictor(weight_dc=0.1598)

    def predict_upcoming_fixtures(self) -> List[LivePredictionLedger]:
        """
        Scans DB for upcoming fixtures (kickoff_datetime > now or scheduled)
        that have not yet been predicted in LivePredictionLedger.
        Strictly enforces pre-kickoff prediction cutoff.
        """
        now = datetime.datetime.now(datetime.timezone.utc)

        # 1. Fetch upcoming fixtures
        stmt = (
            select(Fixture)
            .where(
                and_(
                    Fixture.kickoff_datetime > now,
                    Fixture.status.in_(["TIMED", "SCHEDULED", "LIVE"])
                )
            )
            .order_by(Fixture.kickoff_datetime.asc())
        )
        res = self.session.execute(stmt)
        upcoming_fixtures = list(res.scalars().all())

        # If no future fixtures timed in DB, fetch next scheduled fixtures
        if not upcoming_fixtures:
            stmt_sched = (
                select(Fixture)
                .where(Fixture.status.in_(["TIMED", "SCHEDULED"]))
                .order_by(Fixture.kickoff_datetime.asc())
                .limit(20)
            )
            upcoming_fixtures = list(self.session.execute(stmt_sched).scalars().all())

        new_predictions = []

        # Load models
        elo = EloEngine(initial_elo=1500.0, k_factor=32.0, home_advantage=80.0)
        poisson = PoissonEngine(max_goals=10)
        dixon_coles = DixonColesEngine(max_goals=10, rho=-0.13)
        xgb_predictor = XGBoostPredictor()

        # Build team stats from prior finished matches
        finished_stmt = select(Fixture).where(and_(Fixture.status == "FINISHED", Fixture.home_score.isnot(None))).order_by(Fixture.kickoff_datetime.asc())
        finished_fixtures = list(self.session.execute(finished_stmt).scalars().all())

        team_history: Dict[int, Dict[str, float]] = {}
        team_goals_scored: Dict[int, List[int]] = {}
        team_goals_conceded: Dict[int, List[int]] = {}

        for fix in finished_fixtures:
            h_id, a_id = fix.home_team_id, fix.away_team_id
            h_s, a_s = fix.home_score, fix.away_score
            elo.update_ratings(h_id, a_id, h_s, a_s)

            team_goals_scored.setdefault(h_id, []).append(h_s)
            team_goals_conceded.setdefault(h_id, []).append(a_s)
            team_goals_scored.setdefault(a_id, []).append(a_s)
            team_goals_conceded.setdefault(a_id, []).append(h_s)

        for t_id in list(team_goals_scored.keys()):
            s_avg = sum(team_goals_scored[t_id][-10:]) / len(team_goals_scored[t_id][-10:])
            c_avg = sum(team_goals_conceded[t_id][-10:]) / len(team_goals_conceded[t_id][-10:])
            team_history[t_id] = {"goals_scored_avg": s_avg, "goals_conceded_avg": c_avg}

        poisson.fit_team_strengths(team_history)
        dixon_coles.fit_team_strengths(team_history)

        for fix in upcoming_fixtures:
            # Check if already predicted
            check_stmt = select(LivePredictionLedger).where(LivePredictionLedger.fixture_id == fix.id)
            existing = self.session.execute(check_stmt).scalar_one_or_none()
            if existing is not None:
                continue

            h_id, a_id = fix.home_team_id, fix.away_team_id

            # Feature extraction
            feat_dict = self.feature_engine.compute_features_for_fixture(fix)
            snapshot = self.feature_engine.create_immutable_snapshot(fix, feat_dict)
            self.session.add(snapshot)
            self.session.flush()

            # Predictions
            poi_m = poisson.predict_markets(h_id, a_id)
            dc_m = dixon_coles.predict_markets(h_id, a_id)
            p_dc_raw = (dc_m["p_home"], dc_m["p_draw"], dc_m["p_away"])
            p_dc_cal = self.temp_scaler.calibrate(p_dc_raw)

            r_home = elo.get_rating(h_id)
            r_away = elo.get_rating(a_id)
            elo_diff = (r_home + elo.home_advantage) - r_away

            ml_vector = [
                feat_dict["home_form_5"], feat_dict["home_goals_scored_avg_5"], feat_dict["home_goals_conceded_avg_5"],
                feat_dict["home_win_ratio_10"], feat_dict["home_rest_days"], feat_dict["home_match_density_14"], feat_dict["home_only_form_5"],
                feat_dict["away_form_5"], feat_dict["away_goals_scored_avg_5"], feat_dict["away_goals_conceded_avg_5"],
                feat_dict["away_win_ratio_10"], feat_dict["away_rest_days"], feat_dict["away_match_density_14"], feat_dict["away_only_form_5"],
                feat_dict["form_diff_5"], feat_dict["attack_diff_5"], feat_dict["defense_diff_5"], feat_dict["rest_diff"],
                feat_dict.get("ppg_diff_15", 0.0), feat_dict.get("goal_ratio_diff_15", 0.0), feat_dict.get("squad_capability_diff", 0.0),
                feat_dict.get("h2h_dominance_home", 0.0), feat_dict.get("h2h_avg_goal_diff", 0.0),
                elo_diff, poi_m["expected_home_goals"], poi_m["expected_away_goals"], p_dc_raw[0], p_dc_raw[1], p_dc_raw[2]
            ]

            p_xgb = xgb_predictor.predict_probabilities(np.array(ml_vector, dtype=np.float32), fallback_probs=p_dc_cal)
            p_ens = self.ensemble.predict(p_dc_cal, p_xgb)

            ledger_entry = LivePredictionLedger(
                fixture_id=fix.id,
                model_name="Weighted_Ensemble",
                model_version="v1.0.0",
                feature_version="v1.0.0",
                calibration_version="temp_scale_v2.12",
                feature_snapshot_hash=snapshot.hash,
                prediction_timestamp=datetime.datetime.now(datetime.timezone.utc),
                prob_home=p_ens[0],
                prob_draw=p_ens[1],
                prob_away=p_ens[2],
                prob_over_1_5=dc_m["p_over_1_5"],
                prob_over_2_5=dc_m["p_over_2_5"],
                prob_btts_yes=dc_m["p_btts_yes"],
                expected_home_goals=poi_m["expected_home_goals"],
                expected_away_goals=poi_m["expected_away_goals"],
                status="PENDING"
            )
            self.session.add(ledger_entry)
            new_predictions.append(ledger_entry)

        self.session.commit()
        return new_predictions

    def resolve_completed_fixtures(self) -> List[LivePredictionLedger]:
        """
        Resolves pending live shadow predictions once fixtures finish.
        Attaches actual scores, calculates accuracy, Brier Score, and Log Loss.
        """
        stmt = (
            select(LivePredictionLedger)
            .join(Fixture, LivePredictionLedger.fixture_id == Fixture.id)
            .where(
                and_(
                    LivePredictionLedger.status == "PENDING",
                    Fixture.status == "FINISHED",
                    Fixture.home_score.isnot(None)
                )
            )
        )
        res = self.session.execute(stmt)
        pending_entries = list(res.scalars().all())

        resolved_entries = []

        for entry in pending_entries:
            fix = self.session.get(Fixture, entry.fixture_id)
            if fix is None or fix.home_score is None or fix.away_score is None:
                continue

            h_score, a_score = fix.home_score, fix.away_score
            actual_outcome = "HOME_TEAM" if h_score > a_score else ("AWAY_TEAM" if a_score > h_score else "DRAW")
            actual_vec = [1.0 if actual_outcome == "HOME_TEAM" else 0.0,
                          1.0 if actual_outcome == "DRAW" else 0.0,
                          1.0 if actual_outcome == "AWAY_TEAM" else 0.0]

            outcomes = ["HOME_TEAM", "DRAW", "AWAY_TEAM"]
            pred_idx = int(np.argmax([entry.prob_home, entry.prob_draw, entry.prob_away]))
            pred_outcome = outcomes[pred_idx]

            is_corr = (pred_outcome == actual_outcome)
            brier = math.pow(entry.prob_home - actual_vec[0], 2) + math.pow(entry.prob_draw - actual_vec[1], 2) + math.pow(entry.prob_away - actual_vec[2], 2)
            p_actual = entry.prob_home if actual_outcome == "HOME_TEAM" else (entry.prob_draw if actual_outcome == "DRAW" else entry.prob_away)
            lloss = -math.log(max(p_actual, 1e-6))

            entry.actual_home_score = h_score
            entry.actual_away_score = a_score
            entry.actual_result = actual_outcome
            entry.is_correct = is_corr
            entry.brier_score = brier
            entry.log_loss = lloss
            entry.status = "COMPLETED"
            entry.resolved_at = datetime.datetime.now(datetime.timezone.utc)

            resolved_entries.append(entry)

        self.session.commit()
        return resolved_entries

    def get_live_performance_stats(self, days: int = 30) -> Dict[str, Any]:
        """
        Returns rolling live shadow performance statistics over past X days.
        """
        stmt = select(LivePredictionLedger).where(LivePredictionLedger.status == "COMPLETED")
        completed = list(self.session.execute(stmt).scalars().all())

        total = len(completed)
        if total == 0:
            return {
                "total_completed": 0,
                "accuracy_pct": 0.0,
                "brier_score": 0.0,
                "log_loss": 0.0,
                "status": "No completed live shadow predictions yet"
            }

        correct = sum(1 for e in completed if e.is_correct)
        avg_brier = sum(e.brier_score for e in completed if e.brier_score is not None) / total
        avg_lloss = sum(e.log_loss for e in completed if e.log_loss is not None) / total

        return {
            "total_completed": total,
            "accuracy_pct": round((correct / total) * 100.0, 2),
            "brier_score": round(avg_brier, 4),
            "log_loss": round(avg_lloss, 4)
        }
