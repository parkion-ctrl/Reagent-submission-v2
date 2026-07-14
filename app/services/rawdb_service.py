import psycopg
from app.core.db import PG_HOST, PG_PORT, PG_DBNAME, PG_USER, PG_PASSWORD, ConnectionWrapper, ALL_SCHEMAS
from app.utils.constants import get_part_map, REAGENT_TYPE_MAP


def _get_public_conn():
    """public 스키마 전용 연결 (raw_db 테이블용)"""
    conn = psycopg.connect(
        host=PG_HOST,
        port=PG_PORT,
        dbname=PG_DBNAME,
        user=PG_USER,
        password=PG_PASSWORD,
        options="-c search_path=public",
    )
    return ConnectionWrapper(conn)


Y_VALUES = {"1", "Y", "y", "YES", "Yes", "yes", "예", "사용"}
N_VALUES = {"0", "N", "n", "No", "no", "아니오", "무"}


def _normalize(val):
    if val is None:
        return ""
    s = str(val).strip()
    return "" if s.lower() in {"nan", "none", "<na>"} else s


def _haz(val):
    v = _normalize(val).upper()
    return "Y" if v in Y_VALUES else "N"


def get_rawdb_filter_options():
    conn = _get_public_conn()
    cursor = conn.cursor()
    cursor.execute(
        "SELECT DISTINCT hazardous_grade FROM public.raw_db ORDER BY hazardous_grade"
    )
    rows = [row[0] for row in cursor.fetchall()]
    conn.close()
    has_blank = any(v is None or str(v).strip() == "" for v in rows)
    opts = []
    if has_blank:
        opts.append("__BLANK__")
    opts.extend(str(v).strip() for v in rows if v is not None and str(v).strip() != "")
    return {"hazardous_grade_options": opts}


_IN_MASTER_EXISTS = """EXISTS (
    SELECT 1 FROM dlab.inventory WHERE item_code = raw_db.item_code AND part = raw_db.part AND disposed_at IS NULL
    UNION ALL
    SELECT 1 FROM path.inventory WHERE item_code = raw_db.item_code AND part = raw_db.part AND disposed_at IS NULL
    UNION ALL
    SELECT 1 FROM nm.inventory   WHERE item_code = raw_db.item_code AND part = raw_db.part AND disposed_at IS NULL
    UNION ALL
    SELECT 1 FROM haz.inventory  WHERE item_code = raw_db.item_code AND part = raw_db.part AND disposed_at IS NULL
)"""


def get_rawdb_items(part="", q="", hazardous_grade="", not_in_master=False, in_master="", sort="", order="", schema=None):
    conn = _get_public_conn()
    cursor = conn.cursor()

    query = f"""
        SELECT id, part, hazardous, hazardous_grade, item_code, item_name, spec, unit,
               lot_no, expiry_date, reagent_type, vendor, unit_price, equipment, cas_no,
               CASE WHEN {_IN_MASTER_EXISTS} THEN 'Y' ELSE 'N' END AS in_master
        FROM public.raw_db
        WHERE 1=1
    """
    params = []

    # 부서(스키마) 필터: dlab은 NULL로 저장
    if schema is not None:
        db_schema = None if schema == "dlab" else schema
        if db_schema is None:
            query += " AND schema_name IS NULL"
        else:
            query += " AND schema_name = %s"
            params.append(db_schema)

    if part:
        query += " AND part = %s"
        params.append(part)
    if q:
        query += " AND (item_code ILIKE %s OR item_name ILIKE %s)"
        params.extend([f"%{q}%", f"%{q}%"])
    if hazardous_grade:
        if hazardous_grade == "__BLANK__":
            query += " AND (hazardous_grade IS NULL OR TRIM(hazardous_grade) = '')"
        else:
            query += " AND hazardous_grade = %s"
            params.append(hazardous_grade)
    if not_in_master or in_master == "N":
        query += f" AND NOT {_IN_MASTER_EXISTS}"
    elif in_master == "Y":
        query += f" AND {_IN_MASTER_EXISTS}"

    allowed = ["item_code", "item_name", "part", "unit_price"]
    if sort in allowed:
        ord_sql = "DESC" if order == "desc" else "ASC"
        query += f" ORDER BY {sort} {ord_sql}"
    else:
        query += " ORDER BY item_code ASC"

    cursor.execute(query, params or None)
    rows = cursor.fetchall()
    conn.close()

    _part_map = get_part_map()
    result = []
    for row in rows:
        r = dict(row)
        part_code = r.get("part", "")
        part_name = _part_map.get(part_code, "")
        r["part_label"] = f"{part_code} ({part_name})" if part_name else part_code
        reagent_raw = _normalize(r.get("reagent_type"))
        r["reagent_type_display"] = REAGENT_TYPE_MAP.get(reagent_raw, reagent_raw)
        haz_raw = _normalize(r.get("hazardous"))
        r["hazardous"] = "Y" if haz_raw in Y_VALUES else ("N" if haz_raw else "")
        r["hazardous_grade"] = str(r.get("hazardous_grade") or "").strip()
        expiry_raw = _normalize(r.get("expiry_date"))
        r["expiry_date"] = "" if expiry_raw == "9999-12-31" else (expiry_raw[:10] if expiry_raw else "")
        r["lot_no"] = str(r.get("lot_no") or "").strip()
        r["vendor"] = str(r.get("vendor") or "").strip()
        r["equipment"] = str(r.get("equipment") or "").strip()
        r["spec"] = str(r.get("spec") or "").strip()
        r["unit"] = str(r.get("unit") or "").strip()
        result.append(r)
    return result


def get_rawdb_item_by_id(item_id: int):
    conn = _get_public_conn()
    cursor = conn.cursor()
    cursor.execute("SELECT * FROM public.raw_db WHERE id = %s", (item_id,))
    row = cursor.fetchone()
    conn.close()
    if not row:
        return None
    r = dict(row)
    for col in ("lot_no", "vendor", "equipment", "spec", "unit", "hazardous_grade", "expiry_date", "cas_no"):
        r[col] = str(r.get(col) or "").strip()
    part_code = r.get("part", "")
    part_name = get_part_map().get(part_code, "")
    r["part_label"] = f"{part_code} ({part_name})" if part_name else part_code
    return r


def create_rawdb_item(part, hazardous, hazardous_grade, item_code, item_name, spec, unit,
                      lot_no, expiry_date, reagent_type, vendor, equipment, schema=None, cas_no=None):
    conn = _get_public_conn()
    cursor = conn.cursor()
    db_schema = None if (schema is None or schema == "dlab") else schema
    cursor.execute(
        """
        INSERT INTO public.raw_db
            (part, hazardous, hazardous_grade, item_code, item_name, spec, unit,
             lot_no, expiry_date, reagent_type, vendor, equipment, schema_name, cas_no)
        VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s)
        """,
        (part, _haz(hazardous), hazardous_grade or None, item_code, item_name,
         spec, unit, lot_no, expiry_date or None, reagent_type, vendor, equipment, db_schema, cas_no or None),
    )
    conn.commit()
    conn.close()


def _sync_rawdb_to_inventory_schemas(old_item_code, old_part, new_part, haz, hazardous_grade, item_code, item_name, spec, unit):
    """raw_db 수정 후 전 스키마 inventory 동기화 (품목코드+파트 일치 행만)"""
    for schema in ALL_SCHEMAS:
        try:
            conn = psycopg.connect(
                host=PG_HOST, port=PG_PORT, dbname=PG_DBNAME,
                user=PG_USER, password=PG_PASSWORD,
                options=f"-c search_path={schema},public",
            )
            wrapped = ConnectionWrapper(conn)
            cur = wrapped.cursor()
            cur.execute(
                """
                UPDATE inventory
                SET part=%s, hazardous=%s, hazardous_grade=%s,
                    item_code=%s, item_name=%s, spec=%s, unit=%s
                WHERE item_code=%s AND part=%s AND disposed_at IS NULL
                """,
                (new_part, haz, hazardous_grade or None,
                 item_code, item_name, spec, unit,
                 old_item_code, old_part),
            )
            wrapped.commit()
            wrapped.close()
        except Exception:
            pass


def sync_master_update_to_rawdb(old_item_code, old_part, new_part, hazardous, hazardous_grade, item_code, item_name, spec, unit):
    """inventory 수정 후 raw_db 동기화 (품목코드+파트 일치 행만)"""
    conn = _get_public_conn()
    cur = conn.cursor()
    cur.execute(
        """
        UPDATE public.raw_db
        SET part=%s, hazardous=%s, hazardous_grade=%s,
            item_code=%s, item_name=%s, spec=%s, unit=%s
        WHERE item_code=%s AND part=%s
        """,
        (new_part, _haz(hazardous), hazardous_grade or None,
         item_code, item_name, spec, unit,
         old_item_code, old_part),
    )
    conn.commit()
    conn.close()


def update_rawdb_item(item_id, part, hazardous, hazardous_grade, item_code, item_name, spec, unit,
                      lot_no, expiry_date, reagent_type, vendor, equipment):
    old = get_rawdb_item_by_id(item_id)
    old_item_code = old["item_code"] if old else None
    old_part = old["part"] if old else None

    conn = _get_public_conn()
    cursor = conn.cursor()
    cursor.execute(
        """
        UPDATE public.raw_db
        SET part=%s, hazardous=%s, hazardous_grade=%s, item_code=%s, item_name=%s,
            spec=%s, unit=%s, lot_no=%s, expiry_date=%s,
            reagent_type=%s, vendor=%s, equipment=%s
        WHERE id=%s
        """,
        (part, _haz(hazardous), hazardous_grade or None, item_code, item_name,
         spec, unit, lot_no, expiry_date or None,
         reagent_type, vendor, equipment, item_id),
    )
    conn.commit()
    conn.close()

    if old_item_code and old_part:
        _sync_rawdb_to_inventory_schemas(
            old_item_code, old_part, part, _haz(hazardous),
            hazardous_grade, item_code, item_name, spec, unit,
        )


def delete_rawdb_item(item_id: int):
    conn = _get_public_conn()
    cursor = conn.cursor()
    cursor.execute("DELETE FROM public.raw_db WHERE id = %s", (item_id,))
    conn.commit()
    conn.close()


def bulk_delete_rawdb_items(item_ids: list):
    conn = _get_public_conn()
    cursor = conn.cursor()
    for item_id in item_ids:
        cursor.execute("DELETE FROM public.raw_db WHERE id = %s", (item_id,))
    conn.commit()
    conn.close()


def _ensure_list_tables():
    """vendor_list / equipment_list 테이블이 없으면 생성하고, 비어있으면 전 스키마 inventory에서 시딩"""
    conn = _get_public_conn()
    cur = conn.cursor()

    # ── vendor_list ──────────────────────────────────────────────
    cur.execute("""
        CREATE TABLE IF NOT EXISTS public.vendor_list (
            id   SERIAL PRIMARY KEY,
            name VARCHAR(200) NOT NULL,
            CONSTRAINT vendor_list_name_unique UNIQUE (name)
        )
    """)

    # ── equipment_list (part 포함) ────────────────────────────────
    cur.execute("""
        CREATE TABLE IF NOT EXISTS public.equipment_list (
            id   SERIAL PRIMARY KEY,
            name VARCHAR(200) NOT NULL,
            part VARCHAR(20)  NOT NULL DEFAULT ''
        )
    """)
    # 마이그레이션: part 컬럼 없으면 추가
    cur.execute("ALTER TABLE public.equipment_list ADD COLUMN IF NOT EXISTS part VARCHAR(20) NOT NULL DEFAULT ''")
    # 마이그레이션: 기존 name-only UNIQUE 제약 제거
    cur.execute("ALTER TABLE public.equipment_list DROP CONSTRAINT IF EXISTS equipment_list_name_unique")
    # 마이그레이션: (name, part) 복합 UNIQUE 추가 (이미 있으면 무시)
    cur.execute("SAVEPOINT sp_equip_uniq")
    try:
        cur.execute("ALTER TABLE public.equipment_list ADD CONSTRAINT equipment_list_name_part_unique UNIQUE (name, part)")
    except Exception:
        cur.execute("ROLLBACK TO SAVEPOINT sp_equip_uniq")
    cur.execute("RELEASE SAVEPOINT sp_equip_uniq")

    # ── 초기 시딩 ────────────────────────────────────────────────
    cur.execute("SELECT COUNT(*) FROM public.vendor_list")
    if cur.fetchone()[0] == 0:
        for schema in ALL_SCHEMAS:
            try:
                cur.execute(
                    f"INSERT INTO public.vendor_list (name) "
                    f"SELECT DISTINCT vendor FROM {schema}.inventory "
                    f"WHERE vendor IS NOT NULL AND TRIM(vendor) != '' "
                    f"ON CONFLICT DO NOTHING"
                )
            except Exception:
                pass

    cur.execute("SELECT COUNT(*) FROM public.equipment_list")
    if cur.fetchone()[0] == 0:
        for schema in ALL_SCHEMAS:
            try:
                cur.execute(
                    f"INSERT INTO public.equipment_list (name, part) "
                    f"SELECT DISTINCT equipment, part FROM {schema}.inventory "
                    f"WHERE equipment IS NOT NULL AND TRIM(equipment) != '' "
                    f"ON CONFLICT DO NOTHING"
                )
            except Exception:
                pass

    conn.commit()
    conn.close()


def get_vendor_list() -> list:
    _ensure_list_tables()
    conn = _get_public_conn()
    cur = conn.cursor()
    cur.execute("SELECT id, name FROM public.vendor_list ORDER BY name")
    rows = [dict(r) for r in cur.fetchall()]
    conn.close()
    return rows


def get_equipment_list(part: str = "") -> list:
    _ensure_list_tables()
    conn = _get_public_conn()
    cur = conn.cursor()
    if part:
        cur.execute("SELECT id, name, part FROM public.equipment_list WHERE part=%s ORDER BY name", (part,))
    else:
        cur.execute("SELECT id, name, part FROM public.equipment_list ORDER BY part, name")
    _part_map = get_part_map()
    rows = []
    for r in cur.fetchall():
        d = dict(r)
        part_code = d.get("part", "")
        part_name = _part_map.get(part_code, "")
        d["part_label"] = f"{part_code} ({part_name})" if part_name else part_code
        rows.append(d)
    conn.close()
    return rows


def create_vendor(name: str):
    _ensure_list_tables()
    conn = _get_public_conn()
    cur = conn.cursor()
    cur.execute(
        "INSERT INTO public.vendor_list (name) VALUES (%s) ON CONFLICT (name) DO NOTHING",
        (name.strip(),),
    )
    conn.commit()
    conn.close()


def update_vendor(item_id: int, name: str):
    conn = _get_public_conn()
    cur = conn.cursor()
    cur.execute("UPDATE public.vendor_list SET name=%s WHERE id=%s", (name.strip(), item_id))
    conn.commit()
    conn.close()


def create_equipment(name: str, part: str = ""):
    _ensure_list_tables()
    conn = _get_public_conn()
    cur = conn.cursor()
    cur.execute(
        "INSERT INTO public.equipment_list (name, part) VALUES (%s, %s) ON CONFLICT (name, part) DO NOTHING",
        (name.strip(), part.strip()),
    )
    conn.commit()
    conn.close()


def update_equipment(item_id: int, name: str, part: str = ""):
    conn = _get_public_conn()
    cur = conn.cursor()
    cur.execute(
        "UPDATE public.equipment_list SET name=%s, part=%s WHERE id=%s",
        (name.strip(), part.strip(), item_id),
    )
    conn.commit()
    conn.close()


def get_master_vendor_equipment_options(schema: str) -> dict:
    """업로드 미리보기용 업체/장비 드롭다운 목록 (vendor_list / equipment_list 테이블 사용)"""
    _ensure_list_tables()
    conn = _get_public_conn()
    cur = conn.cursor()
    cur.execute("SELECT name FROM public.vendor_list ORDER BY name")
    vendors = [row[0] for row in cur.fetchall()]
    cur.execute("SELECT name, part FROM public.equipment_list ORDER BY part, name")
    equipments = [{"name": row[0], "part": row[1]} for row in cur.fetchall()]
    conn.close()
    return {"vendors": vendors, "equipments": equipments}


def upload_rawdb_items_to_master(schema: str, items_data: list) -> tuple:
    """raw_db 항목을 지정 스키마의 inventory(시약 마스터)에 등록.

    items_data: list of dicts — item_id, lot_no, expiry_date, reagent_type, vendor, equipment
    반환: (success_count, error_list)
    """
    conn = psycopg.connect(
        host=PG_HOST, port=PG_PORT, dbname=PG_DBNAME,
        user=PG_USER, password=PG_PASSWORD,
        options=f"-c search_path={schema},public",
    )
    wrapped = ConnectionWrapper(conn)
    cur = wrapped.cursor()

    success = 0
    errors = []

    for d in items_data:
        raw = get_rawdb_item_by_id(d["item_id"])
        if not raw:
            errors.append(f"ID {d['item_id']}: 항목 없음")
            continue

        lot_no = (d.get("lot_no") or "").strip()
        expiry_date = (d.get("expiry_date") or "").strip() or None
        reagent_type = (d.get("reagent_type") or "").strip() or None
        vendor = (d.get("vendor") or "").strip()
        equipment = (d.get("equipment") or "").strip()
        hazardous = raw.get("hazardous") or "N"
        if hazardous not in ("Y", "N"):
            hazardous = "N"

        cur.execute(
            "SELECT id FROM inventory WHERE item_code = %s AND lot_no = %s AND disposed_at IS NULL",
            (raw["item_code"], lot_no),
        )
        if cur.fetchone():
            errors.append(f"{raw['item_code']} / {lot_no or '(공란)'}: 이미 등록된 항목")
            continue

        cur.execute(
            """
            INSERT INTO inventory (
                hazardous, hazardous_grade, part, item_code, item_name,
                lot_no, expiry_date, spec, unit, reagent_type,
                equipment, vendor, safety_stock, current_stock, required_qty
            ) VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,0,0,0)
            """,
            (
                hazardous, raw.get("hazardous_grade") or "",
                raw["part"], raw["item_code"], raw["item_name"],
                lot_no, expiry_date,
                raw.get("spec") or "", raw.get("unit") or "",
                reagent_type, equipment, vendor,
            ),
        )
        success += 1

    wrapped.commit()
    wrapped.close()
    return success, errors


def sync_rawdb_to_inventory() -> dict:
    """public.raw_db → 각 스키마 inventory 동기화.

    item_code AND part가 일치하는 행에 spec, unit, hazardous, hazardous_grade를 덮어씁니다.
    반환: {schema: updated_row_count, ...}
    """
    conn = _get_public_conn()
    cursor = conn.cursor()
    result = {}
    for schema in ALL_SCHEMAS:
        cursor.execute(
            f"""
            UPDATE {schema}.inventory AS inv
            SET spec            = r.spec,
                unit            = r.unit,
                hazardous       = r.hazardous,
                hazardous_grade = r.hazardous_grade
            FROM public.raw_db AS r
            WHERE inv.item_code = r.item_code
              AND inv.part      = r.part
            """
        )
        result[schema] = cursor.rowcount
    conn.commit()
    conn.close()
    return result
