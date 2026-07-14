import psycopg
from app.core.db import PG_HOST, PG_PORT, PG_DBNAME, PG_USER, PG_PASSWORD, ALL_SCHEMAS

for schema in ALL_SCHEMAS:
    conn = psycopg.connect(
        host=PG_HOST, port=PG_PORT, dbname=PG_DBNAME,
        user=PG_USER, password=PG_PASSWORD,
        options=f"-c search_path={schema},public"
    )
    cur = conn.cursor()
    cur.execute(
        "UPDATE transaction_history SET created_by = 'superuser', created_by_empno = '0000000' "
        "WHERE created_by = '' OR created_by IS NULL"
    )
    print(f"{schema}: {cur.rowcount}건 업데이트")
    conn.commit()
    conn.close()

print("완료")
