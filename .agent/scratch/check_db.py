import psycopg2

attempts = [
    dict(dbname='postgres', user='postgres', password='postgres', host='localhost', port=5432),
    dict(dbname='postgres', user='postgres', password='admin', host='localhost', port=5432),
    dict(dbname='postgres', user='postgres', password='123456', host='localhost', port=5432),
    dict(dbname='postgres', user='postgres', password='password', host='localhost', port=5432),
]
for a in attempts:
    try:
        conn = psycopg2.connect(**a, connect_timeout=3)
        print(f"CONNECTED: user={a['user']} password={a['password']}")
        cur = conn.cursor()
        cur.execute("SELECT version()")
        print("  Version:", cur.fetchone()[0][:50])
        conn.close()
        break
    except Exception as e:
        print(f"  user={a['user']} password={a['password']} -> {str(e)[:80]}")
