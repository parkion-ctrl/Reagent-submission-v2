from datetime import datetime

from app.core.db import get_connection, get_current_schema
from app.services.reagent_history_service import sync_expired_reagents
from app.utils.constants import get_part_map, REAGENT_TYPE_MAP
from app.services.rawdb_service import sync_master_update_to_rawdb


Y_VALUES = {"1", "Y", "y", "YES", "Yes", "yes", "예", "사용"}
N_VALUES = {"0", "N", "n", "NO", "No", "no", "아니오", "무"}


def get_master_items(
    part: str = "",
    q: str = "",
    reagent_type: str = "",
    equipment: str = "",
    vendor: str = "",
    hazardous: str = "",
    hazardous_grade: str = "",
    is_new_lot: str = "",
    sort: str = "",
    order: str = "",
):
    sync_expired_reagents()

    conn = get_connection()
    cursor = conn.cursor()

    schema = get_current_schema()
    if schema == "path":
        query = """
            SELECT
                i.id, i.is_new_lot, i.hazardous, i.hazardous_grade, i.part, i.item_code, i.item_name, i.lot_no,
                i.expiry_date, i.spec, i.unit, i.reagent_type, i.equipment,
                i.vendor, i.safety_stock, i.current_stock, i.required_qty, i.registered_at,
                r.cas_no
            FROM inventory i
            LEFT JOIN public.raw_db r ON r.item_code = i.item_code AND r.schema_name = 'path'
            WHERE i.disposed_at IS NULL
        """
    else:
        query = """
            SELECT
                id, is_new_lot, hazardous, hazardous_grade, part, item_code, item_name, lot_no,
                expiry_date, spec, unit, reagent_type, equipment,
                vendor, safety_stock, current_stock, required_qty, registered_at,
                NULL AS cas_no
            FROM inventory
            WHERE disposed_at IS NULL
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

    allowed_sort = ["item_code", "item_name", "expiry_date", "safety_stock", "current_stock", "registered_at"]
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
        expiry_raw = str(row.get("expiry_date") or "").strip()
        row["expiry_date"] = "" if expiry_raw in ("9999-12-31", "None") else (expiry_raw[:10] if expiry_raw else "")

        part_code = str(row.get("part", "")).strip()
        part_name = get_part_map(get_current_schema()).get(part_code.upper(), "")
        row["part"] = part_code
        row["part_label"] = f"{part_code} ({part_name})" if part_name else part_code

        reagent_type_code = str(row.get("reagent_type", "")).strip()
        row["reagent_type"] = REAGENT_TYPE_MAP.get(reagent_type_code, reagent_type_code)

        hazardous_raw = str(row.get("hazardous", "")).strip()
        if hazardous_raw in Y_VALUES:
            row["hazardous"] = "Y"
        elif hazardous_raw in N_VALUES:
            row["hazardous"] = "N"
        else:
            row["hazardous"] = hazardous_raw

        is_new_lot_raw = str(row.get("is_new_lot", "N") or "N").strip()
        row["is_new_lot"] = "Y" if is_new_lot_raw == "Y" else "N"

        raw_reg = str(row.get("registered_at", "") or "").strip()
        row["registered_at"] = raw_reg[:10] if raw_reg else ""

        row["hazardous_grade"] = str(row.get("hazardous_grade") or "").strip()

        items.append(row)

    return items


def normalize_reagent_type(value):
    v = normalize_text(value).strip().upper()
    return v if v in {"1", "2", "3", "4", "5"} else value


def normalize_part_strict(value):
    part = normalize_text(value).upper()
    part_map = get_part_map(get_current_schema())
    if part not in part_map:
        valid = ", ".join(f"{code} ({name})" for code, name in part_map.items())
        raise ValueError(f"파트 코드가 올바르지 않습니다. 허용 값: {valid}")
    return part


def normalize_hazardous_strict(value):
    hazardous = normalize_text(value).upper()
    if hazardous not in {"Y", "N"}:
        raise ValueError("hazardous는 Y 또는 N만 입력할 수 있습니다.")
    return hazardous


def normalize_reagent_type_strict(value):
    normalized = normalize_reagent_type(value)
    normalized_text = normalize_text(normalized).strip()
    if normalized_text not in REAGENT_TYPE_MAP:
        raise ValueError("reagent_type은 등록된 시약 구분만 입력할 수 있습니다.")
    return normalized_text


def create_master_item(
    hazardous: str,
    part: str,
    item_code: str,
    item_name: str,
    lot_no: str,
    expiry_date: str,
    spec: str,
    unit: str,
    reagent_type: str,
    equipment: str,
    vendor: str,
    safety_stock: int,
    hazardous_grade: str = "",
    cas_no: str = "",
):
    hazardous = normalize_hazardous_strict(hazardous)
    part = normalize_part_strict(part)
    reagent_type = normalize_reagent_type_strict(reagent_type)
    expiry_date = normalize_date(expiry_date)

    conn = get_connection()
    cursor = conn.cursor()
    cursor.execute(
        """
        SELECT id
        FROM inventory
        WHERE item_code = ? AND lot_no = ? AND disposed_at IS NULL
        """,
        (item_code, lot_no),
    )

    if cursor.fetchone():
        conn.close()
        return False, "동일한 품목코드 + Lot No 조합이 이미 등록되어 있습니다."

    current_stock = 0
    required_qty = max(safety_stock - current_stock, 0)

    cursor.execute(
        """
        INSERT INTO inventory (
            hazardous, hazardous_grade, part, item_code, item_name, lot_no,
            expiry_date, spec, unit, reagent_type, equipment,
            vendor, safety_stock, current_stock, required_qty, registered_at
        )
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """,
        (
            hazardous, hazardous_grade, part, item_code, item_name, lot_no,
            expiry_date, spec, unit, reagent_type, equipment,
            vendor, safety_stock, current_stock, required_qty,
            datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
        ),
    )

    conn.commit()

    if get_current_schema() == "path" and cas_no:
        cursor.execute(
            "UPDATE public.raw_db SET cas_no = ? WHERE item_code = ? AND schema_name = 'path'",
            (cas_no, item_code),
        )
        conn.commit()

    conn.close()
    return True, "품목이 등록되었습니다."


def get_master_item_by_id(item_id: int):
    sync_expired_reagents()
    conn = get_connection()
    cursor = conn.cursor()
    schema = get_current_schema()
    if schema == "path":
        cursor.execute(
            """
            SELECT i.*, r.cas_no
            FROM inventory i
            LEFT JOIN public.raw_db r ON r.item_code = i.item_code AND r.schema_name = 'path'
            WHERE i.id = ? AND i.disposed_at IS NULL
            """,
            (item_id,),
        )
    else:
        cursor.execute("SELECT * FROM inventory WHERE id = ? AND disposed_at IS NULL", (item_id,))
    row = cursor.fetchone()
    conn.close()
    return dict(row) if row else None


def update_master_item(
    item_id: int,
    hazardous: str,
    part: str,
    item_code: str,
    item_name: str,
    lot_no: str,
    expiry_date: str,
    spec: str,
    unit: str,
    reagent_type: str,
    equipment: str,
    vendor: str,
    safety_stock: int,
    hazardous_grade: str = "",
    cas_no: str = "",
):
    hazardous = normalize_hazardous_strict(hazardous)
    part = normalize_part_strict(part)
    reagent_type = normalize_reagent_type_strict(reagent_type)
    expiry_date = normalize_date(expiry_date)

    conn = get_connection()
    cursor = conn.cursor()

    # 수정 전 품목코드·파트 조회 (raw_db 역동기화 키)
    cursor.execute("SELECT item_code, part FROM inventory WHERE id = ? AND disposed_at IS NULL", (item_id,))
    old_row = cursor.fetchone()
    old_item_code = old_row["item_code"] if old_row else None
    old_part = old_row["part"] if old_row else None

    # base_item_name은 (New)/(Old) 접미사를 제거한 순수 이름
    import re as _re
    base_item_name = _re.sub(r'\s*\(New\)$|\s*\(Old\)$', '', item_name).strip()

    cursor.execute(
        """
        UPDATE inventory
        SET
            hazardous = ?,
            hazardous_grade = ?,
            part = ?,
            item_code = ?,
            item_name = ?,
            base_item_name = ?,
            lot_no = ?,
            expiry_date = ?,
            spec = ?,
            unit = ?,
            reagent_type = ?,
            equipment = ?,
            vendor = ?,
            safety_stock = ?,
            required_qty = CASE
                WHEN ? - current_stock > 0 THEN ? - current_stock
                ELSE 0
            END
        WHERE id = ? AND disposed_at IS NULL
        """,
        (
            hazardous, hazardous_grade, part, item_code, item_name, base_item_name, lot_no,
            expiry_date, spec, unit, reagent_type,
            equipment, vendor, safety_stock,
            safety_stock, safety_stock, item_id,
        ),
    )
    conn.commit()

    if get_current_schema() == "path" and cas_no is not None:
        cursor.execute(
            "UPDATE public.raw_db SET cas_no = ? WHERE item_code = ? AND schema_name = 'path'",
            (cas_no, item_code),
        )
        conn.commit()

    conn.close()

    # raw_db 역동기화
    if old_item_code and old_part:
        try:
            sync_master_update_to_rawdb(
                old_item_code, old_part, part, hazardous, hazardous_grade,
                item_code, item_name, spec, unit,
            )
        except Exception:
            pass


def delete_master_item(item_id: int):
    conn = get_connection()
    cursor = conn.cursor()
    cursor.execute("DELETE FROM inventory WHERE id = ? AND disposed_at IS NULL", (item_id,))
    conn.commit()
    conn.close()


REQUIRED_COLUMNS = [
    "hazardous",
    "part",
    "item_code",
    "item_name",
    "lot_no",
    "expiry_date",
    "spec",
    "unit",
    "reagent_type",
    "equipment",
    "vendor",
    "safety_stock",
]


def normalize_text(value):
    if value is None:
        return ""
    text = str(value).strip()
    if text.lower() in {"nan", "none", "<na>"}:
        return ""
    return text


def normalize_date(value):
    value = normalize_text(value)
    if not value:
        return "9999-12-31"
    for fmt in ("%Y%m%d", "%Y-%m-%d"):
        try:
            dt = datetime.strptime(value, fmt)
            return dt.strftime("%Y-%m-%d")
        except ValueError:
            continue
    raise ValueError(f"날짜 형식 오류: {value} (형식: YYYYMMDD)")


def is_duplicate_master_item(item_name, lot_no):
    sync_expired_reagents()
    conn = get_connection()
    cursor = conn.cursor()
    cursor.execute(
        """
        SELECT COUNT(*)
        FROM inventory
        WHERE item_name = ? AND COALESCE(lot_no, '') = COALESCE(?, '') AND disposed_at IS NULL
        """,
        (item_name, lot_no),
    )
    exists = cursor.fetchone()[0] > 0
    conn.close()
    return exists


def preview_bulk_master_items(df):
    for col in REQUIRED_COLUMNS:
        if col not in df.columns:
            raise ValueError(f"필수 컬럼이 없습니다: {col}")

    preview_rows = []
    upload_rows = []
    invalid_messages = []
    duplicate_names = []
    total_count = len(df)

    for idx, row in df.iterrows():
        excel_row_num = idx + 2
        try:
            hazardous = normalize_text(row.get("hazardous")).upper()
            part = normalize_text(row.get("part"))
            item_code = normalize_text(row.get("item_code"))
            item_name = normalize_text(row.get("item_name"))
            lot_no = normalize_text(row.get("lot_no"))
            expiry_date = normalize_date(row.get("expiry_date"))
            spec = normalize_text(row.get("spec"))
            unit = normalize_text(row.get("unit"))
            reagent_type = normalize_text(row.get("reagent_type"))
            equipment = normalize_text(row.get("equipment"))
            vendor = normalize_text(row.get("vendor"))
            safety_stock_raw = normalize_text(row.get("safety_stock"))

            if hazardous not in {"Y", "N"}:
                hazardous = "N"
            if not item_code:
                raise ValueError("item_code 값이 비어 있습니다.")
            if not item_name:
                raise ValueError("item_name 값이 비어 있습니다.")

            safety_stock = 0 if safety_stock_raw == "" else int(float(safety_stock_raw))
            duplicate = is_duplicate_master_item(item_name, lot_no)

            row_data = {
                "hazardous": hazardous,
                "part": part,
                "item_code": item_code,
                "item_name": item_name,
                "lot_no": lot_no,
                "expiry_date": expiry_date,
                "spec": spec,
                "unit": unit,
                "reagent_type": reagent_type,
                "equipment": equipment,
                "vendor": vendor,
                "safety_stock": safety_stock,
                "duplicate": duplicate,
            }
            preview_rows.append(row_data)

            if duplicate:
                duplicate_names.append(f"{item_name} / {item_code} / {lot_no} / {equipment}")
            else:
                upload_rows.append(row_data)

        except Exception as exc:
            invalid_messages.append(f"{excel_row_num}행: {str(exc)}")

    return {
        "preview_rows": preview_rows,
        "upload_rows": upload_rows,
        "total_count": total_count,
        "valid_count": len(upload_rows),
        "duplicate_count": len(duplicate_names),
        "duplicate_names": duplicate_names,
        "invalid_count": len(invalid_messages),
        "invalid_messages": invalid_messages,
    }


def confirm_bulk_master_items(rows):
    conn = get_connection()
    cursor = conn.cursor()

    success = 0
    fail = 0
    fail_messages = []

    for idx, row in enumerate(rows, start=1):
        try:
            hazardous = normalize_hazardous_strict(row["hazardous"])
            part = normalize_part_strict(row["part"])
            reagent_type = normalize_reagent_type_strict(row["reagent_type"])
            expiry_date = normalize_date(row["expiry_date"])
            safety_stock = 0 if normalize_text(row["safety_stock"]) == "" else int(float(row["safety_stock"]))

            cursor.execute(
                """
                INSERT INTO inventory (
                    hazardous, part, item_code, item_name, lot_no,
                    expiry_date, spec, unit, reagent_type, equipment,
                    vendor, safety_stock
                )
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    hazardous,
                    part,
                    row["item_code"],
                    row["item_name"],
                    row["lot_no"],
                    expiry_date,
                    row["spec"],
                    row["unit"],
                    reagent_type,
                    row["equipment"],
                    row["vendor"],
                    safety_stock,
                ),
            )
            success += 1
        except Exception as exc:
            fail += 1
            fail_messages.append(f"{idx}번째 데이터 업로드 실패: {str(exc)}")

    conn.commit()
    conn.close()

    return {
        "total": len(rows),
        "success": success,
        "fail": fail,
        "fail_messages": fail_messages,
    }


def preview_bulk_master_items_v2(df):
    for col in REQUIRED_COLUMNS:
        if col not in df.columns:
            raise ValueError(f"필수 컬럼이 없습니다: {col}")

    preview_rows = []
    upload_rows = []
    invalid_messages = []
    duplicate_names = []
    total_count = len(df)

    for idx, row in df.iterrows():
        excel_row_num = idx + 2
        try:
            hazardous = normalize_text(row.get("hazardous")).upper()
            part = normalize_text(row.get("part"))
            item_code = normalize_text(row.get("item_code"))
            item_name = normalize_text(row.get("item_name"))
            lot_no = normalize_text(row.get("lot_no"))
            expiry_date = normalize_date(row.get("expiry_date"))
            spec = normalize_text(row.get("spec"))
            unit = normalize_text(row.get("unit"))
            reagent_type = normalize_text(row.get("reagent_type"))
            equipment = normalize_text(row.get("equipment"))
            vendor = normalize_text(row.get("vendor"))
            safety_stock_raw = normalize_text(row.get("safety_stock"))

            if hazardous not in {"Y", "N"}:
                hazardous = "N"
            if not item_code:
                raise ValueError("item_code 값이 비어 있습니다.")
            if not item_name:
                raise ValueError("item_name 값이 비어 있습니다.")

            safety_stock = 0 if safety_stock_raw == "" else int(float(safety_stock_raw))
            duplicate = is_duplicate_master_item(item_name, lot_no)

            row_data = {
                "hazardous": hazardous,
                "part": part,
                "part_pill_class": "part-pill" if not duplicate else "part-pill part-pill-neutral",
                "item_code": item_code,
                "item_name": item_name,
                "lot_no": lot_no,
                "expiry_date": expiry_date,
                "spec": spec,
                "unit": unit,
                "reagent_type": reagent_type,
                "equipment": equipment,
                "vendor": vendor,
                "safety_stock": safety_stock,
                "duplicate": duplicate,
                "status": "오류" if duplicate else "업로드 예정",
            }
            preview_rows.append(row_data)

            if duplicate:
                duplicate_names.append(f"{item_name} / {item_code} / {lot_no} / {equipment}")
            else:
                upload_rows.append(row_data)
        except Exception as exc:
            preview_rows.append(
                {
                    "hazardous": normalize_text(row.get("hazardous")).upper(),
                    "part": normalize_text(row.get("part")),
                    "part_pill_class": "part-pill part-pill-neutral",
                    "item_code": normalize_text(row.get("item_code")),
                    "item_name": normalize_text(row.get("item_name")),
                    "lot_no": normalize_text(row.get("lot_no")),
                    "expiry_date": normalize_text(row.get("expiry_date")),
                    "spec": normalize_text(row.get("spec")),
                    "unit": normalize_text(row.get("unit")),
                    "reagent_type": normalize_text(row.get("reagent_type")),
                    "equipment": normalize_text(row.get("equipment")),
                    "vendor": normalize_text(row.get("vendor")),
                    "safety_stock": normalize_text(row.get("safety_stock")),
                    "duplicate": False,
                    "status": "오류",
                }
            )
            invalid_messages.append(f"{excel_row_num}행: {str(exc)}")

    return {
        "preview_rows": preview_rows,
        "upload_rows": upload_rows,
        "total_count": total_count,
        "valid_count": len(upload_rows),
        "duplicate_count": len(duplicate_names),
        "duplicate_names": duplicate_names,
        "invalid_count": len(invalid_messages),
        "invalid_messages": invalid_messages,
    }


def preview_bulk_master_items_v3(df):
    for col in REQUIRED_COLUMNS:
        if col not in df.columns:
            raise ValueError(f"필수 컬럼이 없습니다: {col}")

    preview_rows = []
    upload_rows = []
    invalid_messages = []
    duplicate_names = []
    total_count = len(df)

    for idx, row in df.iterrows():
        excel_row_num = idx + 2
        try:
            hazardous = normalize_hazardous_strict(row.get("hazardous"))
            part = normalize_part_strict(row.get("part"))
            item_code = normalize_text(row.get("item_code"))
            item_name = normalize_text(row.get("item_name"))
            lot_no = normalize_text(row.get("lot_no"))
            expiry_date = normalize_date(row.get("expiry_date"))
            spec = normalize_text(row.get("spec"))
            unit = normalize_text(row.get("unit"))
            reagent_type = normalize_reagent_type_strict(row.get("reagent_type"))
            equipment = normalize_text(row.get("equipment"))
            vendor = normalize_text(row.get("vendor"))
            safety_stock_raw = normalize_text(row.get("safety_stock"))

            if not item_code:
                raise ValueError("item_code 값이 비어 있습니다.")
            if not item_name:
                raise ValueError("item_name 값이 비어 있습니다.")

            safety_stock = 0 if safety_stock_raw == "" else int(float(safety_stock_raw))
            duplicate = is_duplicate_master_item(item_name, lot_no)
            part_label = f"{part} ({get_part_map(get_current_schema()).get(part, '')})" if get_part_map(get_current_schema()).get(part, "") else part

            row_data = {
                "hazardous": hazardous,
                "part": part,
                "part_label": part_label,
                "part_pill_class": "part-pill" if not duplicate else "part-pill part-pill-neutral",
                "item_code": item_code,
                "item_name": item_name,
                "lot_no": lot_no,
                "expiry_date": expiry_date,
                "spec": spec,
                "unit": unit,
                "reagent_type": REAGENT_TYPE_MAP.get(reagent_type, reagent_type),
                "equipment": equipment,
                "vendor": vendor,
                "safety_stock": safety_stock,
                "duplicate": duplicate,
                "status": "오류" if duplicate else "업로드 예정",
            }
            preview_rows.append(row_data)

            if duplicate:
                duplicate_names.append(f"{item_name} / {item_code} / {lot_no} / {equipment}")
            else:
                upload_rows.append(row_data)
        except Exception as exc:
            raw_part = normalize_text(row.get("part")).upper()
            part_name = get_part_map(get_current_schema()).get(raw_part, "")
            preview_rows.append(
                {
                    "hazardous": normalize_text(row.get("hazardous")).upper(),
                    "part": raw_part,
                    "part_label": f"{raw_part} ({part_name})" if part_name else raw_part,
                    "part_pill_class": "part-pill part-pill-neutral",
                    "item_code": normalize_text(row.get("item_code")),
                    "item_name": normalize_text(row.get("item_name")),
                    "lot_no": normalize_text(row.get("lot_no")),
                    "expiry_date": normalize_text(row.get("expiry_date")),
                    "spec": normalize_text(row.get("spec")),
                    "unit": normalize_text(row.get("unit")),
                    "reagent_type": normalize_text(row.get("reagent_type")),
                    "equipment": normalize_text(row.get("equipment")),
                    "vendor": normalize_text(row.get("vendor")),
                    "safety_stock": normalize_text(row.get("safety_stock")),
                    "duplicate": False,
                    "status": "오류",
                }
            )
            invalid_messages.append(f"{excel_row_num}행: {str(exc)}")

    return {
        "preview_rows": preview_rows,
        "upload_rows": upload_rows,
        "total_count": total_count,
        "valid_count": len(upload_rows),
        "duplicate_count": len(duplicate_names),
        "duplicate_names": duplicate_names,
        "invalid_count": len(invalid_messages),
        "invalid_messages": invalid_messages,
    }
