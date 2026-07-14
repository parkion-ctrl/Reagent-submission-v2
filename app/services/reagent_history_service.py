from datetime import date
from html import escape

from app.core.db import get_connection, get_current_schema
from app.utils.constants import get_part_map, REAGENT_TYPE_MAP


Y_VALUES = {"1", "Y", "y", "YES", "Yes", "yes", "유", "사용"}
N_VALUES = {"0", "N", "n", "NO", "No", "no", "무", "미사용"}


def strip_lot_status_suffix(item_name: str) -> str:
    name = str(item_name or "").strip()
    if name.endswith(" (New)"):
        return name[:-6].strip()
    if name.endswith(" (Old)"):
        return name[:-6].strip()
    return name


def compose_item_name(base_item_name: str, lot_status: str) -> str:
    base = strip_lot_status_suffix(base_item_name)
    if lot_status == "NEW":
        return f"{base} (New)"
    if lot_status == "OLD":
        return f"{base} (Old)"
    return base


def compose_item_name_html(item_name: str, lot_status: str) -> str:
    escaped_name = escape(str(item_name or ""))
    if lot_status == "NEW":
        return f'<span style="color:#198754 !important; font-weight:600 !important;">{escaped_name}</span>'
    return escaped_name


def normalize_hazardous(value):
    hazardous_raw = str(value or "").strip()
    if hazardous_raw in Y_VALUES:
        return "Y"
    if hazardous_raw in N_VALUES:
        return "N"
    return hazardous_raw


def sync_expired_reagents():
    conn = get_connection()
    cursor = conn.cursor()
    today_text = date.today().isoformat()

    cursor.execute(
        """
        UPDATE inventory
        SET base_item_name = TRIM(
            CASE
                WHEN item_name LIKE '% (New)' THEN substr(item_name, 1, length(item_name) - 6)
                WHEN item_name LIKE '% (Old)' THEN substr(item_name, 1, length(item_name) - 6)
                ELSE item_name
            END
        )
        WHERE base_item_name IS NULL OR TRIM(base_item_name) = ''
        """
    )

    cursor.execute(
        """
        UPDATE inventory
        SET disposed_at = expiry_date
        WHERE disposed_at IS NOT NULL
          AND disposal_type = 'AUTO_EXPIRED'
          AND expiry_date IS NOT NULL
          AND TRIM(expiry_date) != ''
          AND expiry_date != '9999-12-31'
        """
    )

    cursor.execute(
        """
        UPDATE inventory
        SET disposed_at = substr(disposed_at, 1, 10)
        WHERE disposed_at IS NOT NULL
          AND (disposal_type IS NULL OR disposal_type != 'AUTO_EXPIRED')
        """
    )

    cursor.execute(
        """
        UPDATE inventory
        SET
            disposed_at = COALESCE(disposed_at, expiry_date),
            disposal_reason = CASE
                WHEN disposal_reason = '' THEN '유효기간 경과'
                ELSE disposal_reason
            END,
            disposal_type = CASE
                WHEN disposal_type = '' THEN 'AUTO_EXPIRED'
                ELSE disposal_type
            END
        WHERE disposed_at IS NULL
          AND expiry_date IS NOT NULL
          AND TRIM(expiry_date) != ''
          AND expiry_date != '9999-12-31'
          AND expiry_date < ?
        """,
        (today_text,),
    )

    cursor.execute(
        """
        WITH duplicated_groups AS (
            SELECT item_code, base_item_name
            FROM inventory
            WHERE disposed_at IS NULL
              AND base_item_name IS NOT NULL
              AND TRIM(base_item_name) != ''
              AND COALESCE(reagent_type, '') NOT IN ('4', '5')
            GROUP BY item_code, base_item_name
            HAVING COUNT(*) >= 2 AND COUNT(DISTINCT COALESCE(NULLIF(TRIM(lot_no), ''), '*')) >= 2
        )
        UPDATE inventory
        SET lot_status = '', is_new_lot = 'N'
        WHERE COALESCE(lot_status, '') != ''
          AND (item_code, base_item_name) NOT IN (
              SELECT item_code, base_item_name
              FROM duplicated_groups
          )
        """
    )

    cursor.execute(
        """
        UPDATE inventory
        SET item_name = base_item_name, is_new_lot = 'N'
        WHERE COALESCE(lot_status, '') = ''
          AND base_item_name IS NOT NULL
          AND TRIM(base_item_name) != ''
          AND item_name != base_item_name
        """
    )

    cursor.execute(
        """
        UPDATE inventory
        SET item_name = base_item_name || ' (New)', is_new_lot = 'Y'
        WHERE lot_status = 'NEW'
          AND base_item_name IS NOT NULL
          AND TRIM(base_item_name) != ''
          AND item_name != base_item_name || ' (New)'
        """
    )

    cursor.execute(
        """
        UPDATE inventory
        SET item_name = base_item_name || ' (Old)', is_new_lot = 'N'
        WHERE lot_status = 'OLD'
          AND base_item_name IS NOT NULL
          AND TRIM(base_item_name) != ''
          AND item_name != base_item_name || ' (Old)'
        """
    )

    conn.commit()
    conn.close()


def dispose_reagent(item_id: int, reason: str = "수동 폐기", disposal_type: str = "MANUAL"):
    conn = get_connection()
    cursor = conn.cursor()
    cursor.execute(
        """
        UPDATE inventory
        SET disposed_at = ?, disposal_reason = ?, disposal_type = ?
        WHERE id = ? AND disposed_at IS NULL
        """,
        (date.today().isoformat(), reason, disposal_type, item_id),
    )
    conn.commit()
    conn.close()


def get_reagent_history_filter_options():
    sync_expired_reagents()
    conn = get_connection()
    cursor = conn.cursor()

    cursor.execute(
        """
        SELECT DISTINCT reagent_type
        FROM inventory
        WHERE reagent_type IS NOT NULL
          AND TRIM(reagent_type) != ''
        ORDER BY reagent_type
        """
    )
    reagent_types = [row[0] for row in cursor.fetchall()]

    cursor.execute("SELECT DISTINCT equipment FROM inventory ORDER BY equipment")
    equipment_rows = [row[0] for row in cursor.fetchall()]

    cursor.execute("SELECT DISTINCT vendor FROM inventory ORDER BY vendor")
    vendor_rows = [row[0] for row in cursor.fetchall()]

    cursor.execute(
        """
        SELECT DISTINCT hazardous_grade FROM inventory
        ORDER BY hazardous_grade
        """
    )
    hazardous_grade_rows = [row[0] for row in cursor.fetchall()]

    conn.close()

    def _blank_opts(rows):
        has_blank = any(v is None or str(v).strip() == "" for v in rows)
        opts = []
        if has_blank:
            opts.append("__BLANK__")
        opts.extend(str(v).strip() for v in rows if v is not None and str(v).strip() != "")
        return opts

    return {
        "reagent_types": [
            {
                "value": str(v).strip(),
                "label": REAGENT_TYPE_MAP.get(str(v).strip(), str(v).strip()),
            }
            for v in reagent_types
        ],
        "equipments": [str(v).strip() for v in equipment_rows if v is not None and str(v).strip()],
        "vendors": [str(v).strip() for v in vendor_rows if v is not None and str(v).strip()],
        "hazardous_options": [{"value": "Y", "label": "Y"}, {"value": "N", "label": "N"}],
        "disposed_options": [{"value": "Y", "label": "Y"}, {"value": "N", "label": "N"}],
        "new_lot_options": [{"value": "Y", "label": "Y"}, {"value": "N", "label": "N"}],
        "hazardous_grade_options": _blank_opts(hazardous_grade_rows),
    }


def get_reagent_history_items(
    part: str = "",
    q: str = "",
    reagent_type: str = "",
    equipment: str = "",
    vendor: str = "",
    hazardous: str = "",
    hazardous_grade: str = "",
    is_new_lot: str = "",
    disposed: str = "",
    lot_status: str = "",
    sort: str = "",
    order: str = "",
):
    sync_expired_reagents()

    conn = get_connection()
    cursor = conn.cursor()

    query = """
        SELECT
            id, hazardous, hazardous_grade, is_new_lot, part, item_code, item_name, lot_no,
            expiry_date, disposed_at, opened_at, parallel_at,
            base_item_name, lot_status,
            spec, unit, reagent_type, equipment, vendor, registered_at
        FROM inventory
        WHERE 1=1
    """
    params = []

    if part:
        query += " AND part = ?"
        params.append(part)
    if q:
        query += " AND (item_code ILIKE ? OR item_name ILIKE ? OR lot_no ILIKE ?)"
        params.extend([f"%{q}%", f"%{q}%", f"%{q}%"])
    if reagent_type:
        query += " AND reagent_type = ?"
        params.append(reagent_type)
    if equipment:
        query += " AND equipment = ?"
        params.append(equipment)
    if vendor:
        query += " AND vendor = ?"
        params.append(vendor)
    if hazardous == "Y":
        query += " AND hazardous IN ('1', 'Y', 'y', 'Yes', 'yes', '유', '사용')"
    elif hazardous == "N":
        query += " AND hazardous IN ('0', 'N', 'n', 'No', 'no', '무', '미사용')"
    if hazardous_grade:
        if hazardous_grade == "__BLANK__":
            query += " AND (hazardous_grade IS NULL OR TRIM(hazardous_grade) = '')"
        else:
            query += " AND hazardous_grade = ?"
            params.append(hazardous_grade)
    if is_new_lot == "Y":
        query += " AND is_new_lot = 'Y'"
    elif is_new_lot == "N":
        query += " AND (is_new_lot IS NULL OR is_new_lot != 'Y')"
    if disposed == "Y":
        query += " AND disposed_at IS NOT NULL"
    elif disposed == "N":
        query += " AND disposed_at IS NULL"
    if lot_status == "NEW":
        query += " AND lot_status = 'NEW'"
    elif lot_status == "OLD":
        query += " AND lot_status = 'OLD'"

    allowed_sort = [
        "item_code",
        "item_name",
        "lot_no",
        "expiry_date",
        "disposed_at",
        "opened_at",
        "parallel_at",
        "registered_at",
        "reagent_type",
        "equipment",
        "vendor",
    ]
    if sort in allowed_sort:
        order_sql = "DESC" if order == "desc" else "ASC"
        query += f" ORDER BY {sort} {order_sql}"
    else:
        query += " ORDER BY CASE WHEN disposed_at IS NULL THEN 0 ELSE 1 END ASC, item_code ASC, lot_no ASC"

    cursor.execute(query, params)
    rows = cursor.fetchall()
    conn.close()

    items = []
    for row in rows:
        row = dict(row)
        part_code = str(row.get("part", "")).strip()
        part_name = get_part_map(get_current_schema()).get(part_code.upper(), "")
        row["part_label"] = f"{part_code} ({part_name})" if part_name else part_code
        row["reagent_type"] = REAGENT_TYPE_MAP.get(
            str(row.get("reagent_type", "")).strip(),
            str(row.get("reagent_type", "")).strip(),
        )
        row["hazardous"] = normalize_hazardous(row.get("hazardous"))
        row["hazardous_grade"] = str(row.get("hazardous_grade") or "").strip()
        is_new_lot_raw = str(row.get("is_new_lot") or "").strip()
        row["is_new_lot"] = "Y" if is_new_lot_raw == "Y" else "N"
        row["disposed"] = "Y" if row.get("disposed_at") else "N"
        base_item_name = row.get("base_item_name") or row.get("item_name") or ""
        row["item_name"] = compose_item_name(base_item_name, row.get("lot_status"))
        row["item_name_html"] = compose_item_name_html(row["item_name"], row.get("lot_status"))
        row["item_name_class"] = "lot-new-name" if row.get("lot_status") == "NEW" else ""
        row["expiry_date"] = format_date_text(row.get("expiry_date"))
        row["disposed_at"] = format_date_text(row.get("disposed_at"))
        row["opened_at"] = format_date_text(row.get("opened_at"))
        row["parallel_at"] = format_date_text(row.get("parallel_at"))
        row["registered_at"] = format_date_text(row.get("registered_at"))
        items.append(row)

    return items


def format_date_text(value):
    raw = str(value or "").strip()
    if not raw or raw == "9999-12-31":
        return ""
    return raw[:10]


def update_opened_at(item_id: int, opened_at: str):
    date_text = str(opened_at or "").strip()[:10]
    if not date_text:
        return False, "일시는 필수입니다."

    conn = get_connection()
    cursor = conn.cursor()

    cursor.execute("SELECT item_code, base_item_name, lot_status FROM inventory WHERE id = ?", (item_id,))
    row = cursor.fetchone()
    if not row:
        conn.close()
        return False, "대상 시약을 찾을 수 없습니다."

    cursor.execute("UPDATE inventory SET opened_at = ? WHERE id = ?", (date_text, item_id))

    # opened_at 입력 시 New Lot 해제 (New/Old 그룹 전체)
    lot_status = str(row["lot_status"] or "").strip()
    item_code = row["item_code"]
    base_item_name = row["base_item_name"]
    if lot_status in ("NEW", "OLD") and item_code and base_item_name:
        cursor.execute(
            """
            UPDATE inventory
            SET lot_status = '', is_new_lot = 'N', item_name = base_item_name
            WHERE item_code = ? AND base_item_name = ?
              AND COALESCE(lot_status, '') != ''
            """,
            (item_code, base_item_name),
        )

    conn.commit()
    conn.close()
    return True, "등록했습니다."


def update_parallel_at(item_id: int, parallel_at: str):
    date_text = str(parallel_at or "").strip()[:10]
    if not date_text:
        return False, "일시는 필수입니다."

    conn = get_connection()
    cursor = conn.cursor()

    cursor.execute("SELECT item_code, base_item_name, lot_status FROM inventory WHERE id = ?", (item_id,))
    row = cursor.fetchone()
    if not row:
        conn.close()
        return False, "대상 시약을 찾을 수 없습니다."

    cursor.execute("UPDATE inventory SET parallel_at = ? WHERE id = ?", (date_text, item_id))

    # parallel 일시 입력 시 New Lot 해제 (New/Old 그룹 전체)
    lot_status = str(row["lot_status"] or "").strip()
    item_code = row["item_code"]
    base_item_name = row["base_item_name"]
    if lot_status in ("NEW", "OLD") and item_code and base_item_name:
        cursor.execute(
            """
            UPDATE inventory
            SET lot_status = '', is_new_lot = 'N', item_name = base_item_name
            WHERE item_code = ? AND base_item_name = ?
              AND COALESCE(lot_status, '') != ''
            """,
            (item_code, base_item_name),
        )

    conn.commit()
    conn.close()
    return True, "등록했습니다."


def update_reagent_date(item_id: int, column_name: str, value: str):
    date_text = str(value or "").strip()[:10]
    if not date_text:
        return False, "일시는 필수입니다."

    conn = get_connection()
    cursor = conn.cursor()
    cursor.execute(
        f"UPDATE inventory SET {column_name} = ? WHERE id = ?",
        (date_text, item_id),
    )
    conn.commit()
    updated = cursor.rowcount > 0
    conn.close()

    if not updated:
        return False, "대상 시약을 찾을 수 없습니다."
    return True, "등록했습니다."


def get_old_new_lot_items(part: str = "", only_new: bool = False):
    sync_expired_reagents()

    if not part:
        return []

    conn = get_connection()
    cursor = conn.cursor()
    cursor.execute(
        """
        WITH duplicated_groups AS (
            SELECT item_code, base_item_name
            FROM inventory
            WHERE part = ?
              AND disposed_at IS NULL
              AND base_item_name IS NOT NULL
              AND TRIM(base_item_name) != ''
              AND COALESCE(reagent_type, '') NOT IN ('4', '5')
            GROUP BY item_code, base_item_name
            HAVING COUNT(*) >= 2 AND COUNT(DISTINCT COALESCE(NULLIF(TRIM(lot_no), ''), '*')) >= 2
        )
        SELECT
            i.id,
            i.part,
            i.item_code,
            i.item_name,
            i.base_item_name,
            i.lot_no,
            i.expiry_date,
            i.disposed_at,
            i.lot_status
        FROM inventory i
        INNER JOIN duplicated_groups g
            ON g.item_code = i.item_code
           AND g.base_item_name = i.base_item_name
        WHERE i.part = ?
          AND i.disposed_at IS NULL
        """
        + (" AND i.lot_status = 'NEW'" if only_new else "")
        + """
        ORDER BY i.base_item_name ASC, i.item_code ASC, i.expiry_date ASC, i.lot_no ASC
        """,
        (part, part),
    )
    rows = cursor.fetchall()
    conn.close()

    items = []
    for row in rows:
        row = dict(row)
        base_item_name = row.get("base_item_name") or row.get("item_name") or ""
        row["base_item_name"] = base_item_name
        row["item_name"] = compose_item_name(base_item_name, row.get("lot_status"))
        row["item_name_html"] = compose_item_name_html(row["item_name"], row.get("lot_status"))
        row["item_name_class"] = "lot-new-name" if row.get("lot_status") == "NEW" else ""
        row["group_key"] = f"{row.get('item_code', '')}||{base_item_name}"
        row["part_label"] = f"{row.get('part', '')} ({get_part_map(get_current_schema()).get(str(row.get('part', '')).upper(), '')})".strip()
        row["disposed"] = "Y" if row.get("disposed_at") else "N"
        row["expiry_date"] = format_date_text(row.get("expiry_date"))
        items.append(row)
    return items


def save_old_new_lot_selection(part: str, visible_item_ids: list[int], new_lot_item_ids: list[int]):
    sync_expired_reagents()

    conn = get_connection()
    cursor = conn.cursor()

    if not visible_item_ids:
        conn.close()
        return False, "저장할 대상이 없습니다."

    placeholders = ",".join("?" for _ in visible_item_ids)
    cursor.execute(
        f"""
        SELECT id, item_code, base_item_name, lot_status
        FROM inventory
        WHERE part = ?
          AND id IN ({placeholders})
        ORDER BY item_code, base_item_name, id
        """,
        [part, *visible_item_ids],
    )
    rows = [dict(row) for row in cursor.fetchall()]
    if not rows:
        conn.close()
        return False, "저장할 대상이 없습니다."

    grouped = {}
    for row in rows:
        group_key = (row["item_code"], row["base_item_name"])
        grouped.setdefault(group_key, []).append(row)

    selected_set = {int(item_id) for item_id in new_lot_item_ids}
    for group_key, group_rows in grouped.items():
        selected_in_group = [row for row in group_rows if row["id"] in selected_set]
        if len(selected_in_group) > 1:
            conn.close()
            return False, "동일 품목명 그룹에서는 New lot를 하나만 선택할 수 있습니다."

        if len(selected_in_group) == 1:
            selected_id = selected_in_group[0]["id"]
            for row in group_rows:
                if row["id"] == selected_id:
                    cursor.execute(
                        "UPDATE inventory SET lot_status = 'NEW', item_name = base_item_name || ' (New)', is_new_lot = 'Y' WHERE id = ?",
                        (row["id"],),
                    )
                else:
                    cursor.execute(
                        "UPDATE inventory SET lot_status = 'OLD', item_name = base_item_name || ' (Old)', is_new_lot = 'N' WHERE id = ?",
                        (row["id"],),
                    )
        else:
            for row in group_rows:
                cursor.execute(
                    "UPDATE inventory SET lot_status = '', item_name = base_item_name, is_new_lot = 'N' WHERE id = ?",
                    (row["id"],),
                )

    conn.commit()
    conn.close()
    sync_expired_reagents()
    return True, "Old/New lot 설정을 저장했습니다."
