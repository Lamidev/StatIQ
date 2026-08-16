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

# Stores ticket IDs that were explicitly dismissed — never regenerated
DISMISSED_FILE = os.path.join(
    os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))),
    "data",
    "notifications_dismissed.json"
)


def _ensure_data_dir():
    data_dir = os.path.dirname(NOTIFICATIONS_FILE)
    if not os.path.exists(data_dir):
        os.makedirs(data_dir, exist_ok=True)


def load_notifications() -> List[Dict[str, Any]]:
    _ensure_data_dir()
    if not os.path.exists(NOTIFICATIONS_FILE):
        return []
    try:
        with open(NOTIFICATIONS_FILE, "r", encoding="utf-8") as f:
            data = json.load(f)
            return data if isinstance(data, list) else []
    except Exception:
        return []


def save_notifications(notifications: List[Dict[str, Any]]):
    _ensure_data_dir()
    with open(NOTIFICATIONS_FILE, "w", encoding="utf-8") as f:
        json.dump(notifications, f, indent=2)


def load_dismissed() -> set:
    """Load ticket IDs that the user explicitly cleared."""
    _ensure_data_dir()
    if not os.path.exists(DISMISSED_FILE):
        return set()
    try:
        with open(DISMISSED_FILE, "r", encoding="utf-8") as f:
            data = json.load(f)
            return set(data) if isinstance(data, list) else set()
    except Exception:
        return set()


def save_dismissed(dismissed: set):
    _ensure_data_dir()
    with open(DISMISSED_FILE, "w", encoding="utf-8") as f:
        json.dump(list(dismissed), f)


def push_win_notification(ticket: Dict[str, Any]):
    """
    Called immediately when a ticket transitions to WON during evaluation/sync.
    Adds the notification instantly without waiting for a GET request.
    """
    tid = ticket.get("id")
    if not tid:
        return
    dismissed = load_dismissed()
    if tid in dismissed:
        return
    existing = load_notifications()
    if any(n.get("ticket_id") == tid for n in existing):
        return  # already notified

    code = ticket.get("code") or "TICKET"
    flex_text = ticket.get("flex_status_text") or "WON (Clean Sweep - 0 Losses)"
    mode = ticket.get("mode") or "AUDITOR"
    stake = ticket.get("stake") or 1000

    new_notif = {
        "id": f"NOTIF-{tid}",
        "ticket_id": tid,
        "code": code,
        "mode": mode,
        "title": f"\U0001f389 Ticket WON! \u2014 {code}",
        "message": f"{flex_text} \u2022 Stake \u20a6{stake:,.2f}",
        "flex_status_text": flex_text,
        "status": "WON",
        "odds": ticket.get("total_odds") or ticket.get("odds") or "1.00",
        "potential_payout": ticket.get("potential_win") or 0.0,
        "created_at": ticket.get("settled_at") or ticket.get("created_at") or time.strftime("%Y-%m-%d %H:%M:%S"),
        "read": False
    }
    combined = [new_notif] + existing
    combined.sort(key=lambda x: x.get("created_at", ""), reverse=True)
    save_notifications(combined)


def sync_win_notifications() -> List[Dict[str, Any]]:
    """
    Scans all WON tickets and adds notifications for new ones only.
    Never re-adds dismissed notifications.
    """
    dismissed = load_dismissed()
    existing = load_notifications()
    existing_ids = {n.get("ticket_id") for n in existing}

    tickets = get_tracked_tickets()
    won_tickets = [t for t in tickets if t.get("status") == "WON"]

    new_notifs = []
    for t in won_tickets:
        tid = t.get("id")
        if not tid or tid in dismissed or tid in existing_ids:
            continue
        code = t.get("code") or "TICKET"
        flex_text = t.get("flex_status_text") or "WON (Clean Sweep - 0 Losses)"
        mode = t.get("mode") or "AUDITOR"
        stake = t.get("stake") or 1000
        new_notifs.append({
            "id": f"NOTIF-{tid}",
            "ticket_id": tid,
            "code": code,
            "mode": mode,
            "title": f"\U0001f389 Ticket WON! \u2014 {code}",
            "message": f"{flex_text} \u2022 Stake \u20a6{stake:,.2f}",
            "flex_status_text": flex_text,
            "status": "WON",
            "odds": t.get("total_odds") or t.get("odds") or "1.00",
            "potential_payout": t.get("potential_win") or 0.0,
            "created_at": t.get("settled_at") or t.get("created_at") or time.strftime("%Y-%m-%d %H:%M:%S"),
            "read": False
        })

    if new_notifs:
        combined = new_notifs + existing
        combined.sort(key=lambda x: x.get("created_at", ""), reverse=True)
        save_notifications(combined)
        return combined
    return existing


@router.get("")
def get_notifications_endpoint():
    """Return notifications. Only creates entries for NEW WON tickets; never re-adds dismissed ones."""
    notifs = sync_win_notifications()
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
    """
    Clear all notifications permanently.
    All cleared ticket IDs are added to the dismissed list so they never reappear.
    """
    existing = load_notifications()
    dismissed = load_dismissed()
    for n in existing:
        tid = n.get("ticket_id")
        if tid:
            dismissed.add(tid)
    save_dismissed(dismissed)
    save_notifications([])
    return {"status": "SUCCESS", "notifications": [], "unread_count": 0}


@router.delete("/dismiss/{ticket_id}")
def dismiss_single_notification(ticket_id: str):
    """Dismiss a single ticket's notification permanently."""
    dismissed = load_dismissed()
    dismissed.add(ticket_id)
    save_dismissed(dismissed)
    existing = load_notifications()
    filtered = [n for n in existing if n.get("ticket_id") != ticket_id]
    save_notifications(filtered)
    unread_count = sum(1 for n in filtered if not n.get("read"))
    return {"status": "SUCCESS", "notifications": filtered, "unread_count": unread_count}

