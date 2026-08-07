import datetime
import math
import uuid
import numpy as np
from dataclasses import dataclass, field
from typing import List, Dict, Any, Optional, Tuple
from sqlalchemy import select, and_


from app.db.models import Fixture, LivePredictionLedger, MarketOdds, ScenarioAnalysis, ScenarioAnalysisItem

@dataclass
class ScenarioRequest:
    fixture_ids: List[int] = field(default_factory=list)
    target_combined_value: Optional[float] = None
    tolerance: float = 0.15
    minimum_probability: float = 0.60
    minimum_confidence: float = 0.60
    minimum_edge: float = 0.0
    minimum_legs: int = 1
    maximum_legs: int = 4
    competitions: List[str] = field(default_factory=list)
    markets: List[str] = field(default_factory=list)
    allow_same_fixture_multiple_markets: bool = False

@dataclass
class SelectionCandidate:
    fixture_id: int
    competition_code: str
    home_team_id: int
    away_team_id: int
    kickoff_datetime: datetime.datetime
    market_type: str            # 1X2, OVER_UNDER, BTTS
    market_line: Optional[float] # 2.5
    selection: str              # HOME, DRAW, AWAY, OVER, UNDER, YES, NO
    model_probability: float
    confidence: float
    implied_probability: Optional[float] = None
    model_edge: Optional[float] = None
    prediction_id: Optional[int] = None
    model_version: str = "Weighted_Ensemble_v1.0.0"

class ScenarioBuilderEngine:
    """
    Phase 10 Target Probability & Scenario Builder Engine.
    Generates candidate multi-match scenarios under strict model probability preservation.
    
    Core Rules:
    - Downstream consumption only: NEVER alters model probabilities.
    - Fixture independence constraint (allow_same_fixture_multiple_markets = False by default).
    - Correlation protection: Joint probability stored as naive 'independence_assumption'.
    - Bounded Beam Search to prevent combinatorial explosion.
    - Model quality ranking (joint prob, min prob, avg prob, edge), not target proximity.
    """
    def __init__(self, session):
        self.session = session

    def get_candidate_pool(self, request: ScenarioRequest) -> List[SelectionCandidate]:
        """
        Retrieves and pre-filters eligible SelectionCandidates strictly from live predictions.
        """
        stmt = (
            select(LivePredictionLedger, Fixture)
            .join(Fixture, LivePredictionLedger.fixture_id == Fixture.id)
            .where(LivePredictionLedger.status == "PENDING")
        )
        if request.fixture_ids:
            stmt = stmt.where(Fixture.id.in_(request.fixture_ids))
        if request.competitions:
            stmt = stmt.where(Fixture.competition_code.in_(request.competitions))

        results = self.session.execute(stmt).all()
        candidates = []

        for pred, fix in results:
            # Map predictions
            raw_options = [
                ("1X2", None, "HOME", pred.prob_home),
                ("1X2", None, "DRAW", pred.prob_draw),
                ("1X2", None, "AWAY", pred.prob_away),
                ("OVER_UNDER", 1.5, "OVER", pred.prob_over_1_5 or 0.0),
                ("OVER_UNDER", 2.5, "OVER", pred.prob_over_2_5 or 0.0),
                ("BTTS", None, "YES", pred.prob_btts_yes or 0.0),
                ("BTTS", None, "NO", 1.0 - (pred.prob_btts_yes or 0.5))
            ]

            fixture_candidates = []
            for mkt_type, line, sel, p_val in raw_options:
                if request.markets and mkt_type not in request.markets:
                    continue

                if p_val >= request.minimum_probability and p_val >= request.minimum_confidence:
                    cand = SelectionCandidate(
                        fixture_id=fix.id,
                        competition_code=fix.competition_code,
                        home_team_id=fix.home_team_id,
                        away_team_id=fix.away_team_id,
                        kickoff_datetime=fix.kickoff_datetime,
                        market_type=mkt_type,
                        market_line=line,
                        selection=sel,
                        model_probability=p_val,
                        confidence=p_val,
                        prediction_id=pred.id,
                        model_version=pred.model_version
                    )
                    fixture_candidates.append(cand)

            # Pre-filter max 1 candidate per fixture by default to prevent intra-fixture correlation
            if not request.allow_same_fixture_multiple_markets and fixture_candidates:
                fixture_candidates.sort(key=lambda c: c.model_probability, reverse=True)
                candidates.append(fixture_candidates[0])
            else:
                candidates.extend(fixture_candidates)

        return candidates

    def build_scenarios(self, request: ScenarioRequest) -> Dict[str, Any]:
        """
        Executes bounded beam search combination generation and quality ranking.
        """
        candidates = self.get_candidate_pool(request)
        if not candidates:
            return {
                "request_id": f"req_{uuid.uuid4().hex[:8]}",
                "candidate_pool_size": 0,
                "scenarios": [],
                "status": "ZERO_CANDIDATES"
            }

        # Sort candidate pool by probability
        candidates.sort(key=lambda c: c.model_probability, reverse=True)

        # Beam search for multi-leg combinations
        beam_width = 50
        beam = [[c] for c in candidates]

        all_combos: List[List[SelectionCandidate]] = []
        
        # Add single leg candidates if within range
        if request.minimum_legs <= 1 <= request.maximum_legs:
            all_combos.extend([[c] for c in candidates])

        current_level = beam
        for leg in range(2, request.maximum_legs + 1):
            next_level = []
            for combo in current_level:
                combo_fixture_ids = {c.fixture_id for c in combo}
                for c in candidates:
                    if not request.allow_same_fixture_multiple_markets and c.fixture_id in combo_fixture_ids:
                        continue
                    # Canonical ordering to prevent duplicate sets
                    if c.fixture_id > combo[-1].fixture_id:
                        new_combo = combo + [c]
                        next_level.append(new_combo)

            # Sort next level by joint probability
            next_level.sort(key=lambda combo: np.prod([c.model_probability for c in combo]), reverse=True)
            current_level = next_level[:beam_width]

            if leg >= request.minimum_legs:
                all_combos.extend(current_level)

        # Build output scenarios
        scenarios_out = []
        req_id = f"scenario_{uuid.uuid4().hex[:8]}"

        # Create database analysis record
        db_analysis = ScenarioAnalysis(
            scenario_id=req_id,
            model_version="Weighted_Ensemble_v1.0.0",
            request_parameters={
                "min_prob": request.minimum_probability,
                "min_legs": request.minimum_legs,
                "max_legs": request.maximum_legs
            },
            scenario_count=len(all_combos),
            status="COMPLETED"
        )
        self.session.add(db_analysis)
        self.session.flush()

        for idx, combo in enumerate(all_combos[:30]):
            group_id = f"SCN_{idx+1:03d}"
            probs = [c.model_probability for c in combo]
            joint_p = float(np.prod(probs))
            avg_p = float(np.mean(probs))
            min_p = float(np.min(probs))

            scenario_item_list = []
            for c in combo:
                item_db = ScenarioAnalysisItem(
                    scenario_analysis_id=db_analysis.id,
                    scenario_item_group_id=group_id,
                    fixture_id=c.fixture_id,
                    prediction_id=c.prediction_id,
                    market_type=c.market_type,
                    market_line=c.market_line,
                    selection=c.selection,
                    model_probability=c.model_probability
                )
                self.session.add(item_db)
                scenario_item_list.append({
                    "fixture_id": c.fixture_id,
                    "competition_code": c.competition_code,
                    "market_type": c.market_type,
                    "market_line": c.market_line,
                    "selection": c.selection,
                    "model_probability": round(c.model_probability, 4)
                })

            scenarios_out.append({
                "scenario_id": group_id,
                "leg_count": len(combo),
                "selections": scenario_item_list,
                "independence_assumption_probability": round(joint_p, 4),
                "average_probability": round(avg_p, 4),
                "minimum_probability": round(min_p, 4)
            })

        # Rank primarily by model quality (joint_p descending, min_p descending)
        scenarios_out.sort(key=lambda s: (s["independence_assumption_probability"], s["minimum_probability"]), reverse=True)
        self.session.commit()

        return {
            "request_id": req_id,
            "candidate_pool_size": len(candidates),
            "total_scenarios_generated": len(all_combos),
            "scenarios": scenarios_out
        }
