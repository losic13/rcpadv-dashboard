# `/.well-known/*` 핸들러

> PR #30 에서 신규.

## 1. 왜 필요했나

Chrome 계열 브라우저의 DevTools 가 페이지를 열 때마다 자동으로 다음 경로를 호출:

```
GET /.well-known/appspecific/com.chrome.devtools.json
```

본 앱은 인증 미들웨어가 *모든* 요청을 가로채 미정의 경로는 401/303 으로 떨어뜨리고,
해당 경로 자체도 정의되지 않아 404 가 함께 발생 → **개발 콘솔/서버 로그에 빨간
noise 가 누적**. 디버깅 시 진짜 에러를 찾기 어려워짐.

## 2. 어떻게 처리했나

1. **신규 라우터** `app/routers/well_known.py`
   - `prefix="/.well-known"`, `include_in_schema=False` (OpenAPI 에서 숨김)
   - `GET /appspecific/com.chrome.devtools.json` → **204 No Content** 로 조용히 응답.
   - 그 외 `/.well-known/*` 는 정의되지 않음 → FastAPI 의 정상 404 (글로벌 swallow 가 아님).

2. **인증 우회**
   - `app/routers/auth.py::PUBLIC_PATH_PREFIXES` 에 `"/.well-known/"` 추가.
   - 미인증 상태에서도 204 가 그대로 도달하도록.

3. **main.py**
   - `app.include_router(well_known.router)` 등록 (다른 라우터와 동일).

## 3. 검증

| 요청 | 미인증 | 인증 후 |
|------|--------|---------|
| `GET /.well-known/appspecific/com.chrome.devtools.json` | 204 | 204 |
| `GET /.well-known/security.txt` (미정의) | 404 | 404 |
| `GET /.well-known/anything-else` | 404 | 404 |

→ 의도된 경로만 무음 처리, 다른 well-known 경로는 정상 404 로 *명시적 미지원* 신호.

## 4. 다른 well-known 경로를 추가하고 싶다면

예: `security.txt` 를 노출.

```python
# app/routers/well_known.py 에 추가
@router.get("/security.txt", include_in_schema=False)
def security_txt():
    return PlainTextResponse(
        "Contact: mailto:secops@example.com\n"
        "Expires: 2027-01-01T00:00:00Z\n",
        media_type="text/plain",
    )
```

별도의 인증 우회 작업은 *불필요* — 이미 `PUBLIC_PATH_PREFIXES` 에 `"/.well-known/"`
가 있으므로 모든 하위 경로가 인증을 통과한다.

## 5. 보안 메모

- `PUBLIC_PATH_PREFIXES` 에 `"/.well-known/"` 를 추가했으므로, 이 prefix 아래에는
  **민감 정보를 절대 두지 말 것**. (예: `/.well-known/internal-config` 같은 경로 사용 금지)
- well-known 은 *공개 메타데이터* 를 위한 IANA 레지스트리 prefix. 의도된 용도 외
  사용은 보안 사고로 이어질 수 있음.

## 6. 관련 PR

- PR #30 — `/.well-known/appspecific/com.chrome.devtools.json` 204 응답
