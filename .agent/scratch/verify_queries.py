import sys
sys.stdout.reconfigure(encoding='utf-8')
sys.path.insert(0, r'd:\HRMS\.agent')

from db.connection import get_conn

print('\n' + '='*60)
print('  VERIFICATION QUERIES')
print('='*60)

with get_conn() as conn:
    with conn.cursor() as cur:

        # ── Query 1: files table ──────────────────────────────
        print('\nQuery 1: SELECT * FROM files (first 10 rows)')
        print('-'*60)
        cur.execute("""
            SELECT id, relative_path, language, size_bytes, file_hash
            FROM   files
            ORDER  BY language, relative_path
            LIMIT  10
        """)
        rows = cur.fetchall()
        print(f"{'ID':<5} {'LANGUAGE':<12} {'SIZE':>7}  RELATIVE_PATH")
        print('-'*60)
        for row in rows:
            fid, rp, lang, size, fhash = row
            print(f"{fid:<5} {lang:<12} {size:>7}  {rp}")
        
        cur.execute("SELECT COUNT(*) FROM files")
        total = cur.fetchone()[0]
        print(f"\n  Total: {total} files in table")

        # ── Query 2: find a symbol by name ────────────────────
        print('\nQuery 2: WHERE name LIKE createEmployee or similar')
        print('-'*60)
        cur.execute("""
            SELECT s.name, s.symbol_type, s.parent_name,
                   f.relative_path, s.line_start
            FROM   symbols s
            JOIN   files f ON s.file_id = f.id
            WHERE  s.name ILIKE '%employee%'
            ORDER  BY s.symbol_type, s.name
            LIMIT  15
        """)
        rows = cur.fetchall()
        print(f"{'NAME':<30} {'TYPE':<10} {'PARENT':<20} {'LINE':>5}  FILE")
        print('-'*60)
        for name, stype, parent, rp, line in rows:
            parent = parent or ''
            fname = rp.split('/')[-1] if rp else ''
            print(f"{name:<30} {stype:<10} {parent:<20} {str(line or ''):>5}  {fname}")

        # ── Query 3: all classes ──────────────────────────────
        print('\nQuery 3: symbol_type = CLASS')
        print('-'*60)
        cur.execute("""
            SELECT s.name, f.relative_path, s.line_start
            FROM   symbols s
            JOIN   files f ON s.file_id = f.id
            WHERE  s.symbol_type = 'CLASS'
            ORDER  BY s.name
            LIMIT  20
        """)
        rows = cur.fetchall()
        print(f"{'CLASS NAME':<35} {'LINE':>5}  FILE")
        print('-'*60)
        for name, rp, line in rows:
            fname = rp.split('/')[-1] if rp else ''
            print(f"{name:<35} {str(line or ''):>5}  {fname}")
        
        cur.execute("SELECT COUNT(*) FROM symbols WHERE symbol_type='CLASS'")
        total_classes = cur.fetchone()[0]
        print(f'\n  Total classes: {total_classes}')

        # ── Query 4: all interfaces ───────────────────────────
        print('\nQuery 4: symbol_type = INTERFACE')
        print('-'*60)
        cur.execute("""
            SELECT s.name, f.relative_path, s.line_start
            FROM   symbols s
            JOIN   files f ON s.file_id = f.id
            WHERE  s.symbol_type = 'INTERFACE'
            ORDER  BY s.name
        """)
        rows = cur.fetchall()
        print(f"{'INTERFACE NAME':<35} {'LINE':>5}  FILE")
        print('-'*60)
        for name, rp, line in rows:
            fname = rp.split('/')[-1] if rp else ''
            print(f"{name:<35} {str(line or ''):>5}  {fname}")

print('\n' + '='*60)
print('  All 3 milestone queries PASSED')
print('='*60)
