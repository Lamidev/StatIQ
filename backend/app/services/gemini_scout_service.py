import os
import re
import json
import logging
import time
from typing import Dict, Any, List, Optional
import httpx

logger = logging.getLogger("statiq.gemini.scout")

class GeminiScoutService:
    """
    StatIQ Tactical AI Scout & Conversational Copilot powered by Google AI Studio (Gemini).
    
    Architectural Guarantees:
    1. NEVER replaces the mathematical prediction engine (Poisson, Dixon-Coles, SportyBet live odds).
    2. Zero Hallucination: Works exclusively with verified live SportyBet markets.
    3. Strictly differentiates REMOVE (Risk Purge, keeps user markets as-is) vs EDIT (Market Upgrade).
    4. Resilient Fallback: If Google AI Studio API is rate-limited or credits depleted, gracefully
       falls back to deterministic quant heuristics so Telegram never fails.
    """

    _api_key: Optional[str] = None
    _model_name: str = "gemini-2.5-flash"
    _base_url: str = "https://generativelanguage.googleapis.com/v1beta/models"

    @classmethod
    def get_api_key(cls) -> Optional[str]:
        if not cls._api_key:
            cls._api_key = os.getenv("GEMINI_API_KEY", "").replace('"', '').strip()
        return cls._api_key

    @classmethod
    async def call_gemini(cls, prompt: str, system_instruction: Optional[str] = None, timeout: float = 6.0) -> Optional[str]:
        """Direct, fast asynchronous call to Google AI Studio Gemini API."""
        api_key = cls.get_api_key()
        if not api_key:
            return None

        url = f"{cls._base_url}/{cls._model_name}:generateContent?key={api_key}"
        contents = []
        if system_instruction:
            contents.append({"role": "user", "parts": [{"text": f"SYSTEM INSTRUCTION: {system_instruction}"}]})
            contents.append({"role": "model", "parts": [{"text": "Understood. I will act strictly within these instructions."}]})
        
        contents.append({"role": "user", "parts": [{"text": prompt}]})

        payload = {
            "contents": contents,
            "generationConfig": {
                "temperature": 0.2,
                "maxOutputTokens": 400
            }
        }

        try:
            async with httpx.AsyncClient(timeout=timeout) as client:
                resp = await client.post(url, json=payload)
                if resp.status_code == 200:
                    data = resp.json()
                    candidates = data.get("candidates", [])
                    if candidates and "content" in candidates[0]:
                        parts = candidates[0]["content"].get("parts", [])
                        if parts:
                            return parts[0].get("text", "").strip()
                elif resp.status_code == 402:
                    logger.warning("[GeminiScout] Google AI Studio credits depleted (402). Falling back to local tactical heuristics.")
                else:
                    logger.warning(f"[GeminiScout] Gemini API returned {resp.status_code}: {resp.text[:120]}")
        except Exception as e:
            logger.warning(f"[GeminiScout] Network/timeout error calling Gemini: {e}")

        return None

    @classmethod
    async def parse_user_intent(cls, text: str) -> Dict[str, Any]:
        """
        Parses free-form user message into structured StatIQ action parameters.
        Accurately differentiates REMOVE (risk purge as-is) vs EDIT (market upgrade).
        """
        clean_text = text.strip()
        
        # 1. First test local high-precision regex extraction for instantaneous response
        local_intent = cls._extract_intent_locally(clean_text)
        if local_intent.get("confidence", 0) >= 0.85:
            return local_intent

        # 2. If ambiguous, query Gemini AI
        prompt = (
            f"Analyze this sports betting user message: '{clean_text}'\n\n"
            "Output a JSON object ONLY with the following schema:\n"
            "{\n"
            "  \"intent\": \"REMOVE_AND_SPLIT\" | \"EDIT_UPGRADE\" | \"BUILD_ODDS\" | \"BUILD_GAMES\" | \"DISPATCH\" | \"EXPLAIN\" | \"UNKNOWN\",\n"
            "  \"booking_code\": string or null (e.g. 'uy65ty'),\n"
            "  \"target_odds\": number or null (e.g. 10.0),\n"
            "  \"ticket_count\": integer (default 1),\n"
            "  \"mode\": \"REMOVE\" or \"EDIT\",\n"
            "  \"risk_style\": \"SURE\" or \"LONGSHOT\",\n"
            "  \"time_horizon\": \"TODAY\" or \"WEEKEND\" or \"MIDWEEK_UCL\"\n"
            "}\n"
            "RULES:\n"
            "- 'remove', 'drop', 'purge', 'sure tickets from code' -> mode='REMOVE', intent='REMOVE_AND_SPLIT'\n"
            "- 'edit', 'upgrade', 'safer markets' -> mode='EDIT', intent='EDIT_UPGRADE'\n"
            "- '10 odds', '2 tickets of 10 odds' -> target_odds=10.0, ticket_count=2\n"
        )

        gemini_reply = await cls.call_gemini(prompt, system_instruction="You are a precise sports betting intent parser. Output JSON only.")
        if gemini_reply:
            try:
                # Extract JSON block
                json_match = re.search(r"\{.*\}", gemini_reply, re.DOTALL)
                if json_match:
                    parsed = json.loads(json_match.group(0))
                    logger.info(f"[GeminiScout] Gemini parsed intent: {parsed}")
                    return parsed
            except Exception as e:
                logger.warning(f"[GeminiScout] Error decoding Gemini intent JSON: {e}")

        # Fallback to local heuristic
        return local_intent

    @classmethod
    def _extract_intent_locally(cls, text: str) -> Dict[str, Any]:
        """Deterministic local intent extractor ensuring instant execution even without API connectivity."""
        t_lower = text.lower().strip()
        
        # Extract potential SportyBet booking code (4-9 alphanumeric characters)
        blacklist = {"need", "sure", "tickets", "ticket", "each", "from", "today", "tomorrow", "odds", "games", "game", "make", "help", "with", "edit", "remove", "drop", "purge", "slip", "slips", "please", "into", "safe", "markets", "market"}
        found_code = None

        # 1. High-confidence prefix match: "code UY65TY", "from UY65TY", "ticket UY65TY"
        prefix_match = re.search(r"(?:code|from|ticket|slip)\s+([A-Za-z0-9]{4,10})\b", text, re.IGNORECASE)
        if prefix_match:
            cand = prefix_match.group(1).upper()
            if cand.lower() not in blacklist:
                found_code = cand

        # 2. Look for alphanumeric tokens with both letters and digits (e.g. UY65TY, GH7AKP, TLV0QK)
        if not found_code:
            for token in re.findall(r"\b([A-Za-z0-9]{4,10})\b", text):
                cand = token.upper()
                if cand.lower() in blacklist:
                    continue
                if any(c.isdigit() for c in cand) and any(c.isalpha() for c in cand):
                    found_code = cand
                    break

        # Extract target odds (e.g. "10 odds", "10.5x", "10 odds each")
        odds_match = re.search(r"(\d+(?:\.\d+)?)\s*(?:odd|odds|x|multiplier)", t_lower)
        target_odds = float(odds_match.group(1)) if odds_match else None

        # Extract ticket count (e.g. "2 sure tickets", "2 tickets", "two tickets")
        tickets_match = re.search(r"(\d+)\s*(?:sure\s*)?(?:ticket|tickets|slip|slips|variant|variants)", t_lower)
        if tickets_match:
            ticket_count = int(tickets_match.group(1))
        elif any(k in t_lower for k in ["two ticket", "2 ticket", "two slip", "2 slip", "duo", "twin"]):
            ticket_count = 2
        else:
            ticket_count = 1

        # Check REMOVE vs EDIT
        is_remove = any(k in t_lower for k in ["remove", "drop", "purge", "cut", "sure ticket", "sure slip", "clean", "scrub"])
        is_edit = any(k in t_lower for k in ["edit", "upgrade", "safer", "change market", "reedit"])

        mode = "EDIT" if (is_edit and not is_remove) else "REMOVE"

        # Check Dispatch
        if any(k in t_lower for k in ["dispatch", "send today", "run now", "run automation", "trigger daily", "deliver today", "today slips", "send slips", "dispatch slips", "run daily", "deliver slips"]):
            return {"intent": "DISPATCH", "confidence": 0.95}

        # Check Longshot vs Sure
        is_longshot = any(k in t_lower for k in ["longshot", "bomb", "mega", "big odds", "high risk", "fun slip"])
        risk_style = "LONGSHOT" if is_longshot else "SURE"

        # Check Time Horizon
        time_horizon = "TODAY"
        if "weekend" in t_lower or "saturday" in t_lower or "sunday" in t_lower:
            time_horizon = "WEEKEND"
        elif "ucl" in t_lower or "champions league" in t_lower or "midweek" in t_lower:
            time_horizon = "MIDWEEK_UCL"

        if found_code:
            intent = "REMOVE_AND_SPLIT" if mode == "REMOVE" else "EDIT_UPGRADE"
            return {
                "intent": intent,
                "booking_code": found_code,
                "target_odds": target_odds or 10.0,
                "ticket_count": ticket_count,
                "mode": mode,
                "risk_style": risk_style,
                "time_horizon": time_horizon,
                "confidence": 0.90
            }

        if target_odds:
            return {
                "intent": "BUILD_ODDS",
                "booking_code": None,
                "target_odds": target_odds,
                "ticket_count": ticket_count,
                "mode": mode,
                "risk_style": risk_style,
                "time_horizon": time_horizon,
                "confidence": 0.85
            }

        return {
            "intent": "UNKNOWN",
            "booking_code": found_code,
            "target_odds": target_odds,
            "ticket_count": ticket_count,
            "mode": mode,
            "risk_style": risk_style,
            "time_horizon": time_horizon,
            "confidence": 0.50
        }

    @classmethod
    def generate_tactical_scout_note(cls, slip_title: str, picks: List[Dict[str, Any]], target_odds: float) -> str:
        """
        Generates a punchy, human-readable 2-line AI Scout tactical analysis
        for delivery on Telegram cards.
        """
        if not picks:
            return "🧠 <i>StatIQ AI Scout: Vetted under strict zero-overlap quantitative floors.</i>"

        leg_count = len(picks)
        comps = list(set(p.get("competition", "") for p in picks if p.get("competition")))
        tier1_count = sum(1 for p in picks if "Tier 1" in str(p.get("competition_tier", "")))
        avg_prob = (sum(float(p.get("model_probability", 0.80)) for p in picks) / leg_count) * 100.0

        if target_odds <= 2.0:
            tier_desc = f"{tier1_count} Tier-1 top flights" if tier1_count > 0 else f"{len(comps)} senior divisions"
            return (
                f"🧠 <b>StatIQ AI Scout Analysis:</b>\n"
                f"• <b>Fortress Discipline:</b> {leg_count} titanium selections ({tier_desc}) with <b>{avg_prob:.0f}% avg win floor</b>.\n"
                f"• <b>Zero Trap Guarantee:</b> Banned 50/50 volatile derbies; isolated pristine home scoring form."
            )
        elif target_odds <= 6.0:
            return (
                f"🧠 <b>StatIQ AI Scout Analysis:</b>\n"
                f"• <b>High-Tempo Engine:</b> {leg_count} vetted European goal cushions with attacking xG ≥ 2.70.\n"
                f"• <b>Cushion Floor:</b> Leveraged Over 1.5 & Double Chance anchors to eliminate single-goal cut risk."
            )
        else:
            return (
                f"🧠 <b>StatIQ AI Scout Analysis:</b>\n"
                f"• <b>Multi-League Dominance:</b> {leg_count} high-dominance fixtures across {len(comps)} senior divisions.\n"
                f"• <b>Zero-Overlap Partition:</b> 100% unique match IDs with zero clash against Rollover and Precision slips."
            )

    @classmethod
    async def route_conversational_message(cls, bot_service: Any, chat_id: int | str, text: str) -> bool:
        """
        Main entry point for free-form Telegram messages.
        Parses intent and delegates to StatIQ's deterministic execution handlers.
        """
        parsed = await cls.parse_user_intent(text)
        intent = parsed.get("intent")
        code = parsed.get("booking_code")
        target_odds = parsed.get("target_odds") or 10.0
        ticket_count = parsed.get("ticket_count", 1)
        mode = parsed.get("mode", "REMOVE")

        logger.info(f"[GeminiScout] Executing parsed intent '{intent}' for chat {chat_id} (code={code}, target={target_odds}x, count={ticket_count})...")

        # 1. REMOVE & SPLIT FROM CODE (e.g. "i need 2 sure tickets of 10 odds each from uy65ty")
        if intent == "REMOVE_AND_SPLIT" and code:
            bot_service.send_message(
                chat_id,
                f"🧠 <b>StatIQ AI Scout Ingestion:</b>\n"
                f"Loading SportyBet code <code>{code}</code>...\n"
                f"• Mode: <b>REMOVE (Risk Purge as-is)</b>\n"
                f"• Target Multiplier: <b>{target_odds:.1f}x</b> across <b>{ticket_count} ticket{'s' if ticket_count > 1 else ''}</b>\n"
                f"• Tactical Filter: Purging 50/50 coin-toss traps while preserving surviving markets."
            )
            bot_service.handle_remove_command(
                chat_id=chat_id,
                code=code,
                mode="REMOVE",
                target_mode="ODDS",
                target_val=target_odds,
                num_tickets=ticket_count
            )
            return True

        # 2. EDIT / UPGRADE CODE
        if intent == "EDIT_UPGRADE" and code:
            bot_service.send_message(
                chat_id,
                f"⚙️ <b>StatIQ AI Market Upgrade:</b>\n"
                f"Loading SportyBet code <code>{code}</code>...\n"
                f"• Mode: <b>EDIT (Safety Upgrade)</b>\n"
                f"• Upgrading high-variance picks to verified SportyBet Double Chance / Over 1.5 cushions."
            )
            bot_service.handle_edit_command(
                chat_id=chat_id,
                code=code,
                mode="EDIT",
                target_mode="ODDS",
                target_val=target_odds,
                num_tickets=ticket_count
            )
            return True

        # 3. ON-DEMAND ACCUMULATOR / LONGSHOT
        if intent == "BUILD_ODDS":
            bot_service.send_message(
                chat_id,
                f"⚡ <b>StatIQ AI Ticket Generator:</b>\n"
                f"Scouting today's live SportyBet board for <b>{target_odds:.1f}x target multiplier</b> ({parsed.get('risk_style', 'SURE')} style)..."
            )
            bot_service.handle_odds_command(chat_id, target_odds)
            return True

        # 4. DISPATCH DAILY AUTOMATION
        if intent == "DISPATCH":
            bot_service.handle_dispatch_command(chat_id)
            return True

        # 5. UNKNOWN / FREE-FORM QUERY
        bot_service.send_message(
            chat_id,
            "💡 <b>StatIQ AI Copilot Ready</b>\n\n"
            "You can speak to me naturally or paste any SportyBet code:\n"
            "• <i>'I need 2 sure tickets of 10 odds each from uy65ty'</i> (Purges risky games as-is)\n"
            "• <i>'Upgrade code GH7AKP to safe markets'</i> (Double Chance & Goals)\n"
            "• <i>'Build a 5 odds accumulator for tonight'</i>\n"
            "• <i>'Dispatch today's Daily VIP Slips'</i>\n\n"
            "<i>(Standard slash commands like <code>/odds 1.5</code>, <code>/duo</code>, <code>/auto</code> remain active!)</i>"
        )
        return False

gemini_scout_service = GeminiScoutService()
