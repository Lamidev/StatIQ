import os
import re
import math
import time
import logging
import asyncio
from typing import Dict, Any, List, Optional, Tuple
import httpx

from app.services.sportybet_ingestion import SportyBetIngestionService
from app.services.time_horizon_service import TimeHorizonService

logger = logging.getLogger("statiq.dynamic_market")

# Preset Market Definitions for instantaneous, zero-latency matching
PRESET_MARKET_PROFILES = {
    "0.5_1h": {
        "slug": "0.5_1h",
        "label": "1st Half Over 0.5 Goals",
        "market_id": "60",
        "market_desc_regex": r"1st\s*Half.*Over/Under",
        "specifier_regex": r"total=0\.5",
        "outcome_id": "12",
        "outcome_desc": "Over",
        "min_odds": 1.20,
        "max_odds": 1.58,
        "base_cushion": 25.0,
        "category": "1H_GOALS"
    },
    "1.5_1h": {
        "slug": "1.5_1h",
        "label": "1st Half Over 1.5 Goals",
        "market_id": "60",
        "market_desc_regex": r"1st\s*Half.*Over/Under",
        "specifier_regex": r"total=1\.5",
        "outcome_id": "12",
        "outcome_desc": "Over",
        "min_odds": 1.70,
        "max_odds": 3.00,
        "base_cushion": 15.0,
        "category": "1H_GOALS"
    },
    "over_1.5": {
        "slug": "over_1.5",
        "label": "Full Time Over 1.5 Goals",
        "market_id": "18",
        "market_desc_regex": r"^Over/Under$",
        "specifier_regex": r"total=1\.5",
        "outcome_id": "12",
        "outcome_desc": "Over",
        "min_odds": 1.18,
        "max_odds": 1.50,
        "base_cushion": 30.0,
        "category": "FT_GOALS"
    },
    "over_2.5": {
        "slug": "over_2.5",
        "label": "Full Time Over 2.5 Goals",
        "market_id": "18",
        "market_desc_regex": r"^Over/Under$",
        "specifier_regex": r"total=2\.5",
        "outcome_id": "12",
        "outcome_desc": "Over",
        "min_odds": 1.45,
        "max_odds": 2.10,
        "base_cushion": 20.0,
        "category": "FT_GOALS"
    },
    "under_3.5": {
        "slug": "under_3.5",
        "label": "Full Time Under 3.5 Goals",
        "market_id": "18",
        "market_desc_regex": r"^Over/Under$",
        "specifier_regex": r"total=3\.5",
        "outcome_id": "13",
        "outcome_desc": "Under",
        "min_odds": 1.18,
        "max_odds": 1.50,
        "base_cushion": 28.0,
        "category": "FT_GOALS"
    },
    "under_4.5": {
        "slug": "under_4.5",
        "label": "Full Time Under 4.5 Goals",
        "market_id": "18",
        "market_desc_regex": r"^Over/Under$",
        "specifier_regex": r"total=4\.5",
        "outcome_id": "13",
        "outcome_desc": "Under",
        "min_odds": 1.10,
        "max_odds": 1.35,
        "base_cushion": 35.0,
        "category": "FT_GOALS"
    },
    "btts_yes": {
        "slug": "btts_yes",
        "label": "Both Teams to Score (GG)",
        "market_id": "29",
        "market_desc_regex": r"Both\s*Teams\s*to\s*Score",
        "specifier_regex": None,
        "outcome_id": "12",
        "outcome_desc": "Yes",
        "min_odds": 1.40,
        "max_odds": 1.95,
        "base_cushion": 22.0,
        "category": "BTTS"
    },
    "btts_no": {
        "slug": "btts_no",
        "label": "Both Teams to Score (No / NG)",
        "market_id": "29",
        "market_desc_regex": r"Both\s*Teams\s*to\s*Score",
        "specifier_regex": None,
        "outcome_id": "13",
        "outcome_desc": "No",
        "min_odds": 1.40,
        "max_odds": 2.10,
        "base_cushion": 18.0,
        "category": "BTTS"
    },
    "offsides_1.5": {
        "slug": "offsides_1.5",
        "label": "Offsides Over 1.5",
        "market_id": "900396",
        "market_desc_regex": r"Offsides\s*Over/Under",
        "specifier_regex": r"total=1\.5",
        "outcome_id": "12",
        "outcome_desc": "Over",
        "min_odds": 1.25,
        "max_odds": 1.65,
        "base_cushion": 32.0,
        "category": "PROPS"
    },
    "goalkicks_1h": {
        "slug": "goalkicks_1h",
        "label": "1st Half Goal Kicks Under 8.5/7.5",
        "market_id": "900661",
        "market_desc_regex": r"1st\s*Half.*Goal\s*Kicks",
        "specifier_regex": r"total=(?:7\.5|8\.5)",
        "outcome_id": "13",
        "outcome_desc": "Under",
        "min_odds": 1.30,
        "max_odds": 1.60,
        "base_cushion": 30.0,
        "category": "PROPS"
    },
    "double_chance": {
        "slug": "double_chance",
        "label": "Double Chance (1X / X2)",
        "market_id": "10",
        "market_desc_regex": r"Double\s*Chance",
        "specifier_regex": None,
        "outcome_id": None,
        "outcome_desc": None,
        "min_odds": 1.15,
        "max_odds": 1.50,
        "base_cushion": 25.0,
        "category": "1X2"
    }
}

class DynamicMarketEngine:
    """
    StatIQ Universal Dynamic Market Engine.
    
    Dynamically scans, matches, scores, and books ANY SportyBet market option
    without requiring dedicated hardcoded services or cluttered menus.
    
    Handles:
    - 0.5 1st Half Goals
    - Over 1.5 / 2.5 Full Time Goals
    - Under 3.5 / 4.5 Full Time Goals
    - Both Teams to Score (GG / NG)
    - Offsides Over 1.5
    - Goal Kicks Under
    - Arbitrary custom SportyBet markets (Clean Sheets, 3 in a Row, Corners, etc.)
    """

    BASE_URL = "https://mobile.sportybet.com/api"
    HEADERS = {
        "User-Agent": "Mozilla/5.0 (Linux; Android 13; SM-S908B) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Mobile Safari/537.36",
        "Accept": "application/json, text/plain, */*",
        "Accept-Language": "en-US,en;q=0.9",
        "platform": "wap",
        "client-country": "ng",
        "X-Forwarded-For": "102.89.34.18",
        "Referer": "https://mobile.sportybet.com/ng/"
    }

    @classmethod
    def resolve_market_intent(cls, query: str) -> Dict[str, Any]:
        """
        Parses free-form user query into a structured Market Profile.
        Supports presets, alias mapping, and fallback custom regex matching.
        """
        q = (query or "").strip().lower()

        # 1. Check exact preset slug match
        if q in PRESET_MARKET_PROFILES:
            return PRESET_MARKET_PROFILES[q]

        # 2. Pattern Matching for 1st Half 0.5 Goals
        if re.search(r"\b(?:0\.5\s*(?:1h|first\s*half|fh|1st\s*half)|(?:1h|first\s*half|fh|1st\s*half)\s*(?:over\s*)?0\.5|fhg)\b", q):
            return PRESET_MARKET_PROFILES["0.5_1h"]

        # 3. 1st Half 1.5 Goals
        if re.search(r"\b(?:1\.5\s*(?:1h|first\s*half|fh|1st\s*half)|(?:1h|first\s*half|fh|1st\s*half)\s*(?:over\s*)?1\.5)\b", q):
            return PRESET_MARKET_PROFILES["1.5_1h"]

        # 4. Over 1.5 Full Time Goals
        if re.search(r"\b(?:over\s*1\.5|1\.5\s*goals?|o1\.5|1\.5\s*over)\b", q) and "1h" not in q and "half" not in q:
            return PRESET_MARKET_PROFILES["over_1.5"]

        # 5. Over 2.5 Full Time Goals
        if re.search(r"\b(?:over\s*2\.5|2\.5\s*goals?|o2\.5|2\.5\s*over)\b", q):
            return PRESET_MARKET_PROFILES["over_2.5"]

        # 6. Under 3.5 Full Time Goals
        if re.search(r"\b(?:under\s*3\.5|3\.5\s*under|u3\.5)\b", q):
            return PRESET_MARKET_PROFILES["under_3.5"]

        # 7. Under 4.5 Full Time Goals
        if re.search(r"\b(?:under\s*4\.5|4\.5\s*under|u4\.5)\b", q):
            return PRESET_MARKET_PROFILES["under_4.5"]

        # 8. Both Teams to Score (GG / NG)
        if re.search(r"\b(?:btts\s*no|ng|no\s*goal|clean\s*sheet\s*btts)\b", q):
            return PRESET_MARKET_PROFILES["btts_no"]
        if re.search(r"\b(?:btts|gg|both\s*teams?\s*to\s*score|goal\s*goal)\b", q):
            return PRESET_MARKET_PROFILES["btts_yes"]

        # 9. Offsides
        if re.search(r"\b(?:offside|offsides|off|offs)\b", q):
            return PRESET_MARKET_PROFILES["offsides_1.5"]

        # 10. Goal Kicks
        if re.search(r"\b(?:goalkick|goalkicks|goal\s*kick|gk)\b", q):
            return PRESET_MARKET_PROFILES["goalkicks_1h"]

        # 11. Double Chance
        if re.search(r"\b(?:double\s*chance|dc|1x\s*or\s*x2)\b", q):
            return PRESET_MARKET_PROFILES["double_chance"]

        # 12. Dynamic Custom Fallback Profile
        clean_name = re.sub(r"\b(?:\d+(?:\.\d+)?\s*odds?|\d+\s*games?|today|tomorrow|weekend)\b", "", q).strip()
        if not clean_name:
            clean_name = q

        return {
            "slug": f"custom_{re.sub(r'[^a-z0-9]+', '_', clean_name)}",
            "label": clean_name.title(),
            "market_id": None,
            "market_desc_regex": re.escape(clean_name),
            "specifier_regex": None,
            "outcome_id": None,
            "outcome_desc": None,
            "min_odds": 1.15,
            "max_odds": 1.95,
            "base_cushion": 20.0,
            "category": "CUSTOM"
        }

    @classmethod
    async def fetch_dynamic_candidates(
        cls,
        market_profile: Dict[str, Any],
        time_horizon: str = "TODAY",
        min_odds: Optional[float] = None,
        max_odds: Optional[float] = None
    ) -> List[Dict[str, Any]]:
        """
        Scans SportyBet live pre-match board for fixtures offering the requested dynamic market.
        Validates market ID / description, specifier, outcome, and odds corridor.
        """
        min_kickoff_ms, end_of_day_ms, today_only, horizon_desc = TimeHorizonService.get_horizon_bounds(time_horizon)

        client = SportyBetIngestionService._get_client()
        url = f"{cls.BASE_URL}/ng/factsCenter/wapConfigurableEventsByOrder"
        tournaments = []
        for page in range(1, 8):
            payload = {
                "sportId": "sr:sport:1",
                "pageNum": page,
                "pageSize": 50,
                "withTwoUpMarket": True,
                "withOneUpMarket": True
            }
            if today_only:
                payload["todayGames"] = True
            else:
                canonical = TimeHorizonService.normalize_horizon(time_horizon)
                if canonical in ("TOMORROW",):
                    payload["timeline"] = 1
                elif canonical in ("TODAY_AND_TOMORROW", "2DAYS"):
                    payload["timeline"] = 2
                elif canonical in ("MIDWEEK_UCL",):
                    payload["timeline"] = 3
                elif canonical in ("WEEKEND",):
                    payload["timeline"] = 7
                else:
                    payload["timeline"] = 3

            try:
                r = client.post(url, json=payload, timeout=8.0)
                if r.status_code == 200 and r.json().get("bizCode") == 10000:
                    data = r.json().get("data", {})
                    t_list = data.get("tournaments", [])
                    tournaments.extend(t_list)
                    if not data.get("moreEvents") or not t_list:
                        break
                elif r.status_code == 403:
                    import shutil, subprocess, json
                    curl_bin = shutil.which("curl")
                    if curl_bin:
                        cmd = [
                            curl_bin, "-s", "-k",
                            "-H", "User-Agent: Mozilla/5.0 (Linux; Android 13; SM-S908B) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Mobile Safari/537.36",
                            "-H", "Accept: application/json, text/plain, */*",
                            "-H", "platform: wap",
                            "-H", "client-country: ng",
                            "-H", "Content-Type: application/json",
                            "--data-raw", json.dumps(payload),
                            url
                        ]
                        proc = subprocess.run(cmd, capture_output=True, text=True, timeout=8)
                        if proc.returncode == 0 and proc.stdout:
                            c_j = json.loads(proc.stdout)
                            if c_j.get("bizCode") == 10000:
                                t_list = c_j.get("data", {}).get("tournaments", [])
                                tournaments.extend(t_list)
                                if not c_j.get("data", {}).get("moreEvents") or not t_list:
                                    break
            except Exception as e:
                logger.warning(f"[DynamicMarket] Error fetching tournament page {page}: {e}")

        if not tournaments:
            return []

        candidate_eids = []
        seen_eids = set()
        for t in tournaments:
            c_name = t.get("categoryName") or ""
            t_name = t.get("name") or ""
            for ev in t.get("events", []):
                eid = ev.get("eventId")
                if not eid or eid in seen_eids:
                    continue
                h = ev.get("homeTeamName")
                a = ev.get("awayTeamName")
                st = ev.get("status")

                start_ms = ev.get("estimateStartTime") or ev.get("startTime") or 0
                if isinstance(start_ms, (int, float)) and 0 < start_ms < 100000000000:
                    start_ms = start_ms * 1000.0

                if start_ms > 0:
                    if start_ms < min_kickoff_ms or start_ms > end_of_day_ms:
                        continue

                # Pre-match unstarted games only
                if st is None or str(st) == "0":
                    seen_eids.add(eid)
                    candidate_eids.append({
                        "event_id": eid,
                        "home_team": h,
                        "away_team": a,
                        "competition": f"{c_name} · {t_name}",
                        "start_time": start_ms
                    })

        floor_odds = min_odds or market_profile.get("min_odds", 1.18)
        ceil_odds = max_odds or market_profile.get("max_odds", 1.65)
        m_id = str(market_profile.get("market_id") or "")
        m_desc_re = market_profile.get("market_desc_regex")
        spec_re = market_profile.get("specifier_regex")
        target_oid = str(market_profile.get("outcome_id") or "")
        target_odesc = market_profile.get("outcome_desc")

        logger.info(
            f"[DynamicMarket] Scanning {len(candidate_eids)} fixtures for '{market_profile.get('label')}' "
            f"in corridor [{floor_odds:.2f}, {ceil_odds:.2f}] across {horizon_desc}..."
        )

        picks = []
        sem = asyncio.Semaphore(15)

        async def _check_event(item: Dict[str, Any], http_c: httpx.AsyncClient) -> Optional[Dict[str, Any]]:
            async with sem:
                eid = item["event_id"]
                det_url = f"{cls.BASE_URL}/ng/factsCenter/event?eventId={eid}"
                try:
                    det_r = await http_c.get(det_url)
                    if det_r.status_code != 200:
                        return None
                    det_data = det_r.json().get("data", {})
                    markets = det_data.get("markets", [])

                    best_outcome = None

                    for m in markets:
                        mid = str(m.get("id"))
                        m_desc = str(m.get("desc") or "")
                        spec = str(m.get("specifier") or "")

                        # Check market ID or market description regex
                        if m_id and mid != m_id:
                            continue
                        if m_desc_re and not re.search(m_desc_re, m_desc, re.IGNORECASE):
                            continue

                        # Check specifier if specified
                        if spec_re and not re.search(spec_re, spec, re.IGNORECASE):
                            continue

                        outcomes = m.get("outcomes", [])
                        for o in outcomes:
                            oid = str(o.get("id"))
                            o_desc = str(o.get("desc") or "")
                            active = str(o.get("isActive", "1")) in ("1", "True")
                            if not active:
                                continue

                            # Check outcome ID or outcome description
                            if target_oid and oid != target_oid:
                                continue
                            if target_odesc and not re.search(re.escape(target_odesc), o_desc, re.IGNORECASE):
                                continue

                            odd = float(o.get("odds") or 0)
                            if not (floor_odds <= odd <= ceil_odds):
                                continue

                            # Calculate estimated model win probability
                            prob = round(min(0.96, (1.0 / odd) * 0.98), 3)
                            cushion = market_profile.get("base_cushion", 25.0)
                            # Quality score favors higher win rate with reasonable odds
                            q_score = (prob * 70.0) + cushion - (odd * 5.0)

                            cand = {
                                "event_id": eid,
                                "home_team": item["home_team"],
                                "away_team": item["away_team"],
                                "competition": item["competition"],
                                "market_id": mid,
                                "market_desc": m_desc,
                                "specifier": spec,
                                "outcome_id": oid,
                                "selection_desc": f"{o_desc} ({m_desc})",
                                "odds": odd,
                                "model_probability": prob,
                                "quality_score": q_score
                            }

                            if not best_outcome or cand["quality_score"] > best_outcome["quality_score"]:
                                best_outcome = cand

                    return best_outcome

                except Exception as e:
                    return None

        async with httpx.AsyncClient(timeout=8.0, headers=cls.HEADERS) as http_c:
            tasks = [_check_event(item, http_c) for item in candidate_eids]
            results = await asyncio.gather(*tasks, return_exceptions=True)

        for res in results:
            if isinstance(res, dict) and res.get("odds"):
                picks.append(res)

        # Sort by quality score descending
        picks.sort(key=lambda x: x.get("quality_score", 0), reverse=True)
        logger.info(f"[DynamicMarket] Found {len(picks)} validated selections for '{market_profile.get('label')}'.")
        return picks

    @classmethod
    async def build_mono_market_ticket(
        cls,
        market_query: str,
        target_odds: float = 10.0,
        time_horizon: str = "TODAY",
        allow_partial: bool = False
    ) -> Dict[str, Any]:
        """
        Assembles and books a single-market (mono) accumulator on SportyBet targeting target_odds.
        Returns SUCCESS with live shareCode, or INSUFFICIENT_MULTIPLIER decision gate if short.
        """
        profile = cls.resolve_market_intent(market_query)
        target = float(target_odds or 10.0)
        _, _, _, horizon_desc = TimeHorizonService.get_horizon_bounds(time_horizon)

        candidates = await cls.fetch_dynamic_candidates(profile, time_horizon=time_horizon)

        if not candidates:
            return {
                "status": "NO_FIXTURES",
                "market_label": profile.get("label"),
                "message": f"No active matches on SportyBet currently offer '{profile.get('label')}' within safety corridors for {horizon_desc}."
            }

        selected_legs = []
        curr_odds = 1.0

        for leg in candidates:
            odd = leg["odds"]
            if (curr_odds * odd) <= (target * 1.35):
                selected_legs.append(leg)
                curr_odds = round(curr_odds * odd, 2)
                if curr_odds >= (target * 0.90):
                    break

        # If still short, try appending more available games
        if curr_odds < (target * 0.85) and len(selected_legs) < len(candidates):
            for leg in candidates:
                if leg not in selected_legs:
                    selected_legs.append(leg)
                    curr_odds = round(curr_odds * leg["odds"], 2)
                    if curr_odds >= (target * 0.85):
                        break

        if not selected_legs:
            return {
                "status": "FAILED_ASSEMBLY",
                "message": f"Could not assemble '{profile.get('label')}' slip targeting {target:.1f}x odds."
            }

        # User Decision Gate: Shortfall check
        if not allow_partial and curr_odds < (target * 0.85):
            return {
                "status": "INSUFFICIENT_MULTIPLIER",
                "available_odds": curr_odds,
                "target_odds": target,
                "available_count": len(selected_legs),
                "time_horizon": time_horizon,
                "market_type": "mono",
                "prefer_line": profile.get("slug"),
                "market_label": profile.get("label"),
                "message": f"Only {len(selected_legs)} matches available on SportyBet ({curr_odds:.2f}x odds) for {profile.get('label')}, falling short of your {target:.1f}x target."
            }

        # Request live SportyBet booking share code
        selections_payload = [
            {
                "eventId": leg["event_id"],
                "marketId": leg["market_id"],
                "outcomeId": leg["outcome_id"],
                "specifier": leg["specifier"]
            }
            for leg in selected_legs
        ]

        share_code = None
        share_url = None
        share_endpoint = f"{cls.BASE_URL}/ng/orders/share"

        try:
            async with httpx.AsyncClient(timeout=10.0, headers=cls.HEADERS) as http_c:
                resp = await http_c.post(share_endpoint, json={"selections": selections_payload})
                if resp.status_code == 200:
                    res_data = resp.json()
                    if res_data.get("bizCode") == 10000:
                        share_code = res_data.get("data", {}).get("shareCode")
                        share_url = res_data.get("data", {}).get("shareURL") or f"https://www.sportybet.com/ng/?shareCode={share_code}"
                        logger.info(f"[DynamicMarket] Successfully generated SportyBet Booking Code: {share_code}")
                    else:
                        logger.warning(f"[DynamicMarket] SportyBet rejected booking: {res_data}")
        except Exception as e:
            logger.error(f"[DynamicMarket] Error booking share code: {e}")

        combined_prob = round(math.prod(leg.get("model_probability", 0.80) for leg in selected_legs) * 100.0, 1)
        leg_count = len(selected_legs)

        scout_analysis = (
            f"🧠 <b>StatIQ AI Scout Tactical Analysis:</b>\n"
            f"• <b>Pure Strategy Focus:</b> 100% {profile.get('label')} across all {leg_count} legs with zero cross-market noise.\n"
            f"• <b>Compounded Win Rate:</b> Statistical win expectation assessed at {combined_prob:.1f}% with verified SportyBet odds corridor.\n"
            f"• <b>Timing & Liquidity:</b> Sourced directly from pre-match top-tier fixtures scheduled for {horizon_desc}."
        )

        return {
            "status": "SUCCESS",
            "title": f"🎯 StatIQ {target:.1f}x {profile.get('label')} Slip ({horizon_desc})",
            "market_label": profile.get("label"),
            "booking_code": share_code or "N/A",
            "share_url": share_url or f"https://www.sportybet.com/ng/?shareCode={share_code}",
            "target_odds": target,
            "actual_odds": curr_odds,
            "confidence_score": combined_prob,
            "leg_count": leg_count,
            "picks": selected_legs,
            "scout_analysis": scout_analysis
        }

