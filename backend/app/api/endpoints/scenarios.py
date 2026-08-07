from typing import List, Dict, Any, Optional
from fastapi import APIRouter, Depends, Query, HTTPException
from sqlalchemy.orm import Session
from sqlalchemy import select

from app.db.session import get_db
from app.db.models import ScenarioAnalysis, ScenarioAnalysisItem
from app.markets.scenario_builder import ScenarioBuilderEngine, ScenarioRequest

router = APIRouter()

@router.post("/analyze")
def generate_scenarios(req_data: Dict[str, Any], db: Session = Depends(get_db)):
    """
    Phase 10 Target Probability & Scenario Builder API.
    Generates multi-match candidate scenarios under strict probability preservation.
    """
    req = ScenarioRequest(
        fixture_ids=req_data.get("fixture_ids", []),
        target_combined_value=req_data.get("target_combined_value"),
        minimum_probability=req_data.get("minimum_probability", 0.60),
        minimum_confidence=req_data.get("minimum_confidence", 0.60),
        minimum_legs=req_data.get("minimum_legs", 1),
        maximum_legs=req_data.get("maximum_legs", 4),
        competitions=req_data.get("competitions", []),
        markets=req_data.get("markets", []),
        allow_same_fixture_multiple_markets=req_data.get("allow_same_fixture_multiple_markets", False)
    )

    builder = ScenarioBuilderEngine(db)
    return builder.build_scenarios(req)

@router.get("/candidates")
def get_scenario_candidate_pool(min_prob: float = Query(default=0.60, ge=0.1, le=1.0), db: Session = Depends(get_db)):
    """
    Returns eligible selection candidates available for scenario building.
    """
    req = ScenarioRequest(minimum_probability=min_prob, minimum_confidence=min_prob)
    builder = ScenarioBuilderEngine(db)
    candidates = builder.get_candidate_pool(req)

    items = []
    for c in candidates:
        items.append({
            "fixture_id": c.fixture_id,
            "competition": c.competition_code,
            "kickoff_datetime": c.kickoff_datetime.isoformat(),
            "market_type": c.market_type,
            "market_line": c.market_line,
            "selection": c.selection,
            "model_probability_pct": round(c.model_probability * 100, 2),
            "model_version": c.model_version
        })
    return {"total": len(items), "candidates": items}

@router.get("/history")
def get_scenario_history(limit: int = Query(default=20, le=100), db: Session = Depends(get_db)):
    """
    Returns historical scenario analysis audit records.
    """
    stmt = select(ScenarioAnalysis).order_by(ScenarioAnalysis.created_at.desc()).limit(limit)
    records = list(db.execute(stmt).scalars().all())

    items = []
    for r in records:
        items.append({
            "scenario_id": r.scenario_id,
            "model_version": r.model_version,
            "scenario_count": r.scenario_count,
            "status": r.status,
            "created_at": r.created_at.isoformat()
        })
    return {"total": len(items), "history": items}
