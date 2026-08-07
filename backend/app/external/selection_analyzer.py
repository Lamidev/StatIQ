from typing import Dict, Any, List, Optional
from sqlalchemy import select
from app.db.models import Fixture, LivePredictionLedger, ExternalCodeAnalysis, ExternalCodeItem
from app.external.code_parser import ParsedExternalCode, ExternalSelection
from app.external.fixture_resolver import FixtureResolver

class SelectionAnalyzerEngine:
    """
    Phase 11 Selection Analyzer & Weakness Classification Engine.
    Analyzes decoded external selections against MatchIQ Prediction Engine outputs.
    
    Weakness Classifications (Configurable):
    - Prob >= 0.70 -> VERY_STRONG
    - Prob >= 0.60 -> STRONG
    - Prob >= 0.50 -> MODERATE
    - Prob <  0.50 -> WEAK
    
    Discovers alternative MatchIQ-supported selections without modifying user's original selection.
    """
    def __init__(self, session, very_strong_thresh: float = 0.70, strong_thresh: float = 0.60, moderate_thresh: float = 0.50):
        self.session = session
        self.resolver = FixtureResolver(session)
        self.very_strong_thresh = very_strong_thresh
        self.strong_thresh = strong_thresh
        self.moderate_thresh = moderate_thresh

    def classify_probability(self, prob: Optional[float]) -> str:
        if prob is None:
            return "INSUFFICIENT_DATA"
        if prob >= self.very_strong_thresh:
            return "VERY_STRONG"
        if prob >= self.strong_thresh:
            return "STRONG"
        if prob >= self.moderate_thresh:
            return "MODERATE"
        return "WEAK"

    def analyze_parsed_code(self, parsed: ParsedExternalCode) -> Dict[str, Any]:
        audit_analysis = ExternalCodeAnalysis(
            provider=parsed.provider,
            raw_code=parsed.raw_code,
            parse_status=parsed.parse_status,
            total_selections=len(parsed.selections)
        )
        self.session.add(audit_analysis)
        self.session.flush()

        analyzed_items = []
        resolved_count = 0
        unresolved_count = 0

        for sel in parsed.selections:
            res = self.resolver.resolve_selection(sel, provider=parsed.provider)
            fix_id = res.get("matchiq_fixture_id")

            prob_model = None
            classification = "UNRESOLVED"
            alternatives = []

            if fix_id:
                resolved_count += 1
                pred_stmt = select(LivePredictionLedger).where(LivePredictionLedger.fixture_id == fix_id)
                pred = self.session.execute(pred_stmt).scalar_one_or_none()

                if pred:
                    # Match selection to model probabilities
                    m_key = sel.selection.upper()
                    if sel.market in ["1X2", "MATCH_RESULT"]:
                        if m_key == "HOME": prob_model = pred.prob_home
                        elif m_key == "DRAW": prob_model = pred.prob_draw
                        elif m_key == "AWAY": prob_model = pred.prob_away
                    elif sel.market in ["OVER_UNDER", "OVER_UNDER_2_5"]:
                        if m_key == "OVER": prob_model = pred.prob_over_2_5
                        elif m_key == "UNDER": prob_model = 1.0 - (pred.prob_over_2_5 or 0.5)
                    elif sel.market == "BTTS":
                        if m_key == "YES": prob_model = pred.prob_btts_yes
                        elif m_key == "NO": prob_model = 1.0 - (pred.prob_btts_yes or 0.5)

                    classification = self.classify_probability(prob_model)

                    # Find alternatives if selection is WEAK or MODERATE
                    if prob_model is not None and prob_model < self.strong_thresh:
                        alt_candidates = [
                            ("1X2", "HOME", pred.prob_home),
                            ("1X2", "AWAY", pred.prob_away),
                            ("OVER_UNDER_1_5", "OVER", pred.prob_over_1_5 or 0.0),
                            ("OVER_UNDER_2_5", "OVER", pred.prob_over_2_5 or 0.0),
                            ("BTTS", "YES", pred.prob_btts_yes or 0.0)
                        ]
                        for a_mkt, a_sel, a_p in alt_candidates:
                            if a_p >= self.strong_thresh:
                                alternatives.append({
                                    "market": a_mkt,
                                    "selection": a_sel,
                                    "model_probability": round(a_p, 4)
                                })
            else:
                unresolved_count += 1

            item_db = ExternalCodeItem(
                analysis_id=audit_analysis.id,
                matchiq_fixture_id=fix_id,
                external_fixture_name=f"{sel.home_team} vs {sel.away_team}",
                external_market_name=sel.market,
                external_selection=sel.selection,
                external_odds=sel.odds,
                resolution_status=res.get("match_status", "UNRESOLVED"),
                matchiq_probability=prob_model,
                classification=classification
            )
            self.session.add(item_db)

            analyzed_items.append({
                "external_fixture": f"{sel.home_team} vs {sel.away_team}",
                "external_market": sel.market,
                "external_selection": sel.selection,
                "resolution_status": res.get("match_status"),
                "matchiq_fixture_id": fix_id,
                "model_probability": round(prob_model, 4) if prob_model is not None else None,
                "classification": classification,
                "suggested_alternatives": alternatives
            })

        audit_analysis.resolved_count = resolved_count
        audit_analysis.unresolved_count = unresolved_count
        self.session.commit()

        return {
            "analysis_id": audit_analysis.id,
            "provider": parsed.provider,
            "raw_code": parsed.raw_code,
            "parse_status": parsed.parse_status,
            "total_selections": len(parsed.selections),
            "resolved_count": resolved_count,
            "unresolved_count": unresolved_count,
            "items": analyzed_items
        }
