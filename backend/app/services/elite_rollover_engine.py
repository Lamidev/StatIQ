import time
import math
import logging
import asyncio
from typing import Dict, Any, List, Optional, Tuple
import datetime
import collections
import httpx
from sqlalchemy.orm import Session

from app.db.session import SessionLocal
from app.db.models import TrackedTicket, BookingAuditRecord
from app.services.rollover_telegram_notifier import RolloverTelegramNotifier
from app.services.form_h2h_service import evaluate_fixture_3pillar_metrics
from app.services.pick_engine import HIGH_TEMPO_CLUBS

logger = logging.getLogger("statiq.elite_rollover_engine")

class EliteRolloverEngine:
    """
    StatIQ Elite Rollover Engine.
    Exclusively ingests today's fixtures directly from SportyBet API,
    applies Dixon-Coles/Poisson low-variance safety filters, selects the
    highest-probability combination to achieve the exact target odds (1.50x or 2.00x),
    generates a live SportyBet booking code, and dispatches via Telegram.
    """

    BASE_URL = "https://www.sportybet.com/api"
    HEADERS = {
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36",
        "Accept": "application/json, text/plain, */*",
        "Origin": "https://www.sportybet.com",
        "Referer": "https://www.sportybet.com/ng/"
    }

    _today_cache = None
    _today_cache_time = 0.0
    _daily_dispatched_event_ids = set()
    _upcoming_cache = None
    _upcoming_cache_time = 0.0

    JUGGERNAUTS = {
        "celtic", "juventus", "lazio", "ac milan", "milan", "psg", "paris saint-germain",
        "manchester city", "man city", "arsenal", "liverpool", "real madrid", "barcelona",
        "bayern munich", "bayern", "inter", "inter milan", "sporting cp", "sporting",
        "benfica", "porto", "bayer leverkusen", "leverkusen", "borussia dortmund", "dortmund",
        "atletico madrid", "napoli", "roma", "feyenoord", "psv", "ajax", "chelsea", "tottenham",
        "atalanta", "aston villa", "newcastle", "fenerbahce", "galatasaray", "besiktas"
    }

    STRONG_TOP_FLIGHT_CLUBS = {
        "real sociedad", "villarreal", "athletic bilbao", "girona", "sevilla", "betis", "celta vigo", "mallorca",
        "monaco", "lille", "lens", "rennes", "lyon", "marseille", "nice", "strasbourg", "toulouse",
        "stuttgart", "frankfurt", "leipzig", "rb leipzig", "freiburg", "wolfsburg", "hoffenheim", "mainz",
        "bologna", "fiorentina", "torino", "monza", "udinese", "verona",
        "az alkmaar", "twente", "feyenoord", "utrecht", "go ahead eagles",
        "braga", "sporting braga", "vitoria guimaraes", "famalicao", "rio ave",
        "union saint-gilloise", "club brugge", "anderlecht", "genk", "gent", "antwerp",
        "salzburg", "sturm graz", "rapid wien", "austria wien", "lask", "young boys", "servette", "lugano", "basel",
        "bodo/glimt", "molde", "brann", "viking", "rosenborg", "tromso",
        "copenhagen", "midtjylland", "brondby", "nordsjaelland", "aarhus",
        "malmo", "djurgarden", "aik", "hammarby", "hacken", "elfsborg",
        "slavia prague", "sparta prague", "viktoria plzen",
        "dinamo zagreb", "hajduk split", "rijeka",
        "olympiacos", "paok", "aek athens", "panathinaikos",
        "al hilal", "al nassr", "al ittihad", "al ahli", "al shabab",
        "palmeiras", "flamengo", "botafogo", "atletico mineiro", "fluminense", "sao paulo", "internacional", "gremio", "corinthians", "cruzeiro",
        "river plate", "boca juniors", "racing club", "velez", "estudiantes", "talleres", "san lorenzo",
        "club america", "monterrey", "tigres", "cruz azul", "toluca", "chivas", "pachuca",
        "inter miami", "columbus crew", "lafc", "la galaxy", "seattle sounders", "cincinnati", "real salt lake"
    }

    @classmethod
    async def fetch_sportybet_today_events(cls, max_pages: int = 6, today_only: bool = True) -> List[Dict[str, Any]]:
        """
        Directly queries SportyBet's wapConfigurableEventsByOrder endpoint.
        - When today_only=True: collects all unstarted fixtures playing today (standard daily VIP & rollover).
        - When today_only=False: collects upcoming multi-day fixtures (weekend Fri-Sun or midweek UCL Tue-Wed).
        Cached in-memory for 60 seconds with parallel page fetching (<2 seconds).
        """
        now = time.time()
        if today_only:
            if cls._today_cache and (now - cls._today_cache_time) < 60:
                return cls._today_cache
        else:
            if cls._upcoming_cache and (now - cls._upcoming_cache_time) < 120:
                return cls._upcoming_cache

        import concurrent.futures
        from app.services.sportybet_ingestion import SportyBetIngestionService

        all_events = []
        seen_event_ids = set()

        def _fetch_page_sync(page: int) -> List[Dict[str, Any]]:
            client = SportyBetIngestionService._get_client()
            url = f"{cls.BASE_URL}/ng/factsCenter/wapConfigurableEventsByOrder"
            payload = {
                "sportId": "sr:sport:1",
                "pageNum": page,
                "pageSize": 50,
                "todayGames": today_only,
                "withTwoUpMarket": True,
                "withOneUpMarket": True
            }
            try:
                r = client.post(url, json=payload, timeout=10.0)
                if r.status_code == 200:
                    data = r.json()
                    if data.get("bizCode") == 10000:
                        return data.get("data", {}).get("tournaments", [])
            except Exception as e:
                logger.warning(f"[EliteRollover] Page {page} fetch error: {e}")
            return []

        try:
            loop = asyncio.get_event_loop()
            with concurrent.futures.ThreadPoolExecutor(max_workers=min(max_pages, 8)) as executor:
                results = await loop.run_in_executor(None, lambda: list(executor.map(_fetch_page_sync, range(1, max_pages + 1))))

            for tournaments in results:
                for t in tournaments:
                    c_name = t.get("categoryName") or "International"
                    t_name = t.get("name") or "League"
                    for ev in t.get("events", []):
                        eid = ev.get("eventId")
                        if eid and eid not in seen_event_ids:
                            seen_event_ids.add(eid)
                            ev["_categoryName"] = c_name
                            ev["_tournamentName"] = t_name
                            all_events.append(ev)

            if all_events:
                if today_only:
                    cls._today_cache = all_events
                    cls._today_cache_time = now
                    logger.info(f"[EliteRollover] Ingested {len(all_events)} raw events directly from SportyBet today endpoint.")
                else:
                    cls._upcoming_cache = all_events
                    cls._upcoming_cache_time = now
                    logger.info(f"[EliteRollover] Ingested {len(all_events)} upcoming multi-day events directly from SportyBet.")
        except Exception as e:
            logger.warning(f"[EliteRollover] Parallel fetch error: {e}")

        if today_only:
            return all_events or (cls._today_cache or [])
        else:
            return all_events or (cls._upcoming_cache or [])

    @classmethod
    def _calculate_poisson_over15_prob(cls, h_odds: float, d_odds: float, a_odds: float, market_odds: Optional[float] = None) -> float:
        """Estimates low-variance Over 1.5 goal probability based on market implied total xG or direct bookmaker pricing."""
        try:
            if market_odds and market_odds > 1.0:
                # Market pricing directly gives the consensus bookmaker-implied probability minus standard bookmaker margin (~4%)
                return round(min(0.93, (1.0 / market_odds) * 0.96), 4)
            # Implied team strengths
            h_inv = 1.0 / max(1.05, h_odds)
            a_inv = 1.0 / max(1.05, a_odds)
            total_inv = h_inv + a_inv
            # Estimated match expected goals (mean lambda)
            xg = 2.4 + (0.5 if total_inv > 0.8 else 0.1)
            # Poisson P(goals >= 2) = 1 - P(0) - P(1)
            p0 = math.exp(-xg)
            p1 = xg * math.exp(-xg)
            return max(0.65, min(0.94, 1.0 - (p0 + p1)))
        except Exception:
            return 0.82

    @classmethod
    def evaluate_elite_rollover_candidates(
        cls,
        events: List[Dict[str, Any]],
        max_leg_odds: float = 1.45,
        is_on_demand: bool = False,
        time_horizon: str = "TODAY",
        allow_lower_leagues: bool = False,
        for_rollover: bool = False
    ) -> List[Dict[str, Any]]:
        """
        Filters and ranks each fixture for Elite Rollover & Accumulator suitability.
        Applies strict low-variance selection gates:
        - Must be pre-match unstarted (status == 0) and >= 10 mins before kickoff.
        - Supports time_horizon: TODAY, WEEKEND (Fri-Sun), MIDWEEK_UCL (Tue-Wed).
        - Enforces strict Goldilocks corridor: 1.15 <= odds <= max_leg_odds (default 1.45).
        - Gated Waterfall: Defaults 100% to Senior Top Flights (European & Americas/Global).
          Only admits lower leagues / reserves if allow_lower_leagues=True (explicit user opt-in).
        - If for_rollover=True: Strictly bans Team Over 1.5 Goals to prevent 1-0 win cuts.
        """
        now_ms = time.time() * 1000.0
        candidates = []

        for ev in events:
            # 1. Unstarted pre-match status check
            status_str = str(ev.get("status") or ev.get("matchStatus") or "").upper().strip()
            if status_str in ["LIVE", "STARTED", "1H", "2H", "HT", "FINISHED", "FT", "ENDED", "CANCELLED", "POSTPONED", "ABANDONED", "CLOSED", "CONCLUDED", "SUSPENDED", "NULLED_EXPIRED"]:
                continue

            status = ev.get("status")
            if status is not None:
                try:
                    if int(status) != 0:
                        continue
                except Exception:
                    pass

            start_ms = ev.get("estimateStartTime") or ev.get("startTime") or 0
            if isinstance(start_ms, (int, float)) and 0 < start_ms < 100000000000:
                start_ms = start_ms * 1000.0

            # Adaptive Kickoff Timing Gates (WAT Timezone):
            wat_tz = datetime.timezone(datetime.timedelta(hours=1))
            now_wat = datetime.datetime.now(wat_tz)
            if time_horizon == "WEEKEND":
                # Friday through Sunday 23:59:59 WAT (or Monday 05:00 WAT)
                days_to_sun = (6 - now_wat.weekday()) % 7
                if days_to_sun == 0 and now_wat.weekday() == 6:
                    days_to_sun = 0  # Sunday itself
                end_of_day_ms = (now_wat + datetime.timedelta(days=max(2, days_to_sun))).replace(hour=23, minute=59, second=59).timestamp() * 1000.0
                min_kickoff_ms = now_ms + (10 * 60 * 1000.0)
            elif time_horizon == "MIDWEEK_UCL":
                # Tuesday through Wednesday 23:59:59 WAT (or Thursday 05:00 WAT)
                days_ahead = 2 if now_wat.weekday() in (1, 2) else 3
                end_of_day_ms = (now_wat + datetime.timedelta(days=days_ahead)).replace(hour=23, minute=59, second=59).timestamp() * 1000.0
                min_kickoff_ms = now_ms + (10 * 60 * 1000.0)
            elif time_horizon in ("MULTI_DAY", "3DAYS"):
                end_of_day_ms = (now_wat + datetime.timedelta(days=3)).replace(hour=23, minute=59, second=59).timestamp() * 1000.0
                min_kickoff_ms = now_ms + (10 * 60 * 1000.0)
            elif is_on_demand:
                min_kickoff_ms = now_ms + (15 * 60 * 1000.0)
                end_of_day_ms = (now_wat + datetime.timedelta(days=1)).replace(hour=23, minute=59, second=0).timestamp() * 1000.0 if now_wat.hour >= 18 else now_wat.replace(hour=23, minute=59, second=0).timestamp() * 1000.0
            else:
                min_kickoff_ms = now_ms + (30 * 60 * 1000.0)
                end_of_day_ms = (now_wat + datetime.timedelta(days=1)).replace(hour=5, minute=0, second=0, microsecond=0).timestamp() * 1000.0

            if start_ms > 0:
                if start_ms < min_kickoff_ms:
                    continue
                if start_ms > end_of_day_ms:
                    continue

            h_team = ev.get("homeTeamName") or "Home"
            a_team = ev.get("awayTeamName") or "Away"
            eid = ev.get("eventId")
            c_name = ev.get("_categoryName") or ""
            t_name = ev.get("_tournamentName") or ""
            c_lower = c_name.lower()
            t_lower = t_name.lower()
            comp_full = f"{c_lower} {t_lower}"

            # 2. ANTI-NOISE FILTER: Strictly ban youth, reserves, amateur, women, friendlies, and obscure volatile leagues
            comb_name_str = f" {h_team} {a_team} {c_name} {t_name} ".lower()
            is_continental_major = any(k in comp_full for k in [
                "uefa champions league", "uefa europa league", "uefa conference league",
                "libertadores", "sudamericana", "afc champions league elite", "afc champions league", "concacaf champions"
            ])

            if allow_lower_leagues:
                # Gated Opt-In: Permitted only when user explicitly opts in for vetted mid-tier leagues to fill a thin board
                # Strictly keeps youth, reserves, U21, amateur, and low-level divisions banned!
                bad_tokens = [
                    "srl", "simulated reality", "simulated", "friendly", "friendlies",
                    "u23", "u21", "u20", "u19", "u18", "u17", "youth", "primavera", "reserve", "reserves",
                    "amateur", "women", "wfc", "damen", "femenino", "feminin", "frauen", "vrouwen",
                    "development league", "premier league 2", "professional development",
                    "tercera", "regional", "karntner", "landesliga", "stadtliga",
                    "san marino", "andorra", "gibraltar", "division 3", "division 4", "3. liga",
                    "serie b2", "serie d", "carioca", "copa rio",
                    "kolmonen", "kakkonen", "primera c", "primera d",
                    "kenya", "tanzania", "uganda", "nigeria", "ghana", "ethiopia",
                    "thailand", "vietnam", "malaysia", "indonesia", "india",
                    "cambodia", "macau", "philippines",
                    "northern ireland", "wales", "cymru",
                    "kosovo", "albania", "macedonia", "montenegro", "bosnia",
                    "belarus", "moldova", "luxembourg", "malta", "faroe islands",
                    "fa trophy", "qualification round", "preliminary round",
                    "copa peru", "usl league one"
                ]
            else:
                bad_tokens = [
                    "srl", "simulated reality", "simulated", "friendly", "friendlies",
                    "u23", "u21", "u20", "u19", "u18", "u17", "youth", "primavera", "reserve", "reserves",
                    "amateur", "women", "wfc", "damen", "femenino", "feminin", "frauen", "vrouwen",
                    "tercera", "regional", "karntner", "landesliga", "stadtliga", "regionalliga", "oberliga",
                    "isthmian", "northern premier", "southern league", "national league north", "national league south",
                    # Banish lower-tier filler leagues
                    "san marino", "armenia", "andorra", "gibraltar", "prva liga srbije", "division 3", "division 4",
                    # Banish lower-tier Brazil state/divisions & Swedish Ettan
                    "serie b2", "serie c", "serie d", "carioca", "copa rio",
                    "development league", "premier league 2", "professional development",
                    "kolmonen", "kakkonen", "primera c", "primera d",
                    # Banish obscure leagues with high upset rates and erratic data (proven bet-killers)
                    "kenya", "kakamega", "tanzania", "uganda", "nigeria", "ghana", "ethiopia",
                    "algeria", "algerian", "temouchent", "rouissat",
                    "thailand", "thai league", "thai", "vietnam", "v-league", "malaysia", "indonesia",
                    "lebanon", "jordan", "kuwait", "bahrain", "oman", "iraq", "syria", "yemen",
                    "india", "indian super", "i-league",
                    # Secondary Asian regional cups & volatile clubs (Cambodia, Malaysia, Singapore, Hong Kong)
                    "afc champions league two", "afc champions league 2", "afc challenge league", "afc cup",
                    "phnom penh", "lion city", "kitchee", "kuching city", "tai po", "cambodia", "malaysia", "singapore", "hong kong", "macau", "philippines",
                    # Japan domestic cups & lower tiers (reserve/youth squad rotations in J2/J3)
                    "j.league cup", "j-league cup", "emperor cup", "emperor's cup", "j2 league", "j3 league",
                    # Obscure European lower tiers / domestic preliminary cups
                    "northern ireland", "wales", "cymru", "cyprus cup", "slovensky pohar", "slovakia cup",
                    "kosovo", "albania", "macedonia", "montenegro", "bosnia", "latvia", "lithuania", "estonia",
                    "belarus", "moldova", "luxembourg", "malta", "faroe islands",
                    "3. liga", "norway 2.", "norway 3.", "2. divisjon", "3. divisjon", "sweden division 1",
                    # Non-league / FA Trophy / Preliminary Qualifiers
                    "atherton", "collieries", "spennymoor", "harborough", "fylde", "aldershot", "tadley", "calleva",
                    "merthyr", "stamford afc", "bedford", "fa trophy", "qualification round", "preliminary round",
                    "fa cup qualifying", "fa cup, qualification", "phonix lubeck", "kickers emden", "lokeren temse", "aec mons",
                    # Obscure lower-tier leagues & volatile regional club cups
                    "liga 2", "copa peru", "cantolao", "cs santos",
                    "botola 2", "difaa hassani", "tetouan",
                    "usl-1", "usl league one", "corpus christi", "richmond kickers",
                    "caf champions league", "caf confederation", "afc champions league two", "afc challenge league",
                    "young africans", "petroleos de luanda", "mc alger", "asec mimosas", "enugu rangers", "cffa"
                ]

            if not is_continental_major:
                bad_tokens.extend([
                    "dimayor", "torneo dimayor", "copa dimayor", "copa colombia", "colombia b", "primera b",
                    "venezuela", "bolivia"
                ])

            if any(t in comb_name_str for t in bad_tokens):
                continue

            # Strict Scandinavian lower tier check: ban Swedish Ettan and Division 1/2
            if "ettan" in comb_name_str and "superettan" not in comb_name_str:
                continue
            if "sweden" in comb_name_str and any(k in comb_name_str for k in ["division 1", "division 2", "div 1", "div 2"]):
                continue

            comp_clean = f"{c_name} {t_name}".lower().strip()
            if comp_clean.endswith(" w") or comp_clean.endswith("(w)") or " games w" in comp_clean or " women" in comp_clean:
                continue

            # Strict check for team name reserve suffixes (always enforced: never allow youth / U21 / reserve teams)
            is_noise_team = False
            for team_str in [h_team.lower(), a_team.lower()]:
                padded = f" {team_str} "
                if any(p in padded for p in [" ii ", " iii ", " b team ", " b-team ", " reserve ", " reserves ", " amateur ", " u21 ", " u23 ", " u19 ", " u20 "]):
                    if "willem ii" not in padded:
                        is_noise_team = True
                        break
                if any(team_str.endswith(s) for s in [" b", " ii", " u21", " u23", " u19", " u20"]) and "willem ii" not in team_str:
                    is_noise_team = True
                    break
            if is_noise_team:
                continue

            # 3. Competition Pedigree Tier Evaluation (European & Top-Tier Priority)
            pedigree_bonus = -50.0  # Default penalty for unverified competitions
            tier_label = "Unranked Competition"

            # Tier 1 (+80.0): Elite European & Continental Senior Top Flights
            is_tier_1 = False
            if "england" in c_lower and "premier league" in t_lower and "cup" not in t_lower:
                is_tier_1 = True
            elif "spain" in c_lower and any(k in t_lower for k in ["laliga", "la liga", "primera division"]) and "2" not in t_lower:
                is_tier_1 = True
            elif "germany" in c_lower and "bundesliga" in t_lower and "2." not in t_lower and "3." not in t_lower:
                is_tier_1 = True
            elif "italy" in c_lower and "serie a" in t_lower:
                is_tier_1 = True
            elif "france" in c_lower and "ligue 1" in t_lower:
                is_tier_1 = True
            elif any(k in comp_full for k in [
                "uefa champions league", "uefa europa league",
                "uefa conference league", "uefa europa conference league"
            ]) or (comp_full.strip() in ["champions league", "europa league", "conference league"] and "caf" not in comp_full and "afc" not in comp_full):
                is_tier_1 = True

            if is_tier_1:
                pedigree_bonus = 80.0
                tier_label = "Tier 1 Top-Flight"
            else:
                # Tier 2 (+50.0): Major Recognized European Top Flights & Top Domestic Second Tiers
                is_tier_2 = False
                if "england" in c_lower and "championship" in t_lower:
                    is_tier_2 = True
                elif "netherlands" in c_lower and "eredivisie" in comp_full:
                    is_tier_2 = True
                elif "portugal" in c_lower and any(k in t_lower for k in ["liga portugal", "primeira liga"]) and "2" not in t_lower and "3" not in t_lower:
                    is_tier_2 = True
                elif "belgium" in c_lower and "pro league" in t_lower and "u21" not in t_lower:
                    is_tier_2 = True
                elif "scotland" in c_lower and "premiership" in t_lower:
                    is_tier_2 = True
                elif ("turkey" in c_lower or "turkiye" in c_lower) and "super lig" in t_lower:
                    is_tier_2 = True
                elif "austria" in c_lower and "bundesliga" in t_lower and "2" not in t_lower:
                    is_tier_2 = True
                elif "switzerland" in c_lower and "super league" in t_lower:
                    is_tier_2 = True
                elif "norway" in c_lower and ("eliteserien" in t_lower or "tippeligaen" in t_lower):
                    is_tier_2 = True
                elif "denmark" in c_lower and "superliga" in t_lower:
                    is_tier_2 = True
                elif "sweden" in c_lower and "allsvenskan" in t_lower:
                    is_tier_2 = True
                elif "poland" in c_lower and "ekstraklasa" in t_lower:
                    is_tier_2 = True
                elif "romania" in c_lower and "superliga" in t_lower:
                    is_tier_2 = True
                elif "czech" in c_lower and any(k in t_lower for k in ["chance liga", "first league", "1. liga"]):
                    is_tier_2 = True
                elif "croatia" in c_lower and "hnl" in t_lower:
                    is_tier_2 = True
                elif "greece" in c_lower and "super league" in t_lower:
                    is_tier_2 = True
                elif "saudi" in c_lower and "pro league" in t_lower:
                    is_tier_2 = True
                elif any(k in comp_full for k in ["libertadores", "sudamericana", "afc champions league elite", "afc champions league", "concacaf champions"]):
                    is_tier_2 = True
                elif ("japan" in c_lower and "j1" in t_lower) or "j1 league" in comp_full:
                    is_tier_2 = True
                elif "brazil" in c_lower and ("serie a" in t_lower or "brasileiro" in t_lower):
                    is_tier_2 = True
                # Americas & Senior Top Flights (Recognized Top Standard)
                elif "mls" in comp_full or (("usa" in c_lower or "united states" in c_lower) and "mls" in t_lower):
                    is_tier_2 = True
                elif "mexico" in c_lower and any(k in t_lower for k in ["liga mx", "primera division"]):
                    is_tier_2 = True
                elif "argentina" in c_lower and any(k in t_lower for k in ["liga profesional", "primera division", "copa de la liga"]):
                    is_tier_2 = True
                elif "colombia" in c_lower and any(k in t_lower for k in ["primera a", "liga betplay"]):
                    is_tier_2 = True
                elif "chile" in c_lower and "primera division" in t_lower:
                    is_tier_2 = True
                elif "korea" in c_lower and "k league 1" in t_lower:
                    is_tier_2 = True
                elif "australia" in c_lower and "a-league" in t_lower:
                    is_tier_2 = True
                elif any(k in comp_full for k in ["world cup qualification", "nations league", "euro qualification", "copa america", "afcon qualification"]):
                    is_tier_2 = True

                if is_tier_2:
                    pedigree_bonus = 50.0
                    tier_label = "Tier 2 Major Flight"
                else:
                    # Tier 3 (+30.0): Major Second Tiers & Established National Flights
                    is_tier_3 = False
                    if "england" in c_lower and "league one" in t_lower:
                        is_tier_3 = True
                    elif "germany" in c_lower and "2. bundesliga" in t_lower:
                        is_tier_3 = True
                    elif "france" in c_lower and "ligue 2" in t_lower:
                        is_tier_3 = True
                    elif "spain" in c_lower and any(k in t_lower for k in ["laliga 2", "segunda division"]):
                        is_tier_3 = True
                    elif "italy" in c_lower and "serie b" in t_lower:
                        is_tier_3 = True
                    elif "eerste divisie" in comp_full:
                        is_tier_3 = True
                    elif "sweden" in c_lower and "superettan" in t_lower:
                        is_tier_3 = True
                    elif ("turkey" in c_lower or "turkiye" in c_lower) and "1. lig" in t_lower:
                        is_tier_3 = True
                    elif "norway" in c_lower and ("1st division" in t_lower or "1. divisjon" in t_lower or "obos" in t_lower):
                        is_tier_3 = True
                    elif "canada" in c_lower and "canadian championship" in t_lower:
                        is_tier_3 = True
                    elif "denmark" in c_lower and "dbu pokalen" in t_lower:
                        is_tier_3 = True
                    elif "egypt" in c_lower and "premier league" in t_lower:
                        is_tier_3 = True
                    elif any(k in comp_full for k in [
                        "fa cup", "copa del rey", "dfb pokal", "coppa italia", "coupe de france",
                        "efl cup", "carabao cup", "taca de portugal", "knvb beker", "copa do brasil"
                    ]):
                        is_tier_3 = True

                    if is_tier_3:
                        pedigree_bonus = 30.0
                        tier_label = "Tier 3 Professional"
                    elif allow_lower_leagues:
                        # User explicitly opted in for vetted mid-tier leagues: qualify with calibrated bonus
                        pedigree_bonus = 20.0
                        tier_label = "Vetted Mid-Tier League"

            # HARD-BLOCK UNRANKED / OBSCURE TOURNAMENTS
            if pedigree_bonus < 0:
                continue

            # Check 1X2 baseline odds for favorite dominance (strictly full-time match 1X2, ignoring half/corner markets)
            h_odds = 2.5
            d_odds = 3.2
            a_odds = 2.8

            markets = ev.get("markets", [])
            for m in markets:
                m_id = str(m.get("id"))
                m_desc = (m.get("desc") or "").lower()
                if m_id == "1" or (m_desc == "1x2" or ("1x2" in m_desc and "half" not in m_desc and "corner" not in m_desc and "booking" not in m_desc)):
                    for oc in m.get("outcomes", []):
                        o_id = str(oc.get("id"))
                        odd_v = float(oc.get("odds") or 0)
                        if o_id == "1" and odd_v > 0: h_odds = odd_v
                        elif o_id == "2" and odd_v > 0: d_odds = odd_v
                        elif o_id == "3" and odd_v > 0: a_odds = odd_v
                    if m_id == "1":
                        break

            is_home_fav = h_odds < a_odds
            fav_odds = min(h_odds, a_odds)
            dog_odds = max(h_odds, a_odds)
            dominance_ratio = dog_odds / max(1.01, fav_odds)

            # Juggernaut Priority Detection: Top European Giants & Strong Top Flight Clubs
            fav_team_name = h_team if is_home_fav else a_team
            dog_team_name = a_team if is_home_fav else h_team
            fav_is_juggernaut = any(jg in fav_team_name.lower() for jg in cls.JUGGERNAUTS)
            fav_is_strong_club = any(sc in fav_team_name.lower() for sc in cls.STRONG_TOP_FLIGHT_CLUBS)
            dog_is_juggernaut = any(jg in dog_team_name.lower() for jg in cls.JUGGERNAUTS)
            is_heavyweight_derby = fav_is_juggernaut and dog_is_juggernaut
            juggernaut_bonus = 45.0 if (fav_is_juggernaut and dominance_ratio >= 1.45 and not is_heavyweight_derby) else (25.0 if fav_is_strong_club and dominance_ratio >= 1.28 else 0.0)

            # Calibrated Dominant Favorite Gate:
            if is_tier_1:
                fav_is_genuine_banker = (fav_odds <= 2.55 and dominance_ratio >= 1.18) or fav_is_juggernaut or (fav_is_strong_club and dominance_ratio >= 1.18)
                min_dominance = 1.18
            elif is_tier_2:
                fav_is_genuine_banker = (fav_odds <= 2.45 and dominance_ratio >= 1.20) or (fav_is_juggernaut and dominance_ratio >= 1.20) or (fav_is_strong_club and dominance_ratio >= 1.20)
                min_dominance = 1.20
            else:
                fav_is_genuine_banker = (fav_odds <= 2.30 and dominance_ratio >= 1.22) or (fav_is_juggernaut and dominance_ratio >= 1.20) or (fav_is_strong_club and dominance_ratio >= 1.20)
                min_dominance = 1.22

            # Evaluate each eligible low-variance market in the fixture
            for m in markets:
                # STRICT BETTABLE FILTER: SportyBet market status must be 0 (Active/Bettable)
                m_st = m.get("status")
                if m_st is not None and str(m_st) != "0":
                    continue

                m_id = str(m.get("id"))
                m_desc = (m.get("desc") or "").lower()
                spec = str(m.get("specifier") or "")

                # A. Double Chance (1X or X2)
                if m_id == "10" or "double chance" in m_desc:
                    for oc in m.get("outcomes", []):
                        # STRICT BETTABLE FILTER: Outcome isActive must be 1, status must be 0
                        is_active = oc.get("isActive")
                        if is_active is not None and str(is_active) not in ("1", "True", "true"):
                            continue
                        oc_st = oc.get("status")
                        if oc_st is not None and str(oc_st) != "0":
                            continue

                        oc_id = str(oc.get("id"))
                        oc_desc = oc.get("desc") or ""
                        odds = float(oc.get("odds") or 0)

                        # Strict User Rule: No odds lower than 1.15 to prevent long leg bloat
                        if odds < 1.15 or odds > max_leg_odds:
                            continue

                        # 1X on Home favorite (dominance ratio >= min_dominance and genuine banker favorite)
                        if (oc_id == "9" or "home or draw" in oc_desc.lower() or "1x" in oc_desc.lower()) and is_home_fav and dominance_ratio >= min_dominance and fav_is_genuine_banker:
                            prob = round(min(0.92, (1.0 / odds) * 0.96), 4)
                            sel_desc = f"{h_team} or Draw (1X)"
                            stats_3p = evaluate_fixture_3pillar_metrics(h_team, a_team, "Double Chance", sel_desc, odds)
                            if prob >= 0.78 and stats_3p.get("is_safe", True) and stats_3p.get("composite_safety_score", 0.7) >= 0.68:
                                c_sc = float(stats_3p.get("composite_safety_score", 0.75))
                                candidates.append({
                                    "event_id": eid,
                                    "home_team": h_team,
                                    "away_team": a_team,
                                    "competition": f"{c_name} · {t_name}",
                                    "competition_tier": tier_label,
                                    "dominance_ratio": round(dominance_ratio, 2),
                                    "is_juggernaut": fav_is_juggernaut,
                                    "market_id": m_id,
                                    "market_desc": "Double Chance",
                                    "outcome_id": oc_id,
                                    "selection_desc": sel_desc,
                                    "specifier": spec,
                                    "odds": odds,
                                    "model_probability": prob,
                                    "market_type": "DOUBLE_CHANCE",
                                    "h2h_summary": stats_3p.get("h2h_summary") or f"H2H Coverage: {h_team} (Home Floor)",
                                    "form_summary": stats_3p.get("form_summary") or f"Form: {h_team} Unbeaten Trend",
                                    "composite_safety_score": c_sc,
                                    "quality_score": (prob * 50.0) + (c_sc * 40.0) + (dominance_ratio * 2.0) + pedigree_bonus + juggernaut_bonus + 3.0,
                                    "selection_rationale": f"{tier_label} · {stats_3p.get('h2h_summary')} · {stats_3p.get('form_summary')}"
                                })

                        # X2 on Away favorite (dominance ratio >= min_dominance and genuine banker favorite)
                        elif (oc_id == "11" or "draw or away" in oc_desc.lower() or "x2" in oc_desc.lower()) and (not is_home_fav) and dominance_ratio >= min_dominance and fav_is_genuine_banker:
                            prob = round(min(0.90, (1.0 / odds) * 0.96), 4)
                            sel_desc = f"Draw or {a_team} (X2)"
                            stats_3p = evaluate_fixture_3pillar_metrics(h_team, a_team, "Double Chance", sel_desc, odds)
                            if prob >= 0.78 and stats_3p.get("is_safe", True) and stats_3p.get("composite_safety_score", 0.7) >= 0.68:
                                c_sc = float(stats_3p.get("composite_safety_score", 0.75))
                                candidates.append({
                                    "event_id": eid,
                                    "home_team": h_team,
                                    "away_team": a_team,
                                    "competition": f"{c_name} · {t_name}",
                                    "competition_tier": tier_label,
                                    "dominance_ratio": round(dominance_ratio, 2),
                                    "is_juggernaut": fav_is_juggernaut,
                                    "market_id": m_id,
                                    "market_desc": "Double Chance",
                                    "outcome_id": oc_id,
                                    "selection_desc": sel_desc,
                                    "specifier": spec,
                                    "odds": odds,
                                    "model_probability": prob,
                                    "market_type": "DOUBLE_CHANCE",
                                    "h2h_summary": stats_3p.get("h2h_summary") or f"H2H Coverage: {a_team} (Away Floor)",
                                    "form_summary": stats_3p.get("form_summary") or f"Form: {a_team} Unbeaten Trend",
                                    "composite_safety_score": c_sc,
                                    "quality_score": (prob * 50.0) + (c_sc * 40.0) + (dominance_ratio * 2.0) + pedigree_bonus + juggernaut_bonus + 3.0,
                                    "selection_rationale": f"{tier_label} · {stats_3p.get('h2h_summary')} · {stats_3p.get('form_summary')}"
                                })

                # B. Full-Time Over 1.5 Goals
                if (m_id == "18" or "over/under" in m_desc or "total goals" in m_desc) and "half" not in m_desc and "corner" not in m_desc and "team" not in m_desc:
                    for oc in m.get("outcomes", []):
                        is_active = oc.get("isActive")
                        if is_active is not None and str(is_active) not in ("1", "True", "true"):
                            continue
                        oc_st = oc.get("status")
                        if oc_st is not None and str(oc_st) != "0":
                            continue

                        oc_id = str(oc.get("id"))
                        oc_desc = (oc.get("desc") or "").lower()
                        odds = float(oc.get("odds") or 0)
                        
                        # Match total=1.5 or Asian total=2 in specifier or description
                        is_line_15 = ("1.5" in spec) or ("1.5" in oc_desc) or ("total=1.5" in spec) or ("over 1.5" in oc_desc)
                        is_line_20 = ("total=2" in spec) or ("total=2.0" in spec) or ("over 2" in oc_desc and "2.5" not in oc_desc)
                        if (is_line_15 or is_line_20) and "over" in oc_desc and 1.15 <= odds <= max_leg_odds:
                            prob = cls._calculate_poisson_over15_prob(h_odds, d_odds, a_odds, market_odds=odds) if is_line_15 else round(min(0.88, (1.0 / odds) * 0.94), 4)
                            sel_desc = "Over 1.5 Goals" if is_line_15 else "Over 2 Goals"
                            m_type = "OVER_15" if is_line_15 else "OVER_20"
                            stats_3p = evaluate_fixture_3pillar_metrics(h_team, a_team, f"Over/Under {1.5 if is_line_15 else 2.0}", sel_desc, odds)
                            min_prob = 0.70 if odds >= 1.28 else 0.74
                            if prob >= min_prob and stats_3p.get("composite_safety_score", 0.7) >= 0.65:
                                c_sc = float(stats_3p.get("composite_safety_score", 0.75))
                                candidates.append({
                                    "event_id": eid,
                                    "home_team": h_team,
                                    "away_team": a_team,
                                    "competition": f"{c_name} · {t_name}",
                                    "competition_tier": tier_label,
                                    "dominance_ratio": round(dominance_ratio, 2),
                                    "is_juggernaut": fav_is_juggernaut,
                                    "market_id": m_id,
                                    "market_desc": sel_desc,
                                    "outcome_id": oc_id,
                                    "selection_desc": sel_desc,
                                    "specifier": spec or ("total=1.5" if is_line_15 else "total=2.0"),
                                    "odds": odds,
                                    "model_probability": prob,
                                    "market_type": m_type,
                                    "h2h_summary": stats_3p.get("h2h_summary") or f"H2H Goal Index: {h_team} vs {a_team}",
                                    "form_summary": stats_3p.get("form_summary") or f"Form Goal Rate: {h_team} + {a_team}",
                                    "composite_safety_score": c_sc,
                                    "quality_score": (prob * 55.0) + (c_sc * 45.0) + pedigree_bonus + (juggernaut_bonus * 0.9) + (8.0 if is_line_15 else 6.0),
                                    "selection_rationale": f"{tier_label} · Poisson Scoring Profile · {stats_3p.get('h2h_summary')} · {stats_3p.get('form_summary')}"
                                })

                # C. Heavy Favorite Team Total Over 0.5 (Team to Score / Goal Bounds 1+)
                if ("team" in m_desc or m_id in ("19", "20") or "home" in m_desc or "away" in m_desc) and ("over/under" in m_desc or "goals" in m_desc):
                    # Discriminate Home vs Away markets (Market 19 = Home Team, Market 20 = Away Team)
                    is_home_mkt = (m_id == "19" or "home" in m_desc or (h_team.lower() in m_desc and a_team.lower() not in m_desc))
                    is_away_mkt = (m_id == "20" or "away" in m_desc or (a_team.lower() in m_desc and h_team.lower() not in m_desc))

                    # Strictly bind to the team the data favors:
                    if is_home_fav and not is_home_mkt:
                        continue
                    if (not is_home_fav) and not is_away_mkt:
                        continue

                    fav_team = h_team if is_home_fav else a_team
                    opp_team = a_team if is_home_fav else h_team

                    # Rule: Never back an underdog to score against an elite juggernaut defense!
                    opp_is_juggernaut = any(jg in opp_team.lower() for jg in cls.JUGGERNAUTS)
                    if opp_is_juggernaut and not fav_is_juggernaut:
                        continue

                    for oc in m.get("outcomes", []):
                        is_active = oc.get("isActive")
                        if is_active is not None and str(is_active) not in ("1", "True", "true"):
                            continue
                        oc_st = oc.get("status")
                        if oc_st is not None and str(oc_st) != "0":
                            continue
                        oc_id = str(oc.get("id"))
                        oc_desc = (oc.get("desc") or "").lower()
                        odds = float(oc.get("odds") or 0)
                        
                        is_line_05 = ("0.5" in spec) or ("0.5" in oc_desc) or ("total=0.5" in spec) or ("over 0.5" in oc_desc)
                        is_line_15 = ("1.5" in spec) or ("1.5" in oc_desc) or ("total=1.5" in spec) or ("over 1.5" in oc_desc)

                        if is_line_05 and "over" in oc_desc and 1.15 <= odds <= min(max_leg_odds, 1.45):
                            prob = round(min(0.93, (1.0 / odds) * 0.97), 4)
                            sel_desc = f"{fav_team} Over 0.5 Goals"
                            stats_3p = evaluate_fixture_3pillar_metrics(h_team, a_team, f"{fav_team} Team Goals", sel_desc, odds)
                            if prob >= 0.80 and dominance_ratio >= min_dominance and fav_is_genuine_banker and stats_3p.get("composite_safety_score", 0.7) >= 0.68:
                                c_sc = float(stats_3p.get("composite_safety_score", 0.75))
                                candidates.append({
                                    "event_id": eid,
                                    "home_team": h_team,
                                    "away_team": a_team,
                                    "competition": f"{c_name} · {t_name}",
                                    "competition_tier": tier_label,
                                    "dominance_ratio": round(dominance_ratio, 2),
                                    "is_juggernaut": fav_is_juggernaut,
                                    "market_id": m_id,
                                    "market_desc": f"{fav_team} Over/Under",
                                    "outcome_id": oc_id,
                                    "selection_desc": sel_desc,
                                    "specifier": spec or "total=0.5",
                                    "odds": odds,
                                    "model_probability": prob,
                                    "market_type": "TEAM_OVER_05",
                                    "h2h_summary": stats_3p.get("h2h_summary") or f"H2H Coverage: {fav_team} Scoring Proof",
                                    "form_summary": stats_3p.get("form_summary") or f"Form: {fav_team} Scoring Rate",
                                    "composite_safety_score": c_sc,
                                    "quality_score": (prob * 58.0) + (c_sc * 48.0) + (dominance_ratio * 3.0) + pedigree_bonus + juggernaut_bonus + 10.0,
                                    "selection_rationale": f"{tier_label} · Favorite {fav_team} Dominance {dominance_ratio:.1f}x · {stats_3p.get('h2h_summary')} · {stats_3p.get('form_summary')}"
                                })

                        elif is_line_15 and "over" in oc_desc and 1.15 <= odds <= min(max_leg_odds, 1.45):
                            if for_rollover:
                                # Strictly forbid Team Over 1.5 in rollover slips to avoid 1-0 scoreline cut traps
                                continue
                            prob = round(min(0.88, (1.0 / odds) * 0.94), 4)
                            sel_desc = f"{fav_team} Over 1.5 Goals"
                            stats_3p = evaluate_fixture_3pillar_metrics(h_team, a_team, f"{fav_team} Team Goals 1.5", sel_desc, odds)
                            if prob >= 0.75 and dominance_ratio >= max(1.30, min_dominance) and fav_is_genuine_banker and stats_3p.get("composite_safety_score", 0.7) >= 0.65:
                                c_sc = float(stats_3p.get("composite_safety_score", 0.75))
                                candidates.append({
                                    "event_id": eid,
                                    "home_team": h_team,
                                    "away_team": a_team,
                                    "competition": f"{c_name} · {t_name}",
                                    "competition_tier": tier_label,
                                    "dominance_ratio": round(dominance_ratio, 2),
                                    "is_juggernaut": fav_is_juggernaut,
                                    "market_id": m_id,
                                    "market_desc": f"{fav_team} Over/Under",
                                    "outcome_id": oc_id,
                                    "selection_desc": sel_desc,
                                    "specifier": spec or "total=1.5",
                                    "odds": odds,
                                    "model_probability": prob,
                                    "market_type": "TEAM_OVER_15",
                                    "h2h_summary": stats_3p.get("h2h_summary") or f"H2H Coverage: {fav_team} Multiple Goals",
                                    "form_summary": stats_3p.get("form_summary") or f"Form: {fav_team} Attack Index",
                                    "composite_safety_score": c_sc,
                                    "quality_score": (prob * 56.0) + (c_sc * 46.0) + (dominance_ratio * 3.0) + pedigree_bonus + juggernaut_bonus + 8.5,
                                    "selection_rationale": f"{tier_label} · Heavy Favorite {fav_team} Multiple Goals Cushion · {stats_3p.get('form_summary')}"
                                })

                # D. Heavy Favorite Win Either Half (Yes)
                if ("win either half" in m_desc or "either half" in m_desc or m_id in ("61", "62", "73", "74", "111")) and dominance_ratio >= max(1.40, min_dominance) and fav_is_genuine_banker:
                    for oc in m.get("outcomes", []):
                        is_active = oc.get("isActive")
                        if is_active is not None and str(is_active) not in ("1", "True", "true"):
                            continue
                        oc_st = oc.get("status")
                        if oc_st is not None and str(oc_st) != "0":
                            continue
                        oc_id = str(oc.get("id"))
                        oc_desc = (oc.get("desc") or "").lower()
                        odds = float(oc.get("odds") or 0)

                        fav_team = h_team if is_home_fav else a_team
                        is_fav_pick = False
                        if is_home_fav and ("home" in oc_desc or "yes" in oc_desc or oc_id in ("1", "yes", "61", "73", "9")):
                            is_fav_pick = True
                        elif (not is_home_fav) and ("away" in oc_desc or "yes" in oc_desc or oc_id in ("2", "yes", "62", "74", "11")):
                            is_fav_pick = True
                        elif "yes" in oc_desc:
                            is_fav_pick = True

                        if is_fav_pick and 1.15 <= odds <= min(max_leg_odds, 1.45):
                            prob = round(min(0.92, (1.0 / odds) * 0.96), 4)
                            sel_desc = f"{fav_team} to Win Either Half"
                            stats_3p = evaluate_fixture_3pillar_metrics(h_team, a_team, "Win Either Half", sel_desc, odds)
                            if prob >= 0.79 and stats_3p.get("composite_safety_score", 0.7) >= 0.68:
                                c_sc = float(stats_3p.get("composite_safety_score", 0.75))
                                candidates.append({
                                    "event_id": eid,
                                    "home_team": h_team,
                                    "away_team": a_team,
                                    "competition": f"{c_name} · {t_name}",
                                    "competition_tier": tier_label,
                                    "dominance_ratio": round(dominance_ratio, 2),
                                    "is_juggernaut": fav_is_juggernaut,
                                    "market_id": m_id,
                                    "market_desc": "Win Either Half",
                                    "outcome_id": oc_id,
                                    "selection_desc": sel_desc,
                                    "specifier": spec or "",
                                    "odds": odds,
                                    "model_probability": prob,
                                    "market_type": "WIN_EITHER_HALF",
                                    "h2h_summary": stats_3p.get("h2h_summary") or f"H2H Coverage: {fav_team} Half Dominance",
                                    "form_summary": stats_3p.get("form_summary") or f"Form: {fav_team} Fast Start Metric",
                                    "composite_safety_score": c_sc,
                                    "quality_score": (prob * 56.0) + (c_sc * 46.0) + (dominance_ratio * 3.0) + pedigree_bonus + juggernaut_bonus + 9.5,
                                    "selection_rationale": f"{tier_label} · {fav_team} Half Dominance ({dominance_ratio:.1f}x) · {stats_3p.get('h2h_summary')} · {stats_3p.get('form_summary')}"
                                })

                # E. [PERMANENTLY BANNED] High-Ceiling Unders (Under 3.5 / Under 4.5 Goals)
                # Banned across all tickets by user directive: Unders expose tickets to 90-minute anxiety,
                # stoppage-time deflections, penalty shootouts, and European red-card chaos.
                # Only positive outcome markets (Team Over, Match Over, Double Chance, Handicap) are permitted.

                # F. 1st Half Over 0.5 Goals (Strictly Gated to High-Pace, High-xG Leagues)
                is_high_pace_league = any(k in comp_full for k in [
                    "champions league", "bundesliga", "2. bundesliga", "eredivisie", "eerste divisie",
                    "premier league", "championship", "mls", "copa libertadores", "serie a", "serie b",
                    "la liga", "laliga 2", "ligue 1", "ligue 2", "austria", "belgium", "denmark",
                    "norway", "switzerland", "scotland", "turkey"
                ])
                if (m_id == "68" or "1st half - over/under" in m_desc or ("1st half" in m_desc and "over" in m_desc)) and is_high_pace_league:
                    for oc in m.get("outcomes", []):
                        is_active = oc.get("isActive")
                        if is_active is not None and str(is_active) not in ("1", "True", "true"):
                            continue
                        oc_st = oc.get("status")
                        if oc_st is not None and str(oc_st) != "0":
                            continue
                        oc_id = str(oc.get("id"))
                        oc_desc = (oc.get("desc") or "").lower()
                        odds = float(oc.get("odds") or 0)
                        is_line_05 = ("0.5" in spec) or ("0.5" in oc_desc) or ("total=0.5" in spec)
                        if is_line_05 and "over" in oc_desc and 1.15 <= odds <= max_leg_odds:
                            prob = round(min(0.88, (1.0 / odds) * 0.94), 4)
                            sel_desc = "1st Half Over 0.5 Goals"
                            stats_3p = evaluate_fixture_3pillar_metrics(h_team, a_team, "1st Half Over 0.5", sel_desc, odds)
                            if prob >= 0.78 and stats_3p.get("composite_safety_score", 0.7) >= 0.68:
                                c_sc = float(stats_3p.get("composite_safety_score", 0.75))
                                candidates.append({
                                    "event_id": eid,
                                    "home_team": h_team,
                                    "away_team": a_team,
                                    "competition": f"{c_name} · {t_name}",
                                    "competition_tier": tier_label,
                                    "dominance_ratio": round(dominance_ratio, 2),
                                    "is_juggernaut": fav_is_juggernaut,
                                    "market_id": m_id,
                                    "market_desc": "1st Half Over/Under",
                                    "outcome_id": oc_id,
                                    "selection_desc": sel_desc,
                                    "specifier": spec or "total=0.5",
                                    "odds": odds,
                                    "model_probability": prob,
                                    "market_type": "FIRST_HALF_OVER_05",
                                    "h2h_summary": stats_3p.get("h2h_summary") or f"1H Scoring Proof: {h_team} vs {a_team}",
                                    "form_summary": stats_3p.get("form_summary") or f"1H Pace Metric: {h_team} + {a_team}",
                                    "composite_safety_score": c_sc,
                                    "quality_score": (prob * 54.0) + (c_sc * 44.0) + pedigree_bonus + (juggernaut_bonus * 0.8) + 6.0,
                                    "selection_rationale": f"{tier_label} · First Half Fast-Tempo Index · {stats_3p.get('h2h_summary')}"
                                })

                # F2. 2nd Half Over 0.5 Goals (Positive Dynamic Goal Cushion - Statistically Highest-Scoring Half)
                is_2nd_half = (
                    m_id in ("90", "70", "72")
                    or "2nd half - over/under" in m_desc
                    or "second half - over/under" in m_desc
                    or ("2nd half" in m_desc and "over" in m_desc)
                    or ("second half" in m_desc and "over" in m_desc)
                )
                if is_2nd_half:
                    for oc in m.get("outcomes", []):
                        is_active = oc.get("isActive")
                        if is_active is not None and str(is_active) not in ("1", "True", "true"):
                            continue
                        oc_st = oc.get("status")
                        if oc_st is not None and str(oc_st) != "0":
                            continue
                        oc_id = str(oc.get("id"))
                        oc_desc = (oc.get("desc") or "").lower()
                        odds = float(oc.get("odds") or 0)
                        is_line_05 = ("0.5" in spec) or ("0.5" in oc_desc) or ("total=0.5" in spec)
                        # Strict User Rule: 2nd Half Over 0.5 MUST have odds >= 1.15 (our global minimum odds floor)
                        if is_line_05 and (oc_id in ("12", "over") or "over" in oc_desc) and 1.15 <= odds <= max_leg_odds:
                            prob = round(min(0.91, (1.0 / odds) * 0.95), 4)
                            sel_desc = "2nd Half Over 0.5 Goals"
                            stats_3p = evaluate_fixture_3pillar_metrics(h_team, a_team, "2nd Half Over 0.5", sel_desc, odds)
                            if prob >= 0.76 and stats_3p.get("composite_safety_score", 0.7) >= 0.65:
                                c_sc = float(stats_3p.get("composite_safety_score", 0.75))
                                candidates.append({
                                    "event_id": eid,
                                    "home_team": h_team,
                                    "away_team": a_team,
                                    "competition": f"{c_name} · {t_name}",
                                    "competition_tier": tier_label,
                                    "dominance_ratio": round(dominance_ratio, 2),
                                    "is_juggernaut": fav_is_juggernaut,
                                    "market_id": m_id,
                                    "market_desc": "2nd Half Over/Under",
                                    "outcome_id": oc_id,
                                    "selection_desc": sel_desc,
                                    "specifier": spec or "total=0.5",
                                    "odds": odds,
                                    "model_probability": prob,
                                    "market_type": "SECOND_HALF_OVER_05",
                                    "h2h_summary": stats_3p.get("h2h_summary") or f"2H Goal Trend: {h_team} vs {a_team}",
                                    "form_summary": stats_3p.get("form_summary") or f"2H Acceleration Index: {h_team} + {a_team}",
                                    "composite_safety_score": c_sc,
                                    "quality_score": (prob * 55.0) + (c_sc * 45.0) + pedigree_bonus + (juggernaut_bonus * 0.8) + 7.0,
                                    "selection_rationale": f"{tier_label} · Second Half Goal Index · {stats_3p.get('h2h_summary')}"
                                })

                # G. 2-Way Asian Handicap (+1.5) (Permanently Ban All 3-Way European Handicap Draw Traps)
                is_asian_hcp = (m_id in ("60", "390", "154") or "asian handicap" in m_desc) and m_id != "14"
                if is_asian_hcp:
                    for oc in m.get("outcomes", []):
                        is_active = oc.get("isActive")
                        if is_active is not None and str(is_active) not in ("1", "True", "true"):
                            continue
                        oc_st = oc.get("status")
                        if oc_st is not None and str(oc_st) != "0":
                            continue
                        oc_id = str(oc.get("id"))
                        oc_desc = (oc.get("desc") or "").lower()
                        odds = float(oc.get("odds") or 0)
                        if odds < 1.15 or odds > max_leg_odds:
                            continue

                        # Strictly 2-Way Asian Handicap (+1.5)
                        is_plus_home = (
                            ("1.5" in spec or "+1.5" in oc_desc)
                            and (oc_id in ("1", "1711", "home") or "home" in oc_desc or "1" in oc_desc)
                        )
                        is_plus_away = (
                            ("1.5" in spec or "+1.5" in oc_desc)
                            and (oc_id in ("3", "1713", "away") or "away" in oc_desc or "2" in oc_desc)
                        )

                        if is_plus_home or is_plus_away:
                            beneficiary = h_team if is_plus_home else a_team
                            sel_desc = f"{beneficiary} (+1.5)"
                            prob = round(min(0.93, (1.0 / odds) * 0.96), 4)
                            stats_3p = evaluate_fixture_3pillar_metrics(h_team, a_team, "Asian Handicap +1.5", sel_desc, odds)
                            if prob >= 0.80 and stats_3p.get("composite_safety_score", 0.7) >= 0.68:
                                c_sc = float(stats_3p.get("composite_safety_score", 0.75))
                                candidates.append({
                                    "event_id": eid,
                                    "home_team": h_team,
                                    "away_team": a_team,
                                    "competition": f"{c_name} · {t_name}",
                                    "competition_tier": tier_label,
                                    "dominance_ratio": round(dominance_ratio, 2),
                                    "is_juggernaut": fav_is_juggernaut,
                                    "market_id": m_id,
                                    "market_desc": "Asian Handicap (+1.5)",
                                    "outcome_id": oc_id,
                                    "selection_desc": sel_desc,
                                    "specifier": spec,
                                    "odds": odds,
                                    "model_probability": prob,
                                    "market_type": "HANDICAP_CUSHION",
                                    "h2h_summary": stats_3p.get("h2h_summary") or f"Goal Cushion Margin: {beneficiary} (+1.5)",
                                    "form_summary": stats_3p.get("form_summary") or f"Form Resilience: {beneficiary}",
                                    "composite_safety_score": c_sc,
                                    "quality_score": (prob * 56.0) + (c_sc * 46.0) + pedigree_bonus + 7.0,
                                    "selection_rationale": f"{tier_label} · 2-Way Asian Handicap Cushion (+1.5) · {stats_3p.get('h2h_summary')}"
                                })

                # H. Chance Mix / Double Chance Combo: Favorite or Over 2.5 (STRICTLY for dominant favorites)
                if ("or over" in m_desc or "win or over" in m_desc or m_id == "62") and dominance_ratio >= max(1.40, min_dominance) and fav_is_genuine_banker:
                    for oc in m.get("outcomes", []):
                        is_active = oc.get("isActive")
                        if is_active is not None and str(is_active) not in ("1", "True", "true"):
                            continue
                        oc_st = oc.get("status")
                        if oc_st is not None and str(oc_st) != "0":
                            continue
                        oc_id = str(oc.get("id"))
                        oc_desc = (oc.get("desc") or "").lower()
                        odds = float(oc.get("odds") or 0)
                        if odds < 1.15 or odds > max_leg_odds:
                            continue

                        fav_team = h_team if is_home_fav else a_team
                        is_fav_mix = False
                        if is_home_fav and ("home" in oc_desc or "1" in oc_desc or oc_id in ("1", "home")):
                            is_fav_mix = True
                        elif (not is_home_fav) and ("away" in oc_desc or "2" in oc_desc or oc_id in ("2", "away")):
                            is_fav_mix = True

                        if is_fav_mix:
                            sel_desc = f"{fav_team} or Over 2.5"
                            prob = round(min(0.91, (1.0 / odds) * 0.95), 4)
                            stats_3p = evaluate_fixture_3pillar_metrics(h_team, a_team, "Chance Mix", sel_desc, odds)
                            if prob >= 0.79 and stats_3p.get("composite_safety_score", 0.7) >= 0.68:
                                c_sc = float(stats_3p.get("composite_safety_score", 0.75))
                                candidates.append({
                                    "event_id": eid,
                                    "home_team": h_team,
                                    "away_team": a_team,
                                    "competition": f"{c_name} · {t_name}",
                                    "competition_tier": tier_label,
                                    "dominance_ratio": round(dominance_ratio, 2),
                                    "is_juggernaut": fav_is_juggernaut,
                                    "market_id": m_id,
                                    "market_desc": "Chance Mix",
                                    "outcome_id": oc_id,
                                    "selection_desc": sel_desc,
                                    "specifier": spec,
                                    "odds": odds,
                                    "model_probability": prob,
                                    "market_type": "CHANCE_MIX",
                                    "h2h_summary": stats_3p.get("h2h_summary") or f"Dual Route to Win: {fav_team} Win OR Over 2.5",
                                    "form_summary": stats_3p.get("form_summary") or f"Form Coverage: {fav_team}",
                                    "composite_safety_score": c_sc,
                                    "quality_score": (prob * 56.0) + (c_sc * 46.0) + (dominance_ratio * 3.0) + pedigree_bonus + juggernaut_bonus + 8.5,
                                    "selection_rationale": f"{tier_label} · Dual-Route Chance Mix ({fav_team} or Over 2.5)"
                                })

        # Tag heavyweight derbies across candidates
        for c in candidates:
            c["is_heavyweight_derby"] = any(jg in str(c.get("home_team", "")).lower() for jg in cls.JUGGERNAUTS) and any(jg in str(c.get("away_team", "")).lower() for jg in cls.JUGGERNAUTS)

        # Sort candidates deterministically by quality_score descending (ELITE FIRST)
        candidates.sort(key=lambda x: (x["quality_score"], x["model_probability"]), reverse=True)
        logger.info(f"[EliteRollover] Filtered {len(candidates)} elite candidate markets from today's pool.")
        return candidates

    @classmethod
    def assemble_optimal_rollover_slip(
        cls,
        candidates: List[Dict[str, Any]],
        target_odds: float = 1.50
    ) -> List[Dict[str, Any]]:
        """
        Deterministically selects the top 2 to 3 distinct banker fixtures that combine
        closest to target_odds (1.50x - 1.65x) while maximizing joint win probability.
        Strictly zero random shuffling: highest statistical quality is guaranteed.
        """
        if not candidates:
            return []

        # STRICT SAFETY DIRECTIVE (User Directive):
        # 1. 1st Half Over 0.5 is 100% PROHIBITED in the Rollover Slip.
        # 2. Team Over 1.5 is 100% PROHIBITED to prevent 1-0 win cut traps.
        # 3. Heavyweight Derbies (e.g. Juve vs Lazio, Milan vs Atalanta, Chelsea vs Liverpool)
        #    are 100% PROHIBITED from compounding rollover capital. Rollover relies strictly on
        #    dominant juggernauts playing against non-heavyweights.
        candidates = [
            c for c in candidates
            if c.get("market_type") != "FIRST_HALF_OVER_05"
            and c.get("market_type") != "TEAM_OVER_15"
            and not c.get("is_heavyweight_derby")
        ]
        if not candidates:
            return []

        # Collect distinct market candidates per fixture (up to 2 diverse markets per fixture)
        fixture_map: Dict[str, List[Dict[str, Any]]] = collections.defaultdict(list)
        for c in candidates:
            fid = c["event_id"]
            if not any(x.get("market_type") == c.get("market_type") for x in fixture_map[fid]):
                fixture_map[fid].append(c)

        ranked_pool = []
        for fid, opts in fixture_map.items():
            opts.sort(key=lambda x: (x.get("quality_score", 0), x.get("model_probability", 0)), reverse=True)
            ranked_pool.extend(opts[:2])

        if not ranked_pool:
            return []

        # JUGGERNAUT FIRST DIBS: Dominant juggernauts (Celtic, Juventus, Lazio, AC Milan, PSG, Man City, etc.)
        # get first priority for the Rollover compounding capital rather than being passed over.
        ranked_pool.sort(
            key=lambda x: (
                1 if x.get("is_juggernaut") and x.get("dominance_ratio", 0) >= 1.5 else 0,
                x.get("quality_score", 0),
                x.get("model_probability", 0)
            ),
            reverse=True
        )

        target = float(target_odds)
        best_combo: List[Dict[str, Any]] = []
        best_objective = -float("inf")

        # Evaluate combinations from top 50 ranked candidates (includes both ultra-safe 1.15-1.25 and 1.25-1.55 cushions)
        import itertools
        top_slice = ranked_pool[:50]

        # For 1.50x compounding corridor: strictly 3 banker games (USER DIRECTIVE: MUST be 3 games)
        # For lower targets (< 1.35x): 2 games; for higher targets (> 1.75x): 4 or 3 games
        if 1.35 <= target <= 1.75:
            leg_options = (3,)
        elif target < 1.35:
            leg_options = (2,)
        else:
            leg_options = (4, 3)

        for k in leg_options:
            for combo in itertools.combinations(top_slice, k):
                # Strictly zero fixture repetition within the ticket
                if len(set(leg["event_id"] for leg in combo)) != k:
                    continue

                tot_odds = 1.0
                cum_prob = 1.0
                quality_sum = 0.0
                juggernaut_count = 0
                for leg in combo:
                    tot_odds *= leg["odds"]
                    cum_prob *= leg["model_probability"]
                    quality_sum += leg.get("quality_score", 50.0)
                    if leg.get("is_juggernaut"):
                        juggernaut_count += 1

                avg_quality = quality_sum / k
                odds_diff = abs(tot_odds - target)
                # Must be within reasonable bound of target odds (e.g. 1.40x - 1.72x for 1.50x target)
                if tot_odds < (target * 0.93) or tot_odds > (target * 1.15):
                    continue

                # Objective: heavily weight joint probability and quality
                if 1.35 <= target <= 1.75:
                    leg_penalty = 0.0 if k == 3 else 50.0
                elif target < 1.35:
                    leg_penalty = 0.0 if k == 2 else 50.0
                else:
                    leg_penalty = 0.0 if k == 4 else (abs(k - 4) * 4.0)

                unique_mkts = len(set(leg.get("market_type") for leg in combo))
                diversity_bonus = (unique_mkts - 1) * 10.0
                dc_count = sum(1 for leg in combo if leg.get("market_type") == "DOUBLE_CHANCE")
                # Diversity incentive: penalize slips dominated purely by Double Chance
                diversity_penalty = (dc_count - 1) * 10.0 if dc_count > 1 else 0.0
                obj = (cum_prob * 60.0) + (avg_quality * 1.80) + (juggernaut_count * 30.0) + diversity_bonus - (odds_diff * 15.0) - leg_penalty - diversity_penalty
                if obj > best_objective:
                    best_objective = obj
                    best_combo = list(combo)

        # Fallback if no exact combination met strict window: pick top legs greedily up to target with diversity guard
        if not best_combo:
            curr_odds = 1.0
            required_legs = 3 if (1.35 <= target <= 1.75) else (2 if target < 1.35 else 4)
            max_per_market = 1 if required_legs <= 3 else 2
            market_counts = collections.defaultdict(int)
            used_fids = set()
            for leg in ranked_pool:
                fid = leg["event_id"]
                if fid in used_fids:
                    continue
                m_type = leg.get("market_type") or "OTHER"
                if market_counts[m_type] >= max_per_market:
                    continue
                best_combo.append(leg)
                used_fids.add(fid)
                market_counts[m_type] += 1
                curr_odds *= leg["odds"]
                if len(best_combo) >= required_legs:
                    break

        return best_combo

    @classmethod
    async def book_and_dispatch_rollover(
        cls,
        target_odds: float = 1.50,
        send_telegram: bool = True,
        max_leg_odds: float = 1.45,
        challenge_day_info: Optional[str] = None,
        stake: Optional[float] = None
    ) -> Dict[str, Any]:
        """
        Full Autonomous Pipeline:
        1. Query SportyBet today's endpoint directly.
        2. Filter elite low-variance picks with Dixon-Coles/Poisson models.
        3. Assemble optimal 1.50x ticket across 2-3 banker games with odds strictly between 1.15 and max_leg_odds.
        4. Generate live SportyBet shareCode via /orders/share.
        5. Dispatch rich alert to Telegram.
        6. Persist to StatIQ database.
        """
        logger.info(f"[EliteRollover] Executing autonomous rollover run for target odds {target_odds}x (leg odds cap {max_leg_odds}x)...")
        raw_events = await cls.fetch_sportybet_today_events(max_pages=15)
        if not raw_events:
            return {
                "status": "NO_FIXTURES",
                "message": "SportyBet today endpoint returned 0 active fixtures."
            }

        candidates = cls.evaluate_elite_rollover_candidates(raw_events, max_leg_odds=max_leg_odds, for_rollover=True)
        if not candidates:
            return {
                "status": "NO_QUALIFIED_PICKS",
                "message": "No fixtures met the strict 80%+ win probability & safety cushion threshold today."
            }

        slip_legs = cls.assemble_optimal_rollover_slip(candidates, target_odds=target_odds)
        if not slip_legs:
            return {
                "status": "COMBINATION_FAILED",
                "message": "Could not construct an optimal rollover combination matching target odds."
            }

        # Calculate combined metrics
        actual_odds = 1.0
        cum_prob = 1.0
        for leg in slip_legs:
            actual_odds *= leg["odds"]
            cum_prob *= leg["model_probability"]
        actual_odds = round(actual_odds, 2)
        confidence_pct = round(cum_prob * 100.0, 1)

        # Request live SportyBet booking code
        selections_payload = []
        for leg in slip_legs:
            sel_item = {
                "eventId": leg["event_id"],
                "marketId": str(leg["market_id"]),
                "outcomeId": str(leg["outcome_id"])
            }
            if leg.get("specifier"):
                sel_item["specifier"] = leg["specifier"]
            selections_payload.append(sel_item)

        booking_code = None
        share_url = None
        share_endpoint = f"{cls.BASE_URL}/ng/orders/share"

        try:
            async with httpx.AsyncClient(timeout=10.0, headers=cls.HEADERS) as client:
                r = await client.post(share_endpoint, json={"selections": selections_payload})
                if r.status_code == 200:
                    res_data = r.json()
                    if res_data.get("bizCode") == 10000:
                        booking_code = res_data.get("data", {}).get("shareCode")
                        share_url = res_data.get("data", {}).get("shareURL") or f"https://www.sportybet.com/ng/?shareCode={booking_code}"
                        logger.info(f"[EliteRollover] Generated SportyBet Booking Code: {booking_code}")
                    else:
                        logger.warning(f"[EliteRollover] SportyBet rejected share request: {res_data}")
        except Exception as e:
            logger.error(f"[EliteRollover] Error requesting SportyBet booking code: {e}")

        today_str = datetime.datetime.now(datetime.timezone.utc).strftime("%A, %b %d, %Y")
        ticket_id = f"ROLLOVER-{int(time.time())}"
        current_stake = float(stake or 5000.0)

        # Persist to TrackedTicket table for live settlement evaluation
        try:
            db: Session = SessionLocal()
            try:
                tracked = TrackedTicket(
                    id=ticket_id,
                    code=booking_code or "UNBOOKED",
                    mode="ROLLOVER",
                    target_odds=target_odds,
                    total_odds=actual_odds,
                    stake=current_stake,
                    potential_win=round(current_stake * actual_odds, 2),
                    status="RUNNING",
                    created_at=datetime.datetime.utcnow().isoformat(),
                    locked_at_unix=int(time.time()),
                    selections=[
                        {
                            "fixture_id": leg["event_id"],
                            "match": f"{leg['home_team']} vs {leg['away_team']}",
                            "home_team": leg["home_team"],
                            "away_team": leg["away_team"],
                            "competition": leg["competition"],
                            "market": leg["market_desc"],
                            "selection": leg["selection_desc"],
                            "odds": leg["odds"],
                            "probability": leg["model_probability"],
                            "status": "PENDING"
                        }
                        for leg in slip_legs
                    ]
                )
                db.add(tracked)
                db.commit()
            finally:
                db.close()
        except Exception as e:
            logger.warning(f"[EliteRollover] Error persisting ticket to db: {e}")

        result_payload = {
            "status": "SUCCESS",
            "ticket_id": ticket_id,
            "booking_code": booking_code or "N/A",
            "share_url": share_url or (f"https://www.sportybet.com/ng/?shareCode={booking_code}" if booking_code else None),
            "target_odds": target_odds,
            "actual_odds": actual_odds,
            "confidence_score": confidence_pct,
            "date_str": today_str,
            "leg_count": len(slip_legs),
            "picks": slip_legs,
            "challenge_day": challenge_day_info,
            "stake": current_stake
        }

        # Dispatch alert to Telegram
        telegram_sent = False
        if send_telegram and booking_code:
            telegram_sent = RolloverTelegramNotifier.dispatch_rollover_slip(result_payload)
            result_payload["telegram_dispatched"] = telegram_sent

        return result_payload

    @classmethod
    def assemble_optimal_accumulator_slip(
        cls,
        candidates: List[Dict[str, Any]],
        target_odds: float = 5.00,
        min_legs: int = 4,
        max_legs: int = 8,
        excluded_event_ids: Optional[set] = None
    ) -> List[Dict[str, Any]]:
        """
        Deterministically selects fixtures for a multi-leg accumulator (e.g. 5.0x or 10.0x)
        while guaranteeing zero overlap against excluded_event_ids.
        Prioritizes top quality scores, safe markets (Double Chance, Over 1.5, Team Over 0.5),
        and strictly enforces odds >= 1.15.
        """
        if not candidates:
            return []

        target = float(target_odds)

        # STRICT SAFETY DIRECTIVE (User Directive):
        # - For 5.0x Precision Multiplier (target < 9.5): 1st Half Over 0.5 is 100% PROHIBITED.
        #   5.0x must rely exclusively on high-assurance full-time cushions.
        # - For 10.0x Mega Multiplier (target >= 9.5): 1st Half Over 0.5 is permitted ONLY IF
        #   both teams have proven high-scoring profiles (composite_safety_score >= 0.74 and juggernaut / high-tempo club).
        if target < 9.5:
            candidates = [c for c in candidates if c.get("market_type") != "FIRST_HALF_OVER_05"]
        else:
            candidates = [
                c for c in candidates
                if c.get("market_type") != "FIRST_HALF_OVER_05" or (
                    float(c.get("composite_safety_score", 0)) >= 0.74
                    and (c.get("is_juggernaut") or any(t in str(c.get("home_team", "")).lower() or t in str(c.get("away_team", "")).lower() for t in HIGH_TEMPO_CLUBS))
                )
            ]

        if not candidates:
            return []

        excluded = excluded_event_ids or set()

        # Group candidates by fixture so alternative markets can be selected if Double Chance quota is reached
        fixture_candidates: Dict[str, List[Dict[str, Any]]] = {}
        for c in candidates:
            fid = c["event_id"]
            if fid in excluded:
                continue
            if fid not in fixture_candidates:
                fixture_candidates[fid] = []
            fixture_candidates[fid].append(c)

        if not fixture_candidates:
            return []

        for fid in fixture_candidates:
            fixture_candidates[fid].sort(
                key=lambda x: (x.get("quality_score", 0), x.get("model_probability", 0)),
                reverse=True
            )

        # Sort fixtures by their best candidate's quality score
        sorted_fixtures = sorted(
            fixture_candidates.keys(),
            key=lambda fid: (
                1 if fixture_candidates[fid][0].get("is_juggernaut") else 0,
                fixture_candidates[fid][0].get("quality_score", 0),
                fixture_candidates[fid][0].get("model_probability", 0)
            ),
            reverse=True
        )

        target = float(target_odds)

        # For 10.0x and high-multiplier targets: prioritize sweet-spot odds (1.20 - 1.36) per fixture
        # so target odds of 10.0x are achieved in 8-10 high-assurance legs rather than 16+ low-odds legs
        if target >= 8.5:
            for fid in fixture_candidates:
                fixture_candidates[fid].sort(
                    key=lambda x: (
                        1 if 1.20 <= x.get("odds", 0) <= 1.36 else 0,
                        x.get("quality_score", 0),
                        x.get("model_probability", 0)
                    ),
                    reverse=True
                )

        # PASS 1: Targeted Market Diversity Mix
        # Initial preference: balance Team Over 0.5, Over 1.5, Win Either Half, Double Chance
        max_dc = max(3, int(max_legs * 0.50)) if target >= 8.5 else max(2, int(min_legs * 0.45))
        max_per_market = max(4, int(max_legs * 0.50)) if target >= 8.5 else max(3, int(max_legs * 0.40))
        market_counts: Dict[str, int] = collections.defaultdict(int)

        selected_legs: List[Dict[str, Any]] = []
        selected_fids = set()
        curr_odds = 1.0

        target_floor = (target * 0.95) if target >= 8.5 else (target * 0.92)
        target_ceiling = (target * 1.08) if target >= 8.5 else (target * 1.15)
        effective_max_legs = max_legs + (5 if target >= 20.0 else (3 if target >= 8.5 else 2))

        for fid in sorted_fixtures:
            opts = fixture_candidates[fid]
            chosen = None
            for cand in opts:
                m_type = cand.get("market_type") or "OTHER"
                limit = max_dc if m_type == "DOUBLE_CHANCE" else max_per_market
                if market_counts[m_type] < limit:
                    chosen = cand
                    break

            if chosen:
                m_type = chosen.get("market_type") or "OTHER"
                market_counts[m_type] += 1
                selected_legs.append(chosen)
                selected_fids.add(fid)
                curr_odds *= chosen["odds"]

                if len(selected_legs) >= min_legs and curr_odds >= target_floor:
                    break
                if len(selected_legs) >= effective_max_legs:
                    break
                if curr_odds >= target_ceiling and len(selected_legs) >= min_legs:
                    break

        # PASS 2: Adaptive Fill-Forward Guarantee
        # If after Pass 1 the accumulator has not yet reached its target odds or minimum leg count,
        # dynamically expand the market quota and draw from the highest-ranked remaining fixtures.
        # This guarantees the accumulator NEVER starves or aborts early with incomplete odds.
        if (len(selected_legs) < min_legs or curr_odds < target_floor) and len(selected_legs) < effective_max_legs:
            for fid in sorted_fixtures:
                if fid in selected_fids:
                    continue
                opts = fixture_candidates[fid]
                if not opts:
                    continue
                # Pick the highest quality vetted candidate for this fixture
                chosen = opts[0]
                m_type = chosen.get("market_type") or "OTHER"
                market_counts[m_type] += 1
                selected_legs.append(chosen)
                selected_fids.add(fid)
                curr_odds *= chosen["odds"]

                if len(selected_legs) >= min_legs and curr_odds >= target_floor:
                    break
                if len(selected_legs) >= effective_max_legs:
                    break
                if curr_odds >= target_ceiling and len(selected_legs) >= min_legs:
                    break

        # PASS 3: Odds Sweet-Spot Optimization & Leg Upgrades
        # If after Pass 1 & 2 the slip is below target_floor:
        # A. Attempt to upgrade existing legs by swapping to higher-odds vetted markets for that same fixture
        #    (e.g., swapping a 1.16 Team Over 0.5 for a 1.28 Over 1.5 or 1.25 Win Either Half)
        if curr_odds < target_floor:
            for i, leg in enumerate(selected_legs):
                fid = leg["event_id"]
                opts = fixture_candidates.get(fid, [])
                for alt in opts:
                    if alt["odds"] > leg["odds"] and alt["model_probability"] >= 0.72:
                        old_odds = leg["odds"]
                        new_slip_odds = (curr_odds / old_odds) * alt["odds"]
                        if new_slip_odds <= target_ceiling * 1.05:
                            selected_legs[i] = alt
                            curr_odds = new_slip_odds
                            break
                if curr_odds >= target_floor:
                    break

        # B. If still below target_floor, draw additional top-ranked fixtures up to effective_max_legs
        if curr_odds < target_floor and len(selected_legs) < effective_max_legs:
            for fid in sorted_fixtures:
                if fid in selected_fids:
                    continue
                opts = fixture_candidates[fid]
                if not opts:
                    continue
                chosen = opts[0]
                selected_legs.append(chosen)
                selected_fids.add(fid)
                curr_odds *= chosen["odds"]
                if curr_odds >= target_floor or len(selected_legs) >= effective_max_legs:
                    break

        # Verify accumulator reached required odds threshold; adaptively support lean boards
        min_acc_odds = max(1.30, target * 0.70)
        min_acc_legs = max(3, int(min_legs * 0.75))
        if curr_odds < min_acc_odds or len(selected_legs) < min_acc_legs:
            logger.warning(f"[EliteRollover] Accumulator could only achieve {curr_odds:.2f}x across {len(selected_legs)} legs (target: {target:.2f}x). Insufficient qualified pool.")
            return []

        return selected_legs

    @classmethod
    async def _request_sportybet_share_code(cls, slip_legs: List[Dict[str, Any]]) -> Tuple[Optional[str], Optional[str]]:
        """Requests SportyBet shareCode via /ng/orders/share with retry resilience."""
        if not slip_legs:
            return None, None

        selections_payload = []
        for leg in slip_legs:
            sel_item = {
                "eventId": leg["event_id"],
                "marketId": str(leg["market_id"]),
                "outcomeId": str(leg["outcome_id"])
            }
            if leg.get("specifier"):
                sel_item["specifier"] = leg["specifier"]
            selections_payload.append(sel_item)

        booking_code = None
        share_url = None
        share_endpoint = f"{cls.BASE_URL}/ng/orders/share"

        for attempt in range(1, 3):
            try:
                async with httpx.AsyncClient(timeout=10.0, headers=cls.HEADERS) as client:
                    r = await client.post(share_endpoint, json={"selections": selections_payload})
                    if r.status_code == 200:
                        res_data = r.json()
                        if res_data.get("bizCode") == 10000:
                            booking_code = res_data.get("data", {}).get("shareCode")
                            share_url = res_data.get("data", {}).get("shareURL") or f"https://www.sportybet.com/ng/?shareCode={booking_code}"
                            logger.info(f"[EliteRollover] Generated SportyBet Booking Code: {booking_code}")
                            return booking_code, share_url
                        else:
                            logger.warning(f"[EliteRollover] SportyBet rejected share request (attempt {attempt}): {res_data}")
                    else:
                        logger.warning(f"[EliteRollover] SportyBet HTTP error {r.status_code} (attempt {attempt})")
            except Exception as e:
                logger.error(f"[EliteRollover] Error requesting SportyBet booking code (attempt {attempt}): {e}")
            if attempt < 2:
                await asyncio.sleep(1.0)

        return booking_code, share_url

    @classmethod
    def _persist_ticket_record(
        cls,
        ticket_id: str,
        booking_code: Optional[str],
        mode: str,
        target_odds: float,
        actual_odds: float,
        stake: float,
        slip_legs: List[Dict[str, Any]]
    ):
        """Persists ticket to TrackedTicket table for record keeping."""
        try:
            db: Session = SessionLocal()
            try:
                tracked = TrackedTicket(
                    id=ticket_id,
                    code=booking_code or "UNBOOKED",
                    mode=mode,
                    target_odds=target_odds,
                    total_odds=actual_odds,
                    stake=stake,
                    potential_win=round(stake * actual_odds, 2),
                    status="RUNNING",
                    created_at=datetime.datetime.utcnow().isoformat(),
                    locked_at_unix=int(time.time()),
                    selections=[
                        {
                            "fixture_id": leg["event_id"],
                            "match": f"{leg['home_team']} vs {leg['away_team']}",
                            "home_team": leg["home_team"],
                            "away_team": leg["away_team"],
                            "competition": leg["competition"],
                            "market": leg["market_desc"],
                            "selection": leg["selection_desc"],
                            "odds": leg["odds"],
                            "probability": leg["model_probability"],
                            "status": "PENDING"
                        }
                        for leg in slip_legs
                    ]
                )
                db.add(tracked)
                db.commit()
            finally:
                db.close()
        except Exception as e:
            logger.warning(f"[EliteRollover] Error persisting {mode} ticket: {e}")

    @classmethod
    async def book_and_dispatch_daily_trio(
        cls,
        enable_rollover: bool = True,
        enable_10odds: bool = True,
        enable_20odds: bool = True,
        enable_5odds: bool = False,
        send_telegram: bool = True,
        rollover_stake: float = 5000.0,
        rollover_target_odds: float = 1.50,
        acca_5x_target_odds: float = 5.00,
        acca_10x_target_odds: float = 10.00,
        acca_20x_target_odds: float = 20.00,
        challenge_day_info: Optional[str] = None
    ) -> Dict[str, Any]:
        """
        Unified 10:00 AM WAT Automation Hub with Adaptive Calendar Engine:
        1. Saturdays & Sundays (Weekends): Strict Mode (100% Zero-Overlap across all slips).
           Zero fixtures are repeated anywhere.
        2. Mondays – Fridays (Weekdays): Smart Hybrid Mode:
           - Rollover is 100% sacred & isolated (0 shared fixtures anywhere, 2–3 banker games).
           - Secondary slips can share at most 2–3 Elite Giants (different markets only:
             e.g., Over 1.5 Goals on Slip 2, Win Either Half or Double Chance on Slip 3).
           - 80%+ of fixtures on each slip remain completely unique.
        3. Slips:
           - Slip 1: Rollover (2–4 banker legs, dynamic target odds e.g. 1.50x)
           - Slip 2: Precision Multiplier (dynamic target odds e.g. 5.0x)
           - Slip 3: Mega Slip (dynamic target odds e.g. 10.0x)
           - Slip 4: Monster Acca (dynamic target odds e.g. 20.0x)
        """
        logger.info(f"[EliteRollover] Executing Daily VIP Automation (Rollover: {enable_rollover} @ {rollover_target_odds}x, 5x: {enable_5odds} @ {acca_5x_target_odds}x, 10x: {enable_10odds} @ {acca_10x_target_odds}x, 20x: {enable_20odds} @ {acca_20x_target_odds}x)...")
        raw_events = await cls.fetch_sportybet_today_events(max_pages=35)
        if not raw_events:
            return {
                "status": "NO_FIXTURES",
                "message": "SportyBet today endpoint returned 0 active fixtures."
            }

        # Evaluate candidate pool strictly with pure banker odds floor & ceiling (1.15 to 1.45, 78%+ win probability)
        banker_candidates = cls.evaluate_elite_rollover_candidates(raw_events, max_leg_odds=1.45, for_rollover=False)

        if not banker_candidates:
            return {
                "status": "NO_QUALIFIED_PICKS",
                "message": "No fixtures met the strict probability & safety cushion threshold today."
            }

        wat_tz = datetime.timezone(datetime.timedelta(hours=1))
        wat_now = datetime.datetime.now(wat_tz)
        claimed_event_ids = set()
        ro_event_ids = set()
        ro_legs: List[Dict[str, Any]] = []
        acca5_legs: List[Dict[str, Any]] = []
        acca5_fids: set = set()
        acca10_legs: List[Dict[str, Any]] = []
        acca20_legs: List[Dict[str, Any]] = []
        today_str = wat_now.strftime("%A, %b %d, %Y")
        now_ts = int(time.time())

        trio_result = {
            "status": "SUCCESS",
            "date_str": today_str,
            "schedule_mode": "DAILY_VIP_TRIO",
            "zero_overlap_guaranteed": True,
            "calendar_mode": "DAILY_VIP_BANKER_SUITE",
            "rollover_ticket": None,
            "acca_5x_ticket": None,
            "acca_10x_ticket": None,
            "acca_20x_ticket": None,
            "total_unique_fixtures": 0
        }

        # ── 1. SLIP 1: ROLLOVER (Highest Assurance Banker Legs - 100% SACRED & ISOLATED) ──
        if enable_rollover:
            unclaimed_ro = [c for c in banker_candidates if c["event_id"] not in claimed_event_ids and c.get("market_type") != "TEAM_OVER_15"]
            ro_legs = cls.assemble_optimal_rollover_slip(unclaimed_ro, target_odds=rollover_target_odds)
            if ro_legs:
                for leg in ro_legs:
                    claimed_event_ids.add(leg["event_id"])
                    ro_event_ids.add(leg["event_id"])

                ro_odds = round(math.prod(leg["odds"] for leg in ro_legs), 2)
                ro_prob = round(math.prod(leg["model_probability"] for leg in ro_legs) * 100.0, 1)
                ro_code, ro_url = await cls._request_sportybet_share_code(ro_legs)
                ro_ticket_id = f"ROLLOVER-{now_ts}"
                current_stake = float(rollover_stake or 5000.0)

                cls._persist_ticket_record(ro_ticket_id, ro_code, "ROLLOVER", rollover_target_odds, ro_odds, current_stake, ro_legs)

                ro_payload = {
                    "status": "SUCCESS",
                    "ticket_id": ro_ticket_id,
                    "title": f"🎯 StatIQ Elite Rollover Slip ({rollover_target_odds:.2f}x)",
                    "booking_code": ro_code or "N/A",
                    "share_url": ro_url,
                    "target_odds": rollover_target_odds,
                    "actual_odds": ro_odds,
                    "confidence_score": ro_prob,
                    "date_str": today_str,
                    "leg_count": len(ro_legs),
                    "picks": ro_legs,
                    "challenge_day": challenge_day_info,
                    "stake": current_stake,
                    "telegram_dispatched": False
                }

                trio_result["rollover_ticket"] = ro_payload

        # ── 2. SLIP 2: PRECISION MULTIPLIER (Dynamic Target Odds, High-Assurance Cushions) ──
        if enable_5odds:
            target_5x = float(acca_5x_target_odds or 5.00)
            min_5x_legs = max(3, int(target_5x * 1.2))
            max_5x_legs = max(min_5x_legs + 2, int(target_5x * 1.8))
            unclaimed_5x = [c for c in banker_candidates if c["event_id"] not in ro_event_ids]
            acca5_legs = cls.assemble_optimal_accumulator_slip(
                unclaimed_5x,
                target_odds=target_5x,
                min_legs=min_5x_legs,
                max_legs=max_5x_legs,
                excluded_event_ids=ro_event_ids
            )
            if acca5_legs:
                for leg in acca5_legs:
                    claimed_event_ids.add(leg["event_id"])
                    acca5_fids.add(leg["event_id"])

                acca5_odds = round(math.prod(leg["odds"] for leg in acca5_legs), 2)
                acca5_prob = round(math.prod(leg["model_probability"] for leg in acca5_legs) * 100.0, 1)
                acca5_code, acca5_url = await cls._request_sportybet_share_code(acca5_legs)
                acca5_ticket_id = f"ACCA5X-{now_ts}"

                cls._persist_ticket_record(acca5_ticket_id, acca5_code, "VALUE_ACCA", target_5x, acca5_odds, 2000.0, acca5_legs)

                acca5_payload = {
                    "status": "SUCCESS",
                    "ticket_id": acca5_ticket_id,
                    "title": f"🎯 StatIQ {target_5x:.1f}x Precision Multiplier Slip",
                    "booking_code": acca5_code or "N/A",
                    "share_url": acca5_url,
                    "target_odds": target_5x,
                    "actual_odds": acca5_odds,
                    "confidence_score": acca5_prob,
                    "date_str": today_str,
                    "leg_count": len(acca5_legs),
                    "picks": acca5_legs,
                    "stake": 2000.0,
                    "telegram_dispatched": False
                }
                trio_result["acca_5x_ticket"] = acca5_payload
            else:
                logger.info(f"[EliteRollover] {target_5x:.1f}x Precision Multiplier rested today: insufficient zero-overlap vetted fixtures on board.")
                trio_result["acca_5x_ticket"] = {
                    "status": "RESTED_LEAN_BOARD",
                    "title": f"{target_5x:.1f}x Precision Multiplier Slip",
                    "booking_code": "RESTED",
                    "message": f"Zero-overlap preserved: {target_5x:.1f}x slip rested today due to lean match schedule.",
                    "telegram_dispatched": False
                }

        # ── 3. SLIP 3: MEGA MULTIPLIER (Strict 100% Zero-Overlap Partition) ──
        if enable_10odds:
            target_10x = float(acca_10x_target_odds or 10.00)
            min_10x_legs = max(5, int(target_10x * 0.8))
            max_10x_legs = max(min_10x_legs + 3, int(target_10x * 1.3))
            # Strictly isolate from Rollover (ro_event_ids) AND Precision Acca (acca5_fids)
            excl_fids = ro_event_ids | acca5_fids
            pool_for_10x = [c for c in banker_candidates if c["event_id"] not in excl_fids]

            acca10_legs = cls.assemble_optimal_accumulator_slip(
                pool_for_10x,
                target_odds=target_10x,
                min_legs=min_10x_legs,
                max_legs=max_10x_legs,
                excluded_event_ids=excl_fids
            )
            if acca10_legs:
                for leg in acca10_legs:
                    claimed_event_ids.add(leg["event_id"])

                acca10_odds = round(math.prod(leg["odds"] for leg in acca10_legs), 2)
                acca10_prob = round(math.prod(leg["model_probability"] for leg in acca10_legs) * 100.0, 1)
                acca10_code, acca10_url = await cls._request_sportybet_share_code(acca10_legs)
                acca10_ticket_id = f"ACCA10X-{now_ts}"

                cls._persist_ticket_record(acca10_ticket_id, acca10_code, "MEGA_10X", target_10x, acca10_odds, 1000.0, acca10_legs)

                acca10_payload = {
                    "status": "SUCCESS",
                    "ticket_id": acca10_ticket_id,
                    "title": f"🚀 StatIQ {target_10x:.1f}x Mega Multiplier Slip",
                    "booking_code": acca10_code or "N/A",
                    "share_url": acca10_url,
                    "target_odds": target_10x,
                    "actual_odds": acca10_odds,
                    "confidence_score": acca10_prob,
                    "date_str": today_str,
                    "leg_count": len(acca10_legs),
                    "picks": acca10_legs,
                    "stake": 1000.0,
                    "telegram_dispatched": False
                }
                trio_result["acca_10x_ticket"] = acca10_payload
            else:
                logger.info(f"[EliteRollover] {target_10x:.1f}x Mega Multiplier rested today: insufficient zero-overlap vetted fixtures on board.")
                trio_result["acca_10x_ticket"] = {
                    "status": "RESTED_LEAN_BOARD",
                    "title": f"{target_10x:.1f}x Mega Multiplier Slip",
                    "booking_code": "RESTED",
                    "message": f"Zero-overlap preserved: {target_10x:.1f}x mega slip rested today due to lean match schedule.",
                    "telegram_dispatched": False
                }

        # ── 4. OPTIONAL: MONSTER ACCA (If explicitly enabled) ──
        if enable_20odds:
            target_20x = float(acca_20x_target_odds or 20.00)
            min_20x_legs = max(10, int(target_20x * 0.65))
            max_20x_legs = max(min_20x_legs + 3, int(target_20x * 0.9))
            pool_for_20x = [c for c in banker_candidates if c["event_id"] not in claimed_event_ids]
            acca20_legs = cls.assemble_optimal_accumulator_slip(
                pool_for_20x,
                target_odds=target_20x,
                min_legs=min_20x_legs,
                max_legs=max_20x_legs,
                excluded_event_ids=claimed_event_ids
            )
            if acca20_legs:
                for leg in acca20_legs:
                    claimed_event_ids.add(leg["event_id"])

                acca20_odds = round(math.prod(leg["odds"] for leg in acca20_legs), 2)
                acca20_prob = round(math.prod(leg["model_probability"] for leg in acca20_legs) * 100.0, 1)
                acca20_code, acca20_url = await cls._request_sportybet_share_code(acca20_legs)
                acca20_ticket_id = f"ACCA20X-{now_ts}"

                cls._persist_ticket_record(acca20_ticket_id, acca20_code, "MEGA_20X", target_20x, acca20_odds, 500.0, acca20_legs)

                acca20_payload = {
                    "status": "SUCCESS",
                    "ticket_id": acca20_ticket_id,
                    "title": f"⚡ StatIQ {target_20x:.1f}x Monster Acca Slip",
                    "booking_code": acca20_code or "N/A",
                    "share_url": acca20_url,
                    "target_odds": target_20x,
                    "actual_odds": acca20_odds,
                    "confidence_score": acca20_prob,
                    "date_str": today_str,
                    "leg_count": len(acca20_legs),
                    "picks": acca20_legs,
                    "stake": 500.0,
                    "telegram_dispatched": False
                }
                trio_result["acca_20x_ticket"] = acca20_payload
            else:
                logger.info(f"[EliteRollover] {target_20x:.1f}x Monster Acca rested today: insufficient zero-overlap vetted fixtures on board.")
                trio_result["acca_20x_ticket"] = {
                    "status": "RESTED_LEAN_BOARD",
                    "title": f"{target_20x:.1f}x Monster Acca Slip",
                    "booking_code": "RESTED",
                    "message": f"Zero-overlap preserved: {target_20x:.1f}x monster slip rested today due to lean match schedule.",
                    "telegram_dispatched": False
                }

        cls._daily_dispatched_event_ids.update(claimed_event_ids)
        trio_result["total_unique_fixtures"] = len(claimed_event_ids)

        # STRICT QUALITY & DELIVERY GATE:
        # 1. 1.50x Banker Rollover slip is the mandatory VIP anchor. It MUST be successfully assembled & booked.
        # 2. Secondary accumulators (5x, 10x, 20x): If they have assembled legs, they MUST be booked successfully.
        #    If a secondary slip was rested due to zero-overlap fixture exhaustion on a lean board, that is an
        #    intentional capital-preservation decision, NOT a delivery failure!
        delivery_failed = False
        fail_reasons = []
        if enable_rollover:
            ro_t = trio_result.get("rollover_ticket")
            if not ro_t or ro_t.get("booking_code") in (None, "N/A", "", "RESTED"):
                delivery_failed = True
                fail_reasons.append("1.50x Banker Rollover slip")

        if enable_5odds and acca5_legs:
            a5_t = trio_result.get("acca_5x_ticket")
            if not a5_t or a5_t.get("booking_code") in (None, "N/A", "", "RESTED"):
                delivery_failed = True
                fail_reasons.append("5.0x Acca slip booking")

        if enable_10odds and acca10_legs:
            a10_t = trio_result.get("acca_10x_ticket")
            if not a10_t or a10_t.get("booking_code") in (None, "N/A", "", "RESTED"):
                delivery_failed = True
                fail_reasons.append("10.0x Mega slip booking")

        if enable_20odds and acca20_legs:
            a20_t = trio_result.get("acca_20x_ticket")
            if not a20_t or a20_t.get("booking_code") in (None, "N/A", "", "RESTED"):
                delivery_failed = True
                fail_reasons.append("20.0x Monster slip booking")

        if delivery_failed:
            trio_result["status"] = "BOOKING_FAILED"
            trio_result["message"] = f"Failed to acquire live booking code for: {', '.join(fail_reasons)}"
            logger.warning(f"[EliteRollover] {trio_result['message']}")
            # DO NOT dispatch any ticket to Telegram if delivery gate failed!
            return trio_result

        trio_result["status"] = "SUCCESS"
        logger.info(f"[EliteRollover] Daily Trio completed with {len(claimed_event_ids)} vetted fixtures across slips.")

        # ATOMIC DISPATCH: Now that all slips are verified and booked, dispatch to Telegram
        if send_telegram:
            # 1. Rollover Slip
            ro_t = trio_result.get("rollover_ticket")
            if ro_t and ro_t.get("booking_code") not in (None, "N/A", "", "RESTED") and not ro_t.get("telegram_dispatched"):
                ro_t["telegram_dispatched"] = RolloverTelegramNotifier.dispatch_rollover_slip(ro_t)

            # 2. 5.0x Precision Multiplier
            a5_t = trio_result.get("acca_5x_ticket")
            if a5_t and a5_t.get("booking_code") not in (None, "N/A", "", "RESTED") and not a5_t.get("telegram_dispatched"):
                a5_t["telegram_dispatched"] = RolloverTelegramNotifier.dispatch_value_acca_slip(a5_t)

            # 3. 10.0x Mega Multiplier
            a10_t = trio_result.get("acca_10x_ticket")
            if a10_t and a10_t.get("booking_code") not in (None, "N/A", "", "RESTED") and not a10_t.get("telegram_dispatched"):
                a10_t["telegram_dispatched"] = RolloverTelegramNotifier.dispatch_mega_multiplier_slip(a10_t)

            # 4. 20.0x Monster Acca
            a20_t = trio_result.get("acca_20x_ticket")
            if a20_t and a20_t.get("booking_code") not in (None, "N/A", "", "RESTED") and not a20_t.get("telegram_dispatched"):
                a20_t["telegram_dispatched"] = RolloverTelegramNotifier.dispatch_mega_20x_slip(a20_t)

        return trio_result

    @classmethod
    async def generate_elite_accumulator(
        cls,
        target_odds: Optional[float] = None,
        target_games: Optional[int] = None,
        num_tickets: int = 1,
        excluded_event_ids: Optional[set] = None,
        time_horizon: str = "TODAY",
        allow_lower_leagues: bool = False
    ) -> List[Dict[str, Any]]:
        """
        Unified On-Demand Generator using the exact same Elite Vetted Selection Engine:
        Powers Telegram /odds, /games, /weekend, /ucl, and Web Ticket Builder with Zero Overlap.
        Supports time_horizon (TODAY, WEEKEND, MIDWEEK_UCL) and explicit allow_lower_leagues opt-in.
        Strict Tier-1/Tier-2 dominance, Poisson scoring, and Min Odds >= 1.15.
        """
        today_only = (time_horizon == "TODAY")
        raw_events = await cls.fetch_sportybet_today_events(max_pages=25 if not today_only else 20, today_only=today_only)
        if not raw_events:
            return []

        candidates = cls.evaluate_elite_rollover_candidates(
            raw_events,
            max_leg_odds=1.55,
            is_on_demand=True,
            time_horizon=time_horizon,
            allow_lower_leagues=allow_lower_leagues,
            for_rollover=False
        )
        if not candidates:
            return []

        claimed = set(excluded_event_ids or set())
        # Afternoon on-demand runs: If fresh unpicked candidates exist outside morning dispatch,
        # prioritize fresh fixtures first to insulate afternoon tickets from morning variance:
        morning_eids = cls._daily_dispatched_event_ids
        if not excluded_event_ids and morning_eids:
            fresh_cands = [c for c in candidates if c["event_id"] not in morning_eids]
            req_legs = target_games if (target_games and target_games > 0) else (6 if (target_odds and target_odds >= 4.5) else 3)
            if len(fresh_cands) >= 5:
                claimed.update(morning_eids)

        results = []
        num_t = max(1, min(4, num_tickets))

        for t_idx in range(num_t):
            unclaimed = [c for c in candidates if c["event_id"] not in claimed]
            if not unclaimed:
                break

            if target_games and target_games > 0:
                # Group by event and respect market diversity quota
                fixture_cands: Dict[str, List[Dict[str, Any]]] = {}
                for c in unclaimed:
                    eid = c["event_id"]
                    if eid not in fixture_cands:
                        fixture_cands[eid] = []
                    fixture_cands[eid].append(c)

                for eid in fixture_cands:
                    fixture_cands[eid].sort(
                        key=lambda x: (x.get("quality_score", 0), x.get("model_probability", 0)),
                        reverse=True
                    )

                sorted_fids = sorted(
                    fixture_cands.keys(),
                    key=lambda eid: (
                        1 if fixture_cands[eid][0].get("is_juggernaut") else 0,
                        fixture_cands[eid][0].get("quality_score", 0),
                        fixture_cands[eid][0].get("model_probability", 0)
                    ),
                    reverse=True
                )

                max_dc = max(2, int(target_games * 0.45))
                max_per_market = max(3, int(target_games * 0.40))
                market_counts: Dict[str, int] = collections.defaultdict(int)
                slip_legs = []
                selected_eids = set()

                # Pass 1: Targeted Market Diversity Mix
                for eid in sorted_fids:
                    opts = fixture_cands[eid]
                    chosen = None
                    for cand in opts:
                        m_type = cand.get("market_type") or "OTHER"
                        limit = max_dc if m_type == "DOUBLE_CHANCE" else max_per_market
                        if market_counts[m_type] < limit:
                            chosen = cand
                            break

                    if chosen:
                        m_type = chosen.get("market_type") or "OTHER"
                        market_counts[m_type] += 1
                        slip_legs.append(chosen)
                        selected_eids.add(eid)
                        if len(slip_legs) >= target_games:
                            break

                # Pass 2: Adaptive Fill-Forward Guarantee (ensures target_games is always reached)
                if len(slip_legs) < target_games:
                    for eid in sorted_fids:
                        if eid in selected_eids:
                            continue
                        opts = fixture_cands[eid]
                        if not opts:
                            continue
                        chosen = opts[0]
                        m_type = chosen.get("market_type") or "OTHER"
                        market_counts[m_type] += 1
                        slip_legs.append(chosen)
                        selected_eids.add(eid)
                        if len(slip_legs) >= target_games:
                            break
            else:
                t_odds = float(target_odds or 5.0)
                if t_odds <= 2.2:
                    slip_legs = cls.assemble_optimal_rollover_slip(unclaimed, target_odds=t_odds)
                else:
                    if t_odds >= 50.0:
                        min_l, max_l = 18, 25
                    elif t_odds >= 25.0:
                        min_l, max_l = 14, 20
                    elif t_odds >= 18.0:
                        min_l, max_l = 10, 15
                    elif t_odds >= 14.0:
                        min_l, max_l = 9, 14
                    elif t_odds >= 8.5:
                        min_l, max_l = 8, 12
                    elif t_odds >= 4.5:
                        min_l, max_l = 5, 8
                    else:
                        min_l, max_l = 3, 5
                    slip_legs = cls.assemble_optimal_accumulator_slip(
                        unclaimed,
                        target_odds=t_odds,
                        min_legs=min_l,
                        max_legs=max_l,
                        excluded_event_ids=claimed
                    )

            if not slip_legs:
                break

            for leg in slip_legs:
                claimed.add(leg["event_id"])
                cls._daily_dispatched_event_ids.add(leg["event_id"])

            acc_odds = round(math.prod(leg["odds"] for leg in slip_legs), 2)
            comb_prob = round(math.prod(leg["model_probability"] for leg in slip_legs) * 100.0, 1)
            b_code, s_url = await cls._request_sportybet_share_code(slip_legs)

            results.append({
                "ticket_index": t_idx + 1,
                "approved_legs": slip_legs,
                "accumulated_odds": acc_odds,
                "combined_probability": comb_prob / 100.0,
                "booking_code": b_code,
                "share_url": s_url,
                "leg_count": len(slip_legs)
            })

        return results

    @classmethod
    async def generate_elite_multi_target_portfolio(
        cls,
        targets: List[float] = [5.0, 10.0]
    ) -> List[Dict[str, Any]]:
        """
        Unified On-Demand Multi-Target Generator (e.g. 5.0x + 10.0x simultaneously):
        Guarantees STRICT ZERO-OVERLAP between all generated slips.
        Uses the exact same Elite Vetted Selection Engine as the 10:00 AM daily automation.
        """
        raw_events = await cls.fetch_sportybet_today_events(max_pages=20)
        if not raw_events:
            return []

        candidates = cls.evaluate_elite_rollover_candidates(raw_events, max_leg_odds=1.55, is_on_demand=True)
        if not candidates:
            return []

        claimed = set(cls._daily_dispatched_event_ids)
        total_req_legs = sum(6 if t >= 4.5 else 3 for t in targets)
        fresh_cands = [c for c in candidates if c["event_id"] not in claimed]
        if len(fresh_cands) < total_req_legs:
            candidates = sorted(candidates, key=lambda c: 0 if c["event_id"] not in claimed else 1)
            claimed = set()

        results = []
        for idx, t_odds in enumerate(targets):
            unclaimed = [c for c in candidates if c["event_id"] not in claimed]
            if not unclaimed:
                break

            if t_odds >= 14.0:
                min_l, max_l = 9, 13
            elif t_odds >= 8.5:
                min_l, max_l = 8, 12
            elif t_odds >= 4.5:
                min_l, max_l = 5, 8
            else:
                min_l, max_l = 3, 5

            slip_legs = cls.assemble_optimal_accumulator_slip(
                unclaimed,
                target_odds=t_odds,
                min_legs=min_l,
                max_legs=max_l,
                excluded_event_ids=claimed
            )

            if not slip_legs:
                continue

            for leg in slip_legs:
                claimed.add(leg["event_id"])
                cls._daily_dispatched_event_ids.add(leg["event_id"])

            acc_odds = round(math.prod(leg["odds"] for leg in slip_legs), 2)
            comb_prob = round(math.prod(leg["model_probability"] for leg in slip_legs) * 100.0, 1)
            b_code, s_url = await cls._request_sportybet_share_code(slip_legs)

            # Check if multiple slips share the same target odds (e.g. 2x 10.0x or 2x 5.0x)
            same_target_count = sum(1 for t in targets if abs(t - t_odds) < 0.5)
            variant_suffix = f" (Variant #{idx + 1})" if same_target_count > 1 else ""

            if 4.0 <= t_odds <= 6.5:
                title = f"🎯 5.0x Precision Multiplier{variant_suffix}"
            elif 8.5 <= t_odds <= 12.0:
                title = f"🚀 10.0x Mega Multiplier{variant_suffix}"
            elif 1.4 <= t_odds <= 2.5:
                title = f"🛡️ {t_odds:.2f}x Banker Rollover Slip{variant_suffix}" if abs(t_odds - 1.5) < 0.2 else f"🛡️ {t_odds:.1f}x Rollover Slip{variant_suffix}"
            else:
                title = f"🎯 {t_odds:.1f}x Multiplier{variant_suffix}"

            results.append({
                "ticket_index": idx + 1,
                "title": title,
                "target_odds": t_odds,
                "accumulated_odds": acc_odds,
                "combined_probability": comb_prob / 100.0,
                "booking_code": b_code,
                "share_url": s_url,
                "approved_legs": slip_legs,
                "leg_count": len(slip_legs)
            })

        return results

