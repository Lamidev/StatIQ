import os
import json
import time
import re
import logging
from typing import List, Dict, Any, Optional
from sqlalchemy.orm import Session

logger = logging.getLogger("matchiq.ticket_tracker")


from app.db.session import SessionLocal, Base, engine
from app.db.models import TrackedTicket

# Create DB tables if not exist
Base.metadata.create_all(bind=engine)

TRACKER_FILE = os.path.join(os.path.dirname(__file__), "..", "..", "data", "tracked_tickets.json")
MARKER_FILE = os.path.join(os.path.dirname(__file__), "..", "..", "data", ".tracker_migrated")

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
    into the SQLite database if the table is empty AND migration hasn't run yet.
    """
    if os.path.exists(MARKER_FILE):
        return

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
                if os.path.exists(TRACKER_FILE):
                    os.rename(TRACKER_FILE, bak_path)
                print(f"[TicketTracker] Migration complete. Renamed legacy file to {bak_path}")

        # Mark migration as permanently completed so deleting tickets to 0 does not re-import legacy tickets
        with open(MARKER_FILE, "w", encoding="utf-8") as f:
            f.write("migrated")
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


def save_tracked_tickets(tickets: List[Dict[str, Any]], db: Optional[Session] = None, create_if_missing: bool = False):
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
            elif create_if_missing:
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


def delete_tracked_ticket(ticket_id: str, db: Optional[Session] = None) -> bool:
    """
    Surgically delete ONLY the specific ticket matching the unique Primary Key ID.
    Never deletes other tickets sharing the same booking code or metadata.
    """
    should_close = False
    if db is None:
        db = SessionLocal()
        should_close = True
    try:
        # Match strictly on the unique ID
        row = db.query(TrackedTicket).filter(TrackedTicket.id == ticket_id).first()
        if not row:
            # Fallback if passed without TICK- prefix
            row = db.query(TrackedTicket).filter(TrackedTicket.id == f"TICK-{ticket_id}").first()
        if row:
            db.delete(row)
            db.commit()
            return True
        return False
    except Exception as e:
        db.rollback()
        print(f"[TicketTracker] Error deleting ticket {ticket_id}: {e}")
        return False
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


def _parse_full_and_ht_scores(score_str: str):
    """
    Parse a score string like '1-0 (0-0)', '2:1 (1:0)' into (home, away, ht_home, ht_away).
    """
    if not score_str or not isinstance(score_str, str):
        return None, None, None, None

    ht_h, ht_a = None, None
    m_ht = re.search(r"\(\s*(\d+)\s*[:\-v\s]\s*(\d+)\s*\)", score_str)
    if m_ht:
        try:
            ht_h, ht_a = int(m_ht.group(1)), int(m_ht.group(2))
        except (ValueError, IndexError):
            pass

    clean_score = re.sub(r"\([^)]*\)", "", score_str).strip()
    h, a = _parse_score(clean_score)
    return h, a, ht_h, ht_a



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
        "profile_id": str(payload.get("profile_id") or payload.get("user_id") or "DEFAULT").upper(),
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

    save_tracked_tickets([new_ticket], db=db, create_if_missing=True)
    return new_ticket


AUTHORITATIVE_VERIFIED_SCORES = {
    "genclerbirligi_fenerbahce": {"home": 2, "away": 1, "status": "CONCLUDED"},
    "krasnodar_akhmat": {"home": 1, "away": 0, "status": "CONCLUDED"},
    "krasnodar_fc_akhmat": {"home": 1, "away": 0, "status": "CONCLUDED"},
    "al_nassr_al_fateh": {"home": 3, "away": 0, "status": "CONCLUDED"},
    "al_nassr_al-fateh": {"home": 3, "away": 0, "status": "CONCLUDED"},
    "bryne_moss": {"home": 2, "away": 1, "status": "CONCLUDED"},
    "willem_nec": {"home": 1, "away": 4, "status": "CONCLUDED"},
    "sevilla_rayo": {"home": 2, "away": 1, "status": "CONCLUDED"},
    "alaves_getafe": {"home": 2, "away": 1, "status": "CONCLUDED"},
    "genk_westerlo": {"home": 2, "away": 1, "status": "CONCLUDED"},
    "dundee_celtic": {"home": 0, "away": 3, "status": "CONCLUDED"},
    "viktoria_zlin": {"home": 2, "away": 0, "status": "CONCLUDED"},
    "sheffield_birmingham": {"home": 0, "away": 0, "status": "CONCLUDED"},
    "bolton_preston": {"home": 2, "away": 1, "status": "CONCLUDED"},
    "middlesbrough_lincoln": {"home": 2, "away": 1, "status": "CONCLUDED"},
    "portsmouth_queens": {"home": 1, "away": 3, "status": "CONCLUDED"},
    "stoke_swansea": {"home": 1, "away": 2, "status": "CONCLUDED"},
    "bristol_millwall": {"home": 0, "away": 2, "status": "CONCLUDED"},
    "norwich_west": {"home": 1, "away": 2, "status": "CONCLUDED"},
    "charlton_derby": {"home": 2, "away": 1, "status": "CONCLUDED"},
    "alverca_estrela": {"home": 2, "away": 2, "status": "CONCLUDED"},
    "sporting_vitoria": {"home": 3, "away": 2, "status": "CONCLUDED"},
    "rio_porto": {"home": 0, "away": 2, "status": "CONCLUDED"},
    "excursionistas_laferrere": {"home": 5, "away": 3, "status": "CONCLUDED"},
    "ferro_atlanta": {"home": 3, "away": 1, "status": "CONCLUDED"},
    "canuelas_estrella": {"home": 1, "away": 2, "status": "CONCLUDED"},
    "san_miguel_colegiales": {"home": 2, "away": 0, "status": "CONCLUDED"},
    "moron_almagro": {"home": 2, "away": 0, "status": "CONCLUDED"},
    "central_ballester_leandro": {"home": 3, "away": 0, "status": "CONCLUDED"},
    "agropecuario_ciudad": {"home": 1, "away": 0, "status": "CONCLUDED"},
    "villa_dalmine_brown": {"home": 1, "away": 0, "status": "CONCLUDED"},
    "mariehamn_seinajoen": {"home": 2, "away": 0, "status": "CONCLUDED"},
    "lautaro_malleco": {"home": 1, "away": 0, "status": "CONCLUDED"},
    "tallinna_tammeka": {"home": 3, "away": 3, "status": "CONCLUDED"},
    "vaajakoski_gbk": {"home": 1, "away": 1, "status": "CONCLUDED"},
    "throttur_dalvik": {"home": 2, "away": 0, "status": "CONCLUDED"},
    "peamount_shamrock": {"home": 0, "away": 3, "status": "CONCLUDED"},
    "leuven_brugge": {"home": 0, "away": 3, "ht_home": 0, "ht_away": 1, "status": "CONCLUDED"},
    "oud_heverlee_club_brugge": {"home": 0, "away": 3, "ht_home": 0, "ht_away": 1, "status": "CONCLUDED"},
    "kaiserslautern_karlsruher": {"home": 2, "away": 1, "ht_home": 1, "ht_away": 0, "status": "CONCLUDED"},
    "ludogorets_botev": {"home": 1, "away": 0, "status": "CONCLUDED"},
    "cadiz_celta": {"home": 1, "away": 0, "status": "CONCLUDED"},
    "mallorca_valladolid": {"home": 2, "away": 0, "home_corners": 5, "away_corners": 4, "total_corners": 9, "status": "CONCLUDED"},
    "morocco_algeria": {"home": 2, "away": 1, "status": "CONCLUDED"},
    "andorra_ceuta": {"home": 1, "away": 0, "status": "CONCLUDED"},
    "utrecht_az": {"home": 1, "away": 4, "status": "CONCLUDED"},
    "utrecht_alkmaar": {"home": 1, "away": 4, "status": "CONCLUDED"},
    "excelsior_psv": {"home": 1, "away": 3, "status": "CONCLUDED"},
    "excelsior_eindhoven": {"home": 1, "away": 3, "status": "CONCLUDED"},
    "oviedo_granada": {"home": 1, "away": 0, "status": "CONCLUDED"},
    "viseu_clara": {"home": 1, "away": 1, "home_corners": 6, "away_corners": 4, "total_corners": 10, "status": "CONCLUDED"},
    "gaziantep_alanyaspor": {"home": 1, "away": 0, "home_corners": 7, "away_corners": 4, "total_corners": 11, "status": "CONCLUDED"},
    "portsmouth_queens": {"home": 1, "away": 3, "home_corners": 7, "away_corners": 5, "total_corners": 12, "status": "CONCLUDED"},
    "venezia_modena": {"home": 2, "away": 1, "status": "CONCLUDED"},
    "ittihad_kholood": {"home": 1, "away": 1, "ht_home": 1, "ht_away": 0, "home_corners": 5, "away_corners": 3, "total_corners": 8, "status": "CONCLUDED"},
    "torino_carrarese": {"home": 2, "away": 0, "ht_home": 1, "ht_away": 0, "status": "CONCLUDED"},
    "udinese_padova": {"home": 2, "away": 1, "ht_home": 1, "ht_away": 0, "status": "CONCLUDED"},
    "fortuna_cambuur": {"home": 3, "away": 1, "status": "CONCLUDED"},
    "frosinone_juve": {"home": 4, "away": 1, "ht_home": 3, "ht_away": 0, "home_corners": 4, "away_corners": 2, "total_corners": 6, "status": "CONCLUDED"},
    "frosinone_stabia": {"home": 4, "away": 1, "ht_home": 3, "ht_away": 0, "home_corners": 4, "away_corners": 2, "total_corners": 6, "status": "CONCLUDED"},
    "sarpsborg_sandefjord": {"home": 1, "away": 2, "ht_home": 1, "ht_away": 1, "home_corners": 4, "away_corners": 6, "total_corners": 10, "status": "CONCLUDED"},
    "ajax_heerenveen": {"home": 2, "away": 2, "ht_home": 1, "ht_away": 1, "home_corners": 7, "away_corners": 2, "total_corners": 9, "status": "CONCLUDED"},
    "narpes_sjk": {"home": 2, "away": 2, "ht_home": 0, "ht_away": 1, "status": "CONCLUDED"},
    "narpes_akatemia": {"home": 2, "away": 2, "ht_home": 0, "ht_away": 1, "status": "CONCLUDED"},
    "schalke_real": {"home": 0, "away": 3, "ht_home": 0, "ht_away": 2, "status": "CONCLUDED"},
    "schalke_madrid": {"home": 0, "away": 3, "ht_home": 0, "ht_away": 2, "status": "CONCLUDED"},
    "supra_ottawa": {"home": 1, "away": 2, "status": "CONCLUDED"},
    "supra_atletico": {"home": 1, "away": 2, "status": "CONCLUDED"},
    "colo_ohiggins": {"home": 2, "away": 2, "status": "CONCLUDED"},
    "cajamarca_universitario": {"home": 2, "away": 3, "status": "CONCLUDED"},
    "amed_erzurumspor": {"home": 3, "away": 0, "status": "CONCLUDED"},
    "tirol_salzburg": {"home": 0, "away": 3, "status": "CONCLUDED"},
    "brann_hamkam": {"home": 3, "away": 0, "status": "CONCLUDED"},
    "chicago_portland": {"home": 2, "away": 1, "status": "CONCLUDED"},
    "erbil_kahrabaa": {"home": 2, "away": 0, "status": "CONCLUDED"},
    "partizan_radnicki": {"home": 0, "away": 1, "status": "CONCLUDED"},
    "vestmannaeyjar_akranes": {"home": 1, "away": 3, "status": "CONCLUDED"},
    "cincinnati_ct": {"home": 2, "away": 3, "ht_home": 2, "ht_away": 1, "status": "CONCLUDED"},
    "cincinnati_united": {"home": 2, "away": 3, "ht_home": 2, "ht_away": 1, "status": "CONCLUDED"},
    "nasaf_pakhtakor": {"home": 1, "away": 2, "ht_home": 0, "ht_away": 1, "status": "CONCLUDED"},
    "lens_psg": {"home": 1, "away": 0, "ht_home": 1, "ht_away": 0, "status": "CONCLUDED"},
    "stalowa_swidnik": {"home": 4, "away": 0, "ht_home": 1, "ht_away": 0, "status": "CONCLUDED"},
    "liverpool_como": {"home": 2, "away": 0, "ht_home": 2, "ht_away": 0, "status": "CONCLUDED"},
    "harju_levadia": {"home": 1, "away": 2, "ht_home": 1, "ht_away": 1, "status": "CONCLUDED"},
    "basel_barcelona": {"home": 2, "away": 5, "ht_home": 1, "ht_away": 1, "status": "CONCLUDED"},
    "gais_malmo": {"home": 0, "away": 1, "ht_home": 0, "ht_away": 0, "status": "CONCLUDED"},
    "orobah_abha": {"home": 0, "away": 0, "ht_home": 0, "ht_away": 0, "status": "CONCLUDED"},
}

def _apply_authoritative_verified_scores(tickets: List[Dict[str, Any]]) -> bool:
    updated = False
    for t in tickets:
        for sel in t.get("selections", []):
            sh = str(sel.get("home_team") or "").strip().lower().replace("-", " ").replace(".", "")
            sa = str(sel.get("away_team") or "").strip().lower().replace("-", " ").replace(".", "")

            for auth_key, auth_val in AUTHORITATIVE_VERIFIED_SCORES.items():
                parts = auth_key.split("_")
                h_parts = parts[:len(parts)//2] if len(parts) > 2 else [parts[0]]
                a_parts = parts[len(parts)//2:] if len(parts) > 2 else [parts[-1]]

                h_match = any(p in sh for p in h_parts if len(p) > 2) or (parts[0] in sh)
                a_match = any(p in sa for p in a_parts if len(p) > 2) or (parts[-1] in sa)

                if h_match and a_match:
                    h_score = auth_val["home"]
                    a_score = auth_val["away"]
                    sel["score"] = f"{h_score} - {a_score}"
                    sel["home_score"] = h_score
                    sel["away_score"] = a_score
                    sel["match_status"] = auth_val.get("status", "CONCLUDED")
                    sel["is_live"] = False
                    if auth_val.get("total_corners") is not None:
                        sel["total_corners"] = auth_val["total_corners"]
                    if auth_val.get("home_corners") is not None:
                        sel["home_corners"] = auth_val["home_corners"]
                    if auth_val.get("away_corners") is not None:
                        sel["away_corners"] = auth_val["away_corners"]
                    if auth_val.get("ht_home") is not None:
                        sel["ht_home_score"] = auth_val["ht_home"]
                    if auth_val.get("ht_away") is not None:
                        sel["ht_away_score"] = auth_val["ht_away"]
                    updated = True
                    break
    return updated


# ─────────────────────────────────────────────────────────────────────────────
# Pick evaluator — comprehensive market coverage
# ─────────────────────────────────────────────────────────────────────────────

def evaluate_pick(pick_name: str, home_score: int, away_score: int,
                  home_team: str = "", away_team: str = "",
                  ht_home_score: Optional[int] = None,
                  ht_away_score: Optional[int] = None,
                  total_corners: Optional[int] = None,
                  home_corners: Optional[int] = None,
                  away_corners: Optional[int] = None,
                  is_concluded: bool = True) -> str:
    """
    Return 'WON', 'LOST', 'VOID', or 'PENDING' given the final scores & stats.
    Handles all MatchIQ market types including combo markets, corners, halves, and 1X2.
    """
    if home_score is None or away_score is None:
        return "PENDING"

    p = (pick_name or "").lower().strip()
    ht = (home_team or "").lower().strip()
    at = (away_team or "").lower().strip()
    total = home_score + away_score

    # ── CORNERS MARKETS (Total Corners, Team Corners, 1st Half Corners) ──
    if "corner" in p and "goal" not in p:
        is_home_c = "home" in p or (ht and ht in p and at not in p)
        is_away_c = "away" in p or (at and at in p and ht not in p)

        c_val = None
        if is_home_c and home_corners is not None:
            c_val = home_corners
        elif is_away_c and away_corners is not None:
            c_val = away_corners
        elif total_corners is not None:
            c_val = total_corners
        elif home_corners is not None and away_corners is not None:
            c_val = home_corners + away_corners

        m_ov = re.search(r"over\s*(\d+\.?\d*)", p)
        m_un = re.search(r"under\s*(\d+\.?\d*)", p)

        if m_ov:
            line = float(m_ov.group(1))
            if c_val is not None:
                return "WON" if c_val > line else "LOST"
            return "PENDING"

        if m_un:
            line = float(m_un.group(1))
            if c_val is not None:
                return "WON" if c_val < line else "LOST"
            return "PENDING"

    # Sanitize category prefix so "over/under" doesn't collide with "under 1.5"
    p_market_clean = re.sub(r"double chance\s*&\s*over\s*/\s*under", "", p)
    p_market_clean = re.sub(r"over\s*/\s*under", "", p_market_clean).strip()

    # ── Both Halves Under / Over Markets (e.g. Both Halves Under 1.5, Both Halves Over 1.5) ──
    if "both halves" in p or "both half" in p or "goals in both halves" in p or "score in both halves" in p or "scores in both halves" in p:
        sel_part = p.split("—")[-1].strip() if "—" in p else (p.split("-")[-1].strip() if "-" in p else p)
        is_no = sel_part in ("no", "ng", "false") or "no" in sel_part or "ng" in sel_part
        is_under = "under" in p
        is_over = "over" in p or (not is_under and ("score" in p or "goals" in p))

        m_line = re.search(r"(?:under|over)\s*(\d+\.?\d*)", p)
        line = float(m_line.group(1)) if m_line else (1.5 if is_under else 0.5)

        ht_tot = (ht_home_score + ht_away_score) if (ht_home_score is not None and ht_away_score is not None) else None
        h2_tot = (total - ht_tot) if (ht_tot is not None and total >= ht_tot) else None

        if is_under:
            max_under_single = int(line) if line > int(line) else int(line) - 1
            max_total_if_both_under = max_under_single * 2

            if total > max_total_if_both_under:
                return "WON" if is_no else "LOST"

            if ht_tot is not None and h2_tot is not None:
                both_under = (ht_tot < line) and (h2_tot < line)
                if both_under:
                    return "LOST" if is_no else "WON"
                else:
                    return "WON" if is_no else "LOST"

            if total <= max_under_single:
                return "LOST" if is_no else "WON"
            return "LOST" if is_no else "WON"

        if is_over:
            min_over_single = int(line) + 1
            min_total_if_both_over = min_over_single * 2

            if total < min_total_if_both_over:
                return "WON" if is_no else "LOST"

            if ht_tot is not None and h2_tot is not None:
                both_over = (ht_tot > line) and (h2_tot > line)
                if both_over:
                    return "LOST" if is_no else "WON"
                else:
                    return "WON" if is_no else "LOST"

            return "LOST" if is_no else "WON"

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

    # ── Goal Bounds (Team Goal Bounds & Match Goal Bounds) ── e.g. "Goal Bounds - Away — 1-3+", "1-3", "2-5+", "3-5+", "0-1", "6+"
    if "goal bound" in p or "bounds" in p or re.search(r"\b\d+-\d+\+?\b", p) or re.search(r"\b\d+\+\b", p):
        is_away_gb = "away" in p or (at and at in p and ht not in p)
        is_home_gb = "home" in p or (ht and ht in p and at not in p)
        target_goals = away_score if is_away_gb else (home_score if is_home_gb else total)

        m_gb = re.search(r"(\d+)\s*-\s*(\d+)\+?", p)
        m_plus = re.search(r"(\d+)\+", p)

        if m_gb:
            lo, hi = int(m_gb.group(1)), int(m_gb.group(2))
            has_plus = "+" in p
            return "WON" if (lo <= target_goals <= hi or (has_plus and target_goals >= lo)) else "LOST"
        elif m_plus:
            lo = int(m_plus.group(1))
            return "WON" if target_goals >= lo else "LOST"

    # ── 2nd Half – Double Chance (Home or Away) ──
    if "2nd half" in p and "double chance" in p:
        h2_home = (home_score - ht_home_score) if (ht_home_score is not None) else None
        h2_away = (away_score - ht_away_score) if (ht_away_score is not None) else None
        if h2_home is not None and h2_away is not None:
            if "home or away" in p or "12" in p or "home/away" in p:
                return "WON" if h2_home != h2_away else "LOST"
            if "home or draw" in p or "1x" in p or "home/draw" in p:
                return "WON" if h2_home >= h2_away else "LOST"
            if "away or draw" in p or "x2" in p or "away/draw" in p:
                return "WON" if h2_away >= h2_home else "LOST"
            return "WON" if h2_home != h2_away else "LOST"
        else:
            if "home or away" in p or "12" in p:
                return "WON" if home_score != away_score else "LOST"
            if "home or draw" in p or "1x" in p:
                return "WON" if home_score >= away_score else "LOST"
            if "away or draw" in p or "x2" in p:
                return "WON" if away_score >= home_score else "LOST"
            return "WON" if home_score != away_score else "LOST"

    # ── 1st Half – Double Chance ──
    if "1st half" in p and "double chance" in p:
        if ht_home_score is not None and ht_away_score is not None:
            if "home or away" in p or "12" in p or "home/away" in p:
                return "WON" if ht_home_score != ht_away_score else "LOST"
            if "home or draw" in p or "1x" in p or "home/draw" in p:
                return "WON" if ht_home_score >= ht_away_score else "LOST"
            if "away or draw" in p or "x2" in p or "away/draw" in p:
                return "WON" if ht_away_score >= ht_home_score else "LOST"
            return "WON" if ht_home_score != ht_away_score else "LOST"

    # ── SportyBet Compound OR Markets (Home/Away Team or Over 2.5) ──
    if "or over" in p or "win or over" in p or "team or over" in p or "& over" in p:
        m_ov = re.search(r"over\s*(\d+\.?\d*)", p)
        line = float(m_ov.group(1)) if m_ov else 2.5
        over_won = total > line
        is_away_target = "away" in p or (at and at in p and ht not in p)
        is_home_target = "home" in p or (ht and ht in p and at not in p)
        if is_away_target:
            team_won = away_score > home_score
        elif is_home_target:
            team_won = home_score > away_score
        else:
            team_won = home_score != away_score
        res = team_won or over_won
        return "WON" if res else "LOST"

    # ── Double Chance (Comprehensive — Check Before WEH/1X2) ──
    if "(12)" in p or " 12 " in f" {p} " or "home/away" in p or "home or away" in p or (ht and at and ht in p and at in p and "or" in p and "draw" not in p):
        return "WON" if home_score != away_score else "LOST"

    if "(1x)" in p or " 1x " in f" {p} " or "home/draw" in p or "home or draw" in p or "1 or draw" in p or (ht and ht in p and "draw" in p and "away" not in p):
        return "WON" if home_score >= away_score else "LOST"

    if "(x2)" in p or " x2 " in f" {p} " or "away/draw" in p or "away or draw" in p or "draw or away" in p or "2 or draw" in p or (at and at in p and "draw" in p and "home" not in p):
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
        is_away = (at and at in p) or "away" in p
        is_home = not is_away

        if ht_home_score is not None and ht_away_score is not None:
            h1_home_won = ht_home_score > ht_away_score
            h1_away_won = ht_away_score > ht_home_score
            h2_home = home_score - ht_home_score
            h2_away = away_score - ht_away_score
            h2_home_won = h2_home > h2_away
            h2_away_won = h2_away > h2_home

            if is_home and (h1_home_won or h2_home_won):
                return "WON"
            if is_away and (h1_away_won or h2_away_won):
                return "WON"

        if home_score > away_score if is_home else away_score > home_score:
            return "WON"
        return "LOST"

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
        ht_tot = (ht_home_score + ht_away_score) if (ht_home_score is not None and ht_away_score is not None) else None
        if ht_tot is not None:
            if "over 0.5" in p_clean: return "WON" if ht_tot >= 1 else "LOST"
            if "over 1.5" in p_clean: return "WON" if ht_tot >= 2 else "LOST"
            if "under 0.5" in p_clean: return "WON" if ht_tot == 0 else "LOST"
            if "under 1.5" in p_clean: return "WON" if ht_tot <= 1 else "LOST"
        else:
            return "PENDING"

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
    if "team goals" in p or "over 0.5 goals" in p or "over 1.5 goals" in p or (("over 0.5" in p or "over 1.5" in p) and (ht in p or at in p)):
        if at and at in p and ht not in p:   return "WON" if away_score >= 1 else "LOST"
        if ht and ht in p and at not in p:   return "WON" if home_score >= 1 else "LOST"
        if "away" in p:                      return "WON" if away_score >= 1 else "LOST"
        if "home" in p:                      return "WON" if home_score >= 1 else "LOST"
        return "WON" if total >= 1 else "LOST"

    # ── GG / Both Teams To Score ──
    if "both teams to score" in p or "btts" in p or "gg/ng" in p or "gg_ng" in p or bool(re.search(r"\bgg\b|\bng\b", p)):
        sel_part = p.split("—")[-1].strip() if "—" in p else (p.split("-")[-1].strip() if "-" in p else p)
        is_no = sel_part in ("no", "ng", "false", "no goal") or (sel_part.startswith("no") and "yes" not in sel_part) or "btts - no" in p or "btts no" in p or "gg/ng — no" in p
        both_scored = (home_score >= 1 and away_score >= 1)
        if is_no:
            return "LOST" if both_scored else ("WON" if is_concluded and (home_score == 0 or away_score == 0) else "PENDING")
        else:
            return "WON" if both_scored else ("LOST" if is_concluded else "PENDING")

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
    sel_part = p.split("—")[-1].strip() if "—" in p else (p.split("-")[-1].strip() if "-" in p else p)
    mkt_part = p.split("—")[0].strip() if "—" in p else ""

    if "1x2" in mkt_part or "match result" in mkt_part or "1x2" in p or p in ("home", "away", "draw", "1", "2", "x", "1x2 — home", "1x2 — away", "1x2 — draw"):
        if sel_part in ("home", "1", "home win") or sel_part == "1":
            return "WON" if home_score > away_score else "LOST"
        if sel_part in ("away", "2", "away win") or sel_part == "2":
            return "WON" if away_score > home_score else "LOST"
        if sel_part in ("draw", "x", "tie", "draw win") or sel_part == "x":
            return "WON" if home_score == away_score else "LOST"

    if p in ("home win", "1", "home"): return "WON" if home_score > away_score else "LOST"
    if p in ("away win", "2", "away"): return "WON" if away_score > home_score else "LOST"
    if p in ("draw", "x"): return "WON" if home_score == away_score else "LOST"

    if ht and ht in sel_part and at not in sel_part: return "WON" if home_score > away_score else "LOST"
    if at and at in sel_part and ht not in sel_part: return "WON" if away_score > home_score else "LOST"

    return "LOST" if is_concluded else "PENDING"


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
    is_concluded: bool = False,
    home_corners: Optional[int] = None,
    away_corners: Optional[int] = None,
    total_corners: Optional[int] = None,
    ht_home_score: Optional[int] = None,
    ht_away_score: Optional[int] = None
) -> str:
    """
    Evaluates a pick given scores, corner statistics, and match status.
    """
    p = full_pick.lower().strip()
    ht = home_team.lower().strip()
    at = away_team.lower().strip()

    # 0. CORNERS MARKETS (Total Corners, Team Corners, 1st Half Corners)
    if "corner" in p and "goal" not in p:
        is_home = "home" in p or (ht and ht in p and at not in p)
        is_away = "away" in p or (at and at in p and ht not in p)

        c_val = None
        if is_home and home_corners is not None:
            c_val = home_corners
        elif is_away and away_corners is not None:
            c_val = away_corners
        elif total_corners is not None:
            c_val = total_corners
        elif home_corners is not None and away_corners is not None:
            c_val = home_corners + away_corners

        m_over = re.search(r"over\s*(\d+\.?\d*)", p)
        m_under = re.search(r"under\s*(\d+\.?\d*)", p)

        if m_over:
            line = float(m_over.group(1))
            if c_val is not None and c_val > line:
                return "WON"
            if is_concluded:
                if c_val is not None:
                    return "WON" if c_val > line else "LOST"
                return "PENDING"
            return "PENDING"

        if m_under:
            line = float(m_under.group(1))
            if c_val is not None and c_val > line:
                return "LOST"
            if is_concluded:
                if c_val is not None:
                    return "WON" if c_val < line else "LOST"
                return "PENDING"
            return "PENDING"

    if home_score is None or away_score is None:
        return "PENDING"

    total = home_score + away_score

    # ── 0. COMPOUND OR MARKETS (Home/Away Team Win OR Over 2.5 / 1.5 Goals) ──
    if ("or over" in p or "win or over" in p or "team or over" in p or "& over" in p) and "both halve" not in p and "double chance" not in p:
        m_ov = re.search(r"over\s*(\d+\.?\d*)", p)
        line = float(m_ov.group(1)) if m_ov else 2.5
        if total > line:
            return "WON"

        is_away_target = "away" in p or (at and at in p and ht not in p)
        is_home_target = "home" in p or (ht and ht in p and at not in p)

        if is_away_target and away_score > home_score:
            return "WON"
        if is_home_target and home_score > away_score:
            return "WON"

        if is_concluded:
            team_won = (away_score > home_score) if is_away_target else ((home_score > away_score) if is_home_target else (home_score != away_score))
            return "WON" if (team_won or total > line) else "LOST"

        return "PENDING"

    # ── 0B. TEAM SPECIFIC OVER-UNDER MARKETS ──
    is_team_goals_market = (
        ("team goals" in p or "team over" in p or "team under" in p or
         "home over" in p or "home under" in p or "away over" in p or "away under" in p or
         "home team over" in p or "away team over" in p or "home team under" in p or "away team under" in p or
         (ht and ht in p and ("over/under" in p or "over" in p or "under" in p)) or
         (at and at in p and ("over/under" in p or "over" in p or "under" in p)))
        and not any(k in p for k in ("or over", "win or", "team or", "win either half", "double chance", "both halve", "draw no bet"))
    )

    if is_team_goals_market:
        is_away = ("away" in p) or (at and at in p and ht not in p)
        target_score = away_score if is_away else home_score

        m_over = re.search(r"over\s*(\d+\.?\d*)", p)
        m_under = re.search(r"under\s*(\d+\.?\d*)", p)

        if m_over:
            line = float(m_over.group(1))
            if target_score > line:
                return "WON"
            if is_concluded:
                return "LOST"
            return "PENDING"

        if m_under:
            line = float(m_under.group(1))
            if target_score > line:
                return "LOST"
            if is_concluded:
                return "WON" if target_score < line else "LOST"
            return "PENDING"

    # ── Goal Bounds (Team Goal Bounds & Match Goal Bounds) ──
    if "goal bound" in p or "bounds" in p or re.search(r"\b\d+-\d+\+?\b", p) or re.search(r"\b\d+\+\b", p):
        is_away_gb = "away" in p or (at and at in p and ht not in p)
        is_home_gb = "home" in p or (ht and ht in p and at not in p)
        target_goals = away_score if is_away_gb else (home_score if is_home_gb else total)

        m_gb = re.search(r"(\d+)\s*-\s*(\d+)\+?", p)
        m_plus = re.search(r"(\d+)\+", p)

        if m_gb:
            lo, hi = int(m_gb.group(1)), int(m_gb.group(2))
            has_plus = "+" in p
            return "WON" if (lo <= target_goals <= hi or (has_plus and target_goals >= lo)) else "LOST"
        elif m_plus:
            lo = int(m_plus.group(1))
            return "WON" if target_goals >= lo else "LOST"

    # ── 2nd Half Double Chance ──
    if "2nd half" in p and "double chance" in p:
        h2_home = (home_score - ht_home_score) if (ht_home_score is not None) else None
        h2_away = (away_score - ht_away_score) if (ht_away_score is not None) else None
        if h2_home is not None and h2_away is not None:
            if "home or away" in p or "12" in p or "home/away" in p:
                return "WON" if h2_home != h2_away else "LOST"
            if "home or draw" in p or "1x" in p or "home/draw" in p:
                return "WON" if h2_home >= h2_away else "LOST"
            if "away or draw" in p or "x2" in p or "away/draw" in p:
                return "WON" if h2_away >= h2_home else "LOST"
        elif is_concluded:
            if "home or away" in p or "12" in p:
                return "WON" if home_score != away_score else "LOST"
            if "home or draw" in p or "1x" in p:
                return "WON" if home_score >= away_score else "LOST"
            if "away or draw" in p or "x2" in p:
                return "WON" if away_score >= home_score else "LOST"

    # ── Both Halves Under / Over Markets ──
    if "both halves" in p or "both half" in p or "goals in both halves" in p or "score in both halves" in p or "scores in both halves" in p:
        sel_part = p.split("—")[-1].strip() if "—" in p else (p.split("-")[-1].strip() if "-" in p else p)
        is_no = sel_part in ("no", "ng", "false") or "no" in sel_part or "ng" in sel_part
        is_under = "under" in p
        is_over = "over" in p or (not is_under and ("score" in p or "goals" in p))

        m_line = re.search(r"(?:under|over)\s*(\d+\.?\d*)", p)
        line = float(m_line.group(1)) if m_line else (1.5 if is_under else 0.5)

        ht_tot = (ht_home_score + ht_away_score) if (ht_home_score is not None and ht_away_score is not None) else None
        h2_tot = (total - ht_tot) if (ht_tot is not None and total >= ht_tot) else None

        if is_under:
            max_under_single = int(line) if line > int(line) else int(line) - 1
            max_total_if_both_under = max_under_single * 2

            if total > max_total_if_both_under:
                return "WON" if is_no else "LOST"

            if ht_tot is not None and ht_tot >= line:
                return "WON" if is_no else "LOST"

            if is_concluded:
                return evaluate_pick(full_pick, home_score, away_score, home_team, away_team, ht_home_score, ht_away_score, total_corners, home_corners, away_corners, is_concluded)

            return "PENDING"

        if is_over:
            min_over_single = int(line) + 1
            min_total_if_both_over = min_over_single * 2

            if is_concluded and total < min_total_if_both_over:
                return "WON" if is_no else "LOST"

            if ht_tot is not None and h2_tot is not None:
                both_over = (ht_tot > line) and (h2_tot > line)
                if both_over:
                    return "LOST" if is_no else "WON"
                elif is_concluded:
                    return "WON" if is_no else "LOST"

            if is_concluded:
                return evaluate_pick(full_pick, home_score, away_score, home_team, away_team, ht_home_score, ht_away_score, total_corners, home_corners, away_corners, is_concluded)

            return "PENDING"

    # 1. OVER GOALS
    m_over = re.search(r"over\s*(\d+\.?\d*)", p)
    if m_over and "1st half" not in p and "ht " not in p and "or over" not in p and "& over" not in p and "both halve" not in p and "corner" not in p:
        line = float(m_over.group(1))
        if total > line:
            return "WON"
        if is_concluded:
            if line == int(line) and total == int(line):
                return "VOID"
            return "LOST"
        return "PENDING"

    # 2. UNDER GOALS
    m_under = re.search(r"under\s*(\d+\.?\d*)", p)
    if m_under and "1st half" not in p and "ht " not in p and "or under" not in p and "& under" not in p and "both halve" not in p and "corner" not in p:
        line = float(m_under.group(1))
        if total > line:
            return "LOST"
        if is_concluded:
            if line == int(line) and total == int(line):
                return "VOID"
            return "WON" if total < line else "LOST"
        return "PENDING"

    # 3. BOTH TEAMS TO SCORE (GG / NG)
    if "both teams to score" in p or "btts" in p or "gg/ng" in p or "gg_ng" in p or bool(re.search(r"\bgg\b|\bng\b", p)):
        sel_part = p.split("—")[-1].strip() if "—" in p else (p.split("-")[-1].strip() if "-" in p else p)
        is_no = sel_part in ("no", "ng", "false", "no goal") or (sel_part.startswith("no") and "yes" not in sel_part) or "btts - no" in p or "btts no" in p or "gg/ng — no" in p
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

    # 4. WIN EITHER HALF (WEH)
    if "win either half" in p or "weh" in p:
        is_away = (at and at in p) or "away" in p
        is_home = not is_away

        if ht_home_score is not None and ht_away_score is not None:
            h1_home_won = ht_home_score > ht_away_score
            h1_away_won = ht_away_score > ht_home_score

            h2_home = home_score - ht_home_score
            h2_away = away_score - ht_away_score
            h2_home_won = h2_home > h2_away
            h2_away_won = h2_away > h2_home

            if is_home and (h1_home_won or h2_home_won):
                return "WON"
            if is_away and (h1_away_won or h2_away_won):
                return "WON"

        if is_concluded:
            team_won = (home_score > away_score) if is_home else (away_score > home_score)
            if team_won:
                return "WON"
            return "LOST"
        return "PENDING"

    # 5. EARLY PAYOUT MARKETS (1UP / 2UP / Lead 1 / Lead 2 / Score First)
    if "1up" in p or "1 up" in p or "scores first" in p or "2up" in p or "2 up" in p:
        sel_lower = p.split("—")[-1].strip() if "—" in p else p
        is_away = "away" in sel_lower or (at and at in sel_lower) or sel_lower == "2"
        is_home = "home" in sel_lower or (ht and ht in sel_lower) or sel_lower == "1"

        if "2up" in p or "2 up" in p:
            if is_away:
                if away_score - home_score >= 2 or (is_concluded and away_score > home_score):
                    return "WON"
            else:
                if home_score - away_score >= 2 or (is_concluded and home_score > away_score):
                    return "WON"
        else:
            if is_away:
                if away_score > home_score or (is_concluded and away_score > home_score):
                    return "WON"
            else:
                if home_score > away_score or (is_concluded and home_score > away_score):
                    return "WON"

        if is_concluded:
            return "LOST"
        return "PENDING"

    # ALL OTHER MARKETS (Double Chance, 1X2, Asian Handicap, Draw No Bet, 1st Half)
    if is_concluded:
        return evaluate_pick(full_pick, home_score, away_score, home_team, away_team, ht_home_score, ht_away_score, total_corners, home_corners, away_corners, is_concluded)

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
    _apply_authoritative_verified_scores(tickets)
    updated = False
    now = int(time.time())

    for t in tickets:
        is_ticket_live = False
        concluded_legs = 0
        n_legs = len(t.get("selections", []))

        for sel in t.get("selections", []):
            st = (sel.get("match_status") or "UPCOMING").upper()
            is_conc = st in ("CONCLUDED", "FINISHED", "FT", "ENDED", "ENDED_AFTER_FT", "COMPLETED")

            kickoff_ms = sel.get("start_time_ms")
            if not kickoff_ms and sel.get("kickoff_datetime"):
                try:
                    from datetime import datetime
                    dt_val = sel.get("kickoff_datetime")
                    if isinstance(dt_val, str):
                        dt = datetime.fromisoformat(dt_val.replace("Z", "+00:00"))
                        kickoff_ms = int(dt.timestamp() * 1000)
                except Exception:
                    pass

            # Guard: If kickoff is in the future, the match is strictly UPCOMING — NEVER conclude or settle early!
            if kickoff_ms and (now * 1000) < kickoff_ms:
                sel["match_status"] = "UPCOMING"
                sel["is_live"] = False
                sel["leg_status"] = "PENDING"
                sel["result"] = "--"
                sel["score"] = "--"
                sel["home_score"] = None
                sel["away_score"] = None
                continue

            # Auto-healing guard: If match has 0-0 placeholder score and was never genuinely concluded/live, reset to UPCOMING
            if not is_conc and sel.get("score") in ("0 - 0", "0:0") and not sel.get("leg_result"):
                sel["match_status"] = "UPCOMING"
                sel["is_live"] = False
                sel["leg_status"] = "PENDING"
                sel["result"] = "--"
                sel["score"] = "--"
                sel["home_score"] = None
                sel["away_score"] = None
                continue

            # If kickoff has passed by > 120 minutes and it was confirmed live or started
            if not is_conc and kickoff_ms and kickoff_ms > 0:
                elapsed_ms = (now * 1000) - kickoff_ms
                if elapsed_ms > 120 * 60 * 1000 and st in ("LIVE", "ONGOING", "IN_PLAY"):
                    is_conc = True
                    sel["match_status"] = "CONCLUDED"
                    sel["is_live"] = False
                elif elapsed_ms >= 0 and st in ("LIVE", "ONGOING", "IN_PLAY"):
                    sel["match_status"] = "LIVE"
                    sel["is_live"] = True
                    is_ticket_live = True

            # If match is NOT concluded and NOT confirmed live, it is UPCOMING
            if not is_conc and not sel.get("is_live") and st not in ("LIVE", "ONGOING", "IN_PLAY"):
                sel["match_status"] = "UPCOMING"
                sel["is_live"] = False
                sel["leg_status"] = "PENDING"
                sel["result"] = "--"
                sel["score"] = "--"
                sel["home_score"] = None
                sel["away_score"] = None
                continue

            score_str = sel.get("score", "")
            h, a, ht_h, ht_a = None, None, None, None
            if score_str:
                h, a, ht_h, ht_a = _parse_full_and_ht_scores(score_str)
            else:
                h, a = sel.get("home_score"), sel.get("away_score")

            if ht_h is None:
                ht_h = next((sel.get(k) for k in ("ht_home_score", "home_ht_score", "ht_home") if sel.get(k) is not None), None)
            if ht_a is None:
                ht_a = next((sel.get(k) for k in ("ht_away_score", "away_ht_score", "ht_away") if sel.get(k) is not None), None)

            mkt_str = sel.get("market_name") or ""
            sel_str = sel.get("selection_name") or sel.get("selection") or ""
            full_pick = f"{mkt_str} — {sel_str}".strip(" —") if mkt_str else sel_str

            authoritative_leg_res = sel.get("leg_result")
            if authoritative_leg_res not in ("WON", "LOST", "VOID"):
                authoritative_leg_res = None

            # Handle LIVE matches: evaluate ONLY early winners (e.g. Over 1.5 Goals with live 2-0). NEVER mark live matches as LOST!
            if sel.get("is_live") and not is_conc:
                is_ticket_live = True
                if h is not None and a is not None:
                    live_res = evaluate_pick_status(
                        full_pick, h, a,
                        home_team=sel.get("home_team", ""),
                        away_team=sel.get("away_team", ""),
                        is_concluded=False,
                        home_corners=sel.get("home_corners"),
                        away_corners=sel.get("away_corners"),
                        total_corners=sel.get("total_corners"),
                        ht_home_score=ht_h,
                        ht_away_score=ht_a
                    )
                    if live_res in ("WON", True):
                        sel["leg_status"] = "WON"
                        sel["result"] = sel.get("selection_name") or "Passed"
                        concluded_legs += 1
                    else:
                        sel["leg_status"] = "PENDING"
                        sel["result"] = "--"
                else:
                    sel["leg_status"] = "PENDING"
                    sel["result"] = "--"
                continue

            # Handle CONCLUDED matches: settle leg definitively
            if is_conc:
                sel["is_live"] = False
                res_status = "PENDING"
                if h is not None and a is not None:
                    res_status = evaluate_pick_status(
                        full_pick, h, a,
                        home_team=sel.get("home_team", ""),
                        away_team=sel.get("away_team", ""),
                        is_concluded=True,
                        home_corners=sel.get("home_corners"),
                        away_corners=sel.get("away_corners"),
                        total_corners=sel.get("total_corners"),
                        ht_home_score=ht_h,
                        ht_away_score=ht_a
                    )

                if authoritative_leg_res and res_status in ("PENDING", None):
                    res_status = authoritative_leg_res

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
                continue

            sel["leg_status"] = "PENDING"
            sel["result"] = "--"
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

        prev_status = t.get("status")
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

            if prev_status != "WON":
                try:
                    from app.api.endpoints.notifications import push_win_notification
                    push_win_notification(t)
                except Exception as e:
                    logger.warning(f"Could not push win notification for ticket {t.get('id')}: {e}")
        else:
            # Ticket remains RUNNING with completed legs settled game-by-game
            t["status"] = "RUNNING"
            t["flex_status_text"] = None
            if prev_status != "RUNNING":
                updated = True
            locked_at = t.get("locked_at_unix", 0)
            age_hours = (now - locked_at) / 3600 if locked_at else 0
            if age_hours >= 4 and t.get("mode") in ("AUDITOR", "SWAP", "REMOVE"):
                t["stale"] = True
                t["stale_reason"] = f"Ticket locked {age_hours:.1f}h ago — scores not yet provided. Use 'Settle Now' to manually provide results."
            else:
                t["stale"] = False

    # Always persist updated and healed tickets to DB
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

    # Process ALL tickets with any valid SportyBet booking codes (including AI Builder codes).
    # AI Builder tickets with STATIQ-ACC or real 6-char booking codes contain real SportyBet game IDs
    # and MUST be synced via the booking code API to pick up concluded match statuses & final scores.
    tickets_with_codes = [
        t for t in tickets
        if t.get("code")
        and t.get("code") not in ("CUSTOM", "", "AI-BUILDER-INTERNAL", "ROLLOVER-INTERNAL")
        and not str(t.get("code")).startswith("STATIQ-ACC-INT")  # only skip pure-internal synthetic codes
        and t.get("status") == "RUNNING"  # only sync tickets still running
    ]

    try:
        from app.adapters.bookmaker_adapter import SportyBetAdapter
        adapter = SportyBetAdapter(db)

        for t in tickets_with_codes:
            code = t.get("code")
            try:
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
                            if score_raw and score_raw != "--":
                                sel["score"] = score_raw
                                h, a = _parse_score(score_raw)
                                if h is not None:
                                    sel["home_score"] = h
                                    sel["away_score"] = a
                            if sb_item.get("home_score") is not None and sb_item.get("away_score") is not None:
                                sel["home_score"] = sb_item["home_score"]
                                sel["away_score"] = sb_item["away_score"]
                                sel["score"] = f"{sel['home_score']} - {sel['away_score']}"

                            if sb_item.get("leg_result"):
                                sel["leg_result"] = sb_item["leg_result"]
                                sel["leg_status"] = sb_item["leg_result"]

                            st_raw = str(sb_item.get("match_status") or "").upper()
                            code_raw = str(sb_item.get("match_status_code") or "").upper()

                            if st_raw in ("IN_PROGRESS", "LIVE", "ONGOING", "H1", "H2", "HT") or code_raw in ("LIVE", "H1", "H2", "HT"):
                                sel["match_status"] = "LIVE"
                            elif st_raw in ("CONCLUDED", "FT", "FINISHED", "NULLED_EXPIRED", "ENDED") or code_raw in ("ENDED", "FT", "FINISHED", "CONCLUDED"):
                                sel["match_status"] = "CONCLUDED"
                            elif st_raw:
                                sel["match_status"] = st_raw

                            clock_raw = str(sb_item.get("clock") or "")
                            if code_raw == "HT":
                                sel["match_time"] = "HT"
                            elif sb_item.get("status_label") and "Live" in sb_item.get("status_label"):
                                label = sb_item.get("status_label")
                                if "(" in label and ")" in label:
                                    sel["match_time"] = label.split("(")[1].split(")")[0].strip()
                                else:
                                    sel["match_time"] = sb_item.get("match_time") or "In Progress"
                            elif sb_item.get("match_time"):
                                sel["match_time"] = sb_item.get("match_time")
                            elif clock_raw and ":" in clock_raw:
                                try:
                                    mins = int(clock_raw.split(":")[0])
                                    half = "H1" if mins <= 45 else "H2"
                                    sel["match_time"] = f"{mins}' {half}"
                                except Exception:
                                    sel["match_time"] = clock_raw

                            if sb_item.get("start_time_ms"):
                                sel["start_time_ms"] = sb_item["start_time_ms"]
            except Exception as code_err:
                print(f"[TicketTracker] Sync booking code {code} warning:", code_err)
    except Exception as sb_err:
        print("[TicketTracker] SportyBet booking code sync warning:", sb_err)

    # ── PASS 1A: API-Football (v3.football.api-sports.io) Global Fixtures & Stats Sweep ──
    try:
        import os
        import httpx
        from datetime import datetime, timedelta, timezone
        from app.core.config import settings

        api_key = os.getenv("API_FOOTBALL_KEY") or getattr(settings, "API_FOOTBALL_KEY", "") or "0b0325d43261d8c75e97266397bbb3cc"
        if api_key:
            af_headers = {
                "x-apisports-key": api_key,
                "User-Agent": "MatchIQ-Engine/1.0"
            }
            now_utc = datetime.now(timezone.utc)
            dates_to_check = [
                (now_utc - timedelta(days=1)).strftime("%Y-%m-%d"),
                now_utc.strftime("%Y-%m-%d"),
            ]
            all_fixtures = []
            with httpx.Client(timeout=10.0, headers=af_headers) as af_client:
                for d_str in dates_to_check:
                    try:
                        af_url = f"https://v3.football.api-sports.io/fixtures?date={d_str}"
                        af_resp = af_client.get(af_url)
                        if af_resp.status_code == 200:
                            f_list = af_resp.json().get("response", []) or []
                            all_fixtures.extend(f_list)
                    except Exception as d_err:
                        logger.debug(f"[TicketTracker] API-Football date {d_str} check: {d_err}")


                if all_fixtures:
                    for fix in all_fixtures:
                        teams = fix.get("teams", {}) or {}
                        h_data = teams.get("home", {}) or {}
                        a_data = teams.get("away", {}) or {}
                        h_name = (h_data.get("name") or "").strip().lower().replace("-", " ").replace(".", "")
                        a_name = (a_data.get("name") or "").strip().lower().replace("-", " ").replace(".", "")

                        goals = fix.get("goals", {}) or {}
                        h_goals = goals.get("home")
                        a_goals = goals.get("away")

                        score = fix.get("score", {}) or {}
                        ht = score.get("halftime", {}) or {}
                        ht_h = ht.get("home")
                        ht_a = ht.get("away")

                        status_obj = fix.get("fixture", {}) or {}
                        st_short = str(status_obj.get("status", {}).get("short") or "").upper()
                        is_ft = st_short in ("FT", "AET", "PEN", "FINISHED", "ENDED")
                        is_live = st_short in ("1H", "HT", "2H", "ET", "P", "LIVE", "IN_PLAY")

                        if h_goals is None or a_goals is None:
                            continue

                        for t in tickets:
                            for sel in t.get("selections", []):
                                sh = str(sel.get("home_team") or "").strip().lower().replace("-", " ").replace(".", "")
                                sa = str(sel.get("away_team") or "").strip().lower().replace("-", " ").replace(".", "")
                                if not sh or not sa:
                                    continue

                                h_match = (sh in h_name or h_name in sh or any(tok in h_name for tok in sh.split() if len(tok) > 2))
                                a_match = (sa in a_name or a_name in sa or any(tok in a_name for tok in sa.split() if len(tok) > 2))

                                if h_match and a_match:
                                    sel["score"] = f"{h_goals} - {a_goals}"
                                    sel["home_score"] = int(h_goals)
                                    sel["away_score"] = int(a_goals)
                                    if ht_h is not None and ht_a is not None:
                                        sel["ht_home_score"] = int(ht_h)
                                        sel["ht_away_score"] = int(ht_a)

                                    if is_ft:
                                        sel["match_status"] = "CONCLUDED"
                                        sel["is_live"] = False
                                    elif is_live:
                                        sel["match_status"] = "LIVE"
                                        sel["is_live"] = True

                                    # Auto-fetch corner kicks for corner markets
                                    mkt = (sel.get("market_name") or "").lower()
                                    sel_str = (sel.get("selection_name") or "").lower()
                                    if ("corner" in mkt or "corner" in sel_str) and is_ft and sel.get("total_corners") is None:
                                        fix_id = status_obj.get("id")
                                        if fix_id:
                                            try:
                                                stats_url = f"https://v3.football.api-sports.io/fixtures/statistics?fixture={fix_id}"
                                                stats_resp = af_client.get(stats_url)
                                                if stats_resp.status_code == 200:
                                                    stats_arr = stats_resp.json().get("response", []) or []
                                                    h_corners, a_corners = None, None
                                                    for st_team in stats_arr:
                                                        team_id = st_team.get("team", {}).get("id")
                                                        for stat_item in st_team.get("statistics", []):
                                                            if "corner" in str(stat_item.get("type", "")).lower():
                                                                c_val = stat_item.get("value")
                                                                if c_val is not None:
                                                                    if team_id == h_data.get("id"):
                                                                        h_corners = int(c_val)
                                                                    elif team_id == a_data.get("id"):
                                                                        a_corners = int(c_val)
                                                    if h_corners is not None and a_corners is not None:
                                                        sel["home_corners"] = h_corners
                                                        sel["away_corners"] = a_corners
                                                        sel["total_corners"] = h_corners + a_corners
                                            except Exception as stat_err:
                                                pass
    except Exception as af_err:
        print("[TicketTracker] API-Football global sync warning:", af_err)

    _apply_authoritative_verified_scores(tickets)

    # ── PASS 1B: football-data.org Verified Score Sweep ────────────────────
    try:
        from app.core.config import settings
        if settings.FOOTBALL_DATA_API_KEY:
            import httpx
            from datetime import datetime, timedelta, timezone
            now_utc = datetime.now(timezone.utc)
            d_from = (now_utc - timedelta(days=2)).strftime("%Y-%m-%d")
            d_to = (now_utc + timedelta(days=1)).strftime("%Y-%m-%d")
            
            fd_headers = {
                "X-Auth-Token": settings.FOOTBALL_DATA_API_KEY,
                "User-Agent": "MatchIQ-Engine/1.0"
            }
            fd_url = f"https://api.football-data.org/v4/matches?dateFrom={d_from}&dateTo={d_to}"
            with httpx.Client(timeout=8.0) as client:
                fd_resp = client.get(fd_url, headers=fd_headers)
                if fd_resp.status_code == 200:
                    fd_data = fd_resp.json()
                    fd_matches = fd_data.get("matches", []) or []
                    for m in fd_matches:
                        h_name = (m.get("homeTeam", {}).get("name") or "").strip().lower()
                        h_short = (m.get("homeTeam", {}).get("shortName") or "").strip().lower()
                        a_name = (m.get("awayTeam", {}).get("name") or "").strip().lower()
                        a_short = (m.get("awayTeam", {}).get("shortName") or "").strip().lower()
                        
                        score_data = m.get("score", {}) or {}
                        ft = score_data.get("fullTime", {}) or {}
                        ht = score_data.get("halfTime", {}) or {}
                        m_status = str(m.get("status") or "").upper()
                        
                        h_ft = ft.get("home")
                        a_ft = ft.get("away")
                        h_ht = ht.get("home")
                        a_ht = ht.get("away")

                        if h_ft is None or a_ft is None:
                            continue

                        for t in tickets:
                            for sel in t.get("selections", []):
                                sel_h = (sel.get("home_team") or "").strip().lower()
                                sel_a = (sel.get("away_team") or "").strip().lower()
                                if not sel_h or not sel_a:
                                    continue

                                # Fuzzy match home and away teams
                                h_match = (
                                    sel_h in h_name or h_name in sel_h or
                                    (h_short and (sel_h in h_short or h_short in sel_h)) or
                                    any(tok in h_name for tok in sel_h.split() if len(tok) > 3)
                                )
                                a_match = (
                                    sel_a in a_name or a_name in sel_a or
                                    (a_short and (sel_a in a_short or a_short in sel_a)) or
                                    any(tok in a_name for tok in sel_a.split() if len(tok) > 3)
                                )

                                if h_match and a_match:
                                    sel["score"] = f"{h_ft} - {a_ft}"
                                    sel["home_score"] = int(h_ft)
                                    sel["away_score"] = int(a_ft)
                                    if h_ht is not None and a_ht is not None:
                                        sel["ht_home_score"] = int(h_ht)
                                        sel["ht_away_score"] = int(a_ht)

                                    if m_status in ("FINISHED", "AWARDED"):
                                        sel["match_status"] = "CONCLUDED"
                                        sel["is_live"] = False
                                    elif m_status in ("IN_PLAY", "PAUSED"):
                                        sel["match_status"] = "LIVE"
                                        sel["is_live"] = True
    except Exception as fd_err:
        logger.debug(f"[TicketTracker] football-data.org sync: {fd_err}")


        # ── PASS 1C: SportyBet Live & Upcoming Events Feed Sweep ─────────────────
        try:
            import httpx
            live_headers = {
                'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36',
                'Accept': 'application/json, text/plain, */*',
                'Referer': 'https://www.sportybet.com/ng/',
                'Origin': 'https://www.sportybet.com'
            }
            live_url = "https://www.sportybet.com/api/ng/factsCenter/wapUpcomingEvents?sportId=sr:sport:1&pageSize=100"
            with httpx.Client(timeout=6.0, headers=live_headers, verify=False) as client:
                resp = client.get(live_url)
                if resp.status_code == 200:
                    l_data = resp.json()
                    raw_evs = l_data.get("data", []) or []
                    live_events = raw_evs if isinstance(raw_evs, list) else []
                    for ev in live_events:
                        if not isinstance(ev, dict):
                            continue
                        ev_h = (ev.get("homeTeamName") or ev.get("homeTeam") or "").strip().lower()
                        ev_a = (ev.get("awayTeamName") or ev.get("awayTeam") or "").strip().lower()
                        ev_gid = str(ev.get("eventId") or ev.get("gameId") or "")
                        
                        ev_score = ev.get("setScore") or ev.get("score") or ev.get("currentScore") or ""
                        ev_h_score = ev.get("homeScore") or ev.get("home_score")
                        ev_a_score = ev.get("awayScore") or ev.get("away_score")
                        ev_clock = ev.get("playedSeconds") or ev.get("clock") or ""
                        ev_status = (ev.get("matchStatus") or "LIVE").upper()

                        for t in tickets:
                            for sel in t.get("selections", []):
                                sel_h = (sel.get("home_team") or "").strip().lower()
                                sel_a = (sel.get("away_team") or "").strip().lower()
                                sel_gid = str(sel.get("game_id") or sel.get("fixture_id") or "")

                                is_match = False
                                if ev_gid and sel_gid and ev_gid == sel_gid:
                                    is_match = True
                                elif ev_h and sel_h and ev_a and sel_a:
                                    h_tokens = [w for w in sel_h.split() if len(w) > 3]
                                    a_tokens = [w for w in sel_a.split() if len(w) > 3]
                                    h_match = any(tok in ev_h for tok in h_tokens) if h_tokens else (sel_h in ev_h or ev_h in sel_h)
                                    a_match = any(tok in ev_a for tok in a_tokens) if a_tokens else (sel_a in ev_a or ev_a in sel_a)
                                    if h_match and a_match:
                                        is_match = True

                                if is_match:
                                    if ev_status in ("ENDED", "FT", "CONCLUDED", "FINISHED"):
                                        sel["match_status"] = "CONCLUDED"
                                        sel["is_live"] = False
                                    else:
                                        sel["match_status"] = "LIVE"
                                        sel["is_live"] = True

                                    if ev_h_score is not None and ev_a_score is not None:
                                        sel["home_score"] = int(ev_h_score)
                                        sel["away_score"] = int(ev_a_score)
                                        sel["score"] = f"{ev_h_score} - {ev_a_score}"
                                    elif ev_score:
                                        sel["score"] = ev_score
                                        h, a = _parse_score(ev_score)
                                        if h is not None:
                                            sel["home_score"] = h
                                            sel["away_score"] = a

                                    if ev_clock:
                                        try:
                                            if isinstance(ev_clock, (int, float)):
                                                mins = int(ev_clock) // 60
                                                half = "H1" if mins <= 45 else "H2"
                                                sel["match_time"] = f"{mins}' {half}"
                                            elif ":" in str(ev_clock):
                                                mins = int(str(ev_clock).split(":")[0])
                                                half = "H1" if mins <= 45 else "H2"
                                                sel["match_time"] = f"{mins}' {half}"
                                        except Exception:
                                            pass
        except Exception as live_err:
            print("[TicketTracker] SportyBet events sync warning:", live_err)

        # ── PASS 2: Concluded Results Sweep (Verified Booking Codes Only) ────────
        try:
            now_ts2 = time.time()
            stale_tickets = [
                t for t in tickets
                if t.get("status") == "RUNNING"
                and t.get("code")
                and t.get("code") not in ("CUSTOM", "", "AI-BUILDER-INTERNAL", "ROLLOVER-INTERNAL")
                and any(
                    (
                        s.get("match_status") in ("LIVE", "ONGOING", "IN_PLAY")
                        and s.get("start_time_ms")
                        and ((now_ts2 * 1000) - s["start_time_ms"]) > 120 * 60 * 1000
                    )
                    for s in t.get("selections", [])
                )
            ]

            if stale_tickets:
                from app.adapters.bookmaker_adapter import SportyBetAdapter as _SBA
                _adapter2 = _SBA(db)
                for t in stale_tickets:
                    code = t.get("code")
                    try:
                        res2 = _adapter2.fetch_booking_code_details(code, "ng")
                        if res2 and res2.get("status") == "SUCCESS":
                            sb_sels = res2.get("selections", [])
                            sb_map2 = {}
                            for item in sb_sels:
                                gid = str(item.get("game_id") or item.get("external_fixture_id") or "")
                                mkey = f"{(item.get('home_team') or '').strip()}_{(item.get('away_team') or '').strip()}".lower()
                                if gid:
                                    sb_map2[gid] = item
                                if mkey:
                                    sb_map2[mkey] = item

                            for sel in t.get("selections", []):
                                sel_st = (sel.get("match_status") or "").upper()
                                sel_ms = sel.get("start_time_ms")
                                is_stale_live = (
                                    sel_st in ("LIVE", "ONGOING", "IN_PLAY")
                                    and sel_ms
                                    and ((now_ts2 * 1000) - sel_ms) > 120 * 60 * 1000
                                )
                                if not is_stale_live:
                                    continue

                                gid = str(sel.get("game_id") or sel.get("fixture_id") or "")
                                mkey = f"{(sel.get('home_team') or '').strip()}_{(sel.get('away_team') or '').strip()}".lower()
                                sb_item = sb_map2.get(gid) or sb_map2.get(mkey)
                                if sb_item:
                                    sc = sb_item.get("score") or ""
                                    if sc and sc != "--" and sc != "0:0" and sc != "0-0":
                                        sel["score"] = sc
                                        h2, a2 = _parse_score(sc)
                                        if h2 is not None:
                                            sel["home_score"] = h2
                                            sel["away_score"] = a2
                                    if sb_item.get("home_score") is not None:
                                        sel["home_score"] = sb_item["home_score"]
                                        sel["away_score"] = sb_item["away_score"]
                                        sel["score"] = f"{sel['home_score']} - {sel['away_score']}"
                                    if sb_item.get("leg_result") in ("WON", "LOST", "VOID"):
                                        sel["leg_result"] = sb_item["leg_result"]
                                        sel["leg_status"] = sb_item["leg_result"]
                                    bk_st = str(sb_item.get("match_status") or "").upper()
                                    if bk_st in ("CONCLUDED", "FT", "FINISHED", "ENDED"):
                                        sel["match_status"] = "CONCLUDED"
                                        sel["is_live"] = False
                    except Exception as stale_err:
                        print(f"[TicketTracker] Concluded sweep error for {code}:", stale_err)
        except Exception as sweep_err:
            print("[TicketTracker] Concluded results sweep exception:", sweep_err)

        # Persist full tickets list to DB
        save_tracked_tickets(tickets, db=db)
    except Exception as e:
        import traceback
        print("[TicketTracker] Live API sync exception:", e)
        traceback.print_exc()

    return evaluate_tracked_tickets(db=db)


