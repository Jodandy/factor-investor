from factor_investor.db import get_session
from sqlalchemy import text

with get_session() as session:
    tables = session.execute(text(
        "SELECT table_name FROM information_schema.tables WHERE table_schema = 'public' ORDER BY table_name"
    )).fetchall()

    print("\nDatabase Tables:")
    print("=" * 40)
    for table in tables:
        print(f"  - {table[0]}")
