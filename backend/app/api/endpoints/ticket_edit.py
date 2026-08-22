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
    mode: str = "AUDITOR"                # "AUDITOR", "REMOVE"
    reshuffle_seed: Optional[int] = None
    strict_mode: bool = False
    num_tickets: Optional[int] = 1

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
    Supports num_tickets=1, 2, or 3 with zero-overlap portfolio partitioning.
    Automatically generates verified SportyBet booking codes for all tickets in parallel.
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
                num_tickets=req.num_tickets or 1,
            ),
            timeout=reedit_timeout
        )
    except asyncio.TimeoutError:
        logger.warning(f"re_edit_ticket timed out after {reedit_timeout}s for {n_legs}-leg ticket")
        raise HTTPException(status_code=504, detail=f"Re-edit timed out after {reedit_timeout}s. Try reducing the number of selections or splitting the ticket.")

    # Automatic Phase 14 Verified Booking Code Generation for all portfolio slips in parallel
    portfolio_slips = res.get("portfolio_tickets", [])
    if not portfolio_slips and res.get("final_selections"):
        portfolio_slips = [{
            "ticket_index": 1,
            "final_count": len(res.get("final_selections")),
            "final_selections": res.get("final_selections"),
            "new_total_odds": res.get("new_total_odds"),
            "avg_win_prob": res.get("avg_win_prob")
        }]

    if portfolio_slips:
        try:
            adapter = SportyBetAdapter(db)

            async def _generate_booking_for_slip(slip_data):
                sels = slip_data.get("final_selections", [])
                if not sels:
                    return slip_data
                try:
                    # Run sync adapter method in thread pool to avoid blocking
                    b_res = await asyncio.to_thread(adapter.generate_booking_code, sels, "ng")
                    if b_res.get("status") == "SUCCESS" and b_res.get("booking_code"):
                        slip_data["booking_code"] = b_res.get("booking_code")
                        slip_data["share_url"] = b_res.get("load_url")
                        slip_data["verification_status"] = b_res.get("verification_status", "BOOKING_VERIFIED")
                except Exception as ex:
                    logger.warning(f"Slip booking generation error: {ex}")
                return slip_data

            updated_slips = await asyncio.gather(*[_generate_booking_for_slip(s) for s in portfolio_slips])
            res["portfolio_tickets"] = updated_slips

            if updated_slips and len(updated_slips) > 0:
                primary = updated_slips[0]
                res["booking_code"] = primary.get("booking_code")
                res["share_url"] = primary.get("share_url")
                res["verification_status"] = primary.get("verification_status", "BOOKING_VERIFIED")

        except Exception as e:
            logger.warning(f"Portfolio booking generation error: {e}")

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
