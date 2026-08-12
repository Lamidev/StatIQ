import os
import json
import time
from typing import List, Dict, Any
from fastapi import APIRouter
from app.services.ticket_tracker import get_tracked_tickets

router = APIRouter()

NOTIFICATIONS_FILE = os.path.join(
    os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))),
    "data",
    "notifications.json"
)

def _ensure_data_dir():
    data_dir = os.path.dirname(NOTIFICATIONS_FILE)
    if not os.path.exists(data_dir):
        os.makedirs(data_dir, exist_ok=True)

def load_notifications() -> List[Dict[str, Any]]:
    _ensure_data_dir()
    if not os.path.exists(NOTIFICATIONS_FILE):
        return sync_historical_win_notifications()
    try:
        with open(NOTIFICATIONS_FILE, "r", encoding="utf-8") as f:
            data = json.load(f)
            if not isinstance(data, list):
                return sync_historical_win_notifications()
            return data
    except Exception:
        return sync_historical_win_notifications()

def save_notifications(notifications: List[Dict[str, Any]]):
    _ensure_data_dir()
    with open(NOTIFICATIONS_FILE, "w", encoding="utf-8") as f:
        json.dump(notifications, f, indent=2)

def sync_historical_win_notifications() -> List[Dict[str, Any]]:
    """Scan tracked_tickets.json and generate notifications for all WON tickets, purging stale notifications for lost/deleted tickets."""
    existing = []
    if os.path.exists(NOTIFICATIONS_FILE):
        try:
            with open(NOTIFICATIONS_FILE, "r", encoding="utf-8") as f:
                existing = json.load(f)
                if not isinstance(existing, list):
                    existing = []
        except Exception:
            existing = []

    tickets = get_tracked_tickets()
    tickets_by_id = {t.get("id"): t for t in tickets}

    # Filter existing notifications: purge any notification whose ticket is now LOST or deleted
    valid_existing = []
    for n in existing:
        tid = n.get("ticket_id")
        if tid:
            t_obj = tickets_by_id.get(tid)
            if t_obj and t_obj.get("status") == "WON":
                n["mode"] = t_obj.get("mode") or n.get("mode") or "AUDITOR"
                valid_existing.append(n)
        else:
            valid_existing.append(n)

    existing_ticket_ids = {n.get("ticket_id") for n in valid_existing if n.get("ticket_id")}
    won_tickets = [t for t in tickets if t.get("status") == "WON"]

    new_notifs = []
    for t in won_tickets:
        tid = t.get("id")
        if tid not in existing_ticket_ids:
            code = t.get("code") or "TICKET"
            flex_text = t.get("flex_status_text") or "Ticket Won!"
            odds = t.get("odds") or t.get("total_odds") or "1.00"
            payout = t.get("potential_win") or t.get("pot_win") or 0.0
            mode = t.get("mode") or "AUDITOR"

            new_notifs.append({
                "id": f"NOTIF-{tid}",
                "ticket_id": tid,
                "code": code,
                "mode": mode,
                "title": f"🎉 Ticket WON! — {code}",
                "message": f"{flex_text} • Stake ₦{t.get('stake', 1000):,.2f}",
                "flex_status_text": flex_text,
                "status": "WON",
                "odds": odds,
                "potential_payout": payout,
                "created_at": t.get("created_at") or time.strftime("%Y-%m-%d %H:%M:%S"),
                "read": False
            })

    combined = new_notifs + valid_existing
    # Sort descending by creation time
    combined.sort(key=lambda x: x.get("created_at", ""), reverse=True)
    save_notifications(combined)
    return combined


@router.get("")
def get_notifications_endpoint():
    """Return all notifications, automatically syncing historical WON tickets if needed."""
    notifs = load_notifications()
    notifs = sync_historical_win_notifications()
    unread_count = sum(1 for n in notifs if not n.get("read"))
    return {
        "notifications": notifs,
        "unread_count": unread_count,
        "total_count": len(notifs)
    }

@router.post("/mark-read")
def mark_notifications_read_endpoint(payload: dict):
    """Mark a specific notification or all notifications as read."""
    notif_id = payload.get("id")
    mark_all = payload.get("all", False)

    notifs = load_notifications()
    for n in notifs:
        if mark_all or n.get("id") == notif_id:
            n["read"] = True

    save_notifications(notifs)
    unread_count = sum(1 for n in notifs if not n.get("read"))
    return {"status": "SUCCESS", "unread_count": unread_count, "notifications": notifs}

@router.delete("/clear")
def clear_all_notifications_endpoint():
    """Clear all notifications."""
    save_notifications([])
    return {"status": "SUCCESS", "notifications": [], "unread_count": 0}
