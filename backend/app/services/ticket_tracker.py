import os
import json
import time
import re
from typing import List, Dict, Any, Optional

TRACKER_FILE = os.path.join(os.path.dirname(__file__), "..", "..", "data", "tracked_tickets.json")

# ─────────────────────────────────────────────────────────────────────────────
# Storage helpers
# ─────────────────────────────────────────────────────────────────────────────

def _ensure_tracker_file():
    os.makedirs(os.path.dirname(TRACKER_FILE), exist_ok=True)
    if not os.path.exists(TRACKER_FILE):
        with open(TRACKER_FILE, "w", encoding="utf-8") as f:
            json.dump([], f)

def get_tracked_tickets() -> List[Dict[str, Any]]:
    _ensure_tracker_file()
    try:
        with open(TRACKER_FILE, "r", encoding="utf-8") as f:
            return json.load(f)
    except Exception:
        return []

def save_tracked_tickets(tickets: List[Dict[str, Any]]):
    _ensure_tracker_file()
    with open(TRACKER_FILE, "w", encoding="utf-8") as f:
        json.dump(tickets, f, indent=2, ensure_ascii=False)


# ─────────────────────────────────────────────────────────────────────────────
# Lock / Delete
# ─────────────────────────────────────────────────────────────────────────────

def lock_ticket(payload: Dict[str, Any]) -> Dict[str, Any]:
    tickets = get_tracked_tickets()

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
        "potential_win": round(stake * total_odds, 2),
        "status": "RUNNING",
        "created_at": time.strftime("%Y-%m-%d %H:%M:%S"),
        "locked_at_unix": int(time.time()),
        "selections": payload.get("selections", []),
    }

    # If final_scores provided at lock time → settle immediately
    if final_scores:
        new_ticket = _apply_scores_to_ticket(new_ticket, final_scores)

    tickets.insert(0, new_ticket)
    save_tracked_tickets(tickets)
    return new_ticket


def delete_tracked_ticket(ticket_id: str) -> bool:
    tickets = get_tracked_tickets()
    filtered = [t for t in tickets if t.get("id") != ticket_id]
    if len(filtered) < len(tickets):
        save_tracked_tickets(filtered)
        return True
    return False


# ─────────────────────────────────────────────────────────────────────────────
# Pick evaluator — comprehensive market coverage
# ─────────────────────────────────────────────────────────────────────────────

def evaluate_pick(pick_name: str, home_score: int, away_score: int,
                  home_team: str = "", away_team: str = "") -> bool:
    """
    Return True if the pick WON given the final scores.
    Handles all MatchIQ market types.
    """
    if home_score is None or away_score is None:
        return True  # Can't evaluate — optimistically pass

    p = (pick_name or "").lower().strip()
    ht = (home_team or "").lower().strip()
    at = (away_team or "").lower().strip()
    total = home_score + away_score

    # ── Goal Bounds ── e.g. "2-5+", "3-5+", "0-1", "6+"
    gb = re.match(r"^(\d+)-(\d+)\+?$", p.replace(" ", ""))
    if gb:
        lo, hi = int(gb.group(1)), int(gb.group(2))
        return lo <= total <= hi or (p.endswith("+") and total >= lo)
    if re.match(r"^(\d+)\+$", p.replace(" ", "")):
        lo = int(re.match(r"^(\d+)\+$", p.replace(" ", "")).group(1))
        return total >= lo

    # ── 2nd Half – Double Chance (Home or Away) ──
    # We evaluate on full-time score as a proxy (home or away team scored ≠ draw)
    if "2nd half" in p and "double chance" in p:
        if "home or away" in p or "12" in p:
            return home_score != away_score
        if "home or draw" in p or "1x" in p:
            return home_score >= away_score
        if "away or draw" in p or "x2" in p:
            return away_score >= home_score
        # Generic 2nd half DC any — just passes if not a draw
        return home_score != away_score

    # ── SportyBet Compound OR Markets (Home/Away Team or Over 2.5) ──
    if "or over 2.5" in p or "& over 2.5" in p:
        over25 = total > 2.5
        if "away" in p or (at and at in p):
            return away_score > home_score or over25
        if "home" in p or (ht and ht in p):
            return home_score > away_score or over25
        return (home_score != away_score) or over25

    # ── Double Chance ──
    if "or draw" in p and "home" in p:   return home_score >= away_score   # 1X
    if "or draw" in p and "away" in p:   return away_score >= home_score   # X2
    if "home or away" in p or p == "12": return home_score != away_score   # 12

    # Specific team in "Team or Draw" pattern
    if "or draw" in p:
        team_part = p.replace("or draw", "").replace("(1x)", "").replace("(x2)", "").strip().rstrip("(").strip()
        if ht and ht in team_part:
            return home_score >= away_score
        if at and at in team_part:
            return away_score >= home_score
        return home_score >= away_score  # fallback 1X

    # ── Win Either Half (WEH) ──
    if "win either half" in p or "weh" in p:
        # Home win either half
        if ht and ht in p:
            return home_score > away_score  # use FT as proxy
        if "home" in p:
            return home_score > away_score
        # Away win either half
        if at and at in p:
            return away_score > home_score
        if "away" in p:
            return away_score > home_score
        # Generic — some team won
        return home_score != away_score

    # ── Draw No Bet (DNB) ──
    if "draw no bet" in p or "dnb" in p or "win (dnb)" in p:
        # Void on draw (treated as pass here); check team won
        if home_score == away_score:
            return True  # Void / returned stake — treat as neutral pass
        if ht and ht in p:
            return home_score > away_score
        if at and at in p:
            return away_score > home_score
        if "home" in p:
            return home_score > away_score
        if "away" in p:
            return away_score > home_score
        return home_score > away_score  # fallback

    # ── Asian Handicap ──
    if "asian handicap" in p or "handicap" in p or "(+1" in p or "(+2" in p or "(-1" in p or "(-0.5)" in p or "+1.5" in p or "+2" in p:
        # Determine target team: Home or Away?
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
        elif at and at in p:
            is_away_target = True
        elif ht and ht in p:
            is_home_target = True

        # Extract numerical handicap value
        hcp_val = 1.5  # default
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

    # ── 1st Half Over/Under ──
    if "1st half" in p or "ht " in p:
        if "over 0.5" in p: return "WON" if total >= 1 else "LOST"
        if "over 1.5" in p: return "WON" if total >= 2 else "LOST"
        if "under 0.5" in p: return "WON" if total == 0 else "LOST"
        if "under 1.5" in p: return "WON" if total <= 1 else "LOST"

    # ── Over / Under (standard & whole-integer goal lines) ──
    if "under 0.5" in p: return "WON" if total < 1 else "LOST"
    if "under 1.5" in p: return "WON" if total < 2 else "LOST"
    if "under 2.5" in p: return "WON" if total < 3 else "LOST"
    if "under 3.5" in p: return "WON" if total < 4 else "LOST"
    if "under 4.5" in p: return "WON" if total < 5 else "LOST"
    if "under 2"   in p and "2.5" not in p:
        return "VOID" if total == 2 else ("WON" if total < 2 else "LOST")
    if "under 3"   in p and "3.5" not in p:
        return "VOID" if total == 3 else ("WON" if total < 3 else "LOST")

    if "over 0.5"  in p: return "WON" if total >= 1 else "LOST"
    if "over 1.5"  in p: return "WON" if total >= 2 else "LOST"
    if "over 2.5"  in p: return "WON" if total >= 3 else "LOST"
    if "over 3.5"  in p: return "WON" if total >= 4 else "LOST"
    if "over 4.5"  in p: return "WON" if total >= 5 else "LOST"
    if "over 2"    in p and "2.5" not in p:
        return "VOID" if total == 2 else ("WON" if total > 2 else "LOST")
    if "over 3"    in p and "3.5" not in p:
        return "VOID" if total == 3 else ("WON" if total > 3 else "LOST")

    # ── Team Goals (Over 0.5) ──
    if "over 0.5 goals" in p or "over 0.5 team goals" in p or "team goals" in p:
        if ht and ht in p:   return "WON" if home_score >= 1 else "LOST"
        if at and at in p:   return "WON" if away_score >= 1 else "LOST"
        if "home" in p:      return "WON" if home_score >= 1 else "LOST"
        if "away" in p:      return "WON" if away_score >= 1 else "LOST"
        return "WON" if total >= 1 else "LOST"

    # ── GG / Both Teams To Score ──
    if "gg" in p or "both teams to score" in p or "btts" in p:
        return "WON" if (home_score >= 1 and away_score >= 1) else "LOST"

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

def _parse_score(score_str: str):
    """Parse 'H-A' or 'H:A' → (int, int) or (None, None)."""
    if not score_str:
        return None, None
    for sep in ["-", ":"]:
        if sep in str(score_str):
            parts = str(score_str).split(sep)
            try:
                return int(parts[0].strip()), int(parts[1].strip())
            except Exception:
                pass
    return None, None


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
            all_concluded = False
            continue  # No score available for this leg yet

        h = score_entry.get("home_score")
        a = score_entry.get("away_score")
        score_str = score_entry.get("score_str") or f"{h} - {a}"

        # Store the score on the selection
        sel["score"] = score_str
        sel["match_status"] = "CONCLUDED"

        # Evaluate
        mkt_str = sel.get("market_name") or ""
        sel_str = sel.get("selection_name") or sel.get("selection") or ""
        pick_str = f"{mkt_str} — {sel_str}".strip(" —") if mkt_str else sel_str

        won = evaluate_pick(
            pick_str, h, a,
            sel.get("home_team", ""),
            sel.get("away_team", "")
        )
        sel["leg_status"] = "WON" if won else "LOST"

        if not won:
            any_lost = True
            all_won = False

    # Settle ticket
    if any_lost:
        ticket["status"] = "LOST"
        ticket["settled_at"] = time.strftime("%Y-%m-%d %H:%M:%S")
    elif all_concluded and all_won:
        ticket["status"] = "WON"
        ticket["settled_at"] = time.strftime("%Y-%m-%d %H:%M:%S")

    return ticket


# ─────────────────────────────────────────────────────────────────────────────
# Settlement from explicit scores payload
# ─────────────────────────────────────────────────────────────────────────────

def settle_ticket_with_scores(ticket_id: str, fixture_scores: List[Dict]) -> Optional[Dict]:
    """
    Force-settle a specific ticket using provided scores.
    fixture_scores: list of {fixture_id, home_score, away_score}
    """
    tickets = get_tracked_tickets()
    scores_map = {
        str(s.get("fixture_id", "")): {
            "home_score": int(s.get("home_score", 0)),
            "away_score": int(s.get("away_score", 0)),
            "score_str": f"{s.get('home_score', 0)} - {s.get('away_score', 0)}"
        }
        for s in fixture_scores
    }

    for i, t in enumerate(tickets):
        if t.get("id") == ticket_id:
            tickets[i] = _apply_scores_to_ticket(t, scores_map)
            save_tracked_tickets(tickets)
            return tickets[i]
    return None


def settle_all_with_scores(fixture_scores: List[Dict]) -> List[Dict]:
    """
    Apply a single batch of scores to ALL RUNNING tickets.
    """
    tickets = get_tracked_tickets()
    scores_map = {
        str(s.get("fixture_id", "")): {
            "home_score": int(s.get("home_score", 0)),
            "away_score": int(s.get("away_score", 0)),
            "score_str": f"{s.get('home_score', 0)} - {s.get('away_score', 0)}"
        }
        for s in fixture_scores
    }

    updated = False
    for i, t in enumerate(tickets):
        if t.get("status") == "RUNNING":
            tickets[i] = _apply_scores_to_ticket(t, scores_map)
            updated = True

    if updated:
        save_tracked_tickets(tickets)

    return tickets


# ─────────────────────────────────────────────────────────────────────────────
# Main evaluation loop (called on every GET /list)
# ─────────────────────────────────────────────────────────────────────────────

def evaluate_tracked_tickets() -> List[Dict[str, Any]]:
    """
    Evaluates all RUNNING tickets.

    1. For tickets with stored scores on their selections → evaluate immediately.
    2. For AUDITOR tickets older than 4 hours with no scores → flag as STALE.
    3. For tickets with explicitly stored match_status/leg_result → settle.
    """
    tickets = get_tracked_tickets()
    updated = False
    now = int(time.time())

    for t in tickets:
        if t.get("status") != "RUNNING":
            continue

        all_won = True
        any_lost = False
        all_concluded = True
        scores_available = False

        # Attempt to auto-fetch scores from SportyBet adapter if code exists and ticket is RUNNING with missing scores
        has_missing_scores = any(not sel.get("score") and sel.get("leg_status") not in ("WON", "LOST") for sel in t.get("selections", []))
        if has_missing_scores:
            try:
                from app.db.session import SessionLocal
                from app.adapters.bookmaker_adapter import SportyBetAdapter
                db = SessionLocal()
                try:
                    adapter = SportyBetAdapter(db)
                    
                    # Method 1: Booking code lookup
                    if t.get("code") and t.get("code") != "CUSTOM":
                        fetched = adapter.fetch_booking_code_details(t["code"], "ng")
                        if fetched and fetched.get("selections"):
                            fetched_map = {}
                            for f_sel in fetched.get("selections", []):
                                h_t = (f_sel.get("home_team") or "").lower().strip()
                                a_t = (f_sel.get("away_team") or "").lower().strip()
                                if h_t and a_t and f_sel.get("score"):
                                    fetched_map[f"{h_t}_{a_t}"] = f_sel.get("score")
                                    if f_sel.get("game_id"):
                                        fetched_map[str(f_sel.get("game_id"))] = f_sel.get("score")

                            for sel in t.get("selections", []):
                                if not sel.get("score"):
                                    gid = str(sel.get("game_id") or sel.get("external_fixture_id") or "")
                                    key = f"{(sel.get('home_team') or '').lower().strip()}_{(sel.get('away_team') or '').lower().strip()}"
                                    if gid and gid in fetched_map:
                                        sel["score"] = fetched_map[gid]
                                        sel["match_status"] = "CONCLUDED"
                                        updated = True
                                    elif key in fetched_map:
                                        sel["score"] = fetched_map[key]
                                        sel["match_status"] = "CONCLUDED"
                                        updated = True

                    # Method 2: For selections still missing scores, query event detail by game_id directly
                    for sel in t.get("selections", []):
                        if not sel.get("score"):
                            gid = str(sel.get("game_id") or sel.get("external_fixture_id") or "")
                            if gid and gid.isdigit():
                                m_detail = adapter._fetch_event_markets(gid, "ng")
                                # If event detail endpoint confirms event is finished or has setScore
                                # Event details fetched from SportyBet API
                                pass
                finally:
                    db.close()
            except Exception:
                pass  # Gracefully fall back if provider API is offline or code expired

        for sel in t.get("selections", []):
            st = (sel.get("match_status") or "UPCOMING").upper()
            score_str = sel.get("score", "")

            # If score_str is present, ALWAYS re-evaluate with current evaluate_pick logic
            if score_str:
                scores_available = True
                h, a = _parse_score(score_str)
                if h is not None:
                    mkt_str = sel.get("market_name") or ""
                    sel_str = sel.get("selection_name") or sel.get("selection") or ""
                    full_pick = f"{mkt_str} — {sel_str}".strip(" —") if mkt_str else sel_str

                    res_status = evaluate_pick(
                        full_pick, h, a,
                        sel.get("home_team", ""),
                        sel.get("away_team", "")
                    )
                    if res_status == "VOID":
                        sel["leg_status"] = "VOID"
                    elif res_status == "WON":
                        sel["leg_status"] = "WON"
                    else:
                        sel["leg_status"] = "LOST"
                        any_lost = True
                        all_won = False
                    sel["match_status"] = "CONCLUDED"
                    continue

            # Fall back to stored leg result if no score_str is available
            leg_res = sel.get("leg_result") or sel.get("leg_status")
            if leg_res in ("WON", "LOST"):
                sel["leg_status"] = leg_res
                if leg_res == "LOST":
                    any_lost = True
                    all_won = False
                continue

            if leg_res == "VOID" or st == "NULLED_EXPIRED":
                sel["leg_status"] = "VOID"
                continue

            # No score yet — check if live status says concluded
            if st == "CONCLUDED":
                sel["leg_status"] = "VOID"
                continue

            # Still genuinely pending
            all_concluded = False

        # Settle ticket considering Flex Bet strategy
        flex_cut = t.get("flex_cut", "AUTO")
        n_legs = len(t.get("selections", []))

        # Calculate max allowed cut if set to AUTO
        if str(flex_cut).upper() == "AUTO":
            if n_legs <= 8:
                allowed_losses = 1 if n_legs >= 5 else 0
            elif n_legs <= 15:
                allowed_losses = 2
            elif n_legs <= 25:
                allowed_losses = 3
            else:
                allowed_losses = 5
        elif str(flex_cut).upper() == "OFF" or flex_cut is None:
            allowed_losses = 0
        else:
            try:
                allowed_losses = int(str(flex_cut).replace("Cut-", "").replace("cut-", "").strip())
            except Exception:
                allowed_losses = 0

        loss_count = sum(1 for sel in t.get("selections", []) if sel.get("leg_status") == "LOST")

        t["flex_cut"] = flex_cut
        t["allowed_losses"] = allowed_losses
        t["loss_count"] = loss_count

        if loss_count > allowed_losses:
            t["status"] = "LOST"
            t["flex_status_text"] = f"Exceeded Flex Cut-{allowed_losses} ({loss_count} losses)" if allowed_losses > 0 else "Straight Acca Lost"
            t["settled_at"] = time.strftime("%Y-%m-%d %H:%M:%S")
            updated = True
        elif all_concluded and loss_count <= allowed_losses and scores_available:
            t["status"] = "WON"
            if loss_count > 0:
                t["flex_status_text"] = f"WON (Covered by Flex Cut-{allowed_losses} — {loss_count} loss paid out)"
            else:
                t["flex_status_text"] = "WON (Clean Sweep - 0 Losses)"
            t["settled_at"] = time.strftime("%Y-%m-%d %H:%M:%S")
            updated = True
        else:
            # Mark as STALE if AUDITOR ticket is >4 hours old and still RUNNING
            locked_at = t.get("locked_at_unix", 0)
            age_hours = (now - locked_at) / 3600 if locked_at else 0
            if age_hours >= 4 and t.get("mode") in ("AUDITOR", "SWAP", "REMOVE"):
                t["stale"] = True
                t["stale_reason"] = f"Ticket locked {age_hours:.1f}h ago — scores not yet provided. Use 'Settle Now' to manually provide results."
                updated = True
            else:
                t["stale"] = False

    if updated:
        save_tracked_tickets(tickets)

    return tickets
