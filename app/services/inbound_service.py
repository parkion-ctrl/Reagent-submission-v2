from app.services.transaction_service import (
    confirm_bulk_transaction_items,
    get_today_text,
    get_transaction_table_items,
    get_transaction_filter_options,
    preview_manual_transaction_items,
    preview_bulk_transaction_items,
)


def get_inbound_page_data(q: str = "", part: str = "", sort: str = "", order: str = "", equipment: str = "", reagent_type: str = ""):
    return {
        "items": get_transaction_table_items(tx_type="IN", q=q, part=part, sort=sort, order=order, equipment=equipment, reagent_type=reagent_type),
        "today": get_today_text(),
        **get_transaction_filter_options(part=part),
    }


def preview_bulk_inbound_items(df):
    return preview_bulk_transaction_items(tx_type="IN", df=df)


def create_bulk_inbound_transactions(rows: list[dict], created_by: str = "", created_by_empno: str = ""):
    return confirm_bulk_transaction_items(tx_type="IN", rows=rows, created_by=created_by, created_by_empno=created_by_empno)


def preview_manual_inbound_items(rows: list[dict]):
    return preview_manual_transaction_items(tx_type="IN", rows=rows)
