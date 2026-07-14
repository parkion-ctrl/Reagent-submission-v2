from datetime import date

from app.core.db import get_connection, get_current_schema
from app.services.reagent_history_service import sync_expired_reagents
from app.utils.constants import get_part_map, REAGENT_TYPE_MAP


Y_VALUES = {"1", "Y", "y", "YES", "Yes", "yes", "예", "사용"}
N_VALUES = {"0", "N", "n", "NO", "No", "no", "아니오", "무"}


def _build_options_with_blank(rows):
    """None/빈값 → '__BLANK__' 옵션으로, 나머지는 문자열 정렬해서 반환."""
    has_blank = any(v is None or str(v).strip() == "" for v in rows)
    opts = []
    if has_blank:
        opts.append("__BLANK__")
    opts.extend(str(v).strip() for v in rows if v is not None and str(v).strip() != "")
    return opts


def get_inventory_items(
    part: str = "",
    q: str = "",
    reagent_type: str = "",
    equipment: str = "",
    vendor: str = "",
    hazardous: str = "",
    hazardous_grade: str = "",
    is_new_lot: str = "",
    expiry_filter: str = "",
    sort: str = "",
    order: str = "",
):
    sync_expired_reagents()

    conn = get_connection()
    cursor = conn.cursor()

    query = "SELECT * FROM inventory WHERE disposed_at IS NULL"
    params = []

    if part:
        query += " AND part = ?"
        params.append(part)
    if q:
        query += " AND (item_name ILIKE ? OR item_code ILIKE ? OR lot_no ILIKE ?)"
        params.extend([f"%{q}%", f"%{q}%", f"%{q}%"])
    if reagent_type:
        query += " AND reagent_type = ?"
        params.append(reagent_type)
    if equipment:
        if equipment == "__BLANK__":
            query += " AND (equipment IS NULL OR TRIM(equipment) = '')"
        else:
            query += " AND equipment = ?"
            params.append(equipment)
    if vendor:
        if vendor == "__BLANK__":
            query += " AND (vendor IS NULL OR TRIM(vendor) = '')"
        else:
            query += " AND vendor = ?"
            params.append(vendor)
    if hazardous == "Y":
        query += " AND hazardous IN ('1', 'Y', 'y', 'Yes', 'yes', '예', '사용')"
    elif hazardous == "N":
        query += " AND hazardous IN ('0', 'N', 'n', 'No', 'no', '아니오', '무')"
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
    if expiry_filter == "1w":
        query += " AND expiry_date <= (CURRENT_DATE + INTERVAL '7 days')::date::text"
    elif expiry_filter == "2w":
        query += " AND expiry_date <= (CURRENT_DATE + INTERVAL '14 days')::date::text"
    elif expiry_filter == "4w":
        query += " AND expiry_date <= (CURRENT_DATE + INTERVAL '28 days')::date::text"

    allowed_sort = [
        "item_code", "item_name", "expiry_date",
        "current_stock", "required_qty", "safety_stock",
        "hazardous", "reagent_type", "equipment", "vendor",
    ]
    if sort in allowed_sort:
        order_sql = "DESC" if order == "desc" else "ASC"
        query += f" ORDER BY {sort} {order_sql}"
    else:
        query += " ORDER BY item_code ASC, lot_no ASC, expiry_date ASC"

    cursor.execute(query, params)
    rows = cursor.fetchall()
    conn.close()

    items = []
    for row in rows:
        row = dict(row)
        required_qty = max(row["safety_stock"] - row["current_stock"], 0)
        status = "정상"
        if row["current_stock"] <= row["safety_stock"]:
            status = "부족"

        part_code = str(row.get("part", "")).strip()
        part_name = get_part_map(get_current_schema()).get(part_code, "")
        raw_date = str(row.get("expiry_date") or "").strip()
        expiry_text = ""
        expiry_class = ""

        if raw_date and raw_date not in ("9999-12-31", "None"):
            expiry_text = raw_date[:10]
            expiry_date = date.fromisoformat(raw_date[:10])
            days_left = (expiry_date - date.today()).days
            if days_left <= 7:
                expiry_class = "expiry-red"
            elif days_left <= 14:
                expiry_class = "expiry-yellow"
            elif days_left <= 28:
                expiry_class = "expiry-green"

        reagent_type_code = str(row.get("reagent_type", "")).strip()
        reagent_type_label = REAGENT_TYPE_MAP.get(reagent_type_code, reagent_type_code)

        hazardous_raw = str(row.get("hazardous", "")).strip()
        if hazardous_raw in Y_VALUES:
            hazardous_label = "Y"
        elif hazardous_raw in N_VALUES:
            hazardous_label = "N"
        else:
            hazardous_label = hazardous_raw

        is_new_lot_raw = str(row.get("is_new_lot", "N") or "N").strip()
        is_new_lot_label = "Y" if is_new_lot_raw == "Y" else "N"

        items.append(
            {
                "id": row["id"],
                "is_new_lot": is_new_lot_label,
                "hazardous": hazardous_label,
                "hazardous_grade": str(row.get("hazardous_grade") or "").strip(),
                "part": part_code,
                "part_label": f"{part_code} ({part_name})" if part_name else part_code,
                "item_code": row["item_code"],
                "item_name": row["item_name"],
                "lot_no": row["lot_no"],
                "expiry_date": expiry_text,
                "spec": row["spec"],
                "unit": row["unit"],
                "reagent_type": reagent_type_label,
                "equipment": row.get("equipment", ""),
                "vendor": row.get("vendor", ""),
                "current_stock": row["current_stock"],
                "safety_stock": row["safety_stock"],
                "required_qty": required_qty,
                "expiry_class": expiry_class,
                "status": status,
            }
        )

    return items


def get_inventory_items_by_code(
    part: str = "",
    q: str = "",
    reagent_type: str = "",
    equipment: str = "",
    vendor: str = "",
    hazardous: str = "",
    hazardous_grade: str = "",
    sort: str = "",
    order: str = "",
) -> list:
    sync_expired_reagents()
    conn = get_connection()
    cursor = conn.cursor()

    query = """
        SELECT
            item_code,
            MIN(REPLACE(item_name, ' (New)', '')) AS item_name,
            MAX(part) AS part,
            MAX(reagent_type) AS reagent_type,
            MAX(equipment) AS equipment,
            MAX(vendor) AS vendor,
            MAX(spec) AS spec,
            MAX(unit) AS unit,
            MAX(hazardous) AS hazardous,
            MAX(hazardous_grade) AS hazardous_grade,
            SUM(current_stock) AS current_stock,
            MAX(safety_stock) AS safety_stock
        FROM inventory
        WHERE disposed_at IS NULL
    """
    params = []

    if part:
        query += " AND part = ?"
        params.append(part)
    if q:
        query += " AND (item_name ILIKE ? OR item_code ILIKE ?)"
        params.extend([f"%{q}%", f"%{q}%"])
    if reagent_type:
        query += " AND reagent_type = ?"
        params.append(reagent_type)
    if equipment:
        if equipment == "__BLANK__":
            query += " AND (equipment IS NULL OR TRIM(equipment) = '')"
        else:
            query += " AND equipment = ?"
            params.append(equipment)
    if vendor:
        if vendor == "__BLANK__":
            query += " AND (vendor IS NULL OR TRIM(vendor) = '')"
        else:
            query += " AND vendor = ?"
            params.append(vendor)
    if hazardous == "Y":
        query += " AND hazardous IN ('1', 'Y', 'y', 'Yes', 'yes', '예', '사용')"
    elif hazardous == "N":
        query += " AND hazardous IN ('0', 'N', 'n', 'No', 'no', '아니오', '무')"
    if hazardous_grade:
        if hazardous_grade == "__BLANK__":
            query += " AND (hazardous_grade IS NULL OR TRIM(hazardous_grade) = '')"
        else:
            query += " AND hazardous_grade = ?"
            params.append(hazardous_grade)

    query += " GROUP BY item_code"

    allowed_sort = ["item_code", "item_name", "current_stock", "safety_stock"]
    if sort in allowed_sort:
        query += f" ORDER BY {sort} {'DESC' if order == 'desc' else 'ASC'}"
    else:
        query += " ORDER BY item_code ASC"

    cursor.execute(query, params)
    rows = cursor.fetchall()
    conn.close()

    items = []
    for row in rows:
        row = dict(row)
        current_stock = row["current_stock"] or 0
        safety_stock = row["safety_stock"] or 0
        required_qty = max(safety_stock - current_stock, 0)
        part_code = str(row.get("part", "")).strip()
        part_name = get_part_map(get_current_schema()).get(part_code, "")
        reagent_type_code = str(row.get("reagent_type", "")).strip()
        hazardous_raw = str(row.get("hazardous", "")).strip()
        if hazardous_raw in Y_VALUES:
            hazardous_label = "Y"
        elif hazardous_raw in N_VALUES:
            hazardous_label = "N"
        else:
            hazardous_label = hazardous_raw
        items.append({
            "item_code": row["item_code"],
            "item_name": row["item_name"],
            "part": part_code,
            "part_label": f"{part_code} ({part_name})" if part_name else part_code,
            "reagent_type": REAGENT_TYPE_MAP.get(reagent_type_code, reagent_type_code),
            "equipment": row.get("equipment") or "",
            "vendor": row.get("vendor") or "",
            "spec": row.get("spec") or "",
            "unit": row.get("unit") or "",
            "hazardous": hazardous_label,
            "hazardous_grade": str(row.get("hazardous_grade") or "").strip(),
            "current_stock": current_stock,
            "safety_stock": safety_stock,
            "required_qty": required_qty,
            "status": "부족" if current_stock <= safety_stock else "정상",
        })
    return items


def get_disposed_items(part: str = "", q: str = "") -> list:
    conn = get_connection()
    cursor = conn.cursor()
    query = "SELECT * FROM inventory WHERE disposed_at IS NOT NULL"
    params = []
    if part:
        query += " AND part = ?"
        params.append(part)
    if q:
        query += " AND (item_name ILIKE ? OR item_code ILIKE ? OR lot_no ILIKE ?)"
        params.extend([f"%{q}%", f"%{q}%", f"%{q}%"])
    query += " ORDER BY disposed_at DESC, item_code ASC"
    cursor.execute(query, params)
    rows = cursor.fetchall()
    conn.close()

    items = []
    for row in rows:
        row = dict(row)
        part_code = str(row.get("part", "")).strip()
        part_name = get_part_map(get_current_schema()).get(part_code, "")
        reagent_type_code = str(row.get("reagent_type", "")).strip()
        reagent_type_label = REAGENT_TYPE_MAP.get(reagent_type_code, reagent_type_code)
        expiry_raw = str(row.get("expiry_date") or "").strip()
        expiry_text = expiry_raw[:10] if expiry_raw and expiry_raw not in ("9999-12-31", "None") else ""
        disposed_at_raw = str(row.get("disposed_at") or "").strip()
        disposed_at_text = disposed_at_raw[:10] if disposed_at_raw else ""
        items.append({
            "id": row["id"],
            "part": part_code,
            "part_label": f"{part_code} ({part_name})" if part_name else part_code,
            "item_code": row["item_code"],
            "item_name": row["item_name"],
            "lot_no": row["lot_no"],
            "expiry_date": expiry_text,
            "spec": row.get("spec") or "",
            "unit": row.get("unit") or "",
            "reagent_type": reagent_type_label,
            "vendor": row.get("vendor") or "",
            "current_stock": row.get("current_stock") or 0,
            "safety_stock": row.get("safety_stock") or 0,
            "disposed_at": disposed_at_text,
            "disposal_reason": row.get("disposal_reason") or "",
        })
    return items


def cancel_dispose(item_id: int):
    conn = get_connection()
    cursor = conn.cursor()
    cursor.execute(
        "UPDATE inventory SET disposed_at = NULL, disposal_reason = NULL, disposal_type = NULL, current_stock = 0 WHERE id = ?",
        (item_id,),
    )
    conn.commit()
    conn.close()


def get_part_equipment_options(part: str = "") -> list:
    """파트 기준 장비 목록 반환 — 장비 필터가 걸려있어도 해당 파트 전체 목록 반환."""
    conn = get_connection()
    cursor = conn.cursor()
    part_cond = " AND part = ?" if part else ""
    cursor.execute(
        f"SELECT DISTINCT equipment FROM inventory WHERE disposed_at IS NULL"
        f" AND equipment IS NOT NULL AND TRIM(equipment) != '' {part_cond} ORDER BY equipment",
        (part,) if part else (),
    )
    result = [row[0] for row in cursor.fetchall()]
    conn.close()
    return result


def get_all_vendor_options() -> list:
    """업체 전체 목록 반환 — 파트/업체 필터 무관하게 항상 전체 업체 표시."""
    conn = get_connection()
    cursor = conn.cursor()
    cursor.execute(
        "SELECT DISTINCT vendor FROM inventory WHERE disposed_at IS NULL"
        " AND vendor IS NOT NULL AND TRIM(vendor) != '' ORDER BY vendor"
    )
    result = [row[0] for row in cursor.fetchall()]
    conn.close()
    return result


def get_inventory_filter_options():
    sync_expired_reagents()

    conn = get_connection()
    cursor = conn.cursor()

    cursor.execute(
        """
        SELECT DISTINCT reagent_type
        FROM inventory
        WHERE disposed_at IS NULL
          AND reagent_type IS NOT NULL
          AND reagent_type != ''
        ORDER BY reagent_type
        """
    )
    reagent_types = [row[0] for row in cursor.fetchall()]

    cursor.execute("SELECT DISTINCT equipment FROM inventory WHERE disposed_at IS NULL ORDER BY equipment")
    equipment_rows = [row[0] for row in cursor.fetchall()]

    cursor.execute("SELECT DISTINCT vendor FROM inventory WHERE disposed_at IS NULL ORDER BY vendor")
    vendor_rows = [row[0] for row in cursor.fetchall()]

    cursor.execute(
        """
        SELECT DISTINCT hazardous_grade FROM inventory
        WHERE disposed_at IS NULL
        ORDER BY hazardous_grade
        """
    )
    hazardous_grade_rows = [row[0] for row in cursor.fetchall()]

    conn.close()

    equipments = []
    if any(v is None or str(v).strip() == "" for v in equipment_rows):
        equipments.append("__BLANK__")
    equipments.extend(str(v).strip() for v in equipment_rows if v is not None and str(v).strip() != "")

    vendors = []
    if any(v is None or str(v).strip() == "" for v in vendor_rows):
        vendors.append("__BLANK__")
    vendors.extend(str(v).strip() for v in vendor_rows if v is not None and str(v).strip() != "")

    return {
        "reagent_types": [
            {
                "value": str(v).strip(),
                "label": REAGENT_TYPE_MAP.get(str(v).strip(), str(v).strip()),
            }
            for v in reagent_types
        ],
        "equipments": equipments,
        "vendors": vendors,
        "hazardous_options": [{"value": "Y", "label": "Y"}, {"value": "N", "label": "N"}],
        "new_lot_options": [{"value": "Y", "label": "Y"}, {"value": "N", "label": "N"}],
        "hazardous_grade_options": _build_options_with_blank(hazardous_grade_rows),
    }
