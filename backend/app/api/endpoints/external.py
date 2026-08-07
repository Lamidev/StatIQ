from typing import Dict, Any
from fastapi import APIRouter, Depends, Query, HTTPException
from sqlalchemy.orm import Session

from app.db.session import get_db
from app.external.code_parser import ExternalCodeParser, ExternalSelection
from app.external.fixture_resolver import FixtureResolver
from app.external.selection_analyzer import SelectionAnalyzerEngine

router = APIRouter()

@router.post("/parse-code")
def parse_external_booking_code(req_data: Dict[str, Any]):
    """
    Phase 11 External Booking Code Parser API.
    Decodes external selections or returns UNSUPPORTED if provider has no official mapping API.
    """
    code = req_data.get("code", "")
    provider = req_data.get("provider", "UNKNOWN")

    parser = ExternalCodeParser()
    res = parser.parse_external_code(code, provider=provider)
    return {
        "provider": res.provider,
        "raw_code": res.raw_code,
        "parse_status": res.parse_status,
        "total_selections": len(res.selections),
        "message": res.message
    }

@router.post("/resolve")
def resolve_external_selection(req_data: Dict[str, Any], db: Session = Depends(get_db)):
    """
    Multi-tier Fixture Resolver API.
    """
    provider = req_data.get("provider", "UNKNOWN")
    sel = ExternalSelection(
        external_fixture_id=req_data.get("external_fixture_id"),
        home_team=req_data.get("home_team"),
        away_team=req_data.get("away_team"),
        market=req_data.get("market", "1X2"),
        selection=req_data.get("selection", "HOME")
    )
    resolver = FixtureResolver(db)
    return resolver.resolve_selection(sel, provider=provider)

@router.post("/analyze")
def analyze_external_code(req_data: Dict[str, Any], db: Session = Depends(get_db)):
    """
    Phase 11 Full External Code Analysis & Selection Weakness Audit API.
    """
    code = req_data.get("code", "")
    provider = req_data.get("provider", "UNKNOWN")

    parser = ExternalCodeParser()
    parsed = parser.parse_external_code(code, provider=provider)

    analyzer = SelectionAnalyzerEngine(db)
    return analyzer.analyze_parsed_code(parsed)
