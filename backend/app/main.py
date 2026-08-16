from typing import Optional
from fastapi import FastAPI, Depends
from fastapi.middleware.cors import CORSMiddleware
from app.api.endpoints.predictions import router as predictions_router
from app.api.endpoints.markets import router as markets_router
from app.api.endpoints.scenarios import router as scenarios_router
from app.api.endpoints.external import router as external_router
from app.api.endpoints.providers import router as providers_router
from app.api.endpoints.monitoring import router as monitoring_router
from app.api.endpoints.ai import router as ai_router
from app.api.endpoints.fixtures import router as fixtures_router
from app.api.endpoints.ticket_edit import router as ticket_edit_router
from app.api.endpoints.ticket_builder import router as ticket_builder_router
from app.api.endpoints.notifications import router as notifications_router
from app.api.endpoints.auth import router as auth_router
from app.db.session import engine
from app.db.models import Base

# Create DB tables if not exist
Base.metadata.create_all(bind=engine)

app = FastAPI(
    title="StatIQ — AI Football Prediction & Intelligence Platform API",
    description="Quantitative prediction engine producing market-independent probability distributions.",
    version="1.0.0"
)

# CORS Middleware
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Mount Routers
app.include_router(auth_router, prefix="/api/v1/auth", tags=["Passkey Authentication"])
app.include_router(predictions_router, prefix="/api/v1/predictions", tags=["Live Predictions"])
app.include_router(markets_router, prefix="/api/v1/markets", tags=["Market Analyzer"])
app.include_router(scenarios_router, prefix="/api/v1/scenarios", tags=["Scenario Builder"])
app.include_router(external_router, prefix="/api/v1/external", tags=["External Code Analyzer"])
app.include_router(providers_router, prefix="/api/v1/providers", tags=["Bookmaker Adapters"])
app.include_router(monitoring_router, prefix="/api/v1/monitoring", tags=["Production Validation & Monitoring"])
app.include_router(ai_router, prefix="/api/v1/ai", tags=["Google AI Studio Gemini Service"])
app.include_router(fixtures_router, prefix="/api/v1/fixtures", tags=["Match Fixtures"])
app.include_router(ticket_edit_router, prefix="/api/v1/ticket-edit", tags=["Ticket Re-Editor"])
app.include_router(ticket_builder_router, prefix="/api/v1/ai-ticket", tags=["AI Ticket Builder Engine"])
app.include_router(notifications_router, prefix="/api/v1/notifications", tags=["Win Notifications"])

from app.db.session import get_db
from sqlalchemy.orm import Session
from app.services.ticket_tracker import (
    lock_ticket,
    get_tracked_tickets,
    delete_tracked_ticket,
    evaluate_tracked_tickets,
    settle_ticket_with_scores,
    settle_all_with_scores,
    sync_tracked_tickets_with_live_apis,
)

# ─────────────────────────────────────────────────────────────────────────────
# Automatic background daemon polling worker
# ─────────────────────────────────────────────────────────────────────────────

@app.on_event("startup")
def start_background_ticket_sync_worker():
    import threading
    import time
    import gc

    def _auto_sync_loop():
        print("[TicketTrackerWorker] Dynamic live score polling daemon active (gentle background sync).")
        # Give server time to finish cold start and health checks before initial sync
        time.sleep(15)
        while True:
            try:
                sync_tracked_tickets_with_live_apis(db=None)
                gc.collect()
            except Exception as e:
                print("[TicketTrackerWorker] Auto-sync loop exception:", e)
            time.sleep(60)

    worker = threading.Thread(target=_auto_sync_loop, daemon=True)
    worker.start()



# ─────────────────────────────────────────────────────────────────────────────
# Ticket Tracker endpoints
# ─────────────────────────────────────────────────────────────────────────────

@app.post("/api/v1/ticket-tracker/lock")
def lock_staked_ticket(payload: dict, db: Session = Depends(get_db)):
    """Lock a re-edited ticket for tracking. Optionally pass final_scores to settle on lock."""
    return lock_ticket(payload, db=db)

@app.get("/api/v1/ticket-tracker/list")
def list_staked_tickets(profile_id: Optional[str] = None, db: Session = Depends(get_db)):
    """Return all tracked tickets immediately (< 2ms), auto-evaluating in-memory scores."""
    all_tickets = evaluate_tracked_tickets(db=db)
    clean_pid = (profile_id or "").strip().upper()
    admin_profiles = ("THISSLAMI1805", "THISSLAMI", "THISISLAMI", "DEFAULT", "ALL", "NULL", "UNDEFINED", "NONE", "")
    if not clean_pid or clean_pid in admin_profiles or "THISSLAMI" in clean_pid or "THISISLAMI" in clean_pid:
        return all_tickets
    
    # User-specific tickets + any global default tickets
    return [
        t for t in all_tickets 
        if str(t.get("profile_id", "DEFAULT")).upper() in (clean_pid, "DEFAULT", "ALL")
    ]

@app.post("/api/v1/ticket-tracker/sync-live-api")
def sync_live_tickets_endpoint(db: Session = Depends(get_db)):
    """
    Queues a live score sync in a background daemon thread.
    Returns immediately so it never blocks other endpoints like /decode.
    The sync will update tracked tickets DB table in the background.
    """
    import threading
    def _run_sync():
        try:
            sync_tracked_tickets_with_live_apis(db=None)
        except Exception as e:
            print("[SyncEndpoint] Background sync error:", e)

    t = threading.Thread(target=_run_sync, daemon=True)
    t.start()
    # Return current cached data immediately (< 2ms)
    return evaluate_tracked_tickets(db=db)

@app.delete("/api/v1/ticket-tracker/{ticket_id}")
def remove_staked_ticket(ticket_id: str, db: Session = Depends(get_db)):
    success = delete_tracked_ticket(ticket_id, db=db)
    return {"status": "SUCCESS" if success else "NOT_FOUND"}

@app.post("/api/v1/ticket-tracker/{ticket_id}/settle")
def settle_single_ticket(ticket_id: str, payload: dict, db: Session = Depends(get_db)):
    """
    Force-settle a specific ticket with known final scores.
    Body: { "fixture_scores": [{"fixture_id": "123", "home_score": 2, "away_score": 1}, ...] }
    """
    fixture_scores = payload.get("fixture_scores", [])
    result = settle_ticket_with_scores(ticket_id, fixture_scores, db=db)
    if result:
        return {"status": "SETTLED", "ticket": result}
    return {"status": "NOT_FOUND"}

@app.post("/api/v1/ticket-tracker/settle-all")
def settle_all_tickets(payload: dict, db: Session = Depends(get_db)):
    """
    Apply a batch of known final scores to ALL RUNNING tickets.
    Body: { "fixture_scores": [{"fixture_id": "123", "home_score": 2, "away_score": 1}, ...] }
    This is used by the Auditor UI to settle historical/expired-code tickets in bulk.
    """
    fixture_scores = payload.get("fixture_scores", [])
    tickets = settle_all_with_scores(fixture_scores, db=db)
    settled = [t for t in tickets if t.get("status") in ("WON", "LOST")]
    running = [t for t in tickets if t.get("status") == "RUNNING"]
    return {
        "status": "BATCH_SETTLED",
        "total_tickets": len(tickets),
        "settled_count": len(settled),
        "still_running": len(running),
        "tickets": tickets,
    }


@app.get("/")
def root():
    return {
        "status": "online",
        "system": "MatchIQ AI Prediction Platform",
        "version": "v1.0.0",
        "docs_url": "/docs"
    }
