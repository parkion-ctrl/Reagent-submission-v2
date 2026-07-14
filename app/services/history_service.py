from datetime import datetime, timedelta

from app.core.db import get_connection, get_current_schema
from app.utils.constants import get_part_map, REAGENT_TYPE_MAP


def recalculate_current_stock():
    """트랜잭션 이력 전체를 기준으로 inventory.current_stock 재계산 (PROV_OUT 제외)"""
    conn = get_connection()
    cursor = conn.cursor()

    cursor.execute(
        """
        SELECT inventory_id, tx_type, qty, billing_type
        FROM transaction_history
        ORDER BY tx_date ASC, id ASC
        """
    )
    rows = cursor.fetchall()

    stock = {}
    for row in rows:
        inv_id = row["inventory_id"]
        qty = int(row["qty"] or 0)
        billing_type = row["billing_type"] or ""
        current = stock.get(inv_id, 0)
        if billing_type == "PROV_OUT":
            stock[inv_id] = current
        elif row["tx_type"] == "IN":
            stock[inv_id] = current + qty
        else:
            stock[inv_id] = current - qty

    for inv_id, val in stock.items():
        cursor.execute(
            "UPDATE inventory SET current_stock = ? WHERE id = ?",
            (val, inv_id),
        )

    conn.commit()
    conn.close()


def backfill_remaining_stock():
    conn = get_connection()
    cursor = conn.cursor()

    cursor.execute(
        """
        SELECT id, inventory_id, tx_type, qty, billing_type
        FROM transaction_history
        ORDER BY tx_date ASC, id ASC
        """
    )
    rows = cursor.fetchall()

    running_stock = {}
    for row in rows:
        history_id = row["id"]
        inventory_id = row["inventory_id"]
        qty = int(row["qty"] or 0)
        billing_type = row["billing_type"] or ""
        current = running_stock.get(inventory_id, 0)
        # 가출고(PROV_OUT)는 재고에 반영 안 함
        if billing_type == "PROV_OUT":
            next_stock = current
        else:
            next_stock = current + qty if row["tx_type"] == "IN" else current - qty
        running_stock[inventory_id] = next_stock
        cursor.execute(
            "UPDATE transaction_history SET remaining_stock = ? WHERE id = ?",
            (next_stock, history_id),
        )

    conn.commit()
    conn.close()


def get_history_vendor_options():
    conn = get_connection()
    cursor = conn.cursor()
    cursor.execute(
        """
        SELECT DISTINCT COALESCE(i.vendor, '') AS vendor
        FROM transaction_history th
        LEFT JOIN inventory i ON i.id = th.inventory_id
        ORDER BY vendor
        """
    )
    rows = [row[0] for row in cursor.fetchall()]
    conn.close()

    options = []
    if any(v is None or str(v).strip() == "" for v in rows):
        options.append("__BLANK__")
    options.extend(str(v).strip() for v in rows if v is not None and str(v).strip() != "")
    return options


def get_history_reagent_type_options():
    conn = get_connection()
    cursor = conn.cursor()
    cursor.execute(
        """
        SELECT DISTINCT i.reagent_type
        FROM transaction_history th
        LEFT JOIN inventory i ON i.id = th.inventory_id
        WHERE i.reagent_type IS NOT NULL AND TRIM(i.reagent_type) != ''
        ORDER BY i.reagent_type
        """
    )
    rows = [row[0] for row in cursor.fetchall()]
    conn.close()
    return [{"value": v, "label": REAGENT_TYPE_MAP.get(str(v).strip(), str(v).strip())} for v in rows]


def get_history_items(
    tx_type: str = "",
    part: str = "",
    q: str = "",
    date_from: str = "",
    date_to: str = "",
    vendor: str = "",
    reagent_type: str = "",
    sort: str = "",
    order: str = "",
    disposed: str = "",
):
    backfill_remaining_stock()

    conn = get_connection()
    cursor = conn.cursor()

    query = """
        SELECT
            th.id, th.inventory_id, th.tx_type, th.qty, th.tx_date, th.remaining_stock,
            th.item_code, th.item_name, th.lot_no, th.part, th.unit, th.created_at, th.billing_type,
            th.created_by, th.created_by_empno,
            COALESCE(i.vendor, '') AS vendor,
            COALESCE(i.reagent_type, '') AS reagent_type,
            COALESCE(i.is_new_lot, 'N') AS is_new_lot,
            i.disposed_at AS disposed_at
        FROM transaction_history th
        LEFT JOIN inventory i ON i.id = th.inventory_id
        WHERE 1 = 1
    """
    params = []

    if tx_type == "FREE_IN":
        query += " AND th.billing_type = 'FREE_IN'"
    elif tx_type == "PROV_OUT":
        query += " AND th.billing_type = 'PROV_OUT'"
    elif tx_type:
        query += " AND th.tx_type = ?"
        params.append(tx_type)

    if part:
        query += " AND th.part = ?"
        params.append(part)

    if q:
        query += " AND (th.item_code ILIKE ? OR th.item_name ILIKE ? OR th.lot_no ILIKE ?)"
        keyword = f"%{q}%"
        params.extend([keyword, keyword, keyword])

    if date_from:
        query += " AND th.tx_date >= ?"
        params.append(date_from)

    if date_to:
        query += " AND th.tx_date <= ?"
        params.append(date_to)

    if vendor == "__BLANK__":
        query += " AND (i.vendor IS NULL OR TRIM(i.vendor) = '')"
    elif vendor:
        query += " AND i.vendor = ?"
        params.append(vendor)

    if reagent_type:
        query += " AND i.reagent_type = ?"
        params.append(reagent_type)

    if disposed == "Y":
        query += " AND i.disposed_at IS NOT NULL AND i.disposed_at >= '2026-04-20'"
    elif disposed == "N":
        query += " AND (i.disposed_at IS NULL OR i.disposed_at < '2026-04-20')"

    query += " AND (th.billing_type IS NULL OR th.billing_type != 'STOCK_ADJUST')"
    if sort in ("item_code", "item_name"):
        direction = "ASC" if order == "asc" else "DESC"
        query += f" ORDER BY th.{sort} {direction}, th.tx_date DESC, th.id DESC"
    else:
        query += " ORDER BY th.tx_date DESC, th.id DESC"

    cursor.execute(query, params)
    rows = cursor.fetchall()
    conn.close()

    items = []
    for row in rows:
        row = dict(row)
        part_code = str(row.get("part", "")).strip()
        part_name = get_part_map(get_current_schema()).get(part_code, "")
        row["part_label"] = f"{part_code} ({part_name})" if part_name else part_code
        row["tx_type_label"] = "입고" if row["tx_type"] == "IN" else "출고"
        is_new_lot_raw = str(row.get("is_new_lot", "N") or "N").strip()
        row["is_new_lot"] = "Y" if is_new_lot_raw == "Y" else "N"
        if row["is_new_lot"] == "N":
            item_name = str(row.get("item_name", "") or "")
            if item_name.endswith(" (New)"):
                row["item_name"] = item_name[:-6]
        reagent_type_code = str(row.get("reagent_type", "")).strip()
        row["reagent_type_label"] = REAGENT_TYPE_MAP.get(reagent_type_code, reagent_type_code)
        disposed_at = str(row.get("disposed_at") or "")
        row["is_disposed"] = "Y" if disposed_at >= "2026-04-20" else "N"
        row["tx_badge_class"] = "text-bg-primary" if row["tx_type"] == "IN" else "text-bg-secondary"
        row["inbound_qty"] = row["qty"] if row["tx_type"] == "IN" else ""
        row["outbound_qty"] = row["qty"] if row["tx_type"] == "OUT" else ""
        billing_type = row.get("billing_type") or ""
        if billing_type == "FREE_IN":
            row["billing_label"] = "무상입고"
            row["billing_badge"] = "badge-teal"
        elif billing_type == "PROV_OUT":
            row["billing_label"] = "가출고"
            row["billing_badge"] = "text-bg-warning"
        else:
            row["billing_label"] = ""
            row["billing_badge"] = ""

        created_at = row.get("created_at")
        if created_at:
            try:
                # psycopg가 datetime 객체로 반환하는 경우
                if hasattr(created_at, "strftime"):
                    from datetime import timezone
                    if created_at.tzinfo is not None:
                        created_at = created_at.astimezone(timezone(timedelta(hours=9)))
                    else:
                        created_at = created_at + timedelta(hours=9)
                    row["created_at_display"] = created_at.strftime("%Y-%m-%d %H:%M")
                else:
                    # 문자열인 경우 앞 16자 (YYYY-MM-DD HH:MM) 만 사용
                    row["created_at_display"] = str(created_at).strip()[:16]
            except Exception:
                row["created_at_display"] = str(created_at)[:16]
        else:
            row["created_at_display"] = ""

        items.append(row)

    return items
