import asyncio
import logging
from typing import List, Dict, Any, Optional
from fastapi import APIRouter, HTTPException, Depends
from pydantic import BaseModel
from sqlalchemy.orm import Session

from app.db.session import get_db
from app.adapters.bookmaker_adapter import SportyBetAdapter
from app.services.ticket_reeditor import re_edit_ticket
from app.services.api_football_stats import batch_fetch_match_stats
from app.core.config import settings

logger = logging.getLogger("matchiq.ticket_edit")
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
    reshuffle_seed: Optional[int] = None
    strict_mode: bool = False

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
async def run_re_edit(req: ReEditRequest, db: Session = Depends(get_db)):
    """
    Runs MatchIQ's statistical ticket re-editor.
    Supports target_mode="ODDS" or target_mode="GAMES" (up to 50 games max).
    Automatically generates a verified SportyBet booking code for the new ticket.
    Server-side timeout scales with ticket size: 75s for ≤15 legs, up to 120s for 50 legs.
    """
    selections_dict = [s.model_dump() for s in req.selections]
    n_legs = len(selections_dict)

    # Adaptive server-side timeout: 75s for ≤15 legs, 100s for 16-30, 120s for 31+
    reedit_timeout = 75 if n_legs <= 15 else (100 if n_legs <= 30 else 120)

    try:
        res = await asyncio.wait_for(
            re_edit_ticket(
                selections=selections_dict,
                target_odds=req.target_odds,
                mode=req.mode,
                target_mode=req.target_mode,
                target_games=req.target_games or 10,
                reshuffle_seed=req.reshuffle_seed,
                strict_mode=req.strict_mode,
            ),
            timeout=reedit_timeout
        )
    except asyncio.TimeoutError:
        logger.warning(f"re_edit_ticket timed out after {reedit_timeout}s for {n_legs}-leg ticket")
        raise HTTPException(status_code=504, detail=f"Re-edit timed out after {reedit_timeout}s. Try reducing the number of selections or splitting the ticket.")

    # Automatic Phase 14 Verified Booking Code Generation
    final_sels = res.get("final_selections", [])
    booking_timeout = 60 if n_legs <= 15 else (90 if n_legs <= 30 else 120)
    if final_sels:
        try:
            from app.services.sportybet_reconciliation import SportyBetVerificationEngine
            engine = SportyBetVerificationEngine(db)
            ver_res = await asyncio.wait_for(
                engine.generate_verified_booking(
                    statiq_ticket_id="REEDIT-AUTO",
                    selections=final_sels,
                    region="ng"
                ),
                timeout=booking_timeout
            )
            if ver_res.get("status") == "VERIFIED":
                res["booking_code"] = ver_res.get("booking_code")
                res["share_url"] = ver_res.get("share_url")
                res["verification_status"] = ver_res.get("status")
                res["reconciliation_summary"] = ver_res.get("reconciliation_summary")

                # ── Back-fill real SportyBet odds into final_selections ──────────
                # audit_resolved contains the actual SportyBet odds per resolved selection.
                # We match by home+away team name and overwrite estimated_odds / odds
                # so the frontend always displays the verified real per-leg odds.
                audit_resolved = ver_res.get("audit_resolved", [])
                if audit_resolved:
                    # Build a lookup: (normalised_home, normalised_away) -> real_odds
                    def _norm(t: str) -> str:
                        return (t or "").lower().strip()

                    odds_map = {
                        (_norm(ar.get("home_team", "")), _norm(ar.get("away_team", ""))): float(ar.get("odds", 0))
                        for ar in audit_resolved
                        if ar.get("odds") and float(ar.get("odds", 0)) >= 1.01
                    }

                    for sel in res.get("final_selections", []):
                        key = (_norm(sel.get("home_team", "")), _norm(sel.get("away_team", "")))
                        if key in odds_map:
                            real_odds = odds_map[key]
                            sel["estimated_odds"] = real_odds
                            sel["odds"] = real_odds
                            sel["odds_source"] = "SPORTYBET_VERIFIED"

                    # Recompute total odds from back-filled real values
                    real_total = 1.0
                    for sel in res.get("final_selections", []):
                        real_total *= float(sel.get("estimated_odds") or sel.get("odds") or 1.25)
                    res["new_total_odds"] = round(real_total, 2)

                res["audit_resolved"] = audit_resolved  # expose for frontend display

        except asyncio.TimeoutError:
            logger.warning(f"generate_verified_booking timed out after {booking_timeout}s for {n_legs}-leg ticket (re-edit result still returned)")
        except Exception as e:
            logger.warning(f"Auto verified booking generation error during re-edit: {e}")

    return res



@router.post("/generate-code")
async def generate_new_booking_code(req: GenerateCodeRequest, db: Session = Depends(get_db)):
    """
    Generates a new Phase 14 verified SportyBet booking code for the final re-edited selections.
    """
    from app.services.sportybet_reconciliation import SportyBetVerificationEngine
    engine = SportyBetVerificationEngine(db)
    res = await engine.generate_verified_booking(
        statiq_ticket_id="REEDIT-TKT",
        selections=req.selections,
        region=req.country_code or "ng"
    )
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
