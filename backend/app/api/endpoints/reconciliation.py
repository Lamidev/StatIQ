from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session
from typing import Dict, Any, List
from datetime import datetime, timezone
from app.db.session import get_db
from app.db.models import TrackedTicket, CanonicalFixture, FixtureProviderMapping
from app.evaluators.base import MatchStateContext
from app.evaluators.router import SettlementRouter
from app.providers.resolver import FixtureIdentityResolver

router = APIRouter()

@router.post("/reconcile")
def reconcile_all_tickets(db: Session = Depends(get_db)) -> Dict[str, Any]:
    """
    StatIQ V2.0 Historical Reconciliation & Repair Endpoint.
    Audits every tracked ticket using the structured settlement router and corrects any historical miscalculations.
    """
    tickets = db.query(TrackedTicket).all()
    repaired_tickets = []
    
    won_count = 0
    lost_count = 0
    running_count = 0

    for t in tickets:
        old_status = t.status
        loss_count = 0
        allowed_losses = t.allowed_losses or (1 if t.flex_cut in ("1-CUT", "1_CUT", "1") else 0)
        all_concluded = True
        updated_selections = []

        for sel in (t.selections or []):
            h = sel.get("home_team", "")
            a = sel.get("away_team", "")
            
            # Fetch scores
            h_score = sel.get("home_score")
            a_score = sel.get("away_score")
            ht_h = sel.get("ht_home_score")
            ht_a = sel.get("ht_away_score")
            tot_c = sel.get("total_corners")
            h_c = sel.get("home_corners")
            a_c = sel.get("away_corners")
            is_conc = sel.get("match_status") in ("CONCLUDED", "FINISHED", "FT", "ENDED", "COMPLETED")

            ctx = MatchStateContext(
                home_score=h_score,
                away_score=a_score,
                is_concluded=is_conc,
                is_live=bool(sel.get("is_live")),
                half_time_home_score=ht_h,
                half_time_away_score=ht_a,
                total_corners=tot_c,
                home_corners=h_c,
                away_corners=a_c,
                home_team=h,
                away_team=a
            )

            eval_res = SettlementRouter.evaluate(
                market_type=sel.get("market_type") or sel.get("market_name") or "",
                market_def=sel,
                ctx=ctx
            )

            sel["leg_status"] = eval_res.status
            sel["result"] = eval_res.result_text
            if eval_res.status == "LOST":
                loss_count += 1
            if eval_res.status not in ("WON", "LOST", "VOID"):
                all_concluded = False

            updated_selections.append(sel)

        t.selections = updated_selections
        t.loss_count = loss_count

        if loss_count > allowed_losses:
            new_status = "LOST"
        elif all_concluded and loss_count <= allowed_losses:
            new_status = "WON"
        else:
            new_status = "RUNNING"

        t.status = new_status
        if old_status != new_status:
            repaired_tickets.append({
                "ticket_id": t.id,
                "code": t.code,
                "old_status": old_status,
                "new_status": new_status,
                "potential_win": t.potential_win
            })

        if new_status == "WON": won_count += 1
        elif new_status == "LOST": lost_count += 1
        else: running_count += 1

    db.commit()

    return {
        "status": "SUCCESS",
        "total_tickets_audited": len(tickets),
        "repaired_count": len(repaired_tickets),
        "summary": {
            "won": won_count,
            "lost": lost_count,
            "running": running_count
        },
        "repaired_tickets": repaired_tickets
    }


@router.get("/tracking-health")
def get_tracking_health(db: Session = Depends(get_db)) -> Dict[str, Any]:
    """
    StatIQ V2.0 Tracking System Health Diagnostics.
    """
    running_tickets = db.query(TrackedTicket).filter(TrackedTicket.status == "RUNNING").count()
    canonical_fixtures = db.query(CanonicalFixture).count()
    live_fixtures = db.query(CanonicalFixture).filter(CanonicalFixture.status.in_(["LIVE", "HALFTIME", "SECOND_HALF"])).count()
    provider_mappings = db.query(FixtureProviderMapping).count()

    return {
        "status": "HEALTHY",
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "active_running_tickets": running_tickets,
        "total_canonical_fixtures": canonical_fixtures,
        "active_live_fixtures": live_fixtures,
        "total_provider_mappings": provider_mappings,
        "scheduler_active": True
    }


@router.post("/import-tickets")
def import_tickets_bulk(payload: Dict[str, Any], db: Session = Depends(get_db)) -> Dict[str, Any]:
    """
    StatIQ V2.0 Bulk Ticket Import & Cloud Seeding Endpoint.
    Idempotently inserts or updates an array of tracked tickets.
    """
    incoming = payload.get("tickets", [])
    if not isinstance(incoming, list):
        return {"status": "ERROR", "message": "Expected list of tickets in payload['tickets']"}

    imported_count = 0
    updated_count = 0

    for t_data in incoming:
        tid = t_data.get("id")
        if not tid:
            continue
            
        existing = db.query(TrackedTicket).filter(TrackedTicket.id == tid).first()
        if existing:
            existing.code = t_data.get("code", existing.code)
            existing.mode = t_data.get("mode", existing.mode)
            existing.target_odds = float(t_data.get("target_odds", existing.target_odds))
            existing.total_odds = float(t_data.get("total_odds", existing.total_odds))
            existing.stake = float(t_data.get("stake", existing.stake))
            existing.flex_cut = t_data.get("flex_cut", existing.flex_cut)
            existing.potential_win = float(t_data.get("potential_win", existing.potential_win))
            existing.status = t_data.get("status", existing.status)
            existing.created_at = t_data.get("created_at", existing.created_at)
            existing.locked_at_unix = int(t_data.get("locked_at_unix", existing.locked_at_unix))
            existing.selections = t_data.get("selections", existing.selections)
            existing.settled_at = t_data.get("settled_at", existing.settled_at)
            existing.flex_status_text = t_data.get("flex_status_text", existing.flex_status_text)
            existing.allowed_losses = t_data.get("allowed_losses", existing.allowed_losses)
            existing.loss_count = t_data.get("loss_count", existing.loss_count)
            existing.is_live = bool(t_data.get("is_live", existing.is_live))
            updated_count += 1
        else:
            new_ticket = TrackedTicket(
                id=tid,
                code=t_data.get("code", "CUSTOM"),
                mode=t_data.get("mode", "SWAP"),
                target_odds=float(t_data.get("target_odds", 1.5)),
                total_odds=float(t_data.get("total_odds", 1.5)),
                stake=float(t_data.get("stake", 100.0)),
                flex_cut=t_data.get("flex_cut"),
                potential_win=float(t_data.get("potential_win", 150.0)),
                status=t_data.get("status", "RUNNING"),
                created_at=t_data.get("created_at", ""),
                locked_at_unix=int(t_data.get("locked_at_unix", 0)),
                selections=t_data.get("selections", []),
                settled_at=t_data.get("settled_at"),
                flex_status_text=t_data.get("flex_status_text"),
                allowed_losses=t_data.get("allowed_losses"),
                loss_count=t_data.get("loss_count"),
                is_live=bool(t_data.get("is_live", False))
            )
            db.add(new_ticket)
            imported_count += 1

    db.commit()
    total_db_tickets = db.query(TrackedTicket).count()

    return {
        "status": "SUCCESS",
        "imported_new": imported_count,
        "updated_existing": updated_count,
        "total_tickets_in_database": total_db_tickets
    }

