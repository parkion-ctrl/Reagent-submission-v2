from datetime import date, datetime

from app.core.db import get_connection, get_current_schema
from app.services.reagent_history_service import sync_expired_reagents
from app.utils.constants import get_part_map


TRANSACTION_UPLOAD_REQUIRED_COLUMNS = ["item_code", "lot_no", "qty", "tx_date"]

# Supply(소모품)/Extra(기타)는 New/Old lot 구분(자동 "(New)" 태깅, 재고 분리 관리)을 적용하지 않는다.
LOT_STATUS_EXCLUDED_REAGENT_TYPES = {"4", "5"}


def _tracks_lot_status(reagent_type) -> bool:
    return str(reagent_type or "").strip() not in LOT_STATUS_EXCLUDED_REAGENT_TYPES


def get_transaction_table_items(tx_type: str, q: str = "", part: str = "", sort: str = "", order: str = "", **kwargs):
    sync_expired_reagents()

    if not q.strip() and not part.strip():
        return []

    conn = get_connection()
    cursor = conn.cursor()

    query = """
        SELECT
            id, part, item_code, item_name, lot_no, unit,
            current_stock, safety_stock, expiry_date, is_new_lot,
            COALESCE(equipment, '') AS equipment,
            COALESCE(reagent_type, '') AS reagent_type
        FROM inventory
        WHERE disposed_at IS NULL
    """
    params = []

    if tx_type == "OUT":
        query += " AND current_stock >= 1"
    if part:
        query += " AND part = ?"
        params.append(part)

    equipment = kwargs.get("equipment", "")
    reagent_type_filter = kwargs.get("reagent_type", "")
    if equipment:
        query += " AND equipment = ?"
        params.append(equipment)
    if reagent_type_filter:
        query += " AND reagent_type = ?"
        params.append(reagent_type_filter)

    if q:
        query += " AND (item_code ILIKE ? OR item_name ILIKE ?)"
        keyword = f"%{q}%"
        params.extend([keyword, keyword])

    allowed_sort = ["item_name"]
    if sort in allowed_sort:
        order_sql = "DESC" if order == "desc" else "ASC"
        query += f" ORDER BY {sort} {order_sql}, item_code ASC, lot_no ASC, expiry_date ASC"
    else:
        query += " ORDER BY item_code ASC, lot_no ASC, expiry_date ASC"

    cursor.execute(query, params)
    rows = cursor.fetchall()
    conn.close()

    items = []
    for row in rows:
        row = dict(row)
        part_code = str(row.get("part", "")).strip()
        part_name = get_part_map(get_current_schema()).get(part_code, "")
        row["part_label"] = f"{part_code} ({part_name})" if part_name else part_code
        row["display_name"] = f"{row['item_code']} | {row['item_name']} | Lot {row.get('lot_no', '') or '-'}"
        raw_expiry = str(row.get("expiry_date", "") or "").strip()
        row["expiry_date"] = "" if raw_expiry == "9999-12-31" else raw_expiry[:10]
        is_new_lot_raw = str(row.get("is_new_lot", "N") or "N").strip()
        row["is_new_lot"] = "Y" if is_new_lot_raw == "Y" else "N"
        from app.utils.constants import REAGENT_TYPE_MAP
        reagent_type_code = str(row.get("reagent_type", "") or "").strip()
        row["reagent_type_label"] = REAGENT_TYPE_MAP.get(reagent_type_code, reagent_type_code)
        items.append(row)

    return items


def get_transaction_filter_options(part: str = ""):
    """입출고 테이블 필터용 장비/시약구분 옵션 반환. part 지정 시 해당 파트 기준으로 필터링."""
    conn = get_connection()
    cursor = conn.cursor()
    part_cond = " AND part = ?" if part else ""
    part_args = (part,) if part else ()
    cursor.execute(
        f"SELECT DISTINCT equipment FROM inventory WHERE disposed_at IS NULL AND equipment IS NOT NULL AND TRIM(equipment) != '' {part_cond} ORDER BY equipment",
        part_args,
    )
    equipment_options = [row[0] for row in cursor.fetchall()]
    cursor.execute(
        f"SELECT DISTINCT reagent_type FROM inventory WHERE disposed_at IS NULL AND reagent_type IS NOT NULL AND TRIM(reagent_type) != '' {part_cond} ORDER BY reagent_type",
        part_args,
    )
    reagent_type_options = [row[0] for row in cursor.fetchall()]
    conn.close()
    from app.utils.constants import REAGENT_TYPE_MAP
    return {
        "equipment_options": equipment_options,
        "reagent_type_options": [{"value": v, "label": REAGENT_TYPE_MAP.get(v, v)} for v in reagent_type_options],
    }


def apply_stock_transaction(tx_type: str, inventory_id: int, qty: int, tx_date: str, created_by: str = "", created_by_empno: str = ""):
    rows = [{"inventory_id": inventory_id, "qty": qty, "tx_date": tx_date}]
    return apply_bulk_stock_transactions(tx_type=tx_type, rows=rows, created_by=created_by, created_by_empno=created_by_empno)


def apply_bulk_stock_transactions(tx_type: str, rows: list[dict], created_by: str = "", created_by_empno: str = ""):
    if tx_type not in {"IN", "OUT"}:
        return False, "지원하지 않는 거래 유형입니다."
    if not rows:
        return False, "처리할 항목이 없습니다."

    sync_expired_reagents()
    conn = get_connection()
    cursor = conn.cursor()

    try:
        for row in rows:
            qty = int(row.get("qty"))
            tx_date = str(row.get("tx_date", "")).strip()

            if qty <= 0:
                raise ValueError("수량은 1 이상이어야 합니다.")
            if not tx_date:
                raise ValueError("거래 일자는 필수입니다.")

            # --- New Lot row: create master record then process inbound ---
            if row.get("is_new_lot_row"):
                source_id = int(row.get("inventory_id"))
                new_lot_no = str(row.get("new_lot_no", "")).strip()
                new_expiry_date_str = str(row.get("new_expiry_date", "")).strip() or "9999-12-31"

                if not new_lot_no:
                    raise ValueError("New Lot No는 필수입니다.")

                cursor.execute(
                    "SELECT * FROM inventory WHERE id = ? AND disposed_at IS NULL",
                    (source_id,),
                )
                source_item = cursor.fetchone()
                if not source_item:
                    raise ValueError("원본 시약 항목을 찾을 수 없습니다.")

                source = dict(source_item)
                raw_item_name = str(source.get("item_name", "")).strip()
                base_name = raw_item_name.removesuffix(" (New)").removesuffix(" (Old)")
                tracks_lot_status = _tracks_lot_status(source.get("reagent_type"))
                new_item_name = base_name + " (New)" if tracks_lot_status else base_name
                new_lot_status = "NEW" if tracks_lot_status else ""
                new_is_new_lot = "Y" if tracks_lot_status else "N"
                safety_stock = int(source.get("safety_stock", 0) or 0)
                required_qty = max(safety_stock, 0)

                cursor.execute(
                    """
                    INSERT INTO inventory (
                        hazardous, part, item_code, item_name, lot_no,
                        expiry_date, spec, unit, reagent_type, equipment,
                        vendor, safety_stock, current_stock, required_qty,
                        lot_status, is_new_lot, base_item_name, registered_at
                    )
                    VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                    RETURNING id
                    """,
                    (
                        source.get("hazardous") or "",
                        source.get("part") or "",
                        source.get("item_code") or "",
                        new_item_name,
                        new_lot_no,
                        new_expiry_date_str,
                        source.get("spec") or "",
                        source.get("unit") or "",
                        source.get("reagent_type") or "",
                        source.get("equipment") or "",
                        source.get("vendor") or "",
                        safety_stock,
                        0,
                        required_qty,
                        new_lot_status,
                        new_is_new_lot,
                        base_name,
                        datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
                    ),
                )
                result = cursor.fetchone()
                new_inventory_id = result[0]

                next_stock = qty
                new_required_qty = max(safety_stock - next_stock, 0)
                cursor.execute(
                    "UPDATE inventory SET current_stock = ?, required_qty = ? WHERE id = ?",
                    (next_stock, new_required_qty, new_inventory_id),
                )
                cursor.execute(
                    """
                    INSERT INTO transaction_history (
                        inventory_id, tx_type, qty, tx_date, note, remaining_stock,
                        item_code, item_name, lot_no, part, unit,
                        created_by, created_by_empno
                    )
                    VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                    """,
                    (
                        new_inventory_id,
                        tx_type,
                        qty,
                        tx_date,
                        "",
                        next_stock,
                        source.get("item_code") or "",
                        new_item_name,
                        new_lot_no,
                        source.get("part") or "",
                        source.get("unit") or "",
                        created_by,
                        created_by_empno,
                    ),
                )
                continue

            # --- Regular row ---
            inventory_id = int(row.get("inventory_id"))

            cursor.execute(
                "SELECT * FROM inventory WHERE id = ? AND disposed_at IS NULL",
                (inventory_id,),
            )
            inventory_row = cursor.fetchone()
            if not inventory_row:
                raise ValueError("선택한 품목을 찾을 수 없습니다.")

            item = dict(inventory_row)
            current_stock = int(item.get("current_stock", 0) or 0)
            safety_stock = int(item.get("safety_stock", 0) or 0)

            if tx_type == "OUT" and qty > current_stock:
                raise ValueError(
                    f"{item.get('item_code', '')} / {item.get('item_name', '')}의 출고 수량이 현재고보다 많습니다."
                )

            next_stock = current_stock + qty if tx_type == "IN" else current_stock - qty
            required_qty = max(safety_stock - next_stock, 0)

            cursor.execute(
                """
                UPDATE inventory
                SET current_stock = ?, required_qty = ?
                WHERE id = ?
                """,
                (next_stock, required_qty, inventory_id),
            )

            cursor.execute(
                """
                INSERT INTO transaction_history (
                    inventory_id, tx_type, qty, tx_date, note, remaining_stock,
                    item_code, item_name, lot_no, part, unit,
                    created_by, created_by_empno
                )
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    inventory_id,
                    tx_type,
                    qty,
                    tx_date,
                    "",
                    next_stock,
                    item.get("item_code", ""),
                    item.get("item_name", ""),
                    item.get("lot_no", ""),
                    item.get("part", ""),
                    item.get("unit", ""),
                    created_by,
                    created_by_empno,
                ),
            )

            # 첫 출고 시 opened_at 자동 등록 및 New Lot 해제
            if tx_type == "OUT" and not str(item.get("opened_at") or "").strip():
                cursor.execute(
                    "UPDATE inventory SET opened_at = ? WHERE id = ?",
                    (tx_date, inventory_id),
                )
                lot_status = str(item.get("lot_status") or "").strip()
                item_code = str(item.get("item_code") or "")
                base_item_name = str(item.get("base_item_name") or "")
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
        return True, f"{len(rows)}건을 처리했습니다."
    except Exception as exc:
        conn.rollback()
        return False, str(exc)
    finally:
        conn.close()


def preview_bulk_transaction_items(tx_type: str, df):
    for column in TRANSACTION_UPLOAD_REQUIRED_COLUMNS:
        if column not in df.columns:
            raise ValueError(f"필수 컬럼이 없습니다: {column}")

    sync_expired_reagents()
    conn = get_connection()
    cursor = conn.cursor()

    preview_rows = []
    upload_rows = []
    invalid_messages = []
    new_lot_messages = []
    total_count = len(df)

    try:
        for idx, row in df.iterrows():
            excel_row_num = idx + 2
            try:
                item_code = normalize_text(row.get("item_code")).upper()
                lot_no = normalize_text(row.get("lot_no"))
                expiry_date_raw = normalize_text(row.get("expiry_date")) if "expiry_date" in row.index else ""
                expiry_date_str = normalize_date_optional(expiry_date_raw)
                qty = normalize_qty(row.get("qty"))
                tx_date = normalize_tx_date(row.get("tx_date"))

                if not item_code:
                    raise ValueError("item_code 값이 비어 있습니다.")

                inventory_row = find_inventory_row(cursor, tx_type=tx_type, item_code=item_code, lot_no=lot_no)

                # --- New Lot: item_code 있지만 lot_no 없음 (입고만 허용) ---
                if not inventory_row and tx_type == "IN":
                    source_item = find_inventory_by_item_code(cursor, item_code=item_code)
                    if source_item:
                        source = dict(source_item)
                        raw_item_name = str(source.get("item_name", "")).strip()
                        base_name = raw_item_name.removesuffix(" (New)").removesuffix(" (Old)")
                        tracks_lot_status = _tracks_lot_status(source.get("reagent_type"))
                        new_item_name = base_name + " (New)" if tracks_lot_status else base_name
                        part_code = str(source.get("part", "")).strip()
                        part_name = get_part_map(get_current_schema()).get(part_code, "")
                        display_expiry = expiry_date_str if expiry_date_str and expiry_date_str != "9999-12-31" else "-"

                        preview_rows.append(
                            {
                                "inventory_id": None,
                                "part_label": f"{part_code} ({part_name})" if part_name else part_code,
                                "part_pill_class": "part-pill",
                                "item_code": item_code,
                                "item_name": new_item_name,
                                "lot_no": lot_no,
                                "unit": source.get("unit", "") or "",
                                "expiry_date": display_expiry,
                                "current_stock": 0,
                                "qty": qty,
                                "tx_date": tx_date,
                                "remaining_stock": qty,
                                "status": "New Lot 예정" if tracks_lot_status else "등록 예정",
                            }
                        )
                        upload_rows.append(
                            {
                                "inventory_id": source["id"],
                                "qty": qty,
                                "tx_date": tx_date,
                                "is_new_lot_row": True,
                                "new_lot_no": lot_no,
                                "new_expiry_date": expiry_date_str,
                            }
                        )
                        new_lot_messages.append(
                            f"{excel_row_num}행: 기존에 등록되어 있지 않던 New lot no입니다. "
                            f"Lot no: {lot_no}, 유효기간: {display_expiry}"
                        )
                        continue

                if not inventory_row:
                    raise ValueError("일치하는 활성 시약을 찾을 수 없습니다.")

                inventory_item = dict(inventory_row)
                current_stock = int(inventory_item.get("current_stock", 0) or 0)
                if tx_type == "OUT" and qty > current_stock:
                    raise ValueError("출고 수량이 현재고보다 많습니다.")

                remaining_stock = current_stock + qty if tx_type == "IN" else current_stock - qty
                part_code = str(inventory_item.get("part", "")).strip()
                part_name = get_part_map(get_current_schema()).get(part_code, "")

                preview_row = {
                    "inventory_id": inventory_item["id"],
                    "part_label": f"{part_code} ({part_name})" if part_name else part_code,
                    "part_pill_class": "part-pill",
                    "item_code": inventory_item.get("item_code", ""),
                    "item_name": inventory_item.get("item_name", ""),
                    "lot_no": inventory_item.get("lot_no", ""),
                    "unit": inventory_item.get("unit", ""),
                    "expiry_date": format_date_text(inventory_item.get("expiry_date")),
                    "current_stock": current_stock,
                    "qty": qty,
                    "tx_date": tx_date,
                    "remaining_stock": remaining_stock,
                    "status": "등록 예정",
                }
                preview_rows.append(preview_row)
                upload_rows.append(
                    {
                        "inventory_id": inventory_item["id"],
                        "qty": qty,
                        "tx_date": tx_date,
                    }
                )
            except Exception as exc:
                fallback_item = find_inventory_row(
                    cursor,
                    tx_type="IN",
                    item_code=normalize_text(row.get("item_code")),
                    lot_no=normalize_text(row.get("lot_no")),
                )
                fallback_data = dict(fallback_item) if fallback_item else {}
                fallback_part = str(fallback_data.get("part", "")).strip()
                fallback_part_name = get_part_map(get_current_schema()).get(fallback_part, "")
                fallback_current_stock = int(fallback_data.get("current_stock", 0) or 0) if fallback_data else ""
                fallback_qty_raw = normalize_text(row.get("qty"))
                fallback_qty = int(float(fallback_qty_raw)) if fallback_qty_raw not in {"", None} else ""
                preview_rows.append(
                    {
                        "inventory_id": "",
                        "part_label": f"{fallback_part} ({fallback_part_name})" if fallback_part_name else fallback_part,
                        "part_pill_class": "part-pill part-pill-neutral",
                        "item_code": normalize_text(row.get("item_code")).upper(),
                        "item_name": fallback_data.get("item_name", ""),
                        "lot_no": normalize_text(row.get("lot_no")),
                        "unit": fallback_data.get("unit", ""),
                        "expiry_date": "",
                        "current_stock": fallback_current_stock,
                        "qty": fallback_qty_raw,
                        "tx_date": normalize_text(row.get("tx_date")),
                        "remaining_stock": compute_fallback_remaining_stock(
                            tx_type=tx_type,
                            current_stock=fallback_current_stock,
                            qty=fallback_qty,
                        ),
                        "status": "오류",
                    }
                )
                invalid_messages.append(f"{excel_row_num}행: {str(exc)}")
    finally:
        conn.close()

    return {
        "preview_rows": preview_rows,
        "upload_rows": upload_rows,
        "total_count": total_count,
        "valid_count": len(upload_rows),
        "invalid_count": len(invalid_messages),
        "invalid_messages": invalid_messages,
        "new_lot_messages": new_lot_messages,
    }


def preview_manual_transaction_items(tx_type: str, rows: list[dict]):
    sync_expired_reagents()
    conn = get_connection()
    cursor = conn.cursor()

    preview_rows = []
    upload_rows = []
    invalid_messages = []
    new_lot_messages = []

    try:
        for idx, row in enumerate(rows, start=1):
            try:
                # --- New Lot row handling ---
                if row.get("is_new_lot_row"):
                    source_id = int(row.get("inventory_id"))
                    new_lot_no = str(row.get("new_lot_no", "")).strip()
                    new_expiry_date = str(row.get("new_expiry_date", "")).strip()
                    qty = normalize_qty(row.get("qty"))
                    tx_date = normalize_tx_date(row.get("tx_date"))

                    if not new_lot_no:
                        raise ValueError("New Lot No를 입력해 주세요.")

                    cursor.execute(
                        "SELECT * FROM inventory WHERE id = ? AND disposed_at IS NULL",
                        (source_id,),
                    )
                    source_row = cursor.fetchone()
                    if not source_row:
                        raise ValueError("원본 시약 항목을 찾을 수 없습니다.")

                    source = dict(source_row)
                    item_code = source.get("item_code", "") or ""
                    raw_item_name = str(source.get("item_name", "")).strip()
                    base_name = raw_item_name.removesuffix(" (New)").removesuffix(" (Old)")
                    tracks_lot_status = _tracks_lot_status(source.get("reagent_type"))
                    part_code = str(source.get("part", "")).strip()
                    part_name = get_part_map(get_current_schema()).get(part_code, "")
                    unit = source.get("unit", "") or ""

                    cursor.execute(
                        "SELECT 1 FROM inventory WHERE item_code = ? AND lot_no = ? AND disposed_at IS NULL",
                        (item_code, new_lot_no),
                    )
                    if cursor.fetchone() is not None:
                        raise ValueError(f"Lot No '{new_lot_no}'은(는) 이미 마스터에 등록되어 있습니다.")

                    new_item_name = base_name + " (New)" if tracks_lot_status else base_name
                    display_expiry = new_expiry_date if new_expiry_date else "-"

                    preview_rows.append(
                        {
                            "inventory_id": None,
                            "part_label": f"{part_code} ({part_name})" if part_name else part_code,
                            "part_pill_class": "part-pill",
                            "item_code": item_code,
                            "item_name": new_item_name,
                            "lot_no": new_lot_no,
                            "unit": unit,
                            "expiry_date": display_expiry,
                            "current_stock": 0,
                            "qty": qty,
                            "tx_date": tx_date,
                            "remaining_stock": qty,
                            "status": "New Lot 예정" if tracks_lot_status else "등록 예정",
                        }
                    )
                    upload_rows.append(
                        {
                            "inventory_id": source_id,
                            "qty": qty,
                            "tx_date": tx_date,
                            "is_new_lot_row": True,
                            "new_lot_no": new_lot_no,
                            "new_expiry_date": new_expiry_date,
                        }
                    )
                    new_lot_messages.append(
                        f"{idx}번째 항목: 기존에 등록되어 있지 않던 New lot no입니다. "
                        f"Lot no: {new_lot_no}, 유효기간: {display_expiry}"
                    )
                    continue

                # --- Regular row handling ---
                inventory_id = int(row.get("inventory_id"))
                qty = normalize_qty(row.get("qty"))
                tx_date = normalize_tx_date(row.get("tx_date"))

                cursor.execute(
                    """
                    SELECT
                        id, part, item_code, item_name, lot_no, unit,
                        current_stock, safety_stock, expiry_date
                    FROM inventory
                    WHERE id = ? AND disposed_at IS NULL
                    """,
                    (inventory_id,),
                )
                inventory_row = cursor.fetchone()
                if not inventory_row:
                    raise ValueError("선택한 시약을 찾을 수 없습니다.")

                inventory_item = dict(inventory_row)
                current_stock = int(inventory_item.get("current_stock", 0) or 0)
                if tx_type == "OUT" and qty > current_stock:
                    raise ValueError("출고 수량이 현재고보다 많습니다.")

                remaining_stock = current_stock + qty if tx_type == "IN" else current_stock - qty
                part_code = str(inventory_item.get("part", "")).strip()
                part_name = get_part_map(get_current_schema()).get(part_code, "")

                preview_rows.append(
                    {
                        "inventory_id": inventory_item["id"],
                        "part_label": f"{part_code} ({part_name})" if part_name else part_code,
                        "part_pill_class": "part-pill",
                        "item_code": inventory_item.get("item_code", ""),
                        "item_name": inventory_item.get("item_name", ""),
                        "lot_no": inventory_item.get("lot_no", ""),
                        "unit": inventory_item.get("unit", ""),
                        "expiry_date": format_date_text(inventory_item.get("expiry_date")),
                        "current_stock": current_stock,
                        "qty": qty,
                        "tx_date": tx_date,
                        "remaining_stock": remaining_stock,
                        "status": "반영 예정",
                    }
                )
                upload_rows.append(
                    {
                        "inventory_id": inventory_item["id"],
                        "qty": qty,
                        "tx_date": tx_date,
                    }
                )
            except Exception as exc:
                fallback_data = {}
                inventory_id_raw = normalize_text(row.get("inventory_id"))
                if inventory_id_raw:
                    try:
                        cursor.execute(
                            """
                            SELECT
                                id, part, item_code, item_name, lot_no, unit,
                                current_stock, expiry_date
                            FROM inventory
                            WHERE id = ? AND disposed_at IS NULL
                            """,
                            (int(inventory_id_raw),),
                        )
                        fallback_item = cursor.fetchone()
                        fallback_data = dict(fallback_item) if fallback_item else {}
                    except ValueError:
                        fallback_data = {}

                fallback_part = str(fallback_data.get("part", "")).strip()
                fallback_part_name = get_part_map(get_current_schema()).get(fallback_part, "")
                fallback_current_stock = int(fallback_data.get("current_stock", 0) or 0) if fallback_data else ""
                fallback_qty_raw = normalize_text(row.get("qty"))
                fallback_qty = int(float(fallback_qty_raw)) if fallback_qty_raw not in {"", None} else ""
                preview_rows.append(
                    {
                        "inventory_id": inventory_id_raw,
                        "part_label": f"{fallback_part} ({fallback_part_name})" if fallback_part_name else fallback_part,
                        "part_pill_class": "part-pill part-pill-neutral",
                        "item_code": fallback_data.get("item_code", ""),
                        "item_name": fallback_data.get("item_name", ""),
                        "lot_no": fallback_data.get("lot_no", ""),
                        "unit": fallback_data.get("unit", ""),
                        "expiry_date": "",
                        "current_stock": fallback_current_stock,
                        "qty": fallback_qty_raw,
                        "tx_date": normalize_text(row.get("tx_date")),
                        "remaining_stock": compute_fallback_remaining_stock(
                            tx_type=tx_type,
                            current_stock=fallback_current_stock,
                            qty=fallback_qty,
                        ),
                        "status": "오류",
                    }
                )
                invalid_messages.append(f"{idx}번째 항목: {str(exc)}")
    finally:
        conn.close()

    return {
        "preview_rows": preview_rows,
        "upload_rows": upload_rows,
        "total_count": len(rows),
        "valid_count": len(upload_rows),
        "invalid_count": len(invalid_messages),
        "invalid_messages": invalid_messages,
        "new_lot_messages": new_lot_messages,
    }


def confirm_bulk_transaction_items(tx_type: str, rows: list[dict], created_by: str = "", created_by_empno: str = ""):
    normalized_rows = []
    for row in rows:
        if row.get("is_new_lot_row"):
            normalized_rows.append(
                {
                    "inventory_id": int(row["inventory_id"]),
                    "qty": int(row["qty"]),
                    "tx_date": normalize_tx_date(row["tx_date"]),
                    "is_new_lot_row": True,
                    "new_lot_no": str(row.get("new_lot_no", "")).strip(),
                    "new_expiry_date": str(row.get("new_expiry_date", "")).strip(),
                }
            )
        else:
            normalized_rows.append(
                {
                    "inventory_id": int(row["inventory_id"]),
                    "qty": int(row["qty"]),
                    "tx_date": normalize_tx_date(row["tx_date"]),
                }
            )
    return apply_bulk_stock_transactions(tx_type=tx_type, rows=normalized_rows, created_by=created_by, created_by_empno=created_by_empno)


def find_inventory_row(cursor, tx_type: str, item_code: str, lot_no: str):
    query = """
        SELECT *
        FROM inventory
        WHERE disposed_at IS NULL
          AND item_code = ?
          AND lot_no = ?
    """
    params = [item_code, lot_no]
    if tx_type == "OUT":
        query += " AND current_stock >= 1"
    query += " ORDER BY expiry_date ASC, id ASC LIMIT 1"
    cursor.execute(query, params)
    return cursor.fetchone()


def find_inventory_by_item_code(cursor, item_code: str):
    """lot_no 무관하게 item_code로만 조회 (New Lot 등록 시 메타데이터 복사용)."""
    cursor.execute(
        """
        SELECT *
        FROM inventory
        WHERE disposed_at IS NULL
          AND item_code = ?
        ORDER BY id ASC
        LIMIT 1
        """,
        (item_code,),
    )
    return cursor.fetchone()


def normalize_text(value):
    if value is None:
        return ""
    return str(value).strip()


def normalize_qty(value):
    raw = normalize_text(value)
    if not raw:
        raise ValueError("qty 값이 비어 있습니다.")
    qty = int(float(raw))
    if qty <= 0:
        raise ValueError("수량은 1 이상이어야 합니다.")
    return qty


def normalize_date_optional(value):
    """expiry_date 등 선택적 날짜 파싱. 비어 있으면 '' 반환."""
    raw = normalize_text(value)
    if not raw:
        return ""
    for fmt, length in (("%Y%m%d", 8), ("%Y-%m-%d", 10)):
        try:
            return datetime.strptime(raw[:length], fmt).strftime("%Y-%m-%d")
        except ValueError:
            continue
    return ""


def normalize_tx_date(value):
    raw = normalize_text(value)
    if not raw:
        raise ValueError("tx_date 값이 비어 있습니다.")
    for fmt, length in (("%Y%m%d", 8), ("%Y-%m-%d", 10)):
        try:
            return datetime.strptime(raw[:length], fmt).strftime("%Y-%m-%d")
        except ValueError:
            continue
    raise ValueError("거래일 형식은 YYYYMMDD 여야 합니다.")


def format_date_text(value):
    raw = str(value or "").strip()
    if not raw or raw == "9999-12-31":
        return ""
    return raw[:10]


def get_today_text():
    return date.today().isoformat()


def compute_fallback_remaining_stock(tx_type: str, current_stock, qty):
    if current_stock == "" or qty == "":
        return ""
    if tx_type == "IN":
        return current_stock + qty
    return current_stock - qty
