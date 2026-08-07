from typing import Dict, Any, List
from fastapi import APIRouter, Depends, Query
from sqlalchemy.orm import Session
from sqlalchemy import select

from app.db.session import get_db
from app.db.models import ProviderMarketMapping, ProviderFixtureMapping
from app.adapters.bookmaker_adapter import SportyBetAdapter, CanonicalMarketRegistry

router = APIRouter()

@router.get("/capabilities")
def get_provider_capabilities(provider: str = Query(default="SPORTYBET"), db: Session = Depends(get_db)):
    """
    Phase 12 Provider Capability Registry API.
    Checks capability flags before attempting provider operations.
    """
    if provider.upper() == "SPORTYBET":
        adapter = SportyBetAdapter(db)
        caps = adapter.get_capabilities()
        return {
            "provider": caps.provider,
            "supports_fixture_mapping": caps.supports_fixture_mapping,
            "supports_market_mapping": caps.supports_market_mapping,
            "supports_odds_reading": caps.supports_odds_reading,
            "supports_official_api": caps.supports_official_api,
            "status": caps.status
        }
    return {
        "provider": provider,
        "supports_fixture_mapping": False,
        "supports_market_mapping": False,
        "supports_odds_reading": False,
        "supports_official_api": False,
        "status": "UNSUPPORTED_PROVIDER"
    }

@router.get("/markets")
def get_provider_market_mappings(provider: str = Query(default="SPORTYBET"), db: Session = Depends(get_db)):
    """
    Returns canonical market mappings for a specific bookmaker provider.
    """
    stmt = select(ProviderMarketMapping).where(ProviderMarketMapping.provider == provider.upper())
    records = list(db.execute(stmt).scalars().all())

    items = []
    for r in records:
        items.append({
            "provider": r.provider,
            "provider_market_name": r.provider_market_name,
            "matchiq_market_type": r.matchiq_market_type,
            "matchiq_selection": r.matchiq_selection,
            "status": r.mapping_status
        })

    # Return canonical registry if no custom DB mappings exist yet
    if not items:
        for key, (m_type, line, sel) in CanonicalMarketRegistry.CANONICAL_MARKETS.items():
            items.append({
                "provider": provider.upper(),
                "provider_market_name": key,
                "matchiq_market_type": m_type,
                "matchiq_selection": sel,
                "status": "CANONICAL_DEFAULT"
            })

    return {"total": len(items), "mappings": items}

@router.get("/fixtures")
def get_provider_fixture_mappings(provider: str = Query(default="SPORTYBET"), db: Session = Depends(get_db)):
    """
    Returns mapped provider fixture IDs.
    """
    stmt = select(ProviderFixtureMapping).where(ProviderFixtureMapping.provider == provider.upper())
    records = list(db.execute(stmt).scalars().all())

    items = []
    for r in records:
        items.append({
            "provider": r.provider,
            "provider_fixture_id": r.provider_fixture_id,
            "matchiq_fixture_id": r.matchiq_fixture_id,
            "provider_match": f"{r.provider_home_team} vs {r.provider_away_team}",
            "confidence": r.mapping_confidence
        })
    return {"total": len(items), "fixture_mappings": items}

@router.post("/generate-code")
def generate_provider_booking_code(req_data: Dict[str, Any], db: Session = Depends(get_db)):
    """
    Generates a real loadable booking code for SportyBet (or other supported providers).
    """
    provider = req_data.get("provider", "SPORTYBET").upper()
    selections = req_data.get("selections", [])
    country_code = req_data.get("country_code", "ng").lower()

    if provider == "SPORTYBET":
        adapter = SportyBetAdapter(db)
        return adapter.generate_booking_code(selections, country_code=country_code)

    return {"status": "UNSUPPORTED_PROVIDER", "message": f"Code generation for {provider} not supported."}

@router.post("/read-code")
def read_provider_booking_code(req_data: Dict[str, Any], db: Session = Depends(get_db)):
    """
    Reads and decodes an external booking code via direct Web API adapter.
    """
    provider = req_data.get("provider", "SPORTYBET").upper()
    code = req_data.get("code", "")
    country_code = req_data.get("country_code", "ng").lower()

    if provider == "SPORTYBET":
        adapter = SportyBetAdapter(db)
        return adapter.fetch_booking_code_details(code, country_code=country_code)

    return {"status": "UNSUPPORTED_PROVIDER", "message": f"Code reading for {provider} not supported."}

