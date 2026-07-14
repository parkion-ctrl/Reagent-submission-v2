# 시약 관리 시스템 (Reagent)

병원 부서별(진단검사의학과/병리과/핵의학과/유해물질) 시약 입출고, 재고, 이력 관리를
위한 Django 기반 웹 애플리케이션. Flutter 모바일 앱(`mobile/`)과 JWT 기반 API로 연동됩니다.

## 요구 사항

- **Python 3.10 이상** (개발 환경: 3.14.5. `str | None` 문법을 사용하므로 3.10 미만은 동작하지 않음)
- **PostgreSQL** (개발 환경: 18.3. PG 전용 기능은 쓰지 않으므로 14 이상이면 대부분 호환)

## 설치 및 실행

1. Python, PostgreSQL 설치
2. 빈 데이터베이스 생성
   ```
   psql -U postgres -c "CREATE DATABASE reagent;"
   ```
3. 의존 패키지 설치
   ```
   pip install -r requirements.txt
   ```
4. 환경설정 파일 생성 (`.env.example`을 복사해서 `.env`로 만들고 값 채우기)
   ```
   REAGENT_SECRET_KEY=<임의의 긴 랜덤 문자열>
   REAGENT_PGDATABASE=reagent
   REAGENT_PGUSER=postgres
   REAGENT_PGPASSWORD=<실제 DB 비밀번호>
   REAGENT_PGHOST=localhost
   REAGENT_PGPORT=5432
   REAGENT_DEBUG=False
   ```
5. Django 자체 테이블(로그인/권한) 생성
   ```
   python manage.py migrate
   ```
6. 정적 파일 배포 (CSS/JS/이미지)
   ```
   python manage.py collectstatic
   ```
7. 서버 실행
   ```
   python run_server.py
   ```
   또는 `start_server.bat`을 실행해도 됩니다 (PostgreSQL 서비스 시작 →
   Anaconda 가상환경 활성화 → `run_server.py`를 백그라운드로 실행까지
   한 번에 처리).

   부서별 스키마(`dlab`/`path`/`nm`/`haz`)와 테이블은 서버가 처음 뜰 때
   `lab/apps.py`에서 자동으로 생성됩니다. 로그인 계정은 Django 관리자
   페이지(`/admin/`)에서 만들 수 있습니다 (최초 관리자는 `python manage.py
   createsuperuser`로 생성).

## 모바일 앱

`mobile/` 폴더는 Flutter 프로젝트입니다. API 서버 주소는
`mobile/lib/config.dart`의 `API_BASE_URL`로 지정하며, 빌드 시
`--dart-define=API_BASE_URL=...` 로 덮어쓸 수 있습니다.

**현재는 플레이스토어/TestFlight 같은 배포 채널이 없어서, PC에 휴대폰을
USB로 연결한 뒤 `flutter run` 또는 `flutter install`로 직접 설치하는
방법만 가능합니다.** (릴리즈 서명 설정도 아직 비어있어 디버그 키로만
빌드됩니다 - `mobile/android/app/build.gradle.kts` 참고)

## 배포용 스크립트

- `run_server.py` / `start_server.bat`: waitress로 0.0.0.0:8000에서 서비스 시작
- `pg_backup.bat` / `register_backup_task.ps1`: 매일 자동 DB 백업 (Windows 작업 스케줄러)
- `kill_server.bat`: 실행 중인 서버(8000 포트) 종료
