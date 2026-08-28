"""
VirtualFrontTestWorker - Autonomous 24/7 Front-Testing Agent for SportyBet vFootball.
Monitors ~30-min league rounds, generates 2.0x tickets per league + cross-league master slips,
fetches live SportyBet booking codes, dispatches Telegram signals, and audits post-match win rates.
Enforces persistent database configuration, heartbeat emission, and fail-closed state invariants.
"""
import time
import uuid
import threading
import logging
from datetime import datetime, timezone, timedelta
from typing import Dict, Any, List, Optional
from sqlalchemy.orm import Session

from virtual.core.db import SessionLocal
from virtual.models.virtual_models import (
    VirtualFrontTestSlip, VirtualEvent, VirtualAgentConfig, VirtualAgentHeartbeat
)
from virtual.ingestion.virtual_sportybet_client import VirtualSportyBetClient
from virtual.services.telegram_service import VirtualTelegramService
from virtual.api.agent_control_routes import _pick_selections, _build_booking_code

logger = logging.getLogger("statiq.virtual.fronttest_worker")

def _format_wat_time(dt: Optional[datetime]) -> str:
    if not dt:
        return "Upcoming"
    wat_hour = (dt.hour + 1) % 24
    return f"{wat_hour:02d}:{dt.minute:02d} WAT"



class VirtualFrontTestWorker:
    """
    Background worker orchestrating continuous vFootball front-testing.
    Authoritatively bound to the SQLite `virtual_agent_config` table.
    """
    _running: bool = False
    _enabled: bool = True
    _thread: threading.Thread = None
    _last_run_time: float = 0.0
    _poll_interval: int = 10  # Poll every 10 seconds

    # Cached Runtime Configuration (Refreshed on each tick from DB)
    config = {
        "target_odds": 2.0,
        "stake_amount": 1000.0,
        "preferred_market": "ALL",
        "league_count": 2,
        "selected_leagues": ["England Virtual", "Spain Virtual"],
        "min_confidence_prob": 0.72,
        "config_version": 1
    }


    @classmethod
    def start(cls):
        if cls._running:
            return
        cls._running = True
        cls._thread = threading.Thread(target=cls._run_loop, daemon=True, name="StatIQ-FrontTestWorker")
        cls._thread.start()
        logger.info("[FrontTestWorker] Background worker started with persistent DB state.")

    @classmethod
    def set_enabled(cls, enabled: bool):
        cls._enabled = enabled
        logger.info(f"[FrontTestWorker] Local toggle set to: {'ON' if enabled else 'OFF'}")

    @classmethod
    def is_enabled(cls) -> bool:
        return cls._enabled

    @classmethod
    def update_config(cls, new_config: Dict[str, Any]):
        cls.config.update(new_config)

    @classmethod
    def get_status(cls, db: Session) -> Dict[str, Any]:
        """
        Calculates cumulative performance metrics from the database.
        """
        all_slips = db.query(VirtualFrontTestSlip).order_by(VirtualFrontTestSlip.created_at.desc()).all()
        total_slips = len(all_slips)
        won_slips = sum(1 for s in all_slips if s.status == "WON")
        lost_slips = sum(1 for s in all_slips if s.status == "LOST")
        pending_slips = sum(1 for s in all_slips if s.status == "PENDING")

        settled = won_slips + lost_slips
        win_rate = round((won_slips / settled) * 100.0, 1) if settled > 0 else 0.0

        net_profit_units = sum(s.profit_loss for s in all_slips if s.profit_loss is not None)

        recent_slips = []
        seen_codes = set()
        for s in all_slips:
            code_key = s.booking_code or str(s.id)
            if code_key in seen_codes:
                continue
            seen_codes.add(code_key)
            recent_slips.append({
                "id": s.id,
                "ticket_id": s.ticket_id,
                "booking_code": s.booking_code,
                "league_name": s.league_name,
                "round_time": s.round_time.isoformat() if s.round_time else None,
                "actual_odds": s.actual_odds,
                "num_games": s.num_games,
                "status": s.status,
                "profit_loss": s.profit_loss,
                "selections": s.selections,
                "created_at": s.created_at.isoformat() if s.created_at else None,
            })
            if len(recent_slips) >= 15:
                break

        return {
            "is_enabled": cls._enabled,
            "is_running": cls._running,
            "telegram_configured": VirtualTelegramService.is_configured(),
            "config": cls.config,
            "total_slips": total_slips,
            "won_slips": won_slips,
            "lost_slips": lost_slips,
            "pending_slips": pending_slips,
            "win_rate_pct": win_rate,
            "net_profit_units": round(net_profit_units, 2),
            "recent_slips": recent_slips
        }

    _last_daily_report_date: str = ""

    @classmethod
    def _run_loop(cls):
        time.sleep(3)
        while cls._running:
            try:
                db = SessionLocal()
                # 1. Fetch Authoritative Persistent DB Config
                cfg = db.query(VirtualAgentConfig).filter(VirtualAgentConfig.id == "default").first()
                if not cfg:
                    cfg = VirtualAgentConfig(
                        id="default",
                        enabled=True,
                        emergency_stop=False,
                        target_odds=2.0,
                        stake_amount=1000.0,
                        league_count=2,
                        selected_leagues=["England Virtual", "Spain Virtual"],
                        strategy="ADAPTIVE",
                        risk_profile="CONSERVATIVE",
                        config_version=1
                    )
                    db.add(cfg)
                    db.commit()
                    db.refresh(cfg)

                # Sync in-memory runtime cache
                cls._enabled = bool(cfg.enabled)
                cls.config["target_odds"] = float(cfg.target_odds)
                cls.config["stake_amount"] = float(cfg.stake_amount)
                cls.config["league_count"] = int(cfg.league_count)
                cls.config["selected_leagues"] = list(cfg.selected_leagues or [])
                cls.config["preferred_market"] = str(cfg.preferred_market or "ALL")
                cls.config["config_version"] = int(cfg.config_version)

                # 2. Determine Worker State
                if cfg.emergency_stop:
                    worker_state = "EMERGENCY_STOPPED"
                elif not cfg.enabled:
                    worker_state = "PAUSED"
                else:
                    worker_state = "RUNNING"

                # 3. Emit Real-time Heartbeat to Database
                hb = db.query(VirtualAgentHeartbeat).filter(VirtualAgentHeartbeat.worker_id == "vfootball_fronttest_worker").first()
                if not hb:
                    hb = VirtualAgentHeartbeat(worker_id="vfootball_fronttest_worker")
                    db.add(hb)
                hb.last_seen = datetime.now(timezone.utc)
                hb.worker_state = worker_state
                hb.config_version = cfg.config_version
                db.commit()

                # 4. State Execution Invariants (Fail-Closed)
                if worker_state == "RUNNING":
                    cls._process_pre_match_dispatches(db, cfg)
                    cls._process_kickoff_alerts(db)
                else:
                    # In PAUSED / EMERGENCY_STOPPED mode, do NOT dispatch new bets
                    pass

                # Always settle already-placed tickets so ledger remains accurate
                cls._process_settlements(db)
                cls._process_daily_midnight_report(db)
                db.close()
            except Exception as e:
                logger.error(f"[FrontTestWorker] Loop execution error: {e}")

            time.sleep(cls._poll_interval)

    # -----------------------------------------------------------------
    # Kickoff In-Play Alerts
    # -----------------------------------------------------------------

    _sent_kickoff_codes: set = set()

    @classmethod
    def _process_kickoff_alerts(cls, db: Session):
        """
        Sends an alert to Telegram when an upcoming round starts playing.
        Strictly deduplicated to ensure each ticket fires at most once!
        """
        now = datetime.now(timezone.utc)
        active_slips = db.query(VirtualFrontTestSlip).filter(
            VirtualFrontTestSlip.status == "PENDING",
            VirtualFrontTestSlip.kickoff_alert_sent == False,
            VirtualFrontTestSlip.round_time <= now,
            VirtualFrontTestSlip.round_time >= (now - timedelta(minutes=4))
        ).all()

        for slip in active_slips:
            if slip.booking_code in cls._sent_kickoff_codes:
                slip.kickoff_alert_sent = True
                db.commit()
                continue

            cls._sent_kickoff_codes.add(slip.booking_code)
            slip.kickoff_alert_sent = True
            db.commit()

            slip_payload = {
                "league_name": slip.league_name,
                "booking_code": slip.booking_code,
                "actual_odds": slip.actual_odds,
                "round_time_str": _format_wat_time(slip.round_time),
                "selections": slip.selections or []
            }
            VirtualTelegramService.send_kickoff_alert(slip_payload)


    # -----------------------------------------------------------------
    # Midnight 12:00 AM Daily Performance Report
    # -----------------------------------------------------------------

    @classmethod
    def _process_daily_midnight_report(cls, db: Session):
        """
        Automatically generates and delivers the 12:00 AM (00:00) daily performance audit.
        """
        now = datetime.now(timezone.utc)
        today_str = now.strftime("%Y-%m-%d")

        if cls._last_daily_report_date and cls._last_daily_report_date != today_str and now.hour == 0:
            yesterday_start = datetime(now.year, now.month, now.day, tzinfo=timezone.utc) - timedelta(days=1)
            yesterday_end = datetime(now.year, now.month, now.day, tzinfo=timezone.utc)

            day_slips = db.query(VirtualFrontTestSlip).filter(
                VirtualFrontTestSlip.created_at >= yesterday_start,
                VirtualFrontTestSlip.created_at < yesterday_end
            ).all()

            today_total = len(day_slips)
            today_won = sum(1 for s in day_slips if s.status == "WON")
            today_lost = sum(1 for s in day_slips if s.status == "LOST")
            today_settled = today_won + today_lost
            today_win_rate = round((today_won / today_settled) * 100.0, 1) if today_settled > 0 else 0.0
            today_profit = sum(s.profit_loss for s in day_slips if s.profit_loss is not None)
            today_roi = round((today_profit / max(1, today_settled)) * 100.0, 1) if today_settled > 0 else 0.0

            all_stats = cls.get_status(db)
            report_payload = {
                "today_total_slips": today_total,
                "today_won_slips": today_won,
                "today_lost_slips": today_lost,
                "today_win_rate_pct": today_win_rate,
                "today_net_profit_units": today_profit,
                "today_roi_pct": today_roi,
                "total_slips": all_stats.get("total_slips", 0),
                "win_rate_pct": all_stats.get("win_rate_pct", 0.0),
                "net_profit_units": all_stats.get("net_profit_units", 0.0)
            }

            sent = VirtualTelegramService.send_daily_summary_report(report_payload)
            if sent:
                cls._last_daily_report_date = today_str
        elif not cls._last_daily_report_date:
            cls._last_daily_report_date = today_str


    # -----------------------------------------------------------------
    # Phase 1: Pre-Match Scanning & Dispatch (Authoritative DB Gated)
    # -----------------------------------------------------------------

    @classmethod
    def _process_pre_match_dispatches(cls, db: Session, cfg: Optional[VirtualAgentConfig] = None):
        """
        Dispatches target odds tickets for upcoming rounds based on authoritative DB configuration.
        """
        raw_events = VirtualSportyBetClient.fetch_upcoming_virtual_events()
        if not raw_events:
            return

        now = datetime.now(timezone.utc)
        target_odds = float(cfg.target_odds if cfg else cls.config.get("target_odds", 2.0))
        mkt = str(cfg.preferred_market if cfg else cls.config.get("preferred_market", "ALL"))
        league_count = int(cfg.league_count if cfg else cls.config.get("league_count", 2))
        selected_leagues = list((cfg.selected_leagues if cfg else cls.config.get("selected_leagues")) or [])

        # Group events by league
        leagues_map: Dict[str, List[Dict[str, Any]]] = {}
        for ev in raw_events:
            sport = ev.get("sport", {})
            cat = sport.get("category", {}) if isinstance(sport, dict) else {}
            league_name = f"{cat.get('name', 'Virtual')} Virtual"
            leagues_map.setdefault(league_name, []).append(ev)

        # 1. Determine Eligible Leagues
        eligible_leagues = []
        if selected_leagues and len(selected_leagues) > 0:
            for l_name in selected_leagues:
                if l_name in leagues_map:
                    eligible_leagues.append(l_name)
        else:
            # Automatic selection: take the top N available leagues
            eligible_leagues = list(leagues_map.keys())[:league_count]

        # 2. Dispatch Individual League Slips
        for league_name in eligible_leagues:
            events = leagues_map.get(league_name, [])
            if len(events) >= 3:
                cls._dispatch_league_ticket_if_needed(db, league_name, events, target_odds, mkt, now)

        # 3. Cross-League Master Slip (if 2+ leagues active)
        if len(eligible_leagues) >= 2 and len(raw_events) >= 6:
            master_events = []
            for l_name in eligible_leagues:
                master_events.extend(leagues_map.get(l_name, []))
            if master_events:
                cls._dispatch_master_ticket_if_needed(db, master_events, target_odds, mkt, now)


        # 3. Sweep & deliver any pending slips not yet dispatched to Telegram
        undispatched = db.query(VirtualFrontTestSlip).filter(
            VirtualFrontTestSlip.status == "PENDING",
            VirtualFrontTestSlip.telegram_dispatched == False
        ).all()
        for slip in undispatched:
            r_dt = slip.round_time
            if r_dt and r_dt.tzinfo is None:
                r_dt = r_dt.replace(tzinfo=timezone.utc)
            if r_dt and r_dt >= (now - timedelta(minutes=1)):
                slip_payload = {
                    "league_name": slip.league_name,
                    "booking_code": slip.booking_code,
                    "actual_odds": slip.actual_odds,
                    "round_time_str": _format_wat_time(r_dt),
                    "selections": slip.selections or []
                }
                sent = VirtualTelegramService.send_ticket_alert(slip_payload)
                if sent:
                    slip.telegram_dispatched = True
                    db.commit()


    @classmethod
    def _dispatch_league_ticket_if_needed(
        cls, db: Session, league_name: str, events: List[Dict], target_odds: float, mkt: str, now: datetime
    ):
        first_event = events[0]
        start_ms = first_event.get("estimateStartTime", 0)
        if not start_ms:
            return
        round_dt = datetime.fromtimestamp(start_ms / 1000.0, tz=timezone.utc)

        # Only dispatch if round is starting in 2 to 10 minutes (10-min pre-match alert)
        time_to_kickoff = (round_dt - now).total_seconds()
        if not (120 <= time_to_kickoff <= 660):
            return

        # Check if already booked for this round
        existing = db.query(VirtualFrontTestSlip).filter(
            VirtualFrontTestSlip.league_name == league_name,
            VirtualFrontTestSlip.round_time >= (round_dt - timedelta(minutes=3)),
            VirtualFrontTestSlip.round_time <= (round_dt + timedelta(minutes=3))
        ).first()

        if existing:
            return

        # Pick 2-3 winnable selections approximating target odds
        num_games = 2 if target_odds <= 2.2 else 3
        selections = _pick_selections(events, mkt, num_games, target_odds, db=db)
        if not selections or len(selections) < 2:
            return

        # Calculate actual total odds
        total_odds = 1.0
        for s in selections:
            total_odds *= s["odds"]
        total_odds = round(total_odds, 2)

        # Request verified SportyBet booking code
        booking_code = _build_booking_code(selections)
        ticket_id = f"FT-{league_name[:3].upper()}-{round_dt.strftime('%H%M')}-{uuid.uuid4().hex[:4].upper()}"

        slip = VirtualFrontTestSlip(
            ticket_id=ticket_id,
            booking_code=booking_code,
            league_name=league_name,
            round_time=round_dt,
            target_odds=target_odds,
            actual_odds=total_odds,
            num_games=len(selections),
            stake_amount=cls.config.get("stake_amount", 1000.0),
            potential_return=round(cls.config.get("stake_amount", 1000.0) * total_odds, 2),
            selections=selections,
            status="PENDING",
            telegram_dispatched=False,
            created_at=now
        )
        db.add(slip)
        db.commit()

    @classmethod
    def _dispatch_master_ticket_if_needed(
        cls, db: Session, all_events: List[Dict], target_odds: float, mkt: str, now: datetime
    ):
        start_ms = all_events[0].get("estimateStartTime", 0)
        if not start_ms:
            return
        round_dt = datetime.fromtimestamp(start_ms / 1000.0, tz=timezone.utc)

        time_to_kickoff = (round_dt - now).total_seconds()
        if not (120 <= time_to_kickoff <= 660):
            return


        league_name = "Master Multi-League"

        existing = db.query(VirtualFrontTestSlip).filter(
            VirtualFrontTestSlip.league_name == league_name,
            VirtualFrontTestSlip.round_time >= (round_dt - timedelta(minutes=3)),
            VirtualFrontTestSlip.round_time <= (round_dt + timedelta(minutes=3))
        ).first()

        if existing:
            return

        # Pick top 2 safest selections across the entire pool
        selections = _pick_selections(all_events, mkt, 2, target_odds, db=db)

        if not selections or len(selections) < 2:
            return

        total_odds = 1.0
        for s in selections:
            total_odds *= s["odds"]
        total_odds = round(total_odds, 2)

        booking_code = _build_booking_code(selections)
        ticket_id = f"FT-MASTER-{round_dt.strftime('%H%M')}-{uuid.uuid4().hex[:4].upper()}"

        slip = VirtualFrontTestSlip(
            ticket_id=ticket_id,
            booking_code=booking_code,
            league_name=league_name,
            round_time=round_dt,
            target_odds=target_odds,
            actual_odds=total_odds,
            num_games=len(selections),
            stake_amount=cls.config.get("stake_amount", 1000.0),
            potential_return=round(cls.config.get("stake_amount", 1000.0) * total_odds, 2),
            selections=selections,
            status="PENDING",
            telegram_dispatched=False,
            created_at=now
        )
        db.add(slip)
        db.commit()



    # -----------------------------------------------------------------
    @classmethod
    def _extract_final_scores(cls, ev_data: Dict[str, Any], time_since_kickoff: float = 0.0) -> tuple[Optional[int], Optional[int]]:
        """
        Parses home and away scores from SportyBet API payload.
        Ensures match is at full time (matchStatus FT/Ended, status 3, or elapsed simulation >= 130s).
        """
        if not ev_data:
            return None, None

        match_status = str(ev_data.get("matchStatus") or "").upper().strip()
        status_num = ev_data.get("status")
        set_score = ev_data.get("setScore") or ev_data.get("score")

        # 1. STRICT LIVE BLOCKER: If it is playing (H1, H2, HT, Live), NEVER settle
        if any(live_tag in match_status for live_tag in ["H1", "H2", "HT", "1ST", "2ND", "HALF", "LIVE", "NOT START"]):
            return None, None

        # 2. Full-time check: must be ended/FT/FINISHED or status 3
        is_ended = (
            "ENDED" in match_status or 
            "FT" in match_status or 
            "FINISHED" in match_status or 
            status_num == 3
        )
        if not is_ended:
            return None, None


        # 2. Check setScore string (e.g. "2:1" or "3:0")
        if isinstance(set_score, str) and ":" in set_score:
            parts = set_score.split(":")
            try:
                return int(parts[0].strip()), int(parts[1].strip())
            except (ValueError, IndexError):
                pass

        # 3. Check dictionary format
        if isinstance(set_score, dict):
            h = set_score.get("home") or set_score.get("homeScore")
            a = set_score.get("away") or set_score.get("awayScore")
            if h is not None and a is not None:
                try:
                    return int(h), int(a)
                except ValueError:
                    pass

        # 4. Fallback check for market settlement flags
        markets = ev_data.get("markets", [])
        for m in markets:
            if m.get("desc") == "1X2" or str(m.get("id")) == "1":
                for oc in m.get("outcomes", []):
                    if oc.get("status") == 1 or oc.get("isWinner") == 1:
                        desc = str(oc.get("desc") or "").upper()
                        if "HOME" in desc or desc == "1":
                            return 1, 0
                        elif "AWAY" in desc or desc == "2":
                            return 0, 1
                        elif "DRAW" in desc or desc == "X":
                            return 1, 1

        return None, None

    @classmethod
    def _process_settlements(cls, db: Session):
        """
        Settles pending slips once matches have finished (~2 to 3 mins post-kickoff).
        """
        now = datetime.now(timezone.utc)
        # Settle slips whose kickoff was at least 2 minutes ago
        pending = db.query(VirtualFrontTestSlip).filter(
            VirtualFrontTestSlip.status == "PENDING",
            VirtualFrontTestSlip.round_time <= (now - timedelta(minutes=2))
        ).all()

        for slip in pending:
            selections = slip.selections or []
            all_resolved = True
            all_won = True

            r_time = slip.round_time
            if r_time and r_time.tzinfo is None:
                r_time = r_time.replace(tzinfo=timezone.utc)
            time_since_kickoff = (now - (r_time or now)).total_seconds()

            for s in selections:
                # If score already saved in selection from prior poll
                saved_score = s.get("final_score")
                if saved_score and "-" in saved_score:
                    continue

                game_id = s.get("game_id")
                ev_data = VirtualSportyBetClient.fetch_event_result(game_id)
                h_score, a_score = cls._extract_final_scores(ev_data, time_since_kickoff=time_since_kickoff)

                if h_score is None or a_score is None:
                    # If game was played more than 20 mins ago and result closed without score
                    if time_since_kickoff > 1200:
                        all_resolved = False
                        slip.status = "EXPIRED"
                        slip.profit_loss = 0.0
                        db.commit()
                        break
                    else:
                        all_resolved = False
                        break

                leg_won = cls._evaluate_leg(s, h_score, a_score)
                s["final_score"] = f"{h_score} - {a_score}"
                s["leg_won"] = leg_won
                # Flag db modified for JSON column
                from sqlalchemy.orm.attributes import flag_modified
                flag_modified(slip, "selections")
                db.commit()


                if not leg_won:
                    all_won = False

                # Record match outcome in VirtualMatchHistory for rolling team stats
                match_str = s.get("match", "")
                home_t, away_t = "?", "?"
                if " vs " in match_str:
                    parts = match_str.split(" vs ")
                    home_t, away_t = parts[0].strip(), parts[1].strip()
                from virtual.services.virtual_stats_enricher import VirtualStatsEnricher
                VirtualStatsEnricher.record_match_result(
                    db,
                    game_id=game_id,
                    league_name=slip.league_name,
                    home_team=home_t,
                    away_team=away_t,
                    home_score=h_score,
                    away_score=a_score,
                    kickoff_time=r_time or now
                )

            if all_resolved:
                slip.selections = selections
                if all_won:
                    slip.status = "WON"
                    slip.profit_loss = round(slip.actual_odds - 1.0, 2)
                else:
                    slip.status = "LOST"
                    slip.profit_loss = -1.0
                slip.settled_at = now
                db.commit()

                # Get cumulative stats and send settlement alert
                status_data = cls.get_status(db)
                slip_payload = {
                    "league_name": slip.league_name,
                    "booking_code": slip.booking_code,
                    "actual_odds": slip.actual_odds,
                    "selections": selections
                }
                VirtualTelegramService.send_settlement_alert(slip_payload, all_won, status_data)


    @classmethod
    def _evaluate_leg(cls, selection: Dict[str, Any], h_score: int, a_score: int) -> bool:
        pick_code = str(selection.get("pick_code", "")).lower()
        pick = str(selection.get("pick", "")).lower()
        tot_goals = h_score + a_score

        if "over_1.5" in pick_code or "over 1.5" in pick:
            return tot_goals >= 2
        elif "over_2.5" in pick_code or "over 2.5" in pick:
            return tot_goals >= 3
        elif "under_2.5" in pick_code or "under 2.5" in pick:
            return tot_goals < 3
        elif "under_3.5" in pick_code or "under 3.5" in pick:
            return tot_goals < 4
        elif pick_code in ["1x", "dc_1x"] or "1x" in pick or "home or draw" in pick:
            return h_score >= a_score
        elif pick_code in ["x2", "dc_x2"] or "x2" in pick or "draw or away" in pick:
            return a_score >= h_score
        elif pick_code == "1" or "win" in pick and "1" in pick_code:
            return h_score > a_score
        elif pick_code == "2" or "win" in pick and "2" in pick_code:
            return a_score > h_score
        return False

