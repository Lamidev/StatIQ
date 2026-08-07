from typing import Dict, Any, Optional, List
from fastapi import APIRouter
from pydantic import BaseModel

from app.services.gemini_service import GeminiAIService

router = APIRouter()
gemini_service = GeminiAIService()

class MatchExplainRequest(BaseModel):
    home_team: str = "Home Team"
    away_team: str = "Away Team"
    competition: str = "Premier League"
    prob_home_pct: float = 65.0
    prob_draw_pct: float = 20.0
    prob_away_pct: float = 15.0
    prob_over_2_5_pct: float = 55.0
    model_edge_pct: float = 7.5
    ev_pct: float = 12.0

class TicketAuditRequest(BaseModel):
    total_selections: int = 3
    items: list = []

class ChatRequest(BaseModel):
    question: str
    context: Optional[Dict[str, Any]] = None

class UniversalTicketSelection(BaseModel):
    home_team: str
    away_team: str
    league: str = "Unknown"
    selected_market: str  # e.g. "1X2", "Over/Under", "BTTS"
    selected_outcome: str  # e.g. "Home Win", "Over 2.5", "Yes"
    bookmaker_odds: Optional[float] = None

class UniversalAuditRequest(BaseModel):
    selections: List[UniversalTicketSelection]

@router.post("/explain-match")
def explain_match_insight(req: MatchExplainRequest):
    """
    Generates natural language match insights via Google AI Studio Gemini API.
    """
    insight = gemini_service.generate_match_explanation(req.model_dump())
    return {"status": "SUCCESS", "insight": insight}

@router.post("/audit-slip")
def audit_ticket_risk(req: TicketAuditRequest):
    """
    Generates natural language bet slip risk audits via Google AI Studio Gemini API.
    """
    audit = gemini_service.generate_ticket_audit_explanation(req.model_dump())
    return {"status": "SUCCESS", "audit_report": audit}

@router.post("/audit-ticket-universal")
def audit_ticket_universal(req: UniversalAuditRequest):
    """
    UNIVERSAL ticket re-editor — powered by Gemini AI.
    
    Accepts selections from ANY league worldwide (Turkish, Scottish, Greek, Saudi, etc.).
    Not limited to our football-data.org API subscription.
    
    Returns per-selection risk classification + safer alternative markets.
    """
    selections = [s.model_dump() for s in req.selections]
    result = gemini_service.audit_ticket_selections(selections)
    return result

@router.post("/chat")
def chat_with_matchiq_ai(req: ChatRequest):
    """
    Interactive 'Ask MatchIQ' AI Assistant.
    """
    reply = gemini_service.answer_chat_question(req.question, req.context)
    return {"status": "SUCCESS", "response": reply}
