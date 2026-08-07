from typing import List, Dict, Any, Optional
from fastapi import APIRouter, HTTPException, Depends
from pydantic import BaseModel
from sqlalchemy.orm import Session

from app.db.session import get_db
from app.adapters.bookmaker_adapter import SportyBetAdapter
from app.services.ticket_reeditor import re_edit_ticket

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
    mode: str = "SWAP"  # "SWAP", "REMOVE", "AUDITOR"

class GenerateCodeRequest(BaseModel):
    selections: List[Dict[str, Any]]
    country_code: Optional[str] = "ng"

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
    SWAP mode: Replaces risky/unsupported picks with MatchIQ's safe picks at target odds.
    REMOVE mode: Drops risky/unsupported picks, keeping only confident picks.
    """
    if req.target_odds < 1.05:
        raise HTTPException(status_code=400, detail="Target odds must be at least 1.05")

    selections_dict = [s.model_dump() for s in req.selections]
    result = await re_edit_ticket(selections_dict, req.target_odds, req.mode)
    return result

@router.post("/generate-code")
def generate_new_booking_code(req: GenerateCodeRequest, db: Session = Depends(get_db)):
    """
    Generates a new SportyBet booking code for the final re-edited selections.
    """
    adapter = SportyBetAdapter(db)
    res = adapter.generate_booking_code(req.selections, req.country_code)
    return res
