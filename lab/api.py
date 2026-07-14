from django.contrib.auth import authenticate
from ninja import NinjaAPI, Schema

from app.core.db import get_connection
from app.services.inventory_service import get_inventory_filter_options, get_inventory_items
from app.services.outbound_service import create_bulk_outbound_transactions
from app.services.transaction_service import find_inventory_row, get_today_text
from app.utils.constants import get_part_map
from lab.auth import JWTAuth, create_access_token, create_refresh_token, decode_token, schema_for_user

api = NinjaAPI(title="Reagent API")

jwt_auth = JWTAuth()


@api.get("/health")
def health(request):
    return {"status": "ok"}


class LoginIn(Schema):
    username: str
    password: str


class RefreshIn(Schema):
    refresh: str


class DispenseIn(Schema):
    inventory_id: int
    qty: int


class BarcodeConfirmIn(Schema):
    qr_content: str


def _user_payload(user):
    profile = getattr(user, "profile", None)
    return {
        "username": user.username,
        "name": user.get_full_name() or user.username,
        "department": getattr(profile, "department", ""),
        "part": getattr(profile, "part", ""),
        "employee_no": getattr(profile, "employee_no", ""),
        "is_superuser": user.is_superuser,
    }


@api.post("/auth/login")
def login(request, payload: LoginIn):
    user = authenticate(request, username=payload.username, password=payload.password)
    if user is None or not user.is_active:
        return api.create_response(request, {"detail": "아이디 또는 비밀번호가 올바르지 않습니다."}, status=401)
    return {
        "access": create_access_token(user.id),
        "refresh": create_refresh_token(user.id),
        "user": _user_payload(user),
    }


@api.post("/auth/refresh")
def refresh(request, payload: RefreshIn):
    try:
        data = decode_token(payload.refresh)
        if data.get("type") != "refresh":
            raise ValueError("invalid token type")
    except Exception:
        return api.create_response(request, {"detail": "리프레시 토큰이 유효하지 않습니다."}, status=401)
    return {"access": create_access_token(data["user_id"])}


@api.get("/auth/me", auth=jwt_auth)
def me(request):
    return _user_payload(request.user)


@api.get("/parts", auth=jwt_auth)
def parts(request):
    return get_part_map(schema_for_user(request.user))


@api.get("/inventory/filters", auth=jwt_auth)
def inventory_filters(request):
    options = get_inventory_filter_options()
    return {
        "reagent_types": options["reagent_types"],
        "vendors": [v for v in options["vendors"] if v != "__BLANK__"],
    }


@api.get("/inventory", auth=jwt_auth)
def inventory_list(
    request,
    q: str = "",
    part: str = "",
    sort: str = "",
    order: str = "",
    reagent_type: str = "",
    vendor: str = "",
    limit: int = 1000,
):
    items = get_inventory_items(part=part, q=q, sort=sort, order=order, reagent_type=reagent_type, vendor=vendor)
    return items[: max(1, min(limit, 1000))]


@api.post("/dispense", auth=jwt_auth)
def dispense(request, payload: DispenseIn):
    user = request.user
    created_by = user.get_full_name() or user.username
    created_by_empno = getattr(getattr(user, "profile", None), "employee_no", "") or ""

    ok, message = create_bulk_outbound_transactions(
        [{"inventory_id": payload.inventory_id, "qty": payload.qty, "tx_date": get_today_text()}],
        created_by=created_by,
        created_by_empno=created_by_empno,
    )
    if not ok:
        return api.create_response(request, {"detail": message}, status=400)
    return {"detail": message}


def _parse_qr_content(qr_content: str):
    parts = qr_content.split("|")
    if len(parts) < 2 or not parts[0] or not parts[1]:
        return None, None
    return parts[0], parts[1]


@api.get("/barcode/lookup", auth=jwt_auth)
def barcode_lookup(request, qr_content: str):
    item_code, lot_no = _parse_qr_content(qr_content)
    if not item_code:
        return api.create_response(request, {"detail": "인식할 수 없는 QR입니다."}, status=400)

    conn = get_connection()
    cursor = conn.cursor()
    row = find_inventory_row(cursor, "OUT", item_code, lot_no)
    conn.close()
    if not row:
        return api.create_response(request, {"detail": "해당 품목/Lot의 재고를 찾을 수 없습니다."}, status=404)

    item = dict(row)
    return {
        "item_code": item["item_code"],
        "item_name": item["item_name"],
        "lot_no": item["lot_no"],
        "unit": item.get("unit", ""),
        "expiry_date": item.get("expiry_date", ""),
        "current_stock": item.get("current_stock", 0),
    }


@api.post("/barcode/confirm", auth=jwt_auth)
def barcode_confirm(request, payload: BarcodeConfirmIn):
    item_code, lot_no = _parse_qr_content(payload.qr_content)
    if not item_code:
        return api.create_response(request, {"detail": "인식할 수 없는 QR입니다."}, status=400)

    conn = get_connection()
    cursor = conn.cursor()
    row = find_inventory_row(cursor, "OUT", item_code, lot_no)
    conn.close()
    if not row:
        return api.create_response(request, {"detail": "해당 품목/Lot의 재고를 찾을 수 없습니다."}, status=404)

    item = dict(row)
    user = request.user
    created_by = user.get_full_name() or user.username
    created_by_empno = getattr(getattr(user, "profile", None), "employee_no", "") or ""

    ok, message = create_bulk_outbound_transactions(
        [{"inventory_id": item["id"], "qty": 1, "tx_date": get_today_text()}],
        created_by=created_by,
        created_by_empno=created_by_empno,
    )
    if not ok:
        return api.create_response(request, {"detail": message}, status=400)
    return {"detail": f"{item['item_name']} 출고 완료"}
