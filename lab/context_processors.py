from app.utils.constants import DEPT_SCHEMA_MAP

DEPT_LIST = list(DEPT_SCHEMA_MAP.keys())  # ['진단검사의학과', '병리과', '핵의학과', '유해물질']


def user_department(request):
    if not request.user.is_authenticated:
        return {
            "user_department": "기타",
            "is_superuser_session": False,
            "superuser_dept_list": [],
            "is_dlab": False,
        }

    if request.user.is_superuser:
        active_dept = request.session.get("superuser_active_dept", "진단검사의학과")
        schema = DEPT_SCHEMA_MAP.get(active_dept, "dlab")
        return {
            "user_department": active_dept,
            "is_superuser_session": True,
            "superuser_dept_list": DEPT_LIST,
            "is_dlab": schema == "dlab",
        }

    try:
        dept = request.user.profile.department
        schema = DEPT_SCHEMA_MAP.get(dept)
        return {
            "user_department": dept if dept else "기타",
            "is_superuser_session": False,
            "superuser_dept_list": [],
            "is_dlab": schema == "dlab",
        }
    except Exception:
        return {
            "user_department": "기타",
            "is_superuser_session": False,
            "superuser_dept_list": [],
            "is_dlab": False,
        }
