from fastapi import FastAPI
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

from app.services.ticket_tracker import (
    lock_ticket,
    get_tracked_tickets,
    delete_tracked_ticket,
    evaluate_tracked_tickets,
    settle_ticket_with_scores,
    settle_all_with_scores,
)

# ─────────────────────────────────────────────────────────────────────────────
# Ticket Tracker endpoints
# ─────────────────────────────────────────────────────────────────────────────

@app.post("/api/v1/ticket-tracker/lock")
def lock_staked_ticket(payload: dict):
    """Lock a re-edited ticket for tracking. Optionally pass final_scores to settle on lock."""
    return lock_ticket(payload)

@app.get("/api/v1/ticket-tracker/list")
def list_staked_tickets():
    """Return all tracked tickets, auto-evaluating any that have stored scores."""
    return evaluate_tracked_tickets()

@app.delete("/api/v1/ticket-tracker/{ticket_id}")
def remove_staked_ticket(ticket_id: str):
    success = delete_tracked_ticket(ticket_id)
    return {"status": "SUCCESS" if success else "NOT_FOUND"}

@app.post("/api/v1/ticket-tracker/{ticket_id}/settle")
def settle_single_ticket(ticket_id: str, payload: dict):
    """
    Force-settle a specific ticket with known final scores.
    Body: { "fixture_scores": [{"fixture_id": "123", "home_score": 2, "away_score": 1}, ...] }
    """
    fixture_scores = payload.get("fixture_scores", [])
    result = settle_ticket_with_scores(ticket_id, fixture_scores)
    if result:
        return {"status": "SETTLED", "ticket": result}
    return {"status": "NOT_FOUND"}

@app.post("/api/v1/ticket-tracker/settle-all")
def settle_all_tickets(payload: dict):
    """
    Apply a batch of known final scores to ALL RUNNING tickets.
    Body: { "fixture_scores": [{"fixture_id": "123", "home_score": 2, "away_score": 1}, ...] }
    This is used by the Auditor UI to settle historical/expired-code tickets in bulk.
    """
    fixture_scores = payload.get("fixture_scores", [])
    tickets = settle_all_with_scores(fixture_scores)
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
