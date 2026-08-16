import sys
import os
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

import sqlite3
import json
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from app.db.models import Base, TrackedTicket, CanonicalFixture, FixtureProviderMapping, AccessPasskey

PG_URL = "postgresql://statiq_db_user:yo4HfMmj4GGOsxN4hyTz5fGXRT6Fx0hY@dpg-da0op5s9v7es739s4ivg-a.oregon-postgres.render.com/statiq_db"

def migrate():
    print("==================================================")
    print("      STATIQ CLOUD POSTGRESQL DATA MIGRATION      ")
    print("==================================================")
    
    # 1. Connect to PostgreSQL
    print("\n[Step 1] Connecting to PostgreSQL on Render...")
    pg_engine = create_engine(
        PG_URL,
        connect_args={"sslmode": "require", "connect_timeout": 15},
        pool_pre_ping=True
    )

    
    # 2. Create all tables in PostgreSQL
    print("[Step 2] Initializing tables in PostgreSQL (Base.metadata.create_all)...")
    Base.metadata.create_all(bind=pg_engine)
    PgSession = sessionmaker(bind=pg_engine)
    pg_db = PgSession()
    print("  -> PostgreSQL tables verified!")

    # 3. Read from Local SQLite
    sqlite_path = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "matchiq.db"))
    print(f"\n[Step 3] Reading local SQLite database ({sqlite_path})...")
    conn = sqlite3.connect(sqlite_path)
    cur = conn.cursor()
    
    # Migrate Tracked Tickets
    cur.execute("SELECT id, code, mode, target_odds, total_odds, stake, flex_cut, potential_win, status, created_at, locked_at_unix, selections, settled_at, flex_status_text, allowed_losses, loss_count, is_live, stale, stale_reason FROM tracked_tickets")
    rows = cur.fetchall()
    print(f"  -> Found {len(rows)} tickets in local SQLite database.")

    migrated_tickets = 0
    updated_tickets = 0

    for r in rows:
        tid = r[0]
        selections_data = json.loads(r[11]) if isinstance(r[11], str) else (r[11] or [])
        
        existing = pg_db.query(TrackedTicket).filter(TrackedTicket.id == tid).first()
        if existing:
            existing.code = r[1]
            existing.mode = r[2]
            existing.target_odds = float(r[3] or 1.5)
            existing.total_odds = float(r[4] or 1.5)
            existing.stake = float(r[5] or 100.0)
            existing.flex_cut = r[6]
            existing.potential_win = float(r[7] or 150.0)
            existing.status = r[8]
            existing.created_at = r[9]
            existing.locked_at_unix = int(r[10] or 0)
            existing.selections = selections_data
            existing.settled_at = r[12]
            existing.flex_status_text = r[13]
            existing.allowed_losses = r[14]
            existing.loss_count = r[15]
            existing.is_live = bool(r[16])
            existing.stale = bool(r[17])
            existing.stale_reason = r[18]
            updated_tickets += 1
        else:
            new_ticket = TrackedTicket(
                id=tid,
                code=r[1] or "CUSTOM",
                mode=r[2] or "SWAP",
                target_odds=float(r[3] or 1.5),
                total_odds=float(r[4] or 1.5),
                stake=float(r[5] or 100.0),
                flex_cut=r[6],
                potential_win=float(r[7] or 150.0),
                status=r[8] or "RUNNING",
                created_at=r[9] or "",
                locked_at_unix=int(r[10] or 0),
                selections=selections_data,
                settled_at=r[12],
                flex_status_text=r[13],
                allowed_losses=r[14],
                loss_count=r[15],
                is_live=bool(r[16]),
                stale=bool(r[17]),
                stale_reason=r[18]
            )
            pg_db.add(new_ticket)
            migrated_tickets += 1

    # Migrate Access Passkeys
    try:
        cur.execute("SELECT key, label, role, is_active, notes FROM access_passkeys")
        passkey_rows = cur.fetchall()
        for pk in passkey_rows:
            exists = pg_db.query(AccessPasskey).filter(AccessPasskey.key == pk[0]).first()
            if not exists:
                pg_db.add(AccessPasskey(
                    key=pk[0],
                    label=pk[1] or "Beta Tester",
                    role=pk[2] or "BETA_TESTER",
                    is_active=bool(pk[3]),
                    notes=pk[4]
                ))
    except Exception as pk_err:
        pass

    pg_db.commit()
    conn.close()
    
    total_pg_tickets = pg_db.query(TrackedTicket).count()
    pg_db.close()

    print("\n==================================================")
    print(f"  MIGRATION COMPLETE:")
    print(f"  • Inserted new tickets: {migrated_tickets}")
    print(f"  • Updated existing tickets: {updated_tickets}")
    print(f"  • Total tickets in PostgreSQL Cloud: {total_pg_tickets}")
    print("==================================================")

if __name__ == "__main__":
    migrate()
