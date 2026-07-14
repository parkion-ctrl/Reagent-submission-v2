from app.core.db import set_schema
from app.utils.constants import DEPT_SCHEMA_MAP


class DepartmentSchemaMiddleware:
    """
    요청마다 로그인 사용자의 부서에 맞는 PostgreSQL 스키마를
    thread-local에 설정합니다.
    슈퍼유저는 세션의 'superuser_active_dept'를 우선합니다.
    """

    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        schema = None
        if request.user.is_authenticated:
            if request.user.is_superuser:
                if "superuser_active_dept" not in request.session:
                    request.session["superuser_active_dept"] = "진단검사의학과"
                active_dept = request.session.get("superuser_active_dept", "진단검사의학과")
                schema = DEPT_SCHEMA_MAP.get(active_dept, "dlab")
            else:
                try:
                    dept = request.user.profile.department
                    schema = DEPT_SCHEMA_MAP.get(dept)
                except Exception:
                    pass
        set_schema(schema)
        response = self.get_response(request)
        set_schema(None)
        return response
