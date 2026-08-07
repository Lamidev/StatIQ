from typing import List, Dict, Any, Optional
from fastapi import APIRouter, HTTPException, Depends
from pydantic import BaseModel
from sqlalchemy.orm import Session

from app.db.session import get_db
from app.adapters.bookmaker_adapter import SportyBetAdapter
from app.services.ticket_reeditor import re_edit_ticket
from app.services.api_football_stats import batch_fetch_match_stats
from app.core.config import settings

router = APIRouter()

class SelectionItem(BaseModel):
    home_team: str
    away_team: str
    market_name: Optional[str] = "Match Result"
    selection_name: Optional[str] = "1"
    odds: Optional[float] = 1.80
    match_status: Optional[str] = "UPCOMING"

    class Config:
        extra = "allow"

class DecodeRequest(BaseModel):
    code: str
    provider: Optional[str] = "SPORTYBET"
    country_code: Optional[str] = "ng"

class ReEditRequest(BaseModel):
    selections: List[SelectionItem]
    target_odds: float = 5.0
    target_mode: Optional[str] = "ODDS"  # "ODDS" or "GAMES"
    target_games: Optional[int] = 10     # Up to 50 max games on SportyBet
    mode: str = "SWAP"  # "SWAP", "REMOVE", "AUDITOR"

class GenerateCodeRequest(BaseModel):
    selections: List[Dict[str, Any]]
    country_code: Optional[str] = "ng"

class MatchStatsItem(BaseModel):
    home_team: str
    away_team: str
    pick: Optional[str] = ""
    match_date: Optional[str] = None  # "YYYY-MM-DD"

class MatchStatsBatchRequest(BaseModel):
    matches: List[MatchStatsItem]

@router.post("/decode")
def decode_booking_code(req: DecodeRequest, db: Session = Depends(get_db)):
    """
    Decodes an external bookmaker booking code (e.g. SportyBet).
    Returns raw ticket selections.
    """
    if req.provider.upper() == "SPORTYBET":
        adapter = SportyBetAdapter(db)
        res = adapter.fetch_booking_code_details(req.code, req.country_code)
        return res
    raise HTTPException(status_code=400, detail=f"Unsupported provider: {req.provider}")

@router.post("/re-edit")
async def run_re_edit(req: ReEditRequest):
    """
    Runs MatchIQ's statistical ticket re-editor.
    Supports target_mode="ODDS" or target_mode="GAMES" (up to 50 games max).
    """
    selections_dict = [s.model_dump() for s in req.selections]

    res = await re_edit_ticket(
        selections=selections_dict,
        target_odds=req.target_odds,
        mode=req.mode,
        target_mode=req.target_mode,
        target_games=req.target_games or 10,
    )
    return res

@router.post("/generate-code")
def generate_new_booking_code(req: GenerateCodeRequest, db: Session = Depends(get_db)):
    """
    Generates a new SportyBet booking code for the final re-edited selections.
    """
    adapter = SportyBetAdapter(db)
    res = adapter.generate_booking_code(req.selections, req.country_code)
    return res

@router.post("/match-stats")
async def get_match_stats(req: MatchStatsBatchRequest):
    """
    Batch-fetches real match statistics (corners, halftime scores) from API-Football.
    Only fetches for picks that require stat verification:
      - Total Corners Over 7.5
      - 1st Half Over 0.5 Goals
      - Win Either Half
    Returns a dict keyed by match index with corners and halftime data.
    Skips all other picks to conserve API request budget.
    """
    if not settings.API_FOOTBALL_KEY:
        return {
            "status": "NO_API_KEY",
            "message": "API_FOOTBALL_KEY not configured in .env. Corner and 1st half picks will be marked UNVERIFIED.",
            "stats": {}
        }

    matches_dicts = [m.model_dump() for m in req.matches]
    stats = await batch_fetch_match_stats(matches_dicts, settings.API_FOOTBALL_KEY)

    # Convert integer keys to string for JSON serialisation
    return {
        "status": "OK",
        "api_calls_made": len(stats),
        "stats": {str(k): v for k, v in stats.items()}
    }
