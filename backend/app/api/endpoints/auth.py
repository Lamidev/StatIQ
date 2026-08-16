"""
StatIQ Beta Access Passkey Authentication & Management API
===========================================================
Handles passkey verification, session validation, and admin passkey generation.
"""

import random
import datetime
from typing import List, Dict, Any, Optional
from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel
from sqlalchemy.orm import Session
from sqlalchemy import select

from app.db.session import get_db
from app.db.models import AccessPasskey

router = APIRouter()

MASTER_ADMIN_KEY = "THISSLAMI1805"

def _ensure_admin_seed(db: Session):
    """Ensures only THISSLAMI1805 exists as the admin."""
    try:
        from sqlalchemy import delete
        # Delete any admin record that is not THISSLAMI1805
        db.execute(delete(AccessPasskey).where((AccessPasskey.role == "ADMIN") & (AccessPasskey.key != MASTER_ADMIN_KEY)))
        
        # Ensure THISSLAMI1805 exists and is active
        existing_admin = db.execute(select(AccessPasskey).where(AccessPasskey.key == MASTER_ADMIN_KEY)).scalar_one_or_none()
        if not existing_admin:
            admin_key = AccessPasskey(
                key=MASTER_ADMIN_KEY,
                label="Lami (System Admin)",
                role="ADMIN",
                is_active=True,
                created_at=datetime.datetime.utcnow()
            )
            db.add(admin_key)
        elif not existing_admin.is_active or existing_admin.role != "ADMIN":
            existing_admin.is_active = True
            existing_admin.role = "ADMIN"
        db.commit()
    except Exception as e:
        db.rollback()

class VerifyPasskeyRequest(BaseModel):
    passkey: str

class CreatePasskeyRequest(BaseModel):
    label: str
    custom_key: Optional[str] = None
    role: str = "BETA_TESTER"  # "BETA_TESTER" or "ADMIN"
    notes: Optional[str] = None

class TogglePasskeyRequest(BaseModel):
    key: str
    is_active: bool

@router.post("/verify")
def verify_passkey(req: VerifyPasskeyRequest, db: Session = Depends(get_db)):
    """
    Verifies an access passkey.
    Returns profile information, role (ADMIN/BETA_TESTER), and access status.
    """
    _ensure_admin_seed(db)
    raw_key = (req.passkey or "").strip().upper()
    if not raw_key:
        raise HTTPException(status_code=400, detail="Passkey cannot be empty")

    # Check database
    passkey_obj = db.execute(select(AccessPasskey).where(AccessPasskey.key == raw_key)).scalar_one_or_none()

    # If it's the master admin key and wasn't in DB yet
    if not passkey_obj and raw_key == MASTER_ADMIN_KEY:
        passkey_obj = AccessPasskey(
            key=MASTER_ADMIN_KEY,
            label="Lami (System Admin)",
            role="ADMIN",
            is_active=True,
            created_at=datetime.datetime.utcnow()
        )
        db.add(passkey_obj)
        db.commit()

    if not passkey_obj:
        return {
            "success": False,
            "message": "Invalid Access Passkey. Please check your key or request access from the admin."
        }

    if not passkey_obj.is_active:
        return {
            "success": False,
            "message": "This Access Passkey has been paused or revoked by the administrator."
        }

    # Update last used timestamp
    try:
        passkey_obj.last_used_at = datetime.datetime.utcnow()
        db.commit()
    except Exception:
        db.rollback()

    return {
        "success": True,
        "key": passkey_obj.key,
        "label": passkey_obj.label,
        "role": passkey_obj.role,
        "created_at": passkey_obj.created_at.isoformat() if passkey_obj.created_at else None
    }


@router.get("/passkeys")
def list_passkeys(db: Session = Depends(get_db)):
    """
    Lists all issued passkeys (for Admin management).
    """
    _ensure_admin_seed(db)
    passkeys = db.execute(select(AccessPasskey).order_by(AccessPasskey.created_at.desc())).scalars().all()
    return {
        "total": len(passkeys),
        "passkeys": [
            {
                "key": p.key,
                "label": p.label,
                "role": p.role,
                "is_active": p.is_active,
                "created_at": p.created_at.strftime("%Y-%m-%d %H:%M") if p.created_at else "--",
                "last_used_at": p.last_used_at.strftime("%Y-%m-%d %H:%M") if p.last_used_at else "Never",
                "notes": p.notes
            }
            for p in passkeys
        ]
    }


@router.post("/passkeys/create")
def create_passkey(req: CreatePasskeyRequest, db: Session = Depends(get_db)):
    """
    Generates a new access passkey for a beta tester or co-admin.
    """
    _ensure_admin_seed(db)
    label_clean = req.label.strip()
    if not label_clean:
        raise HTTPException(status_code=400, detail="Tester name/label is required")

    if req.custom_key and req.custom_key.strip():
        final_key = req.custom_key.strip()
    else:
        # Generate clean unique passkey with 4 random digits e.g. okey5789, ben6669
        prefix = "".join(c for c in label_clean.lower() if c.isalnum())[:10] or "beta"
        digits = "".join(random.choices("0123456789", k=4))
        final_key = f"{prefix}{digits}"

    # Ensure uniqueness
    existing = db.execute(select(AccessPasskey).where(AccessPasskey.key.ilike(final_key))).scalar_one_or_none()
    if existing:
        extra_digits = "".join(random.choices("0123456789", k=2))
        final_key = f"{final_key}{extra_digits}"

    new_passkey = AccessPasskey(
        key=final_key,
        label=label_clean,
        role=req.role if req.role in ("ADMIN", "BETA_TESTER") else "BETA_TESTER",
        is_active=True,
        created_at=datetime.datetime.utcnow(),
        notes=req.notes
    )
    db.add(new_passkey)
    db.commit()

    return {
        "success": True,
        "key": new_passkey.key,
        "label": new_passkey.label,
        "role": new_passkey.role
    }


@router.post("/passkeys/toggle")
def toggle_passkey(req: TogglePasskeyRequest, db: Session = Depends(get_db)):
    """
    Activates or disables an access passkey.
    """
    p = db.execute(select(AccessPasskey).where(AccessPasskey.key == req.key)).scalar_one_or_none()
    if not p:
        raise HTTPException(status_code=404, detail="Passkey not found")

    p.is_active = req.is_active
    db.commit()
    return {"success": True, "key": p.key, "is_active": p.is_active}


@router.delete("/passkeys/{key}")
def delete_passkey(key: str, db: Session = Depends(get_db)):
    """
    Deletes an access passkey.
    """
    if key == MASTER_ADMIN_KEY:
        raise HTTPException(status_code=400, detail="Cannot delete master admin passkey")

    p = db.execute(select(AccessPasskey).where(AccessPasskey.key == key)).scalar_one_or_none()
    if not p:
        raise HTTPException(status_code=404, detail="Passkey not found")

    db.delete(p)
    db.commit()
    return {"success": True, "deleted_key": key}
