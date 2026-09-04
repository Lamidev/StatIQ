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


class MergeMasterRequest(BaseModel):
    slips: List[Dict[str, Any]]
    target_games: Optional[int] = 10
    country_code: Optional[str] = "ng"


@router.post("/merge-master")
async def merge_portfolio_to_master(req: MergeMasterRequest, db: Session = Depends(get_db)):
    """
    Merges 2 (or more) variant tickets into 1 unified Master Ticket for BetSlip Auditor.
    - Resolves shared fixtures by picking highest conviction/win probability.
    - Slices to user-selected prioritized games count (5, 8, 10, 12, 15 max).
    - Generates live verified SportyBet booking code.
    """
    if not req.slips:
        raise HTTPException(status_code=400, detail="No slips provided to merge.")

    fixture_candidates: Dict[str, List[Dict[str, Any]]] = {}

    for s_idx, slip in enumerate(req.slips):
        legs = slip.get("approved_legs") or slip.get("final_selections") or slip.get("selections") or []
        for leg in legs:
            f_id = str(leg.get("fixture_id") or leg.get("event_id") or leg.get("provider_event_id") or "")
            h_name = str(leg.get("home_team") or "").strip().lower()
            a_name = str(leg.get("away_team") or "").strip().lower()
            f_key = f"{h_name}_vs_{a_name}" if (h_name and a_name) else f_id
            if not f_key:
                continue

            if f_key not in fixture_candidates:
                fixture_candidates[f_key] = []
            fixture_candidates[f_key].append(leg)

    if not fixture_candidates:
        raise HTTPException(status_code=400, detail="No valid match legs found in provided slips.")

    best_picks_per_fixture = []
    for f_key, leg_list in fixture_candidates.items():
        def _score_leg(l):
            prob = float(l.get("model_probability") or l.get("win_prob") or 0.70)
            odds = float(l.get("odds") or l.get("estimated_odds") or 1.25)
            return (prob, -abs(odds - 1.25))

        leg_list.sort(key=_score_leg, reverse=True)
        best_picks_per_fixture.append(leg_list[0])

    def _rank_fixture(l):
        prob = float(l.get("model_probability") or l.get("win_prob") or 0.70)
        odds = float(l.get("odds") or l.get("estimated_odds") or 1.25)
        return (prob, odds)

    best_picks_per_fixture.sort(key=_rank_fixture, reverse=True)

    t_games = max(2, min(15, int(req.target_games or 10)))
    master_legs = best_picks_per_fixture[:t_games]

    acc_odds = 1.0
    comb_prob = 1.0
    for leg in master_legs:
        o = float(leg.get("odds") or leg.get("estimated_odds") or 1.25)
        p = float(leg.get("model_probability") or leg.get("win_prob") or 0.75)
        acc_odds *= o
        comb_prob *= min(0.95, p)

    acc_odds = round(acc_odds, 2)
    comb_prob = round(comb_prob, 4)

    booking_code = None
    share_url = None
    try:
        adapter = SportyBetAdapter(db)
        code_res = await asyncio.to_thread(adapter.generate_booking_code, master_legs, req.country_code or "ng")
        if code_res.get("status") == "SUCCESS" and code_res.get("booking_code"):
            booking_code = code_res.get("booking_code")
            share_url = code_res.get("load_url")
    except Exception as e:
        logger.warning(f"Error generating SportyBet code for master ticket: {e}")

    master_ticket = {
        "scenario_id": f"STATIQ-MASTER-SLIP-{len(master_legs)}G",
        "ticket_index": "MASTER",
        "is_master": True,
        "title": f"⚡ Master Ticket ({len(master_legs)} Legs)",
        "scope_label": f"Master Ticket · Top {len(master_legs)} Prioritized Games",
        "gameweek_label": "MERGED_MASTER",
        "target_mode": "GAMES",
        "target_games": len(master_legs),
        "target_odds": acc_odds,
        "accumulated_odds": acc_odds,
        "new_total_odds": str(acc_odds),
        "final_count": len(master_legs),
        "combined_probability": comb_prob,
        "avg_win_prob": round(sum(float(l.get("model_probability") or l.get("win_prob") or 0.75) for l in master_legs) / max(1, len(master_legs)), 2),
        "confidence_tier": "ELITE" if comb_prob > 0.25 else "HIGH",
        "recommended_stake_pct": 2.5,
        "approved_legs": master_legs,
        "final_selections": master_legs,
        "selections": master_legs,
        "booking_code": booking_code,
        "share_url": share_url or (f"https://www.sportybet.com/ng/?shareCode={booking_code}" if booking_code else None),
        "verification_status": "BOOKING_VERIFIED" if booking_code else "PENDING",
        "notice": f"Merged from {len(req.slips)} slips into {len(master_legs)} prioritized high-conviction games."
    }

    return {
        "status": "SUCCESS",
        "master_ticket": master_ticket
    }

