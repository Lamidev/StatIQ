import os
import json
import time
import re
from typing import List, Dict, Any, Optional
from sqlalchemy.orm import Session

from app.db.session import SessionLocal, Base, engine
from app.db.models import TrackedTicket

# Create DB tables if not exist
Base.metadata.create_all(bind=engine)

TRACKER_FILE = os.path.join(os.path.dirname(__file__), "..", "..", "data", "tracked_tickets.json")

# ─────────────────────────────────────────────────────────────────────────────
# Storage & Migration helpers (SQLite ORM)
# ─────────────────────────────────────────────────────────────────────────────

def _ticket_to_dict(t: TrackedTicket) -> Dict[str, Any]:
    return {
        "id": t.id,
        "code": t.code,
        "mode": t.mode,
        "target_odds": t.target_odds,
        "total_odds": t.total_odds,
        "stake": t.stake,
        "flex_cut": t.flex_cut,
        "potential_win": t.potential_win,
        "status": t.status,
        "created_at": t.created_at,
        "locked_at_unix": t.locked_at_unix,
        "selections": t.selections or [],
        "settled_at": t.settled_at,
        "flex_status_text": t.flex_status_text,
        "allowed_losses": t.allowed_losses,
        "loss_count": t.loss_count,
        "is_live": t.is_live,
        "stale": t.stale,
        "stale_reason": t.stale_reason,
    }


def _migrate_json_to_db_if_needed(db: Session):
    """
    One-time migration: copies legacy tickets from tracked_tickets.json
    into the SQLite database if the table is empty.
    """
    try:
        if os.path.exists(TRACKER_FILE):
            count = db.query(TrackedTicket).count()
            if count == 0:
                with open(TRACKER_FILE, "r", encoding="utf-8") as f:
                    json_tickets = json.load(f)
                if isinstance(json_tickets, list) and json_tickets:
                    print(f"[TicketTracker] Migrating {len(json_tickets)} legacy tickets from JSON file to SQLite database...")
                    save_tracked_tickets(json_tickets, db=db)
                bak_path = TRACKER_FILE + ".bak"
                os.rename(TRACKER_FILE, bak_path)
                print(f"[TicketTracker] Migration complete. Renamed legacy file to {bak_path}")
    except Exception as e:
        print("[TicketTracker] Auto-migration warning:", e)


def get_tracked_tickets(db: Optional[Session] = None) -> List[Dict[str, Any]]:
    should_close = False
    if db is None:
        db = SessionLocal()
        should_close = True
    try:
        _migrate_json_to_db_if_needed(db)
        rows = db.query(TrackedTicket).order_by(TrackedTicket.locked_at_unix.desc()).all()
        return [_ticket_to_dict(r) for r in rows]
    except Exception as e:
        print("[TicketTracker] Fetch DB error:", e)
        return []
    finally:
        if should_close:
            db.close()


def save_tracked_tickets(tickets: List[Dict[str, Any]], db: Optional[Session] = None):
    should_close = False
    if db is None:
        db = SessionLocal()
        should_close = True
    try:
        for data in tickets:
            ticket_id = data.get("id")
            if not ticket_id:
                continue
            existing = db.query(TrackedTicket).filter(TrackedTicket.id == ticket_id).first()
            if existing:
                existing.code = data.get("code", existing.code)
                existing.mode = data.get("mode", existing.mode)
                existing.target_odds = float(data.get("target_odds", existing.target_odds))
                existing.total_odds = float(data.get("total_odds", existing.total_odds))
                existing.stake = float(data.get("stake", existing.stake))
                existing.flex_cut = data.get("flex_cut", existing.flex_cut)
                existing.potential_win = float(data.get("potential_win", existing.potential_win))
                existing.status = data.get("status", existing.status)
                existing.created_at = data.get("created_at", existing.created_at)
                existing.locked_at_unix = int(data.get("locked_at_unix", existing.locked_at_unix))
                existing.selections = data.get("selections", existing.selections)
                existing.settled_at = data.get("settled_at", existing.settled_at)
                existing.flex_status_text = data.get("flex_status_text", existing.flex_status_text)
                existing.allowed_losses = data.get("allowed_losses", existing.allowed_losses)
                existing.loss_count = data.get("loss_count", existing.loss_count)
                existing.is_live = data.get("is_live", existing.is_live)
                existing.stale = data.get("stale", existing.stale)
                existing.stale_reason = data.get("stale_reason", existing.stale_reason)
            else:
                new_t = TrackedTicket(
                    id=ticket_id,
                    code=data.get("code", "CUSTOM"),
                    mode=data.get("mode", "SWAP"),
                    target_odds=float(data.get("target_odds", 1.5)),
                    total_odds=float(data.get("total_odds", 1.5)),
                    stake=float(data.get("stake", 100.0)),
                    flex_cut=data.get("flex_cut"),
                    potential_win=float(data.get("potential_win", 150.0)),
                    status=data.get("status", "RUNNING"),
                    created_at=data.get("created_at", time.strftime("%Y-%m-%d %H:%M:%S")),
                    locked_at_unix=int(data.get("locked_at_unix", time.time())),
                    selections=data.get("selections", []),
                    settled_at=data.get("settled_at"),
                    flex_status_text=data.get("flex_status_text"),
                    allowed_losses=data.get("allowed_losses"),
                    loss_count=data.get("loss_count"),
                    is_live=data.get("is_live", False),
                    stale=data.get("stale", False),
                    stale_reason=data.get("stale_reason"),
                )
                db.add(new_t)
        db.commit()
    except Exception as e:
        db.rollback()
        print("[TicketTracker] Save DB error:", e)
    finally:
        if should_close:
            db.close()


def _parse_score(score_str: str):
    """
    Parse a score string like '0:2', '0 - 2', '2:2', '1-1' into (home, away) integers.
    Returns (None, None) if unparseable.
    """
    if not score_str or not isinstance(score_str, str):
        return None, None
    m = re.search(r"(\d+)\s*[:\-v\s]\s*(\d+)", score_str)
    if m:
        try:
            return int(m.group(1)), int(m.group(2))
        except (ValueError, IndexError):
            return None, None
    return None, None


# ─────────────────────────────────────────────────────────────────────────────
# Lock / Delete
# ─────────────────────────────────────────────────────────────────────────────

def lock_ticket(payload: Dict[str, Any], db: Optional[Session] = None) -> Dict[str, Any]:
    ticket_id = f"TICK-{int(time.time())}"
    stake = float(payload.get("stake", 100.0))
    total_odds = float(payload.get("total_odds", 1.5))

    # Accept pre-baked scores at lock time (for AUDITOR / historical mode)
    final_scores: Dict[str, Dict] = payload.get("final_scores", {})  # fixture_id → {home, away}

    new_ticket = {
        "id": ticket_id,
        "code": payload.get("code", "CUSTOM"),
        "mode": payload.get("mode", "SWAP"),
        "target_odds": payload.get("target_odds", 1.5),
        "total_odds": total_odds,
        "stake": stake,
        "flex_cut": payload.get("flex_cut"),
        "potential_win": round(stake * total_odds, 2),
        "status": "RUNNING",
        "created_at": time.strftime("%Y-%m-%d %H:%M:%S"),
        "locked_at_unix": int(time.time()),
        "selections": payload.get("selections", []),
    }

    # If final_scores provided at lock time → settle immediately
    if final_scores:
        new_ticket = _apply_scores_to_ticket(new_ticket, final_scores)

    save_tracked_tickets([new_ticket], db=db)
    return new_ticket


def delete_tracked_ticket(ticket_id: str, db: Optional[Session] = None) -> bool:
    should_close = False
    if db is None:
        db = SessionLocal()
        should_close = True
    try:
        item = db.query(TrackedTicket).filter(TrackedTicket.id == ticket_id).first()
        if item:
            db.delete(item)
            db.commit()
            return True
        return False
    except Exception as e:
        db.rollback()
        print("[TicketTracker] Delete DB error:", e)
        return False
    finally:
        if should_close:
            db.close()


# ─────────────────────────────────────────────────────────────────────────────
# Pick evaluator — comprehensive market coverage
# ─────────────────────────────────────────────────────────────────────────────

def evaluate_pick(pick_name: str, home_score: int, away_score: int,
                  home_team: str = "", away_team: str = "") -> str:
    """
    Return 'WON', 'LOST', or 'VOID' given the final scores.
    Handles all MatchIQ market types including combo markets.
    """
    if home_score is None or away_score is None:
        return "WON"  # Can't evaluate — optimistically pass

    p = (pick_name or "").lower().strip()
    ht = (home_team or "").lower().strip()
    at = (away_team or "").lower().strip()
    total = home_score + away_score

    # Sanitize category prefix so "over/under" doesn't collide with "under 1.5"
    p_market_clean = re.sub(r"double chance\s*&\s*over\s*/\s*under", "", p)
    p_market_clean = re.sub(r"over\s*/\s*under", "", p_market_clean).strip()

    # ── Combo Markets: Double Chance & Over/Under (e.g. "Home/Away & Over 1.5", "1X & Over 1.5") ──
    if ("double chance" in p or "home/away" in p or "home/draw" in p or "away/draw" in p or "(12)" in p or "(1x)" in p or "(x2)" in p or "12 &" in p or "1x &" in p or "x2 &" in p) and ("over" in p or "under" in p):
        m_ov = re.search(r"over\s*(\d+\.?\d*)", p)
        m_un = re.search(r"under\s*(\d+\.?\d*)", p)

        dc_satisfied = False
        if "home/away" in p or "(12)" in p or " 12 " in f" {p} " or "home or away" in p:
            dc_satisfied = (home_score != away_score)
        elif "home/draw" in p or "(1x)" in p or " 1x " in f" {p} " or "home or draw" in p:
            dc_satisfied = (home_score >= away_score)
        elif "away/draw" in p or "(x2)" in p or " x2 " in f" {p} " or "away or draw" in p:
            dc_satisfied = (away_score >= home_score)
        else:
            if ht and ht in p and "away" not in p:
                dc_satisfied = (home_score >= away_score)
            elif at and at in p and "home" not in p:
                dc_satisfied = (away_score >= home_score)
            else:
                dc_satisfied = (home_score != away_score)

        goals_satisfied = True
        if m_ov:
            goals_satisfied = (total > float(m_ov.group(1)))
        elif m_un:
            goals_satisfied = (total < float(m_un.group(1)))

        return "WON" if (dc_satisfied and goals_satisfied) else "LOST"

    # ── Goal Bounds ── e.g. "2-5+", "3-5+", "0-1", "6+"
    gb = re.match(r"^(\d+)-(\d+)\+?$", p.replace(" ", ""))
    if gb:
        lo, hi = int(gb.group(1)), int(gb.group(2))
        return "WON" if (lo <= total <= hi or (p.endswith("+") and total >= lo)) else "LOST"
    if re.match(r"^(\d+)\+$", p.replace(" ", "")):
        lo = int(re.match(r"^(\d+)\+$", p.replace(" ", "")).group(1))
        return "WON" if total >= lo else "LOST"

    # ── 2nd Half – Double Chance (Home or Away) ──
    if "2nd half" in p and "double chance" in p:
        if "home or away" in p or "12" in p:
            return "WON" if home_score != away_score else "LOST"
        if "home or draw" in p or "1x" in p:
            return "WON" if home_score >= away_score else "LOST"
        if "away or draw" in p or "x2" in p:
            return "WON" if away_score >= home_score else "LOST"
        return "WON" if home_score != away_score else "LOST"

    # ── SportyBet Compound OR Markets (Home/Away Team or Over 2.5) ──
    if "or over 2.5" in p or "& over 2.5" in p:
        over25 = total > 2.5
        if "away" in p or (at and at in p):
            res = (away_score > home_score) or over25
        elif "home" in p or (ht and ht in p):
            res = (home_score > away_score) or over25
        else:
            res = (home_score != away_score) or over25
        return "WON" if res else "LOST"

    # ── Double Chance (Comprehensive) ──
    if "(12)" in p or " 12 " in f" {p} " or "home/away" in p or "home or away" in p or (ht and at and ht in p and at in p and "or" in p and "draw" not in p):
        return "WON" if home_score != away_score else "LOST"

    if "(1x)" in p or " 1x " in f" {p} " or "home/draw" in p or "home or draw" in p or (ht and ht in p and "draw" in p and "away" not in p):
        return "WON" if home_score >= away_score else "LOST"

    if "(x2)" in p or " x2 " in f" {p} " or "away/draw" in p or "away or draw" in p or "draw or away" in p or (at and at in p and "draw" in p and "home" not in p):
        return "WON" if away_score >= home_score else "LOST"

    if "or draw" in p:
        team_part = p.replace("or draw", "").replace("(1x)", "").replace("(x2)", "").strip().rstrip("(").strip()
        if ht and ht in team_part:
            return "WON" if home_score >= away_score else "LOST"
        if at and at in team_part:
            return "WON" if away_score >= home_score else "LOST"
        return "WON" if home_score >= away_score else "LOST"

    # ── Win Either Half (WEH) ──
    if "win either half" in p or "weh" in p:
        if ht and ht in p:
            return "WON" if home_score > away_score else "LOST"
        if "home" in p:
            return "WON" if home_score > away_score else "LOST"
        if at and at in p:
            return "WON" if away_score > home_score else "LOST"
        if "away" in p:
            return "WON" if away_score > home_score else "LOST"
        return "WON" if home_score != away_score else "LOST"

    # ── Draw No Bet (DNB) ──
    if "draw no bet" in p or "dnb" in p or "win (dnb)" in p:
        if home_score == away_score:
            return "VOID"
        if ht and ht in p:
            return "WON" if home_score > away_score else "LOST"
        if at and at in p:
            return "WON" if away_score > home_score else "LOST"
        if "home" in p:
            return "WON" if home_score > away_score else "LOST"
        if "away" in p:
            return "WON" if away_score > home_score else "LOST"
        return "WON" if home_score > away_score else "LOST"

    # ── Asian Handicap ──
    if "asian handicap" in p or "handicap" in p or "(+1" in p or "(+2" in p or "(-1" in p or "(-0.5)" in p or "+1.5" in p or "+2" in p:
        is_away_target = False
        is_home_target = False

        sel_lower = (pick_name or "").lower()
        if at and at in sel_lower:
            is_away_target = True
        elif ht and ht in sel_lower:
            is_home_target = True
        elif "away" in sel_lower or sel_lower.endswith("2"):
            is_away_target = True
        elif "home" in sel_lower or sel_lower.endswith("1"):
            is_home_target = True

        hcp_val = 1.5
        m_val = re.search(r"([+-]?\d+\.?\d*)", p.replace("(+", " +").replace("(-", " -"))
        if m_val:
            try:
                hcp_val = float(m_val.group(1))
            except ValueError:
                hcp_val = 1.5

        if ("+1.5" in p or "+1.5" in sel_lower) and hcp_val > 0: hcp_val = 1.5
        elif ("+2.0" in p or "+2" in p) and hcp_val > 0: hcp_val = 2.0
        elif ("+1.0" in p or "+1" in p) and hcp_val > 0: hcp_val = 1.0
        elif ("+0.5" in p) and hcp_val > 0: hcp_val = 0.5
        elif ("-1.5" in p) and hcp_val > 0: hcp_val = -1.5
        elif ("-1.0" in p) and hcp_val > 0: hcp_val = -1.0
        elif ("-0.5" in p) and hcp_val > 0: hcp_val = -0.5

        is_integer_hcp = (hcp_val == int(hcp_val))
        adj = (away_score + hcp_val - home_score) if is_away_target else (home_score + hcp_val - away_score)

        if is_integer_hcp and adj == 0:
            return "VOID"
        return "WON" if adj > 0 else "LOST"

    # Use sanitized string for pure Over/Under checking
    p_clean = p_market_clean

    # ── 1st Half Over/Under ──
    if "1st half" in p_clean or "ht " in p_clean:
        if "over 0.5" in p_clean: return "WON" if total >= 1 else "LOST"
        if "over 1.5" in p_clean: return "WON" if total >= 2 else "LOST"
        if "under 0.5" in p_clean: return "WON" if total == 0 else "LOST"
        if "under 1.5" in p_clean: return "WON" if total <= 1 else "LOST"

    # ── Over / Under (standard & whole-integer goal lines) ──
    if "under 0.5" in p_clean: return "WON" if total < 1 else "LOST"
    if "under 1.5" in p_clean: return "WON" if total < 2 else "LOST"
    if "under 2.5" in p_clean: return "WON" if total < 3 else "LOST"
    if "under 3.5" in p_clean: return "WON" if total < 4 else "LOST"
    if "under 4.5" in p_clean: return "WON" if total < 5 else "LOST"
    if "under 2"   in p_clean and "2.5" not in p_clean:
        return "VOID" if total == 2 else ("WON" if total < 2 else "LOST")
    if "under 3"   in p_clean and "3.5" not in p_clean:
        return "VOID" if total == 3 else ("WON" if total < 3 else "LOST")

    if "over 0.5"  in p_clean: return "WON" if total >= 1 else "LOST"
    if "over 1.5"  in p_clean: return "WON" if total >= 2 else "LOST"
    if "over 2.5"  in p_clean: return "WON" if total >= 3 else "LOST"
    if "over 3.5"  in p_clean: return "WON" if total >= 4 else "LOST"
    if "over 4.5"  in p_clean: return "WON" if total >= 5 else "LOST"
    if "over 2"    in p_clean and "2.5" not in p_clean:
        return "VOID" if total == 2 else ("WON" if total > 2 else "LOST")
    if "over 3"    in p_clean and "3.5" not in p_clean:
        return "VOID" if total == 3 else ("WON" if total > 3 else "LOST")

    # ── Team Goals / Team Over Under ──
    if "over 0.5 goals" in p or "over 0.5 team goals" in p or "team goals" in p or "over 0.5" in p:
        if ht and ht in p:   return "WON" if home_score >= 1 else "LOST"
        if at and at in p:   return "WON" if away_score >= 1 else "LOST"
        if "home" in p:      return "WON" if home_score >= 1 else "LOST"
        if "away" in p:      return "WON" if away_score >= 1 else "LOST"
        return "WON" if total >= 1 else "LOST"

    # ── GG / Both Teams To Score ──
    if "gg" in p or "both teams to score" in p or "btts" in p:
        return "WON" if (home_score >= 1 and away_score >= 1) else "LOST"

    # ── 1UP / 2UP / Early Payout Markets ──
    if "1up" in p or "1 up" in p or "2up" in p or "2 up" in p or "lead" in p:
        is_home_target = "home" in p or (ht and ht in p) or p.startswith("1")
        is_away_target = "away" in p or (at and at in p) or p.startswith("2")

        if "2up" in p or "2 up" in p:
            if is_away_target:
                return "WON" if (away_score - home_score >= 2 or away_score > home_score) else "LOST"
            return "WON" if (home_score - away_score >= 2 or home_score > away_score) else "LOST"
        else:
            if is_away_target:
                return "WON" if (away_score >= 1 or away_score > home_score) else "LOST"
            return "WON" if (home_score >= 1 or home_score > away_score) else "LOST"

    # ── Standard 1X2 ──
    if "home win" in p or p == "1": return "WON" if home_score > away_score else "LOST"
    if "away win" in p or p == "2": return "WON" if away_score > home_score else "LOST"
    if "draw" in p or p == "x":    return "WON" if home_score == away_score else "LOST"

    if ht and ht in p: return "WON" if home_score > away_score else "LOST"
    if at and at in p: return "WON" if away_score > home_score else "LOST"

    return "WON"


# ─────────────────────────────────────────────────────────────────────────────
# Score application helpers
# ─────────────────────────────────────────────────────────────────────────────

def _apply_scores_to_ticket(ticket: Dict, scores_map: Dict) -> Dict:
    """
    Apply a map of {fixture_id: {home_score, away_score, score_str}} to a ticket's
    selections, evaluating each pick and then settling the overall ticket.
    scores_map keys can be fixture_id (str) or match_key.
    """
    all_won = True
    any_lost = False
    all_concluded = True

    for sel in ticket.get("selections", []):
        fid = str(sel.get("fixture_id", ""))
        mk = sel.get("match_key", "")

        # Find a matching score entry
        score_entry = (
            scores_map.get(fid) or
            scores_map.get(mk) or
            scores_map.get(sel.get("home_team", "") + "_" + sel.get("away_team", ""))
        )

        if not score_entry:
            if sel.get("leg_result") in ("WON", "LOST"):
                sel["leg_status"] = sel["leg_result"]
                if sel["leg_result"] == "LOST":
                    any_lost = True
                    all_won = False
            else:
                all_concluded = False
            continue

        h = score_entry.get("home_score")
        a = score_entry.get("away_score")
        score_str = score_entry.get("score_str") or f"{h} - {a}"

        # Store the score on the selection
        sel["score"] = score_str
        sel["home_score"] = h
        sel["away_score"] = a
        sel["match_status"] = "CONCLUDED"

        # Evaluate
        mkt_str = sel.get("market_name") or ""
        sel_str = sel.get("selection_name") or sel.get("selection") or ""
        pick_str = f"{mkt_str} — {sel_str}".strip(" —") if mkt_str else sel_str

        res_eval = evaluate_pick(
            pick_str, h, a,
            sel.get("home_team", ""),
            sel.get("away_team", "")
        )
        if res_eval == "VOID":
            sel["leg_status"] = "VOID"
        elif res_eval in ("WON", True):
            sel["leg_status"] = "WON"
            sel["result"] = sel.get("selection_name") or "Passed"
        else:
            sel["leg_status"] = "LOST"
            sel["result"] = "Failed"
            any_lost = True
            all_won = False

    # Flex Cut Aware Settlement
    flex_cut_raw = str(ticket.get("flex_cut", "AUTO")).upper().strip()
    n_legs = len(ticket.get("selections", []))

    if flex_cut_raw == "AUTO":
        if n_legs <= 4:
            max_allowed_losses = 0
        elif n_legs <= 8:
            max_allowed_losses = 1
        elif n_legs <= 15:
            max_allowed_losses = 2
        elif n_legs <= 25:
            max_allowed_losses = 3
        else:
            max_allowed_losses = 5
    elif flex_cut_raw in ("OFF", "NONE", "0"):
        max_allowed_losses = 0
    else:
        try:
            max_allowed_losses = int(flex_cut_raw.replace("CUT-", "").replace("CUT", "").strip())
        except ValueError:
            max_allowed_losses = 0

    loss_count = sum(1 for s in ticket.get("selections", []) if s.get("leg_status") == "LOST")
    concluded_count = sum(1 for s in ticket.get("selections", []) if s.get("leg_status") in ("WON", "LOST", "VOID") or s.get("match_status") == "CONCLUDED")
    all_concluded = (concluded_count == n_legs) and n_legs > 0

    ticket["flex_cut"] = flex_cut_raw
    ticket["allowed_losses"] = max_allowed_losses
    ticket["loss_count"] = loss_count

    if loss_count > max_allowed_losses:
        ticket["status"] = "LOST"
        ticket["flex_status_text"] = f"Exceeded Flex Cut-{max_allowed_losses} ({loss_count} losses)" if max_allowed_losses > 0 else "Straight Acca Lost"
        ticket["settled_at"] = time.strftime("%Y-%m-%d %H:%M:%S")
    elif all_concluded and loss_count <= max_allowed_losses:
        ticket["status"] = "WON"
        if loss_count > 0:
            ticket["flex_status_text"] = f"WON (Covered by Flex Cut-{max_allowed_losses} — {loss_count} loss paid out)"
        else:
            ticket["flex_status_text"] = "WON (Clean Sweep - 0 Losses)"
        ticket["settled_at"] = time.strftime("%Y-%m-%d %H:%M:%S")
    else:
        ticket["status"] = "RUNNING"

    return ticket


# ─────────────────────────────────────────────────────────────────────────────
# Settlement from explicit scores payload
# ─────────────────────────────────────────────────────────────────────────────

def delete_tracked_ticket(ticket_id: str, db: Optional[Session] = None) -> bool:
    should_close = False
    if db is None:
        db = SessionLocal()
        should_close = True
    try:
        t_clean = str(ticket_id).strip()
        # Look up ALL ticket records by exact ID, TICK- prefixed ID, booking code, or partial match
        items = db.query(TrackedTicket).filter(
            (TrackedTicket.id == t_clean) |
            (TrackedTicket.id == f"TICK-{t_clean}") |
            (TrackedTicket.code == t_clean) |
            (TrackedTicket.id.like(f"%{t_clean}%")) |
            (TrackedTicket.code.like(f"%{t_clean}%"))
        ).all()

        if items:
            deleted_count = len(items)
            for item in items:
                db.delete(item)
            db.commit()
            print(f"[TicketTracker] Permanently deleted {deleted_count} ticket record(s) for query '{ticket_id}' from SQLite DB")
            return True

        print(f"[TicketTracker] Delete requested for {ticket_id} but not found in DB")
        return False
    except Exception as e:
        db.rollback()
        print("[TicketTracker] Delete DB error:", e)
        return False
    finally:
        if should_close:
            db.close()


def settle_ticket_with_scores(ticket_id: str, fixture_scores: List[Dict], db: Optional[Session] = None) -> Optional[Dict]:
    """
    Force-settle a specific ticket using provided scores.
    fixture_scores: list of {fixture_id, home_score, away_score}
    """
    tickets = get_tracked_tickets(db=db)
    scores_map = {
        str(s.get("fixture_id", "")): {
            "home_score": int(s.get("home_score", 0)),
            "away_score": int(s.get("away_score", 0)),
            "score_str": f"{s.get('home_score', 0)} - {s.get('away_score', 0)}"
        }
        for s in fixture_scores
    }

    for i, t in enumerate(tickets):
        if t.get("id") == ticket_id or t.get("code") == ticket_id:
            updated_t = _apply_scores_to_ticket(t, scores_map)
            save_tracked_tickets([updated_t], db=db)
            return updated_t
    return None


def settle_all_with_scores(fixture_scores: List[Dict], db: Optional[Session] = None) -> List[Dict]:
    """
    Apply a single batch of scores to ALL RUNNING tickets.
    """
    tickets = get_tracked_tickets(db=db)
    scores_map = {
        str(s.get("fixture_id", "")): {
            "home_score": int(s.get("home_score", 0)),
            "away_score": int(s.get("away_score", 0)),
            "score_str": f"{s.get('home_score', 0)} - {s.get('away_score', 0)}"
        }
        for s in fixture_scores
    }

    updated_list = []
    for t in tickets:
        if t.get("status") == "RUNNING":
            t_settled = _apply_scores_to_ticket(t, scores_map)
            updated_list.append(t_settled)

    if updated_list:
        save_tracked_tickets(updated_list, db=db)

    return get_tracked_tickets(db=db)


def evaluate_pick_status(
    full_pick: str,
    home_score: Optional[int],
    away_score: Optional[int],
    home_team: str = "",
    away_team: str = "",
    is_concluded: bool = False
) -> str:
    """
    Evaluates a pick given scores and match status.

    - If is_concluded == True: Evaluates final outcome ('WON', 'LOST', 'VOID').
    - If is_concluded == False (Live / Ongoing / Pending / Upcoming):
        - Returns 'WON' only for Early Win thresholds (e.g., Over 1.5 passed, BTTS Yes both scored).
        - Returns 'LOST' only for Early Loss thresholds (e.g., Under 2.5 exceeded, BTTS No both scored).
        - Otherwise returns 'PENDING'!
    """
    if home_score is None or away_score is None:
        return "PENDING" if not is_concluded else "WON"

    total = home_score + away_score
    p = full_pick.lower().strip()

    # 1. OVER GOALS & CORNERS
    m_over = re.search(r"over\s*(\d+\.?\d*)", p)
    if m_over:
        line = float(m_over.group(1))
        if total > line:
            return "WON"
        if is_concluded:
            return "LOST"
        return "PENDING"

    # 2. UNDER GOALS & CORNERS
    m_under = re.search(r"under\s*(\d+\.?\d*)", p)
    if m_under:
        line = float(m_under.group(1))
        if total > line:
            return "LOST"
        if is_concluded:
            return "WON" if total <= line else "LOST"
        return "PENDING"

    # 3. BOTH TEAMS TO SCORE (GG / NG)
    if "both teams to score" in p or "gg" in p or "btts" in p:
        is_no = "no" in p or "ng" in p
        if is_no:
            if home_score >= 1 and away_score >= 1:
                return "LOST"
            if is_concluded:
                return "WON" if (home_score == 0 or away_score == 0) else "LOST"
            return "PENDING"
        else:
            if home_score >= 1 and away_score >= 1:
                return "WON"
            if is_concluded:
                return "LOST"
            return "PENDING"

    # 4. COMPOUND OR MARKETS (Home/Away Team or Over 2.5)
    if "or over 2.5" in p or "& over 2.5" in p:
        if total >= 3:
            return "WON"
        if is_concluded:
            return evaluate_pick(full_pick, home_score, away_score, home_team, away_team)
        return "PENDING"

    # 5. TEAM GOALS (Over 0.5)
    if "team goals" in p or "over 0.5" in p:
        ht = home_team.lower().strip()
        at = away_team.lower().strip()
        is_home = (ht and ht in p) or "home" in p
        is_away = (at and at in p) or "away" in p

        target = home_score if is_home else (away_score if is_away else total)
        if target >= 1:
            return "WON"
        if is_concluded:
            return "LOST"
        return "PENDING"

    # 6. WIN EITHER HALF (WEH)
    if "win either half" in p or "weh" in p:
        ht = home_team.lower().strip()
        at = away_team.lower().strip()
        is_home = (ht and ht in p) or "home" in p
        is_away = (at and at in p) or "away" in p

        team_leading = (home_score > away_score) if is_home else (away_score > home_score)
        if team_leading and is_concluded:
            return "WON"
        if is_concluded:
            return "LOST"
        return "PENDING"

    # 7. EARLY PAYOUT MARKETS (1UP / 2UP / Lead 1 / Lead 2 / Score First)
    if "1up" in p or "1 up" in p or "scores first" in p or "2up" in p or "2 up" in p:
        ht = home_team.lower().strip()
        at = away_team.lower().strip()
        is_home = "home" in p or (ht and ht in p) or p.startswith("1")
        is_away = "away" in p or (at and at in p) or p.startswith("2")

        if "2up" in p or "2 up" in p:
            if is_home and (home_score - away_score >= 2 or (is_concluded and home_score > away_score)):
                return "WON"
            if is_away and (away_score - home_score >= 2 or (is_concluded and away_score > home_score)):
                return "WON"
        else:
            if is_home and (home_score >= 1 or (is_concluded and home_score > away_score)):
                return "WON"
            if is_away and (away_score >= 1 or (is_concluded and away_score > home_score)):
                return "WON"

        if is_concluded:
            return "LOST"
        return "PENDING"

    # ALL OTHER MARKETS (Double Chance, 1X2, Asian Handicap, Draw No Bet)
    if is_concluded:
        return evaluate_pick(full_pick, home_score, away_score, home_team, away_team)

    return "PENDING"


# ─────────────────────────────────────────────────────────────────────────────
# Main evaluation loop (called on every GET /list)
# ─────────────────────────────────────────────────────────────────────────────

def evaluate_tracked_tickets(db: Optional[Session] = None) -> List[Dict[str, Any]]:
    """
    Evaluates all tracked tickets.

    1. Settles finished legs game-by-game (marking leg_status as WON or LOST).
    2. Enforces Flex Cut early bust: if loss_count > allowed_losses, ticket becomes LOST immediately.
    3. If all legs concluded and loss_count <= allowed_losses, ticket becomes WON.
    4. Otherwise ticket remains RUNNING with finished legs settled game-by-game.
    """
    tickets = get_tracked_tickets(db=db)
    updated = False
    now = int(time.time())

    for t in tickets:
        is_ticket_live = False
        concluded_legs = 0
        n_legs = len(t.get("selections", []))

        for sel in t.get("selections", []):
            st = (sel.get("match_status") or "UPCOMING").upper()
            is_conc = st in ("CONCLUDED", "FINISHED")
            score_str = sel.get("score", "")

            if st in ("LIVE", "ONGOING", "IN_PLAY") or sel.get("is_live"):
                is_ticket_live = True

            if score_str or is_conc:
                h, a = _parse_score(score_str) if score_str else (sel.get("home_score"), sel.get("away_score"))
                mkt_str = sel.get("market_name") or ""
                sel_str = sel.get("selection_name") or sel.get("selection") or ""
                full_pick = f"{mkt_str} — {sel_str}".strip(" —") if mkt_str else sel_str

                res_status = evaluate_pick_status(
                    full_pick, h, a,
                    home_team=sel.get("home_team", ""),
                    away_team=sel.get("away_team", ""),
                    is_concluded=is_conc
                )

                if res_status == "VOID":
                    sel["leg_status"] = "VOID"
                    concluded_legs += 1
                elif res_status in ("WON", True):
                    sel["leg_status"] = "WON"
                    sel["result"] = sel.get("selection_name") or "Passed"
                    concluded_legs += 1
                elif res_status in ("LOST", False):
                    sel["leg_status"] = "LOST"
                    sel["result"] = "Failed"
                    concluded_legs += 1
                else:
                    sel["leg_status"] = "PENDING"
                    sel["result"] = "--"

                if is_conc:
                    sel["match_status"] = "CONCLUDED"
                continue

            leg_res = sel.get("leg_result") or sel.get("leg_status")
            if leg_res in ("WON", "LOST") and is_conc:
                sel["leg_status"] = leg_res
                concluded_legs += 1
                continue

            if leg_res == "VOID" or st in ("NULLED_EXPIRED", "CANCELLED", "POSTPONED"):
                sel["leg_status"] = "VOID"
                concluded_legs += 1
                continue

            sel["leg_status"] = "PENDING"
            sel["result"] = "--"

        t["is_live"] = is_ticket_live

        flex_cut = t.get("flex_cut", "AUTO")
        flex_cut_str = str(flex_cut).upper().strip()
        if flex_cut_str == "AUTO":
            if n_legs <= 4:
                allowed_losses = 0
            elif n_legs <= 8:
                allowed_losses = 1
            elif n_legs <= 15:
                allowed_losses = 2
            elif n_legs <= 25:
                allowed_losses = 3
            else:
                allowed_losses = 5
        elif flex_cut_str in ("OFF", "NONE", "0"):
            allowed_losses = 0
        else:
            try:
                allowed_losses = int(flex_cut_str.replace("CUT-", "").replace("CUT", "").strip())
            except Exception:
                allowed_losses = 0

        loss_count = sum(1 for sel in t.get("selections", []) if sel.get("leg_status") == "LOST")
        all_concluded = (concluded_legs == n_legs) and n_legs > 0

        t["flex_cut"] = flex_cut_str
        t["allowed_losses"] = allowed_losses
        t["loss_count"] = loss_count

        if loss_count > allowed_losses:
            # Losses exceeded flex cut buffer -> INSTANT TICKET BUST (LOST)
            t["status"] = "LOST"
            t["flex_status_text"] = f"Exceeded Flex Cut-{allowed_losses} ({loss_count} losses)" if allowed_losses > 0 else "Straight Acca Lost"
            t["settled_at"] = time.strftime("%Y-%m-%d %H:%M:%S")
            updated = True
        elif all_concluded and loss_count <= allowed_losses:
            # All matches concluded AND losses within flex cut -> Ticket WON!
            t["status"] = "WON"
            if loss_count > 0:
                t["flex_status_text"] = f"WON (Covered by Flex Cut-{allowed_losses} — {loss_count} loss paid out)"
            else:
                t["flex_status_text"] = "WON (Clean Sweep - 0 Losses)"
            t["settled_at"] = t.get("settled_at") or time.strftime("%Y-%m-%d %H:%M:%S")
            updated = True
        else:
            # Ticket remains RUNNING with completed legs settled game-by-game
            t["status"] = "RUNNING"
            t["flex_status_text"] = None
            locked_at = t.get("locked_at_unix", 0)
            age_hours = (now - locked_at) / 3600 if locked_at else 0
            if age_hours >= 4 and t.get("mode") in ("AUDITOR", "SWAP", "REMOVE"):
                t["stale"] = True
                t["stale_reason"] = f"Ticket locked {age_hours:.1f}h ago — scores not yet provided. Use 'Settle Now' to manually provide results."
            else:
                t["stale"] = False

    if updated:
        save_tracked_tickets(tickets, db=db)

    return tickets


_last_sync_time: float = 0.0
_SYNC_COOLDOWN_SECONDS = 10  # Minimum seconds between full syncs (rapid live updates)


def sync_tracked_tickets_with_live_apis(db: Optional[Session] = None) -> List[Dict[str, Any]]:
    """
    Fetches real-time live scores and match statuses dynamically from SportyBet API
    and live data endpoints, updating tracked_tickets DB table and re-evaluating picks.
    Rate-limited to once every 25 seconds to avoid overloading the backend.
    """
    global _last_sync_time
    now_ts = time.time()

    # Rate-limit: don't re-sync if last sync was less than 25s ago
    if now_ts - _last_sync_time < _SYNC_COOLDOWN_SECONDS:
        return evaluate_tracked_tickets(db=db)

    _last_sync_time = now_ts
    tickets = get_tracked_tickets(db=db)

    # Process all tickets with valid SportyBet booking codes against live API data
    running_tickets = [
        t for t in tickets
        if t.get("code")
        and t.get("code") not in ("CUSTOM", "AI-BUILDER-TICKET", "")
    ]

    if not running_tickets:
        return evaluate_tracked_tickets(db=db)

    try:
        from app.adapters.bookmaker_adapter import SportyBetAdapter
        adapter = SportyBetAdapter(db)

        for t in running_tickets:
            code = t.get("code")
            res = adapter.fetch_booking_code_details(code, "ng")
            if res and res.get("status") == "SUCCESS":
                sb_selections = res.get("selections", [])
                sb_map = {}
                for item in sb_selections:
                    gid = str(item.get("game_id") or item.get("external_fixture_id") or "")
                    mkey = f"{(item.get('home_team') or '').strip()}_{(item.get('away_team') or '').strip()}".lower()
                    if gid:
                        sb_map[gid] = item
                    if mkey:
                        sb_map[mkey] = item

                for sel in t.get("selections", []):
                    gid = str(sel.get("game_id") or sel.get("fixture_id") or "")
                    mkey = f"{(sel.get('home_team') or '').strip()}_{(sel.get('away_team') or '').strip()}".lower()
                    sb_item = sb_map.get(gid) or sb_map.get(mkey)
                    if sb_item:
                        score_raw = sb_item.get("score") or ""
                        if score_raw:
                            sel["score"] = score_raw
                            h, a = _parse_score(score_raw)
                            if h is not None:
                                sel["home_score"] = h
                                sel["away_score"] = a
                        if sb_item.get("home_score") is not None:
                            sel["home_score"] = sb_item["home_score"]
                        if sb_item.get("away_score") is not None:
                            sel["away_score"] = sb_item["away_score"]

                        if sb_item.get("leg_result"):
                            sel["leg_result"] = sb_item["leg_result"]
                            sel["leg_status"] = sb_item["leg_result"]

                        if sb_item.get("match_status"):
                            st_raw = str(sb_item["match_status"]).upper()
                            if st_raw in ("IN_PROGRESS", "LIVE", "ONGOING", "H1", "H2", "HT"):
                                sel["match_status"] = "LIVE"
                            elif st_raw in ("CONCLUDED", "FT", "FINISHED"):
                                sel["match_status"] = "CONCLUDED"
                            else:
                                sel["match_status"] = st_raw

                        clock_raw = str(sb_item.get("clock") or "")
                        period_code = str(sb_item.get("match_status_code") or "")
                        if period_code == "HT":
                            sel["match_time"] = "HT"
                        elif clock_raw and ":" in clock_raw:
                            try:
                                mins = int(clock_raw.split(":")[0])
                                half = "H1" if mins <= 45 else "H2"
                                sel["match_time"] = f"{mins}' {half}"
                            except Exception:
                                sel["match_time"] = clock_raw
                        elif sb_item.get("status_label"):
                            sel["match_time"] = sb_item["status_label"]

                        if sb_item.get("start_time_ms"):
                            sel["start_time_ms"] = sb_item["start_time_ms"]

        # Persist full tickets list to DB
        save_tracked_tickets(tickets, db=db)
    except Exception as e:
        import traceback
        print("[TicketTracker] Live API sync exception:", e)
        traceback.print_exc()

    return evaluate_tracked_tickets(db=db)


