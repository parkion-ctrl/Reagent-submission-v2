from app.core.db import get_connection


def _ensure_tables():
    conn = get_connection()
    cursor = conn.cursor()
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS inbound_preset (
            id SERIAL PRIMARY KEY,
            name VARCHAR(100) NOT NULL,
            part VARCHAR(20) NOT NULL,
            created_at TIMESTAMP DEFAULT NOW()
        )
    """)
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS inbound_preset_item (
            id SERIAL PRIMARY KEY,
            preset_id INTEGER REFERENCES inbound_preset(id) ON DELETE CASCADE,
            item_code VARCHAR(50) NOT NULL
        )
    """)
    conn.commit()
    conn.close()


def get_presets(part: str = "") -> list:
    _ensure_tables()
    conn = get_connection()
    cursor = conn.cursor()
    if part:
        cursor.execute("""
            SELECT p.id, p.name, p.part, p.created_at, COUNT(pi.id) AS item_count
            FROM inbound_preset p
            LEFT JOIN inbound_preset_item pi ON pi.preset_id = p.id
            WHERE p.part = ?
            GROUP BY p.id ORDER BY p.name
        """, (part,))
    else:
        cursor.execute("""
            SELECT p.id, p.name, p.part, p.created_at, COUNT(pi.id) AS item_count
            FROM inbound_preset p
            LEFT JOIN inbound_preset_item pi ON pi.preset_id = p.id
            GROUP BY p.id ORDER BY p.part, p.name
        """)
    rows = cursor.fetchall()
    conn.close()
    return [dict(row) for row in rows]


def get_preset(preset_id: int) -> dict:
    _ensure_tables()
    conn = get_connection()
    cursor = conn.cursor()
    cursor.execute("SELECT * FROM inbound_preset WHERE id = ?", (preset_id,))
    row = cursor.fetchone()
    if not row:
        conn.close()
        return None
    preset = dict(row)
    cursor.execute("""
        SELECT pi.item_code,
               MIN(i.item_name) AS item_name
        FROM inbound_preset_item pi
        LEFT JOIN inventory i ON i.item_code = pi.item_code AND i.disposed_at IS NULL
        WHERE pi.preset_id = ?
        GROUP BY pi.item_code
        ORDER BY pi.item_code
    """, (preset_id,))
    preset["items"] = [dict(r) for r in cursor.fetchall()]
    conn.close()
    return preset


def get_part_item_codes(part: str) -> list:
    """파트의 활성 품목코드 목록 (중복 제거, 품목명 포함)"""
    _ensure_tables()
    conn = get_connection()
    cursor = conn.cursor()
    cursor.execute("""
        SELECT DISTINCT ON (item_code) item_code, item_name
        FROM inventory
        WHERE part = ? AND disposed_at IS NULL
        ORDER BY item_code, item_name
    """, (part,))
    rows = cursor.fetchall()
    conn.close()
    return [dict(r) for r in rows]


def create_preset(name: str, part: str, item_codes: list) -> int:
    _ensure_tables()
    conn = get_connection()
    cursor = conn.cursor()
    cursor.execute(
        "INSERT INTO inbound_preset (name, part) VALUES (?, ?) RETURNING id",
        (name, part)
    )
    preset_id = cursor.fetchone()[0]
    for code in item_codes:
        cursor.execute(
            "INSERT INTO inbound_preset_item (preset_id, item_code) VALUES (?, ?)",
            (preset_id, code)
        )
    conn.commit()
    conn.close()
    return preset_id


def update_preset(preset_id: int, name: str, item_codes: list):
    _ensure_tables()
    conn = get_connection()
    cursor = conn.cursor()
    cursor.execute("UPDATE inbound_preset SET name = ? WHERE id = ?", (name, preset_id))
    cursor.execute("DELETE FROM inbound_preset_item WHERE preset_id = ?", (preset_id,))
    for code in item_codes:
        cursor.execute(
            "INSERT INTO inbound_preset_item (preset_id, item_code) VALUES (?, ?)",
            (preset_id, code)
        )
    conn.commit()
    conn.close()


def delete_preset(preset_id: int):
    _ensure_tables()
    conn = get_connection()
    cursor = conn.cursor()
    cursor.execute("DELETE FROM inbound_preset WHERE id = ?", (preset_id,))
    conn.commit()
    conn.close()


def get_preset_cart_items(preset_id: int) -> list:
    """약속 적용 시 카트에 넣을 항목 — 품목코드별 유효기간 가장 긴 lot 1개씩"""
    _ensure_tables()
    conn = get_connection()
    cursor = conn.cursor()
    cursor.execute("""
        SELECT DISTINCT ON (i.item_code)
            i.id, i.item_code, i.item_name, i.lot_no, i.expiry_date,
            i.reagent_type, i.vendor, i.part, i.unit, i.spec
        FROM inbound_preset_item pi
        JOIN inventory i ON i.item_code = pi.item_code
        WHERE pi.preset_id = ?
          AND i.disposed_at IS NULL
        ORDER BY i.item_code, i.expiry_date DESC NULLS LAST, i.id DESC
    """, (preset_id,))
    rows = cursor.fetchall()
    conn.close()
    return [dict(row) for row in rows]
