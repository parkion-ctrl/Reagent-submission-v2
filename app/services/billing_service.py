from collections import defaultdict

from app.core.db import get_connection, get_current_schema
from app.utils.constants import get_part_map


def get_billing_items(month: str = "", part: str = "", date_from: str = "", date_to: str = ""):
    """
    청구용 이력 조회 (항목별 합산).

    버퍼 로직 (inventory_id 단위, 시간순):
      - FREE_IN : 청구 제외, out_buffer += qty
      - PROV_OUT: 청구 포함, out_buffer += qty
      - 일반 OUT : special_occurred 이후라면 out_buffer 에서 차감, 초과분만 청구
      - 일반 IN  : 그대로 청구
    """
    conn = get_connection()
    cursor = conn.cursor()

    # FREE_IN 도 버퍼 계산을 위해 포함하여 전체 조회 (날짜 필터 없음)
    query = """
        SELECT
            th.id, th.inventory_id, th.tx_type, th.qty, th.tx_date,
            th.item_code, th.item_name, th.lot_no, th.part, th.unit, th.billing_type,
            inv.vendor,
            rr.unit_price
        FROM transaction_history th
        LEFT JOIN inventory inv ON inv.id = th.inventory_id
        LEFT JOIN public.raw_db rr ON rr.item_code = th.item_code AND rr.part = th.part
        WHERE 1=1
    """
    params = []
    if part:
        query += " AND th.part = ?"
        params.append(part)

    query += " ORDER BY th.tx_date ASC, th.id ASC"
    cursor.execute(query, params)
    all_rows = cursor.fetchall()
    conn.close()

    # 버퍼 계산
    out_buffer = {}       # inventory_id -> 남은 버퍼 (FREE_IN + PROV_OUT 합산)
    special_occurred = {} # inventory_id -> FREE_IN 또는 PROV_OUT 발생 여부

    processed = []
    for row in all_rows:
        row = dict(row)
        inv_id = row["inventory_id"]
        qty = int(row["qty"] or 0)
        billing_type = row.get("billing_type") or ""
        tx_type = row["tx_type"]

        if billing_type == "STOCK_ADJUST":
            row["billing_qty"] = 0

        elif billing_type == "FREE_IN":
            # 무상입고: 청구 안 함, 버퍼에 추가
            out_buffer[inv_id] = out_buffer.get(inv_id, 0) + qty
            special_occurred[inv_id] = True
            row["billing_qty"] = 0

        elif billing_type == "PROV_OUT":
            # 가출고: 청구 포함, 버퍼에 추가
            out_buffer[inv_id] = out_buffer.get(inv_id, 0) + qty
            special_occurred[inv_id] = True
            row["billing_qty"] = qty

        elif tx_type == "OUT":
            if special_occurred.get(inv_id, False):
                buf = out_buffer.get(inv_id, 0)
                overflow = qty - buf
                out_buffer[inv_id] = max(0, buf - qty)
                row["billing_qty"] = max(0, overflow)
            else:
                row["billing_qty"] = qty

        else:
            # 일반 입고: 그대로 청구
            row["billing_qty"] = qty

        processed.append(row)

    # 조회 월 필터 + billing_qty 0 제거 후 품목코드별 합산 (LOT 구분 없음)
    part_map = get_part_map(get_current_schema())
    agg = {}  # (item_code, tx_type) -> dict

    for row in processed:
        tx_date = row["tx_date"][:10] if row["tx_date"] else ""
        if date_from and tx_date < date_from:
            continue
        if date_to and tx_date > date_to:
            continue
        if not date_from and not date_to and month and not row["tx_date"].startswith(month):
            continue
        if row["billing_qty"] == 0:
            continue

        tx_type = row["tx_type"]
        billing_type = row.get("billing_type") or ""
        key = (row["item_code"], tx_type)

        if key not in agg:
            part_code = str(row.get("part", "")).strip()
            part_name = part_map.get(part_code, "")
            agg[key] = {
                "tx_type": tx_type,
                "item_code": row["item_code"],
                "item_name": row["item_name"],
                "part": part_code,
                "part_label": f"{part_code} ({part_name})" if part_name else part_code,
                "unit": row["unit"],
                "vendor": row.get("vendor") or "",
                "unit_price": row.get("unit_price"),
                "total_qty": 0,
                "prov_qty": 0,
                "real_qty": 0,
            }

        agg[key]["total_qty"] += row["billing_qty"]
        if billing_type == "PROV_OUT":
            agg[key]["prov_qty"] += row["billing_qty"]
        elif tx_type == "OUT":
            agg[key]["real_qty"] += row["billing_qty"]

    # 표시용 필드 생성
    items = []
    for (item_code, tx_type), row in agg.items():
        if tx_type == "IN":
            row["tx_type_label"] = "입고"
            row["tx_badge_class"] = "text-bg-primary"
            row["note"] = ""
        else:
            prov = row["prov_qty"]
            real = row["real_qty"]
            if prov > 0 and real > 0:
                row["tx_type_label"] = "출고"
                row["tx_badge_class"] = "text-bg-secondary"
                row["note"] = f"가출고 {prov}개, 추가 출고 {real}개"
            elif prov > 0:
                row["tx_type_label"] = "가출고"
                row["tx_badge_class"] = "text-bg-warning"
                row["note"] = ""
            else:
                row["tx_type_label"] = "출고"
                row["tx_badge_class"] = "text-bg-secondary"
                row["note"] = ""
        row["qty_display"] = row["total_qty"]
        up = row.get("unit_price")
        row["cost"] = int(up) * row["total_qty"] if up is not None else None
        items.append(row)

    return items
