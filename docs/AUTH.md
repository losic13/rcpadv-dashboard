# 인증 — 단일 비밀번호 + 서명 쿠키 세션

본 문서는 PR #12 에서 추가된 로그인/세션 인증의 설계, 동작, 운영 시 주의점을 설명합니다.

## 1. 요구사항

- 사내 인하우스 도구 — **개별 사용자 식별이 불필요**.
- 비밀번호 한 개로 진입을 통제.
- 비밀번호 입력 페이지를 제공하고, 통과 시 세션을 부여.
- 미인증 사용자는 로그인 페이지로 리다이렉트.

## 2. 구성요소

| 파일 | 역할 |
|------|------|
| `app/config.py` | `APP_PASSWORD`, `SESSION_SECRET_KEY`, `SESSION_MAX_AGE`, `SESSION_COOKIE_NAME` 정의 |
| `app/main.py` | `SessionMiddleware` 등록 + `require_auth_middleware` 정의 |
| `app/routers/auth.py` | `/login` (GET/POST), `/logout` (GET/POST), `is_authenticated()`, `is_public_path()` |
| `app/templates/login.html` | 로그인 카드 UI (base.html 미상속, 독립 레이아웃) |
| `app/templates/_sidebar.html` | 사이드바 하단 로그아웃 버튼 |

## 3. 환경 변수

`app/config.py` 의 기본값:

```python
APP_PASSWORD: str = "changeme"
SESSION_SECRET_KEY: str = "dev-only-secret-please-override-in-env"
SESSION_MAX_AGE: int = 60 * 60 * 12        # 12 시간
SESSION_COOKIE_NAME: str = "rcpadv_session"
```

> **운영 배포 시 반드시 `.env` 에서 두 값을 교체**해야 합니다:
> - `APP_PASSWORD` — 사내에서 공유할 실제 비밀번호
> - `SESSION_SECRET_KEY` — 32바이트 이상의 랜덤 문자열 권장
>
> `SESSION_SECRET_KEY` 가 노출되면 누구든 임의의 세션 쿠키를 위조할 수 있습니다.

## 4. 미들웨어 등록 순서 (Starlette LIFO)

`main.py` 에서 의도적으로 다음 순서를 지킵니다:

```python
@app.middleware("http")            # ← (A) auth 미들웨어 (먼저 등록)
async def require_auth_middleware(request, call_next): ...

app.add_middleware(SessionMiddleware, ...)   # ← (B) Session (나중에 등록)
```

Starlette 는 등록 순서의 **역순으로 wrap** 하므로 실제 호출 순서는:

```
Client → SessionMiddleware → require_auth_middleware → Router → endpoint
```

이 순서가 중요한 이유:
- `require_auth_middleware` 안에서 `request.session.get(...)` 을 호출하려면
  `SessionMiddleware` 가 **외곽**에 있어야 합니다.
- 등록 순서를 뒤집으면 auth 안에서 `request.session` 접근 시
  `AssertionError: SessionMiddleware must be installed to access request.session` 발생.

## 5. 인증 결정 로직 (`require_auth_middleware`)

```
path 가 PUBLIC_PATH_PREFIXES 중 하나인가?
  ├─ YES → 그대로 통과
  └─ NO
       └─ request.session.get("authenticated") == True ?
            ├─ YES → 그대로 통과
            └─ NO
                 ├─ XHR (X-Requested-With: XMLHttpRequest)
                 │  또는 (Accept: application/json && !text/html)
                 │  → 401 JSON {"detail": "인증이 필요합니다. /login 에서 로그인하세요."}
                 └─ 그 외(브라우저 HTML 요청)
                    → 303 RedirectResponse → /login?next=<원래경로?쿼리스트링>
```

### 공개 경로 (`PUBLIC_PATH_PREFIXES`)

```python
PUBLIC_PATH_PREFIXES = (
    "/login",
    "/logout",
    "/static/",
    "/favicon",
)
```

- `/static/` 은 prefix 매치 (`startswith`).
- `/login`, `/logout` 은 정확 매치 또는 prefix 매치 (`/login?next=...` 도 통과).
- `/favicon` 은 일부 브라우저가 `/favicon.ico` 를 자동 요청하므로 차단되지 않게 둠.

## 6. 로그인 흐름

### 6.1 GET `/login`

```python
@router.get("/login")
def login_page(request, next="/", error=None):
    if is_authenticated(request):
        return RedirectResponse(url=next or "/", status_code=303)
    return templates.TemplateResponse(request, "login.html", {"next": ..., "error": ...})
```

- 이미 로그인된 상태라면 `next` 또는 `/` 로 즉시 리다이렉트.
- `next` 쿼리 파라미터는 미인증 미들웨어가 추가한 원래 경로.
- `error` 가 있으면 카드 상단에 "비밀번호가 올바르지 않습니다." 표시.

### 6.2 POST `/login`

```python
@router.post("/login")
def login_submit(request, password: str = Form(...), next: str = Form("/")):
    expected = settings.APP_PASSWORD or ""
    ok = hmac.compare_digest(password or "", expected)
    if not ok:
        return templates.TemplateResponse(... status_code=401)
    request.session["authenticated"] = True
    target = next or "/"
    if not target.startswith("/") or target.startswith("//"):
        target = "/"          # open redirect 방지
    return RedirectResponse(url=target, status_code=303)
```

핵심 포인트:

1. **상수시간 비교**: `hmac.compare_digest()` 로 타이밍 공격 회피.
2. **세션 부여**: `request.session["authenticated"] = True` 한 줄.
   `SessionMiddleware` 가 응답 시 `Set-Cookie: rcpadv_session=...` 자동 발행.
3. **Open redirect 방지**: `target` 이 `/` 로 시작하지 않거나 `//` (스킴-relative) 로
   시작하면 `/` 로 강제. 외부 URL 로 튕겨내지 못하도록.
4. **실패 시 401**: 단순 200 + 폼 재표시 대신 명시적 401 상태로 반환 → API 호출/스크립트가
   인지 가능.

### 6.3 로그아웃

```python
@router.get("/logout")
@router.post("/logout")
def logout(request):
    request.session.clear()
    return RedirectResponse(url="/login", status_code=303)
```

GET/POST 둘 다 받음 — 사이드바 버튼은 form POST 를 사용 (CSRF 측면에서 더 안전한 패턴).

## 7. 세션 저장 방식

`Starlette SessionMiddleware` 는 **stateless 서명 쿠키** 방식을 사용합니다.

- 서버 측 세션 저장소가 없음. 모든 세션 데이터는 쿠키 본문에 base64 인코딩된 JSON 으로 저장되고
  `itsdangerous` 로 서명됨.
- 쿠키 예시:
  ```
  rcpadv_session=eyJhdXRoZW50aWNhdGVkIjogdHJ1ZX0=.afBV9g.9fehHM47BJqo_dfq2-6IHALG_bA
                 ───────────base64 JSON──────── ─epoch─ ─────HMAC SHA1 서명─────
  ```
- 디코딩하면 `{"authenticated": true}`.

쿠키 속성:

| 속성 | 값 | 이유 |
|------|----|------|
| `HttpOnly` | True (Starlette 기본) | XSS 로 쿠키 탈취 방지 |
| `SameSite` | `lax` | CSRF 1차 방어 + 일반 네비게이션 허용 |
| `Max-Age` | `SESSION_MAX_AGE` (기본 12h) | 자동 만료 |
| `Secure` | False | 사내 HTTP 환경 허용 (HTTPS 리버스 프록시 뒤라면 `https_only=True` 권장) |
| `Path` | `/` | 모든 경로에 적용 |

> 사내가 아니라 외부에서 HTTPS 로 서비스하는 경우 `main.py` 의 `https_only=False` 를
> `True` 로 바꾸세요.

## 8. 보안 고려 사항

| 위험 | 완화 |
|------|------|
| 비밀번호 평문 비교 시 타이밍 공격 | `hmac.compare_digest()` 사용 |
| open redirect (`?next=//evil.com`) | `next.startswith("/") and not next.startswith("//")` 검증 |
| 세션 쿠키 탈취 | `HttpOnly` + (옵션) HTTPS + 짧은 `Max-Age` |
| 세션 위조 | `SESSION_SECRET_KEY` 서명. **운영에서 반드시 교체.** |
| 무차별 대입 | 현재 미구현 — 필요 시 IP/세션 단위 rate limiting 또는 fail2ban 권장 |
| CSRF (POST `/login`) | 인하우스 단일 PW 도구 + `SameSite=Lax` 로 1차 차단. 다중 사용자/외부 노출 시 CSRF 토큰 추가 권장 |
| 비밀번호 평문 저장 (`.env`) | 사내 신뢰 환경 가정. 외부 노출 시 secrets manager 도입 권장 |

## 9. 동작 검증 (수동 테스트)

서버 기동 후 (`uv run uvicorn app.main:app --port 8000`):

```bash
# 1) 미인증 — 보호된 페이지 접근 → 303
curl -s -o /dev/null -w "%{http_code} → %{redirect_url}\n" http://127.0.0.1:8000/
# 303 → http://127.0.0.1:8000/login?next=/

# 2) 미인증 XHR → 401
curl -s -o /dev/null -w "%{http_code}\n" -H "X-Requested-With: XMLHttpRequest" http://127.0.0.1:8000/api/logs
# 401

# 3) 잘못된 비밀번호 → 401
curl -s -o /dev/null -w "%{http_code}\n" -X POST http://127.0.0.1:8000/login -d "password=wrong&next=/"
# 401

# 4) 올바른 비밀번호 → 303 + Set-Cookie
curl -s -i -c /tmp/cj.txt -X POST http://127.0.0.1:8000/login -d "password=changeme&next=/" | head -10
# HTTP/1.1 303 See Other
# location: /
# set-cookie: rcpadv_session=...; path=/; Max-Age=43200; HttpOnly; SameSite=lax

# 5) 쿠키로 보호된 경로 접근 → 200
curl -s -o /dev/null -w "%{http_code}\n" -b /tmp/cj.txt http://127.0.0.1:8000/
# 200
```

## 10. 확장 가이드

### 10.1 다중 사용자 / 사용자명 추가

`request.session["authenticated"]` 외에 `request.session["user"] = "..."` 등을 추가:

```python
# auth.py
def is_authenticated(request) -> bool:
    return bool(request.session.get("authenticated"))

def current_user(request) -> str | None:
    return request.session.get("user")
```

라우터에서 `current_user(request)` 를 컨텍스트에 추가해 템플릿에 표시.

### 10.2 SSO / OAuth (Google, Azure AD 등)

- `Authlib` 또는 `fastapi-sso` 라이브러리를 추가.
- `/login` 라우트를 IdP 리다이렉트로 교체, `/auth/callback` 추가.
- 콜백에서 토큰/프로필 검증 후 동일하게 `request.session["authenticated"] = True` 만 세팅.
- `require_auth_middleware` 는 변경 불필요 (인증 *판단* 만 본다).

### 10.3 서버 사이드 세션 저장소

- 서명 쿠키 방식 → Redis 백엔드로 변경하려면 `Starlette SessionMiddleware` 대신
  `starsessions` 등 외부 라이브러리를 도입.
- 즉시 세션 무효화(로그아웃 전체) 기능이 필요할 때 유용.

### 10.4 비밀번호 회전

`.env` 의 `APP_PASSWORD` 만 변경 후 앱 재시작. 기존 세션 쿠키는 `SESSION_MAX_AGE` 까지
유효 (인증 판단은 쿠키만 확인하기 때문). 세션도 즉시 무효화하려면
`SESSION_SECRET_KEY` 도 함께 회전.

## 11. 트러블슈팅

| 증상 | 원인 / 해결 |
|------|------------|
| 로그인 후에도 계속 `/login` 으로 리다이렉트 | 쿠키 차단/`SameSite` 이슈. 브라우저 개발자도구 → Application → Cookies 에서 `rcpadv_session` 확인. 리버스 프록시가 `Set-Cookie` 헤더를 잘라먹지 않는지 확인. |
| `AssertionError: SessionMiddleware must be installed` | 미들웨어 등록 순서 문제. `auth → session` 순으로 add 했는지 확인. |
| 401 만 떨어지고 페이지가 안 뜸 | API 클라이언트가 `Accept: application/json` 만 보내는 경우. 브라우저는 `text/html` 도 함께 보내므로 정상 동작. |
| 운영에서 비밀번호가 안 먹힘 | `.env` 에 `APP_PASSWORD` 가 정확히 적용됐는지 — `app.config.settings.APP_PASSWORD` 출력해 확인. uv 가 .env 를 인식하는 작업 디렉토리에서 실행하는지 확인 (`run.sh` 사용 시 cwd 가 webapp 루트). |

## 12. 관련 문서

- 전체 미들웨어 체인: [ARCHITECTURE.md §3.1](./ARCHITECTURE.md#31-미들웨어-체인-starlette-lifo-등록-규칙)
- `.env` 키 전체 목록: [DEVELOPMENT.md](./DEVELOPMENT.md)
- 이 기능이 추가된 PR: [CHANGELOG.md — PR #12](./CHANGELOG.md)
