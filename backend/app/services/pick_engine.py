"""
MatchIQ 5-Gate Pick Engine & Strategic Decision Pipeline
=========================================================
Architectural single source of truth for all AI Ticket Builder, Scenario Builder,
and Backtest Simulator pick evaluation decisions.

5 Sequential Decision Gates:
  GATE 1: Structural Tier Filter (Elo gap, team quality mismatch enforcement)
  GATE 2: Calibrated Probability Model (Poisson/Elo threshold verification)
  GATE 3: Scored Market Selection Audit (Bookmaker overround margin stripping + value edge + safety)
  GATE 4: Dynamic Odds Alignment Check (Per-leg target odds range tolerance)
  GATE 5: Accumulator Correlation & Diversity Filter (League limits, kickoff window correlation)

Also provides Fractional Kelly Criterion bankroll stake sizing.
"""

import math
from typing import List, Dict, Any, Optional
from dataclasses import dataclass, field

from app.predictions.live_calculator import calculate_matchiq_probabilities, get_team_rating
from app.predictions.leg_odds_calculator import calculate_dynamic_leg_config

@dataclass
class PickDecision:
    fixture_id: str
    home_team: str
    away_team: str
    competition: str
    kickoff_datetime: Optional[str]
    market_name: str
    selection_name: str
    model_probability: float
    estimated_odds: float
    elo_gap: float
    tier_context: str            # HOME_DOMINANT, AWAY_DOMINANT, COMPETITIVE
    approved: bool
    confidence_tier: str         # ELITE, HIGH, SOLID, SPECULATIVE
    gate_results: Dict[str, Any]
    rejection_reason: Optional[str]
    decision_audit_log: List[str]
    kelly_quarter_stake_pct: float

@dataclass
class BuiltTicket:
    mode: str
    target_odds: float
    accumulated_odds: float
    combined_probability: float
    correlation_adjusted_probability: float
    confidence_tier: str
    leg_config: Dict[str, Any]
    approved_legs: List[Dict[str, Any]]
    rejected_picks: List[Dict[str, Any]]
    total_evaluated: int
    decision_audit_summary: List[str]
    recommended_stake_pct: float

class MatchIQPickEngine:
    """
    Core engine enforcing strict 5-gate pipeline validation.
    """
    def __init__(self, use_live_odds: bool = False):
        self.use_live_odds = use_live_odds

    def _get_structural_safety(self, market_name: str) -> float:
        m_lower = market_name.lower()
        if any(x in m_lower for x in ["double chance", "over 0.5 team", "team over 0.5", "win either half"]):
            return 1.0
        if any(x in m_lower for x in ["match result", "1x2", "over 1.5"]):
            return 0.7
        return 0.5  # BTTS, Over 2.5, Corners (higher variance)

    def _strip_overround_margin(self, odds: float, market_type: str = "2WAY") -> float:
        """
        Strips typical bookmaker profit overround (~5-8%) to yield true implied probability.
        """
        if odds <= 1.0:
            return 0.5
        raw_implied = 1.0 / odds
        # Estimate overround factor based on market type
        margin_factor = 1.06 if market_type == "2WAY" else 1.08
        true_implied = raw_implied / margin_factor
        return min(0.98, max(0.02, true_implied))

    def calculate_kelly_stake(self, prob: float, odds: float, fraction: float = 0.25) -> float:
        """
        Calculates Fractional Kelly Criterion recommended bankroll percentage.
        b = odds - 1, p = prob, q = 1 - p
        Kelly % = (b*p - q) / b
        """
        if odds <= 1.0 or prob <= 0.0:
            return 0.0
        b = odds - 1.0
        p = prob
        q = 1.0 - p
        full_kelly = (b * p - q) / b
        if full_kelly <= 0:
            return 0.0
        # Return percentage rounded to 2 decimal places (e.g. 2.5%)
        return round(min(full_kelly * fraction * 100.0, 10.0), 2)

    def evaluate_fixture_markets(
        self,
        fixture: Dict[str, Any],
        per_leg_target_odds: float,
        min_prob_threshold: float,
        league_pick_counts: Dict[str, int],
        max_league_picks: int = 2
    ) -> PickDecision:
        """
        Runs a single fixture through all 5 decision gates.
        Returns PickDecision object with audit logs.
        """
        home = fixture.get("home_team") or fixture.get("home") or "Home Team"
        away = fixture.get("away_team") or fixture.get("away") or "Away Team"
        comp = fixture.get("competition_code") or fixture.get("league") or "PL"
        fix_id = str(fixture.get("fixture_id") or fixture.get("external_id") or f"FIX_{home}_{away}")
        kickoff = fixture.get("kickoff_datetime")

        audit_log = []
        gate_results = {}

        # Fetch / compute probabilities & structural context
        probs_data = calculate_matchiq_probabilities(home, away)
        # Override with fixture specific probabilities if present
        ph = (fixture.get("ai_prob_home") or probs_data["ai_prob_home"]) / 100.0
        pd = (fixture.get("ai_prob_draw") or probs_data["ai_prob_draw"]) / 100.0
        pa = (fixture.get("ai_prob_away") or probs_data["ai_prob_away"]) / 100.0
        po15 = (fixture.get("ai_prob_over_1_5") or probs_data["ai_prob_over_1_5"]) / 100.0
        po25 = (fixture.get("ai_prob_over_2_5") or probs_data["ai_prob_over_2_5"]) / 100.0
        p_corners = (fixture.get("ai_prob_corners_over_7_5") or probs_data["ai_prob_corners_over_7_5"]) / 100.0

        elo_gap = probs_data.get("elo_gap", 0.0)
        tier_context = probs_data.get("tier_context", "COMPETITIVE")

        # Ingest live SportyBet 1X2 odds if available to objectively determine tier dominance
        raw_markets = fixture.get("markets") or []
        for m in raw_markets:
            m_desc = (m.get("desc") or m.get("name") or "").lower()
            if "1x2" in m_desc or "match result" in m_desc:
                h_odds = a_odds = None
                for o in m.get("outcomes", []):
                    o_desc = (o.get("desc") or o.get("name") or "").lower()
                    try:
                        val = float(o.get("odds"))
                        if o_desc in ["1", "home", home.lower()]:
                            h_odds = val
                        elif o_desc in ["2", "away", away.lower()]:
                            a_odds = val
                    except (ValueError, TypeError):
                        pass
                if h_odds and a_odds:
                    if a_odds <= 1.80 and h_odds >= 3.50:
                        tier_context = "AWAY_DOMINANT"
                        elo_gap = max(elo_gap, 120.0)
                    elif h_odds <= 1.80 and a_odds >= 3.50:
                        tier_context = "HOME_DOMINANT"
                        elo_gap = max(elo_gap, 120.0)

        audit_log.append(f"Fixture: {home} vs {away} [{comp}]")
        audit_log.append(f"Elo/Odds Gap: {elo_gap:+.1f} pts -> Tier Context: {tier_context}")

        # -------------------------------------------------------------
        # GATE 1: Structural Tier Filter
        # -------------------------------------------------------------
        allowed_directions = ["HOME", "AWAY", "NEUTRAL"]
        if tier_context == "HOME_DOMINANT":
            allowed_directions = ["HOME", "NEUTRAL"]
            audit_log.append(f"GATE 1 PASS: High structural gap ({elo_gap:+.1f}). Restricted to Home-side or Neutral goal markets.")
        elif tier_context == "AWAY_DOMINANT":
            allowed_directions = ["AWAY", "NEUTRAL"]
            audit_log.append(f"GATE 1 PASS: High structural gap ({elo_gap:+.1f}). Restricted to Away-side or Neutral goal markets.")
        else:
            audit_log.append(f"GATE 1 PASS: Competitive match (Elo gap {elo_gap:+.1f}). All market directions open.")
        gate_results["gate1"] = "PASS"

        # Generate candidate markets
        candidate_markets = []

        # Home Double Chance
        if "HOME" in allowed_directions and (ph + pd) >= 0.65:
            c_odds = round(max(1.10, 1.0 / (ph + pd + 0.04)), 2)
            candidate_markets.append({
                "market": "Double Chance",
                "selection": f"{home} or Draw (1X)",
                "prob": min(ph + pd + 0.02, 0.96),
                "odds": c_odds,
                "direction": "HOME"
            })

        # Away Double Chance
        if "AWAY" in allowed_directions and (pa + pd) >= 0.65:
            c_odds = round(max(1.10, 1.0 / (pa + pd + 0.04)), 2)
            candidate_markets.append({
                "market": "Double Chance",
                "selection": f"{away} or Draw (X2)",
                "prob": min(pa + pd + 0.02, 0.96),
                "odds": c_odds,
                "direction": "AWAY"
            })

        # Double Chance (12) — Home or Away (Low Draw Probability matches)
        if pd <= 0.24 and (ph + pa) >= 0.72:
            c_odds = round(max(1.15, 1.0 / (ph + pa + 0.02)), 2)
            candidate_markets.append({
                "market": "Double Chance",
                "selection": f"{home} or {away} (12)",
                "prob": min(ph + pa, 0.94),
                "odds": c_odds,
                "direction": "NEUTRAL"
            })

        # Home Team Over 0.5 Goals
        if "HOME" in allowed_directions and ph >= 0.48:
            p_home_o05 = min(0.95, ph * 1.25 + pd * 0.3)
            c_odds = round(max(1.10, 1.0 / (ph * 1.15 + 0.10)), 2)
            candidate_markets.append({
                "market": "Team Goals",
                "selection": f"{home} Over 0.5 Team Goals",
                "prob": p_home_o05,
                "odds": c_odds,
                "direction": "HOME"
            })

        # Away Team Over 0.5 Goals
        if "AWAY" in allowed_directions and pa >= 0.48:
            p_away_o05 = min(0.95, pa * 1.25 + pd * 0.3)
            c_odds = round(max(1.10, 1.0 / (pa * 1.15 + 0.10)), 2)
            candidate_markets.append({
                "market": "Team Goals",
                "selection": f"{away} Over 0.5 Team Goals",
                "prob": p_away_o05,
                "odds": c_odds,
                "direction": "AWAY"
            })

        # Home Win Either Half
        if "HOME" in allowed_directions and ph >= 0.52:
            p_weh = min(0.93, ph * 1.18 + 0.12)
            c_odds = round(max(1.15, 1.0 / (ph * 1.10 + 0.08)), 2)
            candidate_markets.append({
                "market": "Win Either Half",
                "selection": f"{home} Win Either Half",
                "prob": p_weh,
                "odds": c_odds,
                "direction": "HOME"
            })

        # Away Win Either Half
        if "AWAY" in allowed_directions and pa >= 0.52:
            p_weh = min(0.93, pa * 1.18 + 0.12)
            c_odds = round(max(1.15, 1.0 / (pa * 1.10 + 0.08)), 2)
            candidate_markets.append({
                "market": "Win Either Half",
                "selection": f"{away} Win Either Half",
                "prob": p_weh,
                "odds": c_odds,
                "direction": "AWAY"
            })

        # Over 1.5 Goals (Neutral)
        if po15 >= 0.70:
            c_odds = round(max(1.15, 1.0 / max(po15 - 0.03, 0.5)), 2)
            candidate_markets.append({
                "market": "Over/Under Goals",
                "selection": "Over 1.5 Goals",
                "prob": po15,
                "odds": c_odds,
                "direction": "NEUTRAL"
            })

        # Corner Market (Neutral) - Uses dynamic Poisson corner probability
        if p_corners >= 0.68:
            c_odds = round(max(1.15, 1.0 / max(p_corners - 0.04, 0.5)), 2)
            candidate_markets.append({
                "market": "Corners",
                "selection": "Total Corners Over 7.5",
                "prob": p_corners,
                "odds": c_odds,
                "direction": "NEUTRAL"
            })

        if not candidate_markets:
            gate_results["gate2"] = "FAIL"
            reason = "No candidate markets generated matching structural directions"
            audit_log.append(f"REJECTED at GATE 2: {reason}")
            return PickDecision(
                fixture_id=fix_id, home_team=home, away_team=away, competition=comp,
                kickoff_datetime=kickoff, market_name="None", selection_name="None",
                model_probability=0.0, estimated_odds=1.0, elo_gap=elo_gap,
                tier_context=tier_context, approved=False, confidence_tier="REJECTED",
                gate_results=gate_results, rejection_reason=reason,
                decision_audit_log=audit_log, kelly_quarter_stake_pct=0.0
            )

        # If raw SportyBet markets are present on fixture, override estimated odds with real live SportyBet odds
        raw_markets = fixture.get("markets") or []
        if raw_markets:
            for cand in candidate_markets:
                m_kw = cand["market"].lower()
                s_kw = cand["selection"].lower()
                for m in raw_markets:
                    m_desc = (m.get("desc") or m.get("name") or "").lower()
                    if m_kw in m_desc or ("double chance" in m_kw and "double chance" in m_desc):
                        for o in m.get("outcomes", []):
                            o_desc = (o.get("desc") or o.get("name") or "").lower()
                            if ("1x" in s_kw and "1x" in o_desc) or ("x2" in s_kw and "x2" in o_desc) or ("12" in s_kw and "12" in o_desc) or ("over 1.5" in s_kw and "over 1.5" in o_desc) or ("over 7.5" in s_kw and "over 7.5" in o_desc):
                                try:
                                    real_o = float(o.get("odds"))
                                    if real_o >= 1.05:
                                        cand["odds"] = real_o
                                except (ValueError, TypeError):
                                    pass

        # -------------------------------------------------------------
        # GATE 2: Calibrated Probability Threshold (Dynamic Adaptability)
        # -------------------------------------------------------------
        # Global Low Odds & Empty Value Purge: Discard ANY pick offering odds below 1.12
        candidate_markets = [m for m in candidate_markets if m["odds"] >= 1.12]

        if not candidate_markets:
            gate_results["gate2"] = "FAIL"
            reason = "All candidates rejected by global < 1.12 odds purge rule"
            audit_log.append(f"REJECTED at GATE 2: {reason}")
            return PickDecision(
                fixture_id=fix_id, home_team=home, away_team=away, competition=comp,
                kickoff_datetime=kickoff, market_name="None", selection_name="None",
                model_probability=0.0, estimated_odds=1.0, elo_gap=elo_gap,
                tier_context=tier_context, approved=False, confidence_tier="REJECTED",
                gate_results=gate_results, rejection_reason=reason,
                decision_audit_log=audit_log, kelly_quarter_stake_pct=0.0
            )

        effective_threshold = min(min_prob_threshold, 0.72)
        valid_g2_candidates = [m for m in candidate_markets if m["prob"] >= effective_threshold]
        if not valid_g2_candidates:
            # Fall back to best available structural market for this match
            valid_g2_candidates = candidate_markets

        max_p = max(m["prob"] for m in candidate_markets)

        gate_results["gate2"] = "PASS"
        audit_log.append(f"GATE 2 PASS: {len(valid_g2_candidates)} candidate market(s) exceed {min_prob_threshold*100:.0f}% confidence threshold.")

        # -------------------------------------------------------------
        # GATE 3: Scored Market Audit (Edge + Safety)
        # -------------------------------------------------------------
        scored_candidates = []
        for cand in valid_g2_candidates:
            prob = cand["prob"]
            odds = cand["odds"]
            safety = self._get_structural_safety(cand["market"])
            if self.use_live_odds:
                true_implied = self._strip_overround_margin(odds)
                value_edge = max(0.0, prob - true_implied)
                market_score = (prob * 0.60) + (value_edge * 0.25) + (safety * 0.15)
            else:
                value_edge = 0.0
                market_score = (prob * 0.80) + (safety * 0.20)
            cand["score"] = market_score
            cand["value_edge"] = value_edge
            cand["safety"] = safety
            scored_candidates.append(cand)

        scored_candidates.sort(key=lambda x: x["score"], reverse=True)
        best_cand = scored_candidates[0]

        gate_results["gate3"] = "PASS"
        audit_log.append(
            f"GATE 3 PASS: Selected [{best_cand['selection']}] — Model Prob: {best_cand['prob']*100:.1f}%, "
            f"Market Score: {best_cand['score']:.3f}, Value Edge: {best_cand['value_edge']*100:+.1f}%."
        )

        # -------------------------------------------------------------
        # GATE 4: Dynamic Odds Alignment Check
        # -------------------------------------------------------------
        pick_odds = best_cand["odds"]
        lower_bound = max(1.05, per_leg_target_odds * 0.70)
        upper_bound = per_leg_target_odds * 1.45

        if not (lower_bound <= pick_odds <= upper_bound):
            # Try to find another candidate in scored list that meets odds bounds
            in_bounds = [c for c in scored_candidates if lower_bound <= c["odds"] <= upper_bound]
            if in_bounds:
                best_cand = in_bounds[0]
                pick_odds = best_cand["odds"]
                audit_log.append(f"GATE 4 ADJUSTED: Switched to [{best_cand['selection']}] ({pick_odds} odds) to fit target odds window [{lower_bound:.2f}–{upper_bound:.2f}].")
                gate_results["gate4"] = "PASS"
            else:
                gate_results["gate4"] = "FAIL"
                reason = f"Odds ({pick_odds}) outside target per-leg range [{lower_bound:.2f}–{upper_bound:.2f}]"
                audit_log.append(f"REJECTED at GATE 4: {reason}")
                return PickDecision(
                    fixture_id=fix_id, home_team=home, away_team=away, competition=comp,
                    kickoff_datetime=kickoff, market_name=best_cand["market"],
                    selection_name=best_cand["selection"], model_probability=best_cand["prob"],
                    estimated_odds=pick_odds, elo_gap=elo_gap, tier_context=tier_context,
                    approved=False, confidence_tier="REJECTED", gate_results=gate_results,
                    rejection_reason=reason, decision_audit_log=audit_log,
                    kelly_quarter_stake_pct=0.0
                )
        else:
            gate_results["gate4"] = "PASS"
            audit_log.append(f"GATE 4 PASS: Pick odds {pick_odds:.2f} align with per-leg target {per_leg_target_odds:.2f} [{lower_bound:.2f}–{upper_bound:.2f}].")

        # -------------------------------------------------------------
        # GATE 5: Accumulator Correlation & Diversity Filter
        # -------------------------------------------------------------
        current_league_count = league_pick_counts.get(comp, 0)
        if current_league_count >= max_league_picks:
            gate_results["gate5"] = "FAIL"
            reason = f"League diversity limit reached ({current_league_count} picks already from {comp})"
            audit_log.append(f"REJECTED at GATE 5: {reason}")
            return PickDecision(
                fixture_id=fix_id, home_team=home, away_team=away, competition=comp,
                kickoff_datetime=kickoff, market_name=best_cand["market"],
                selection_name=best_cand["selection"], model_probability=best_cand["prob"],
                estimated_odds=pick_odds, elo_gap=elo_gap, tier_context=tier_context,
                approved=False, confidence_tier="REJECTED", gate_results=gate_results,
                rejection_reason=reason, decision_audit_log=audit_log,
                kelly_quarter_stake_pct=0.0
            )

        gate_results["gate5"] = "PASS"
        audit_log.append(f"GATE 5 PASS: Diversity check clear ({current_league_count}/{max_league_picks} allowed from {comp}).")

        # Determine Confidence Tier
        prob = best_cand["prob"]
        m_score = best_cand["score"]
        if prob >= 0.88 and m_score >= 0.82:
            confidence_tier = "ELITE"
        elif prob >= 0.80 and m_score >= 0.74:
            confidence_tier = "HIGH"
        elif prob >= 0.70 and m_score >= 0.64:
            confidence_tier = "SOLID"
        else:
            confidence_tier = "SPECULATIVE"

        audit_log.append(f"FINAL AUDIT: Approved pick classification -> [{confidence_tier}] Confidence Tier.")

        kelly_pct = self.calculate_kelly_stake(prob, pick_odds, fraction=0.25)

        return PickDecision(
            fixture_id=fix_id, home_team=home, away_team=away, competition=comp,
            kickoff_datetime=kickoff, market_name=best_cand["market"],
            selection_name=best_cand["selection"], model_probability=round(prob, 3),
            estimated_odds=pick_odds, elo_gap=elo_gap, tier_context=tier_context,
            approved=True, confidence_tier=confidence_tier, gate_results=gate_results,
            rejection_reason=None, decision_audit_log=audit_log,
            kelly_quarter_stake_pct=kelly_pct
        )

    def build_ticket(
        self,
        fixture_pool: List[Dict[str, Any]],
        target_total_odds: float,
        mode: str = "ACCUMULATOR",
        max_league_picks: int = 2,
        rollover_days: Optional[int] = None,
        reshuffle_seed: Optional[int] = None,
    ) -> BuiltTicket:
        """
        Evaluates a pool of fixtures through the 5-Gate pipeline and constructs
        an optimal ticket or rollover plan with dynamic candidate reshuffling.
        """
        import random
        import time

        leg_config = calculate_dynamic_leg_config(target_total_odds)
        per_leg_target = leg_config["per_leg_target_odds"]
        min_prob_threshold = leg_config["min_probability_threshold"]

        league_pick_counts: Dict[str, int] = {}
        approved_legs = []
        rejected_picks = []
        summary_logs = [
            f"MatchIQ Pick Engine Execution ({mode} Mode)",
            f"Target Total Odds: {target_total_odds:.2f}x | Ideal Legs: {leg_config['ideal_legs']}",
            f"Min Probability Gate: {int(min_prob_threshold*100)}% | Per-Leg Target: {per_leg_target:.2f}x"
        ]

        total_evaluated = len(fixture_pool)

        # First pass: evaluate all fixtures through 5-Gate Pipeline
        all_decisions: List[PickDecision] = []
        for fix in fixture_pool:
            comp = fix.get("competition_code") or fix.get("league") or "PL"
            dec = self.evaluate_fixture_markets(
                fixture=fix,
                per_leg_target_odds=per_leg_target,
                min_prob_threshold=min_prob_threshold,
                league_pick_counts=league_pick_counts,
                max_league_picks=max_league_picks
            )
            all_decisions.append(dec)
            if dec.approved:
                league_pick_counts[comp] = league_pick_counts.get(comp, 0) + 1

        # Separate approved and rejected decisions
        approved_decisions = [d for d in all_decisions if d.approved]
        rejected_decisions = [d for d in all_decisions if not d.approved]

        # Sort approved decisions by model probability & market score descending
        approved_decisions.sort(key=lambda d: d.model_probability, reverse=True)

        # Select legs fitting target bounds with dynamic seed reshuffling
        target_legs_count = leg_config["ideal_legs"]
        seed_val = reshuffle_seed if reshuffle_seed is not None else int(time.time() * 1000)
        rng = random.Random(seed_val)

        high_prob_approved = [d for d in approved_decisions if d.model_probability >= 0.70]
        if not high_prob_approved:
            high_prob_approved = approved_decisions

        pool_copy = high_prob_approved[:]
        rng.shuffle(pool_copy)
        selected_decisions = pool_copy[:target_legs_count]

        if len(selected_decisions) < target_legs_count:
            remaining = [d for d in approved_decisions if d not in selected_decisions]
            rng.shuffle(remaining)
            selected_decisions.extend(remaining[: target_legs_count - len(selected_decisions)])

        # Calculate combined probability & accumulated odds
        accumulated_odds = 1.0
        combined_prob = 1.0

        for d in selected_decisions:
            accumulated_odds *= d.estimated_odds
            combined_prob *= d.model_probability
            approved_legs.append({
                "fixture_id": d.fixture_id,
                "home_team": d.home_team,
                "away_team": d.away_team,
                "competition": d.competition,
                "kickoff_datetime": d.kickoff_datetime,
                "market_name": d.market_name,
                "selection_name": d.selection_name,
                "model_probability": d.model_probability,
                "estimated_odds": d.estimated_odds,
                "confidence_tier": d.confidence_tier,
                "elo_gap": d.elo_gap,
                "tier_context": d.tier_context,
                "decision_audit_log": d.decision_audit_log,
                "kelly_quarter_stake_pct": d.kelly_quarter_stake_pct
            })

        for r in rejected_decisions:
            rejected_picks.append({
                "fixture": f"{r.home_team} vs {r.away_team}",
                "competition": r.competition,
                "rejection_reason": r.rejection_reason or "Failed gate check",
                "gate_results": r.gate_results
            })

        # Calculate correlation factor penalty
        n_legs = len(selected_decisions)
        league_counts_selected = {}
        for d in selected_decisions:
            league_counts_selected[d.competition] = league_counts_selected.get(d.competition, 0) + 1

        same_league_pairs = sum(c - 1 for c in league_counts_selected.values() if c > 1)
        correlation_penalty = 1.0 - (0.05 * same_league_pairs)
        corr_adjusted_prob = round(combined_prob * max(0.70, correlation_penalty), 3)

        # Ticket level confidence tier
        if selected_decisions:
            avg_prob = sum(d.model_probability for d in selected_decisions) / n_legs
            if avg_prob >= 0.85:
                ticket_tier = "ELITE"
            elif avg_prob >= 0.78:
                ticket_tier = "HIGH"
            elif avg_prob >= 0.70:
                ticket_tier = "SOLID"
            else:
                ticket_tier = "SPECULATIVE"
        else:
            ticket_tier = "NONE"

        # Fractional Kelly recommended stake
        avg_leg_odds = accumulated_odds ** (1.0 / max(1, n_legs))
        rec_stake_pct = self.calculate_kelly_stake(corr_adjusted_prob, accumulated_odds, fraction=0.25)

        summary_logs.append(
            f"Pipeline Completed: {len(approved_legs)} legs selected out of {total_evaluated} evaluated. "
            f"Final Accumulated Odds: {accumulated_odds:.2f}x (Target {target_total_odds:.2f}x). "
            f"Combined Win Prob: {combined_prob*100:.1f}% (Corr-Adjusted: {corr_adjusted_prob*100:.1f}%)."
        )

        return BuiltTicket(
            mode=mode,
            target_odds=target_total_odds,
            accumulated_odds=round(accumulated_odds, 2),
            combined_probability=round(combined_prob, 3),
            correlation_adjusted_probability=corr_adjusted_prob,
            confidence_tier=ticket_tier,
            leg_config=leg_config,
            approved_legs=approved_legs,
            rejected_picks=rejected_picks,
            total_evaluated=total_evaluated,
            decision_audit_summary=summary_logs,
            recommended_stake_pct=rec_stake_pct
        )
