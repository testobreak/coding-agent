from sqlalchemy import text

from repository_intelligence.db.connection import (
    engine,
    SessionLocal
)

print("\n=== ENGINE URL ===")
print(engine.url)

session = SessionLocal()

try:
    print("\n=== DATABASE ===")
    print(
        session.execute(
            text("select current_database()")
        ).scalar()
    )

    print("\n=== SCHEMA ===")
    print(
        session.execute(
            text("select current_schema()")
        ).scalar()
    )

    print("\n=== TABLES ===")

    rows = session.execute(
        text("""
            SELECT table_name
            FROM information_schema.tables
            WHERE table_schema='public'
            ORDER BY table_name
        """)
    )

    found = False

    for row in rows:
        found = True
        print(row[0])

    if not found:
        print("NO TABLES FOUND")

finally:
    session.close()