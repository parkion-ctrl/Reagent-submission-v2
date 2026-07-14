DEPT_SCHEMA_MAP = {
    "진단검사의학과": "dlab",
    "병리과": "path",
    "핵의학과": "nm",
    "유해물질": "haz",
}

PART_MAP = {
    "HE": "진단혈액",
    "TA": "자동화학",
    "BB": "혈액은행",
    "ML": "임상미생물",
    "IM": "진단면역",
    "CO": "특수분자",
    "PB": "접수채혈",
    "ZZ": "기타",
}


def get_part_map(schema=None) -> dict:
    """DB의 Part 테이블에서 파트 맵을 반환. 실패 시 기본값 사용.
    dlab(schema=None 또는 "dlab") → schema_name=NULL 파트 반환
    path/nm/haz → 해당 schema_name 파트 반환
    """
    # dlab은 DB에 schema_name=NULL로 저장됨
    db_schema = None if (schema is None or schema == "dlab") else schema
    try:
        from lab.models import Part
        qs = Part.objects.filter(schema_name=db_schema)
        parts = dict(qs.values_list("code", "name"))
        if parts:
            return parts
    except Exception:
        pass
    if db_schema is None:
        return dict(PART_MAP)
    return {"ZZ": "기타"}

REAGENT_TYPE_MAP = {
    "1": "Reagent",
    "2": "Control",
    "3": "Calibrator",
    "4": "Supply",
    "5": "Extra",
}
