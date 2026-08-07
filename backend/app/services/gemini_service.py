import os
import json
import re
from typing import Dict, Any, Optional, List
import httpx

class GeminiAIService:
    """
    MatchIQ Google AI Studio (Gemini LLM) Service.
    
    Two modes:
    1. Quantitative Analyst — reads MatchIQ model numbers, writes professional match previews.
    2. Universal Ticket Auditor — analyzes any match from ANY league worldwide using Gemini's
       own football knowledge. Not limited to football-data.org API leagues.
    """
    BASE_URL = "https://generativelanguage.googleapis.com/v1beta/models/gemini-1.5-flash:generateContent"

    def __init__(self, api_key: Optional[str] = None):
        self.api_key = api_key or os.getenv("GEMINI_API_KEY")

    def _call_gemini_api(self, prompt: str) -> str:
        if not self.api_key:
            return "Gemini API key not configured. Please set GEMINI_API_KEY in environment."

        url = f"{self.BASE_URL}?key={self.api_key}"
        payload = {
            "contents": [{
                "parts": [{"text": prompt}]
            }]
        }

        try:
            with httpx.Client(timeout=30.0) as client:
                resp = client.post(url, json=payload)
                if resp.status_code == 200:
                    data = resp.json()
                    candidates = data.get("candidates", [])
                    if candidates:
                        parts = candidates[0].get("content", {}).get("parts", [])
                        if parts:
                            return parts[0].get("text", "No response text generated.")
                return f"Gemini API returned status {resp.status_code}: {resp.text}"
        except Exception as e:
            return f"Gemini API connection error: {str(e)}"

    def generate_match_explanation(self, match_data: Dict[str, Any]) -> str:
        """
        Generates a natural language tactical preview for a match based on MatchIQ model numbers.
        """
        prompt = f"""
You are MatchIQ's Senior AI Quantitative Football Analyst.
Analyze the following quantitative prediction outputs and write a concise, professional, 2-paragraph match insight for the user.

Match Data:
- Home Team: {match_data.get('home_team', 'Home Team')}
- Away Team: {match_data.get('away_team', 'Away Team')}
- Competition: {match_data.get('competition', 'Domestic League')}
- Model Probabilities: Home Win {match_data.get('prob_home_pct', 50)}%, Draw {match_data.get('prob_draw_pct', 25)}%, Away Win {match_data.get('prob_away_pct', 25)}%
- Over 2.5 Goals Probability: {match_data.get('prob_over_2_5_pct', 50)}%
- Model Edge vs Bookmaker: +{match_data.get('model_edge_pct', 5.0)}%
- Expected Value (EV): +{match_data.get('ev_pct', 8.0)}% EV

Write a clean, insightful analysis explaining why MatchIQ identifies value or confidence on this match. Do not invent fake statistics.
"""
        return self._call_gemini_api(prompt)

    def audit_ticket_selections(self, selections: List[Dict[str, Any]]) -> Dict[str, Any]:
        """
        UNIVERSAL ticket auditor — analyzes any match from ANY league worldwide.
        Uses Gemini's own football knowledge for leagues not in our football-data.org API
        (e.g. Turkish Süper Lig, Scottish Premiership, Greek Super League, etc.).
        
        Returns structured JSON: risk per selection + safer alternatives.
        """
        selections_text = json.dumps(selections, indent=2)
        prompt = f"""
You are MatchIQ's Universal AI Ticket Auditor. You have deep knowledge of football across ALL leagues worldwide — Premier League, La Liga, Serie A, Bundesliga, Turkish Süper Lig, Scottish Premiership, Greek Super League, Belgian Pro League, MLS, Saudi Pro League, and any other league.

A user has submitted the following betting ticket for AI re-editing. For EACH selection, use your football knowledge to:
1. Estimate the realistic win probability (%) for the selected outcome by analyzing:
   - Team Structural Hierarchy & Squad Capability Gap (e.g. elite top-tier club vs lower-tier/mid-table club, squad depth & quality).
   - Historical Head-to-Head (H2H) dominance and past records between the two clubs.
   - Current form, home/away venue impact, and league standing structure.
2. Classify the risk: SAFE (>65% probability), MODERATE (50-65%), RISKY (35-50%), AVOID (<35%).
3. If the selection is RISKY or AVOID, suggest a SAFER alternative market or outcome for the same match (e.g. switch from "Away Win" to "Draw No Bet", or from "Home Win" to "Over 1.5 Goals" or "Double Chance 1X").

TICKET SELECTIONS:
{selections_text}

Respond ONLY with a valid JSON array — no explanation text, no markdown fences. Format:
[
  {{
    "index": 0,
    "home_team": "...",
    "away_team": "...",
    "league": "...",
    "selected_market": "...",
    "selected_outcome": "...",
    "estimated_probability": 72,
    "risk_level": "SAFE",
    "keep": true,
    "alternative_market": null,
    "alternative_outcome": null,
    "reasoning": "Brief 1-sentence explanation"
  }}
]
"""
        raw = self._call_gemini_api(prompt)
        # Parse the JSON from Gemini's response
        try:
            # Strip any markdown fences if present
            clean = re.sub(r"```(?:json)?", "", raw).strip().strip("`").strip()
            parsed = json.loads(clean)
            return {"status": "SUCCESS", "analyses": parsed, "total": len(parsed)}
        except Exception:
            return {"status": "PARTIAL", "raw_response": raw, "analyses": [], "total": 0}

    def generate_ticket_audit_explanation(self, ticket_data: Dict[str, Any]) -> str:
        """
        Generates a natural language risk audit for a user's bet slip.
        """
        prompt = f"""
You are MatchIQ's AI Bet Slip Auditor.
Review the following bet slip audit data and provide a concise 3-bullet risk summary for the user in plain English.

Ticket Audit Data:
- Total Selections: {ticket_data.get('total_selections', 0)}
- Selections Summary: {json.dumps(ticket_data.get('items', []), indent=2)}

Highlight strong value selections and warn about any WEAK selections (< 50% model probability).
"""
        return self._call_gemini_api(prompt)

    def answer_chat_question(self, user_question: str, context: Optional[Dict[str, Any]] = None) -> str:
        """
        Answers user questions in conversational assistant mode.
        """
        prompt = f"""
You are "Ask MatchIQ", an intelligent conversational football assistant powered by MatchIQ's calibrated quantitative engine.

User Question: {user_question}
Context Data: {json.dumps(context or {}, indent=2)}

Respond concisely, professionally, and accurately based on data.
"""
        return self._call_gemini_api(prompt)
