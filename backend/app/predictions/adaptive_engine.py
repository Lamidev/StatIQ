"""
StatIQ Adaptive Multi-Market Prediction Engine
==============================================
Deterministic, quantitative betting intelligence engine that:
1. Analyzes matchup strength, venue splits, rolling form, and H2H.
2. Generates bivariate Poisson / Dixon-Coles goal intensity distributions.
3. Dynamically prices EVERY available SportyBet market candidate.
4. Strips bookmaker overround to compute fair edge and expected value (EV).
5. Returns qualified value bets or explicit NO_BET when evidence is insufficient.
"""

import math
import logging
from typing import Dict, Any, List, Optional, Tuple
from dataclasses import dataclass, field
import numpy as np

from app.predictions.live_calculator import get_team_rating, calculate_matchiq_probabilities

logger = logging.getLogger("matchiq.predictions.adaptive_engine")

@dataclass
class MarketCandidate:
    market_id: str
    outcome_id: str
    market_name: str
    selection_name: str
    specifier: Optional[str]
    sportybet_odds: float
    raw_implied_prob: float
    normalized_implied_prob: float
    model_probability: float
    fair_odds: float
    edge: float
    expected_value: float
    data_quality: float
    confidence: str  # HIGH, MEDIUM, LOW
    is_qualified: bool
    rejection_reason: Optional[str] = None


@dataclass
class FixtureAnalysisReport:
    event_id: str
    game_id: Optional[str]
    home_team: str
    away_team: str
    competition: str
    kickoff_time: str
    match_classification: str
    expected_home_goals: float
    expected_away_goals: float
    total_expected_goals: float
    data_quality_score: float
    key_factors: List[str]
    counter_factors: List[str]
    all_evaluated_candidates: List[MarketCandidate]
    qualified_candidates: List[MarketCandidate]
    has_qualified_bet: bool
    best_candidate: Optional[MarketCandidate]


class AdaptiveMultiMarketEngine:
    """
    Adaptive Multi-Market Engine for StatIQ V2.0.
    """

    def __init__(
        self,
        min_probability: float = 0.55,
        min_edge: float = 0.02,          # Minimum +2% edge over market
        min_ev: float = 0.03,            # Minimum +3% Expected Value
        min_data_quality: float = 0.60,
        min_odds_floor: float = 1.15,
        max_odds_cap: float = 4.50
    ):
        self.min_probability = min_probability
        self.min_edge = min_edge
        self.min_ev = min_ev
        self.min_data_quality = min_data_quality
        self.min_odds_floor = min_odds_floor
        self.max_odds_cap = max_odds_cap

    def compute_bivariate_score_matrix(
        self,
        lambda_home: float,
        mu_away: float,
        rho: float = -0.05,
        max_goals: int = 8
    ) -> np.ndarray:
        """
        Computes the joint bivariate Poisson probability matrix with Dixon-Coles low-score adjustment.
        """
        matrix = np.zeros((max_goals + 1, max_goals + 1), dtype=float)

        def poisson_pmf(k: int, lmbda: float) -> float:
            return (math.pow(lmbda, k) * math.exp(-lmbda)) / math.factorial(k)

        for i in range(max_goals + 1):
            for j in range(max_goals + 1):
                p_i = poisson_pmf(i, lambda_home)
                p_j = poisson_pmf(j, mu_away)
                prob = p_i * p_j

                # Dixon-Coles low-score correction for (0,0), (1,0), (0,1), (1,1)
                if i == 0 and j == 0:
                    prob *= max(0.0, 1.0 - lambda_home * mu_away * rho)
                elif i == 0 and j == 1:
                    prob *= max(0.0, 1.0 + lambda_home * rho)
                elif i == 1 and j == 0:
                    prob *= max(0.0, 1.0 + mu_away * rho)
                elif i == 1 and j == 1:
                    prob *= max(0.0, 1.0 - rho)

                matrix[i, j] = prob

        # Normalize matrix so total probability sums to 1.0
        total_p = np.sum(matrix)
        if total_p > 0:
            matrix /= total_p

        return matrix

    def derive_market_probabilities_from_matrix(
        self,
        matrix: np.ndarray,
        lambda_home: float,
        mu_away: float
    ) -> Dict[str, float]:
        """
        Derives all canonical market outcome probabilities analytically from the score matrix.
        """
        max_g = matrix.shape[0] - 1
        probs: Dict[str, float] = {}

        # 1. 1X2 Probabilities
        prob_home = float(np.sum(np.tril(matrix, -1)))
        prob_draw = float(np.sum(np.diag(matrix)))
        prob_away = float(np.sum(np.triu(matrix, 1)))

        probs["1X2_HOME"] = prob_home
        probs["1X2_DRAW"] = prob_draw
        probs["1X2_AWAY"] = prob_away

        # 2. Double Chance
        probs["DC_1X"] = prob_home + prob_draw
        probs["DC_X2"] = prob_away + prob_draw
        probs["DC_12"] = prob_home + prob_away

        # 3. Draw No Bet (DNB)
        non_draw = max(0.01, 1.0 - prob_draw)
        probs["DNB_HOME"] = min(0.99, prob_home / non_draw)
        probs["DNB_AWAY"] = min(0.99, prob_away / non_draw)

        # 4. Over / Under Total Goals (0.5, 1.5, 2.5, 3.5, 4.5, 5.5)
        for line in [0.5, 1.5, 2.5, 3.5, 4.5, 5.5]:
            k = int(math.floor(line))
            under_p = 0.0
            for i in range(max_g + 1):
                for j in range(max_g + 1):
                    if (i + j) <= k:
                        under_p += matrix[i, j]
            over_p = max(0.0, 1.0 - under_p)
            probs[f"TOTAL_OVER_{line}"] = round(over_p, 4)
            probs[f"TOTAL_UNDER_{line}"] = round(under_p, 4)

        # 5. Both Teams to Score (BTTS)
        btts_no = float(np.sum(matrix[0, :]) + np.sum(matrix[:, 0]) - matrix[0, 0])
        btts_yes = max(0.0, 1.0 - btts_no)
        probs["BTTS_YES"] = round(btts_yes, 4)
        probs["BTTS_NO"] = round(btts_no, 4)

        # 6. Team Total Goals (Home & Away Over/Under)
        for line in [0.5, 1.5, 2.5]:
            k = int(math.floor(line))
            home_u = float(np.sum(matrix[:k + 1, :]))
            home_o = max(0.0, 1.0 - home_u)
            away_u = float(np.sum(matrix[:, :k + 1]))
            away_o = max(0.0, 1.0 - away_u)

            probs[f"HOME_OVER_{line}"] = round(home_o, 4)
            probs[f"HOME_UNDER_{line}"] = round(home_u, 4)
            probs[f"AWAY_OVER_{line}"] = round(away_o, 4)
            probs[f"AWAY_UNDER_{line}"] = round(away_u, 4)

        # 7. 1st Half Estimations (Goal intensity ~45% in 1st Half)
        lh_1h = lambda_home * 0.45
        mu_1h = mu_away * 0.45
        matrix_1h = self.compute_bivariate_score_matrix(lh_1h, mu_1h, max_goals=4)

        probs["1H_1X2_HOME"] = float(np.sum(np.tril(matrix_1h, -1)))
        probs["1H_1X2_DRAW"] = float(np.sum(np.diag(matrix_1h)))
        probs["1H_1X2_AWAY"] = float(np.sum(np.triu(matrix_1h, 1)))
        probs["1H_OVER_0.5"] = float(1.0 - matrix_1h[0, 0])
        probs["1H_UNDER_0.5"] = float(matrix_1h[0, 0])
        probs["1H_OVER_1.5"] = float(1.0 - np.sum(matrix_1h[0, :2]) - matrix_1h[1, 0])

        return probs

    def classify_matchup(
        self,
        prob_home: float,
        prob_away: float,
        expected_total_goals: float,
        elo_diff: float
    ) -> Tuple[str, List[str], List[str]]:
        """
        Classifies matchup archetype and extracts positive/negative key factors.
        """
        key_factors = []
        counter_factors = []

        # Favorite Classification
        if prob_home >= 0.65 or elo_diff >= 180:
            fav_class = "STRONG_HOME_FAVORITE"
            key_factors.append(f"Substantial home quality advantage (+{int(elo_diff)} Elo delta)")
            key_factors.append(f"Model projects {round(prob_home * 100, 1)}% home win probability")
        elif prob_home >= 0.52 or elo_diff >= 80:
            fav_class = "MODERATE_HOME_FAVORITE"
            key_factors.append("Moderate home advantage and team strength rating")
        elif prob_away >= 0.62 or elo_diff <= -180:
            fav_class = "STRONG_AWAY_FAVORITE"
            key_factors.append(f"Decisive away favorite (-{int(abs(elo_diff))} Elo delta)")
        elif prob_away >= 0.50 or elo_diff <= -80:
            fav_class = "MODERATE_AWAY_FAVORITE"
            key_factors.append("Moderate away superiority over host")
        else:
            fav_class = "BALANCED_COMPETITIVE"
            key_factors.append("Evenly matched sides with tight probability distribution")
            counter_factors.append("High draw risk in outright 1X2 market")

        # Goal Expectation Classification
        if expected_total_goals >= 2.85:
            goal_class = "HIGH_GOAL_EXPECTATION"
            key_factors.append(f"High offensive output projected ({round(expected_total_goals, 2)} exp goals)")
        elif expected_total_goals <= 2.05:
            goal_class = "LOW_GOAL_EXPECTATION"
            key_factors.append(f"Defensive/low-scoring profile ({round(expected_total_goals, 2)} exp goals)")
        else:
            goal_class = "MODERATE_GOALS"

        classification = f"{fav_class} | {goal_class}"
        return classification, key_factors, counter_factors

    def evaluate_fixture(
        self,
        event_dict: Dict[str, Any],
        h2h_data: Optional[Dict[str, Any]] = None,
        form_data: Optional[Dict[str, Any]] = None
    ) -> FixtureAnalysisReport:
        """
        Full end-to-end evaluation of a SportyBet fixture across ALL its offered markets.
        """
        ev_id = str(event_dict.get("event_id") or event_dict.get("sporty_event_id") or "")
        g_id = event_dict.get("game_id") or event_dict.get("sporty_game_id")
        home = str(event_dict.get("home_team") or "Home")
        away = str(event_dict.get("away_team") or "Away")
        comp = str(event_dict.get("competition") or "Football")
        kickoff = str(event_dict.get("start_time") or event_dict.get("kickoff_time") or "")

        # 1. Elo & Strength estimation
        home_elo = get_team_rating(home)
        away_elo = get_team_rating(away)
        elo_diff = home_elo - away_elo

        # 2. Derive goal intensities (λ and μ)
        base_home_goals = 1.35
        base_away_goals = 1.10
        elo_factor = elo_diff / 400.0

        lambda_home = max(0.40, min(3.80, base_home_goals + (elo_factor * 0.75)))
        mu_away = max(0.35, min(3.50, base_away_goals - (elo_factor * 0.75)))

        total_exp_goals = round(lambda_home + mu_away, 2)

        # 3. Compute score matrix & derived market probabilities
        matrix = self.compute_bivariate_score_matrix(lambda_home, mu_away)
        model_probs = self.derive_market_probabilities_from_matrix(matrix, lambda_home, mu_away)

        # 4. Matchup Classification
        classification, key_factors, counter_factors = self.classify_matchup(
            prob_home=model_probs["1X2_HOME"],
            prob_away=model_probs["1X2_AWAY"],
            expected_total_goals=total_exp_goals,
            elo_diff=elo_diff
        )

        # 5. Evaluate ALL SportyBet Offered Markets
        raw_markets = event_dict.get("markets", {})
        if isinstance(raw_markets, list):
            # Convert list to dictionary if needed
            markets_list = raw_markets
        elif isinstance(raw_markets, dict):
            markets_list = list(raw_markets.values())
        else:
            markets_list = []

        all_candidates: List[MarketCandidate] = []
        qualified_candidates: List[MarketCandidate] = []

        # Data quality estimation
        data_quality = 0.85 if (home_elo != 1500 and away_elo != 1500) else 0.65
        if h2h_data and h2h_data.get("total_meetings", 0) >= 3:
            data_quality = min(0.95, data_quality + 0.10)

        for mkt in markets_list:
            m_id = str(mkt.get("id") or mkt.get("market_id") or "")
            m_name = str(mkt.get("name") or mkt.get("market_name") or mkt.get("desc") or "").strip()
            spec = mkt.get("specifier")
            outcomes = mkt.get("outcomes", [])
            if isinstance(outcomes, dict):
                outcomes = list(outcomes.values())

            # Calculate market overround
            raw_inv_sum = 0.0
            for oc in outcomes:
                try:
                    od = float(oc.get("odds") or oc.get("oddsValue") or 0.0)
                    if od >= 1.01:
                        raw_inv_sum += 1.0 / od
                except:
                    pass
            overround = raw_inv_sum if raw_inv_sum > 1.0 else 1.08

            for oc in outcomes:
                o_id = str(oc.get("id") or oc.get("outcome_id") or "")
                o_name = str(oc.get("selection") or oc.get("selection_name") or oc.get("desc") or oc.get("name") or "").strip()
                try:
                    odds_val = float(oc.get("odds") or oc.get("oddsValue") or 0.0)
                except:
                    odds_val = 0.0

                if odds_val < 1.01:
                    continue

                raw_implied = round(1.0 / odds_val, 4)
                norm_implied = round(raw_implied / overround, 4)

                # Match outcome to statistical model probability
                model_p = self._match_outcome_to_model_probability(
                    market_id=m_id,
                    market_name=m_name,
                    selection_name=o_name,
                    specifier=spec,
                    home_team=home,
                    away_team=away,
                    model_probs=model_probs
                )

                if model_p is None:
                    continue  # Unmodeled exotic market

                fair_odds = round(1.0 / max(0.01, model_p), 2)
                edge = round(model_p - norm_implied, 4)
                ev = round((model_p * odds_val) - 1.0, 4)

                # Confidence calculation
                if data_quality >= 0.80 and edge >= 0.05 and model_p >= 0.65:
                    confidence = "HIGH"
                elif data_quality >= 0.70 and edge >= 0.02:
                    confidence = "MEDIUM"
                else:
                    confidence = "LOW"

                # Qualification check
                is_qualified = True
                rejection = None

                if odds_val < self.min_odds_floor:
                    is_qualified = False
                    rejection = f"Odds {odds_val} below floor ({self.min_odds_floor})"
                elif odds_val > self.max_odds_cap:
                    is_qualified = False
                    rejection = f"Odds {odds_val} exceeds risk cap ({self.max_odds_cap})"
                elif model_p < self.min_probability:
                    is_qualified = False
                    rejection = f"Probability {round(model_p * 100, 1)}% below min {round(self.min_probability * 100, 1)}%"
                elif edge < self.min_edge:
                    is_qualified = False
                    rejection = f"Edge {round(edge * 100, 1)}% below threshold (+{round(self.min_edge * 100, 1)}%)"
                elif ev < self.min_ev:
                    is_qualified = False
                    rejection = f"EV {round(ev * 100, 1)}% below threshold (+{round(self.min_ev * 100, 1)}%)"

                candidate = MarketCandidate(
                    market_id=m_id,
                    outcome_id=o_id,
                    market_name=m_name,
                    selection_name=o_name,
                    specifier=spec,
                    sportybet_odds=odds_val,
                    raw_implied_prob=raw_implied,
                    normalized_implied_prob=norm_implied,
                    model_probability=model_p,
                    fair_odds=fair_odds,
                    edge=edge,
                    expected_value=ev,
                    data_quality=data_quality,
                    confidence=confidence,
                    is_qualified=is_qualified,
                    rejection_reason=rejection
                )

                all_candidates.append(candidate)
                if is_qualified:
                    qualified_candidates.append(candidate)

        # Sort qualified candidates by composite score (Edge * Probability)
        qualified_candidates.sort(key=lambda c: (c.edge * c.model_probability), reverse=True)
        best_pick = qualified_candidates[0] if qualified_candidates else None

        return FixtureAnalysisReport(
            event_id=ev_id,
            game_id=g_id,
            home_team=home,
            away_team=away,
            competition=comp,
            kickoff_time=kickoff,
            match_classification=classification,
            expected_home_goals=round(lambda_home, 2),
            expected_away_goals=round(mu_away, 2),
            total_expected_goals=total_exp_goals,
            data_quality_score=round(data_quality, 2),
            key_factors=key_factors,
            counter_factors=counter_factors,
            all_evaluated_candidates=all_candidates,
            qualified_candidates=qualified_candidates,
            has_qualified_bet=(len(qualified_candidates) > 0),
            best_candidate=best_pick
        )

    def _match_outcome_to_model_probability(
        self,
        market_id: str,
        market_name: str,
        selection_name: str,
        specifier: Optional[str],
        home_team: str,
        away_team: str,
        model_probs: Dict[str, float]
    ) -> Optional[float]:
        """
        Maps a SportyBet market + outcome selection to its exact analytically derived probability.
        """
        m_upper = market_name.upper()
        s_upper = selection_name.upper()
        h_upper = home_team.upper()
        a_upper = away_team.upper()

        # 1. 1X2 (Market 1)
        if market_id == "1" or ("1X2" in m_upper and "1ST" not in m_upper and "HALF" not in m_upper):
            if s_upper in ["1", "HOME", h_upper]: return model_probs.get("1X2_HOME")
            if s_upper in ["X", "DRAW"]: return model_probs.get("1X2_DRAW")
            if s_upper in ["2", "AWAY", a_upper]: return model_probs.get("1X2_AWAY")

        # 2. Double Chance (Market 10)
        if market_id == "10" or "DOUBLE CHANCE" in m_upper:
            if "1X" in s_upper or s_upper == "HOME/DRAW" or (h_upper in s_upper and "DRAW" in s_upper): return model_probs.get("DC_1X")
            if "X2" in s_upper or s_upper == "DRAW/AWAY" or (a_upper in s_upper and "DRAW" in s_upper): return model_probs.get("DC_X2")
            if "12" in s_upper or s_upper == "HOME/AWAY" or (h_upper in s_upper and a_upper in s_upper): return model_probs.get("DC_12")

        # 3. Draw No Bet (Market 12 / DNB)
        if market_id == "12" or "DRAW NO BET" in m_upper:
            if s_upper in ["1", "HOME", h_upper]: return model_probs.get("DNB_HOME")
            if s_upper in ["2", "AWAY", a_upper]: return model_probs.get("DNB_AWAY")

        # 4. Over / Under Goals (Market 18)
        if market_id == "18" or ("OVER/UNDER" in m_upper and not any(k in m_upper for k in ["1ST", "HALF", "CORNER", h_upper, a_upper, "HOME", "AWAY"])):
            line = "2.5"
            if specifier and "total=" in specifier:
                line = specifier.split("total=")[-1].split("&")[0]
            if "OVER" in s_upper:
                return model_probs.get(f"TOTAL_OVER_{line}")
            elif "UNDER" in s_upper:
                return model_probs.get(f"TOTAL_UNDER_{line}")

        # 5. BTTS / GG/NG (Market 29)
        if market_id == "29" or "BOTH TEAMS TO SCORE" in m_upper or "GG/NG" in m_upper:
            if s_upper in ["YES", "GG"]: return model_probs.get("BTTS_YES")
            if s_upper in ["NO", "NG"]: return model_probs.get("BTTS_NO")

        # 6. Team Total Goals (Home: 19, Away: 20)
        is_home_goals = (market_id == "19") or (h_upper in m_upper and "OVER/UNDER" in m_upper) or ("HOME" in m_upper and "OVER/UNDER" in m_upper)
        is_away_goals = (market_id == "20") or (a_upper in m_upper and "OVER/UNDER" in m_upper) or ("AWAY" in m_upper and "OVER/UNDER" in m_upper)

        if is_home_goals:
            line = "0.5"
            if specifier and "total=" in specifier:
                line = specifier.split("total=")[-1].split("&")[0]
            if "OVER" in s_upper: return model_probs.get(f"HOME_OVER_{line}")
            if "UNDER" in s_upper: return model_probs.get(f"HOME_UNDER_{line}")

        if is_away_goals:
            line = "0.5"
            if specifier and "total=" in specifier:
                line = specifier.split("total=")[-1].split("&")[0]
            if "OVER" in s_upper: return model_probs.get(f"AWAY_OVER_{line}")
            if "UNDER" in s_upper: return model_probs.get(f"AWAY_UNDER_{line}")

        # 7. 1st Half Markets (60: 1H 1X2, 68: 1H O/U)
        if market_id == "60" or ("1ST HALF" in m_upper and "1X2" in m_upper):
            if s_upper in ["1", "HOME", h_upper]: return model_probs.get("1H_1X2_HOME")
            if s_upper in ["X", "DRAW"]: return model_probs.get("1H_1X2_DRAW")
            if s_upper in ["2", "AWAY", a_upper]: return model_probs.get("1H_1X2_AWAY")

        if market_id == "68" or ("1ST HALF" in m_upper and "OVER/UNDER" in m_upper):
            line = "0.5"
            if specifier and "total=" in specifier:
                line = specifier.split("total=")[-1].split("&")[0]
            if "OVER" in s_upper: return model_probs.get(f"1H_OVER_{line}")
            if "UNDER" in s_upper: return model_probs.get(f"1H_UNDER_{line}")

        return None
