import sqlite3
import json

conn = sqlite3.connect('matchiq.db')
cursor = conn.cursor()
tables = [row[0] for row in cursor.execute("SELECT name FROM sqlite_master WHERE type='table';").fetchall()]
print('Tables:', tables)

for t in tables:
    try:
        rows = cursor.execute(f'SELECT * FROM {t}').fetchall()
        for r in rows:
            r_str = str(r)
            if '46046' in r_str or 'Strasswalchen' in r_str or 'Salzburg' in r_str or 'Goal Bounds' in r_str:
                print(f'\nFound in table {t}:')
                print(r)
    except Exception as e:
        print(f'Error reading {t}:', e)
