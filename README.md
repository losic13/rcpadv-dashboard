# 사내 대시보드 (Dashboard)

VNAND DB / DRAM DB (MariaDB) / Elasticsearch 데이터를 한 곳에서 조회하는 인하우스 대시보드.

## 스택

- **Backend**: FastAPI + Uvicorn
- **Frontend**: Jinja2 (SSR) + Bootstrap 5 + DataTables + 순수 fetch JS
- **Data**: MariaDB (VNAND, DRAM), Elasticsearch 8.15.1
- **Python**: 3.11+
- **패키지 관리**: uv

## 디렉토리 구조

```
webapp/
├── app/
│   ├── main.py              앱 부트스트랩
│   ├── config.py            .env 로드
│   ├── logger.py            파일 + 인메모리 로거
│   ├── routers/             URL 라우팅 (얇음)
│   ├── services/            비즈니스 로직 (쿼리 실행/가공)
│   ├── repositories/        DB/ES 커넥션 관리
│   ├── queries/             쿼리 상수 정의
│   ├── templates/           Jinja2 템플릿
│   └── static/              CSS/JS/벤더 라이브러리
├── logs/
├── .env.example
├── pyproject.toml
└── run.sh
```

### 계층별 책임

| 계층 | 책임 |
|------|------|
| `routers` | URL 매핑 + 템플릿 렌더링 (얇게) |
| `services` | 쿼리 선택, 결과 가공, 시간 측정 |
| `repositories` | 커넥션/엔진/클라이언트 관리, 실행 |
| `queries` | 쿼리 상수 보관 (Python 상수) |

## 새 쿼리 추가하기

`app/queries/<source>_queries.py` 의 `QUERIES` 딕셔너리에 항목 하나 추가하면 끝.

```python
QUERIES["my_new_query"] = QueryDef(
    id="my_new_query",
    title="내가 만든 새 쿼리",
    sql="SELECT ...",
    show_in_dashboard=True,   # 통합 대시보드에 카드로 노출
)
```

## 설치 및 실행

```bash
# 1. uv 설치 (없으면)
curl -LsSf https://astral.sh/uv/install.sh | sh

# 2. 의존성 설치
uv sync

# 3. 환경 변수
cp .env.example .env
vi .env

# 4. 시작 / 중지
./run.sh start
./run.sh stop
./run.sh status
./run.sh restart
```

브라우저: `http://<서버>:8000/`

## 주요 동작

- **수동 새로고침** 버튼 / **자동갱신**(10초) 체크박스 (기본 OFF)
- **쿼리 실행시간 표시**, 진행 중 스피너
- **DataTables** 정렬/검색/페이징/CSV 내보내기
- **로그 패널**(하단, 접기/펼치기) — 인메모리 최근 N개 표시
- **쿼리 타임아웃** 10분
- **DB 커넥션 풀** SQLAlchemy 기본 (size=5)
