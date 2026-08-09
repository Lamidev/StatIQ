import subprocess
import json
import os

def restore_final():
    file_path = os.path.abspath(os.path.join("backend", "data", "tracked_tickets.json"))
    
    current_tickets = []
    if os.path.exists(file_path):
        with open(file_path, "r", encoding="utf-8") as f:
            try:
                current_tickets = json.load(f)
            except Exception:
                current_tickets = []

    cmd = ["git", "show", "HEAD:backend/data/tracked_tickets.json"]
    res = subprocess.run(cmd, capture_output=True, text=True)
    git_tickets = []
    if res.returncode == 0:
        try:
            git_tickets = json.loads(res.stdout)
        except Exception as e:
            print(f"Error parsing git tickets: {e}")

    seen_ids = set()
    merged = []

    for t in current_tickets:
        tid = t.get("id")
        if tid and tid not in seen_ids:
            seen_ids.add(tid)
            merged.append(t)

    for t in git_tickets:
        tid = t.get("id")
        if tid and tid not in seen_ids:
            seen_ids.add(tid)
            merged.append(t)

    merged.sort(key=lambda x: x.get("locked_at_unix", 0), reverse=True)

    with open(file_path, "w", encoding="utf-8") as f:
        json.dump(merged, f, indent=2, ensure_ascii=False)

    print(f"✅ Restored {len(merged)} tickets!")

if __name__ == "__main__":
    restore_final()
