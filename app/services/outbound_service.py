from app.services.transaction_service import (
    confirm_bulk_transaction_items,
    get_today_text,
    get_transaction_table_items,
    get_transaction_filter_options,
    preview_manual_transaction_items,
    preview_bulk_transaction_items,
)


def get_outbound_page_data(q: str = "", part: str = "", sort: str = "", order: str = "", equipment: str = "", reagent_type: str = ""):
    return {
        "items": get_transaction_table_items(tx_type="OUT", q=q, part=part, sort=sort, order=order, equipment=equipment, reagent_type=reagent_type),
        "today": get_today_text(),
        **get_transaction_filter_options(part=part),
    }


def preview_bulk_outbound_items(df):
    return preview_bulk_transaction_items(tx_type="OUT", df=df)


def create_bulk_outbound_transactions(rows: list[dict], created_by: str = "", created_by_empno: str = ""):
    return confirm_bulk_transaction_items(tx_type="OUT", rows=rows, created_by=created_by, created_by_empno=created_by_empno)


def preview_manual_outbound_items(rows: list[dict]):
    return preview_manual_transaction_items(tx_type="OUT", rows=rows)
