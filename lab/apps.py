from django.apps import AppConfig


class LabConfig(AppConfig):
    name = 'lab'

    def ready(self):
        try:
            from app.core.db import init_all_schemas
            init_all_schemas()
        except Exception:
            # DB 연결 실패 시 서버 시작을 막지 않음
            pass
