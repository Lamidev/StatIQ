import time
import threading
from datetime import datetime, timezone
from typing import Optional, List, Dict, Any
from sqlalchemy.orm import Session
from app.db.session import SessionLocal
from app.db.models import TrackedTicket, CanonicalFixture, FixtureProviderMapping
from app.providers.api_football_provider import ApiFootballProvider
from app.providers.sportybet_provider import SportyBetProvider
from app.providers.resolver import FixtureIdentityResolver
from app.evaluators.base import MatchStateContext
from app.evaluators.router import SettlementRouter

class LiveTrackingScheduler:
    """
    StatIQ V2.0 Smart Match-State-Driven Live Tracking & Settlement Scheduler.
    Runs autonomously in background, dynamically adjusting polling frequencies.
    """
    _instance = None
    _running = False
    _thread = None

    def __init__(self):
        self.api_football = ApiFootballProvider()
        self.sportybet = SportyBetProvider()

    @classmethod
    def start_scheduler(cls):
        if cls._running:
            return
        cls._running = True
        inst = cls()
        cls._thread = threading.Thread(target=inst._run_loop, daemon=True, name="StatIQ-LiveScheduler")
        cls._thread.start()
        print("[LiveTrackingScheduler] V2.0 Autonomous Scheduler daemon active.")

    def _run_loop(self):
        time.sleep(10) # cold start grace period
        while self._running:
            try:
                db = SessionLocal()
                sleep_interval = self.sync_and_settle_all(db)
                db.close()
            except Exception as e:
                print("[LiveTrackingScheduler] Sync loop error:", e)
                sleep_interval = 30

            time.sleep(max(15, sleep_interval))

    def sync_and_settle_all(self, db: Session) -> int:
        """
        Main tick:
        1. Find all running tickets.
        2. Ingest live updates for unique active fixtures.
        3. Evaluate selections using SettlementRouter.
        4. Settle finished accumulators immediately.
        Returns suggested sleep interval in seconds based on highest priority match state.
        """
        tickets = db.query(TrackedTicket).filter(TrackedTicket.status == "RUNNING").all()
        if not tickets:
            return 120 # No active tickets -> slow idle

        has_live_matches = False
        has_approaching_matches = False
        now_ts = int(time.time())

        # 1. Collect unique fixtures to monitor
        fixture_map = {}
        for t in tickets:
            for sel in (t.selections or []):
                h = sel.get("home_team")
                a = sel.get("away_team")
                if not h or not a:
                    continue
                    
                gid = str(sel.get("game_id") or sel.get("fixture_id") or "")
                sr_id = sel.get("sportradar_id") or (gid if gid.startswith("sr:") else None)
                sp_gid = None if gid.startswith("sr:") else gid

                # Ensure canonical fixture exists
                fix = FixtureIdentityResolver.resolve_and_persist(
                    db=db,
                    home_team=h,
                    away_team=a,
                    competition=sel.get("competition") or "League",
                    kickoff_ms=sel.get("start_time_ms") or sel.get("kickoff_datetime"),
                    sportybet_game_id=sp_gid,
                    sportradar_event_id=sr_id
                )
                fixture_map[fix.id] = (fix, sel)

        # 2. Fetch live data for active fixtures
        for fix_id, (fix, sample_sel) in fixture_map.items():
            if fix.status == "FINISHED":
                continue

            # Query provider mappings
            mappings = db.query(FixtureProviderMapping).filter(FixtureProviderMapping.fixture_id == fix_id).all()
            prov_state = None

            # Tier 1: Try SportyBet In-Play if game ID exists
            sp_map = next((m for m in mappings if m.provider == "SPORTYBET"), None)
            sr_map = next((m for m in mappings if m.provider == "SPORTRADAR"), None)
            
            if sp_map or sr_map:
                prov_state = self.sportybet.fetch_fixture_state(
                    provider_event_id=sr_map.provider_event_id if sr_map else None,
                    provider_game_id=sp_map.provider_game_id if sp_map else None
                )

            # Tier 2: Try API-Football if available or not yet found
            af_map = next((m for m in mappings if m.provider == "API_FOOTBALL"), None)
            if not prov_state and af_map and af_map.provider_event_id:
                prov_state = self.api_football.fetch_fixture_state(provider_event_id=af_map.provider_event_id)

            # Tier 3: Autonomous Gemini Search-Grounded Fallback (Zero-Quota Dependency)
            # If match is finished or >105 mins elapsed but score or corners remain unverified
            ko_elapsed_mins = int((now_ts * 1000 - (fix.kickoff_utc.timestamp() * 1000)) / 60000) if fix.kickoff_utc else 0
            if (not prov_state or prov_state.home_score is None) and (ko_elapsed_mins > 105 or fix.status in ("FINISHED", "CONCLUDED", "FT")):
                try:
                    from app.services.gemini_service import GeminiAIService
                    gemini = GeminiAIService()
                    ai_res = gemini.reconcile_match_results([{
                        "fixture_id": fix.id,
                        "home_team": fix.home_team,
                        "away_team": fix.away_team,
                        "competition": fix.competition
                    }])
                    if ai_res and len(ai_res) > 0:
                        first_m = ai_res[0]
                        if first_m.get("home_score") is not None and first_m.get("away_score") is not None:
                            fix.status = "FINISHED"
                            fix.home_score = int(first_m.get("home_score"))
                            fix.away_score = int(first_m.get("away_score"))
                            if first_m.get("ht_home_score") is not None:
                                fix.half_time_home_score = int(first_m.get("ht_home_score"))
                                fix.half_time_away_score = int(first_m.get("ht_away_score", 0))
                            if first_m.get("total_corners") is not None:
                                fix.total_corners = int(first_m.get("total_corners"))
                                fix.home_corners = int(first_m.get("home_corners", 0))
                                fix.away_corners = int(first_m.get("away_corners", 0))
                            fix.updated_at = datetime.now(timezone.utc)
                            db.flush()
                except Exception as e:
                    print(f"[LiveTrackingScheduler] Gemini autonomous reconciliation error for {fix.home_team} vs {fix.away_team}: {e}")

            if prov_state:
                fix.status = prov_state.status
                fix.minute = prov_state.minute
                fix.match_clock = prov_state.match_clock
                if prov_state.home_score is not None:
                    fix.home_score = prov_state.home_score
                    fix.away_score = prov_state.away_score
                if prov_state.half_time_home_score is not None:
                    fix.half_time_home_score = prov_state.half_time_home_score
                    fix.half_time_away_score = prov_state.half_time_away_score
                if prov_state.total_corners is not None:
                    fix.total_corners = prov_state.total_corners
                    fix.home_corners = prov_state.home_corners
                    fix.away_corners = prov_state.away_corners
                fix.updated_at = datetime.now(timezone.utc)
                db.flush()

            # Check priority for scheduler timing
            ko_ms = int(fix.kickoff_utc.timestamp() * 1000) if fix.kickoff_utc else 0
            if fix.status in ("LIVE", "HALFTIME", "SECOND_HALF"):
                has_live_matches = True
            elif ko_ms and (ko_ms - (now_ts * 1000)) < 15 * 60 * 1000:
                has_approaching_matches = True


        # 3. Synchronize selections and evaluate tickets
        for t in tickets:
            all_concluded = True
            loss_count = 0
            allowed_losses = t.allowed_losses or (1 if t.flex_cut in ("1-CUT", "1_CUT", "1") else 0)
            updated_selections = []

            for sel in (t.selections or []):
                h = sel.get("home_team", "")
                a = sel.get("away_team", "")
                canon_id = FixtureIdentityResolver.generate_canonical_id(h, a)
                fix = db.query(CanonicalFixture).filter(CanonicalFixture.id == canon_id).first()

                h_score = fix.home_score if fix else sel.get("home_score")
                a_score = fix.away_score if fix else sel.get("away_score")
                ht_h = fix.half_time_home_score if fix else sel.get("ht_home_score")
                ht_a = fix.half_time_away_score if fix else sel.get("ht_away_score")
                tot_c = fix.total_corners if fix else sel.get("total_corners")
                h_c = fix.home_corners if fix else sel.get("home_corners")
                a_c = fix.away_corners if fix else sel.get("away_corners")
                
                is_conc = (fix.status == "FINISHED") if fix else (sel.get("match_status") in ("CONCLUDED", "FINISHED", "FT"))

                # Context for evaluator
                ctx = MatchStateContext(
                    home_score=h_score,
                    away_score=a_score,
                    is_concluded=is_conc,
                    is_live=(fix.status in ("LIVE", "HALFTIME", "SECOND_HALF")) if fix else bool(sel.get("is_live")),
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

                # Mirror state into selection dict for frontend API consumers
                sel["leg_status"] = eval_res.status
                sel["result"] = eval_res.result_text
                if h_score is not None and a_score is not None:
                    sel["score"] = f"{h_score} - {a_score}"
                    sel["home_score"] = h_score
                    sel["away_score"] = a_score
                if ht_h is not None: sel["ht_home_score"] = ht_h
                if ht_a is not None: sel["ht_away_score"] = ht_a
                if tot_c is not None: sel["total_corners"] = tot_c
                if fix:
                    sel["match_status"] = "CONCLUDED" if fix.status == "FINISHED" else fix.status
                    sel["match_time"] = fix.match_clock or "--"
                    sel["is_live"] = fix.status in ("LIVE", "HALFTIME", "SECOND_HALF")

                if eval_res.status == "LOST":
                    loss_count += 1
                if eval_res.status not in ("WON", "LOST", "VOID"):
                    all_concluded = False

                updated_selections.append(sel)

            t.selections = updated_selections
            t.loss_count = loss_count

            # Enforce Accumulator / Flex Cut settlement
            if loss_count > allowed_losses:
                t.status = "LOST"
                t.settled_at = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M:%S")
            elif all_concluded and loss_count <= allowed_losses:
                t.status = "WON"
                t.settled_at = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M:%S")

        db.commit()

        if has_live_matches:
            return 25 # In-play matches -> 25s polling
        if has_approaching_matches:
            return 60 # Kickoff approaching -> 60s polling
        return 180 # All pre-match -> 3m polling
