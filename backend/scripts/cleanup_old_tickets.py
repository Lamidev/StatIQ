import sqlite3
import os

db_path = os.path.abspath("matchiq.db")
conn = sqlite3.connect(db_path)
c = conn.cursor()

c.execute("SELECT COUNT(*) FROM tracked_tickets")
initial = c.fetchone()[0]
print(f"Initial tickets count: {initial}")

c.execute("DELETE FROM tracked_tickets WHERE created_at < '2026-08-16 00:00:00'")
deleted = c.rowcount
conn.commit()

c.execute("VACUUM")
c.execute("SELECT COUNT(*), MIN(created_at), MAX(created_at) FROM tracked_tickets")
res = c.fetchone()
print(f"Deleted: {deleted} old tickets.")
print(f"Remaining tickets: {res[0]} (Range: {res[1]} to {res[2]})")
conn.close()
