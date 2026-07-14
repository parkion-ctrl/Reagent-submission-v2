from django.core.management.base import BaseCommand
import psycopg
from app.core.db import PG_HOST, PG_PORT, PG_DBNAME, PG_USER, PG_PASSWORD, ALL_SCHEMAS


class Command(BaseCommand):
    help = 'inventory 테이블에 is_new_lot 컬럼 추가 및 기존 데이터 N 처리'

    def handle(self, *args, **options):
        for schema in ALL_SCHEMAS:
            try:
                conn = psycopg.connect(
                    host=PG_HOST, port=PG_PORT, dbname=PG_DBNAME,
                    user=PG_USER, password=PG_PASSWORD,
                    options=f"-c search_path={schema},public",
                )
                cur = conn.cursor()

                cur.execute(
                    """
                    SELECT 1 FROM information_schema.columns
                    WHERE table_schema = %s
                      AND table_name = 'inventory'
                      AND column_name = 'is_new_lot'
                    """,
                    (schema,),
                )
                exists = cur.fetchone() is not None

                if not exists:
                    cur.execute(
                        "ALTER TABLE inventory ADD COLUMN is_new_lot TEXT NOT NULL DEFAULT 'N'"
                    )
                    conn.commit()
                    self.stdout.write(self.style.SUCCESS(f"[{schema}] is_new_lot 컬럼 추가 완료 (기존 데이터 N 처리됨)"))
                else:
                    # 컬럼은 있지만 NULL인 행을 N으로 업데이트
                    cur.execute(
                        "UPDATE inventory SET is_new_lot = 'N' WHERE is_new_lot IS NULL OR TRIM(is_new_lot) = ''"
                    )
                    conn.commit()
                    self.stdout.write(self.style.SUCCESS(f"[{schema}] 이미 존재 - NULL/빈값 N으로 업데이트 완료"))

                conn.close()
            except Exception as e:
                self.stdout.write(self.style.ERROR(f"[{schema}] 오류: {e}"))
