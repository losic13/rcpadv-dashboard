# EQP I/F Manager (`/eqp-if`)

> PR #20 에서 신규. PR #21 에서 카드 제목/버튼 정리 + content max-width 해제.

## 1. 무엇을 하는 페이지인가

외부 EQP I/F Manager 사이트를 **iframe** 으로 임베드하여, 사이드바 메뉴 한 번으로
같은 인증 세션 안에서 접근 가능하게 한다. (별도 새 탭/창을 열지 않음으로써
"한 화면에서 모니터링" 흐름을 유지)

## 2. 라우트

```
GET /eqp-if           (HTML 페이지, iframe 포함)
```

별도의 JSON API 없음. 외부 사이트와는 **표준 HTTP 만** 으로 상호작용 — 본 앱은
프록시/리버스프록시를 하지 *않는다*.

## 3. 구성

```
app/routers/eqp_if.py
   └─ GET /eqp-if  → templates/eqp_if.html  (settings.EQP_IF_MANAGER_URL 주입)

app/templates/eqp_if.html
   └─ <iframe src="{{ url }}" style="width:100%; height: calc(100vh - <header>)">

app/config.py
   └─ EQP_IF_MANAGER_URL: str = "https://www.google.com"  (placeholder)
   └─ EQP_IF_MANAGER_TITLE: str = "EQP I/F Manager"
```

## 4. 환경 변수

| 변수 | 기본값 | 의미 |
|------|--------|------|
| `EQP_IF_MANAGER_URL` | `https://www.google.com` | iframe 의 `src`. 운영 환경에서 실제 URL 로 교체. |
| `EQP_IF_MANAGER_TITLE` | `EQP I/F Manager` | 페이지/카드 헤더에 표시될 라벨. |

`.env` 또는 `app/config.py` 의 `Settings` 로 주입.

## 5. iframe 임베드 가능 여부 — 중요

iframe 임베드는 **외부 서버의 응답 헤더에 좌우** 됩니다.

| 외부 서버 헤더 | 결과 |
|---------------|------|
| `X-Frame-Options: DENY` | 임베드 불가 |
| `X-Frame-Options: SAMEORIGIN` | 다른 도메인이면 임베드 불가 |
| `Content-Security-Policy: frame-ancestors 'none'` | 임베드 불가 |
| `Content-Security-Policy: frame-ancestors '<our-host>'` | 가능 |
| (헤더 없음 / `ALLOW-FROM ...`) | 가능(브라우저별 차이) |

→ 운영 도입 전 반드시 *대상 사이트의 응답 헤더* 를 확인하고, 거부되면
관리자에게 화이트리스트 협조 요청. 그래도 막히면 fallback 으로 *외부 링크 버튼*
(`target="_blank"`) 을 노출하도록 페이지를 보완할 것.

> 본 저장소의 PR 본문에 "임베드 거부 시 fallback 으로 외부 링크 안내 + 새 탭 버튼"
> 이라는 메모가 있음. 현재는 placeholder URL 로 되어 있으니, 운영 URL 교체와 함께
> fallback 분기 구현 여부를 확인할 것.

## 6. 인증/세션

- `/eqp-if` 자체는 본 앱의 **로그인 필요 경로** (PUBLIC_PATH_PREFIXES 에 없음).
- 외부 EQP I/F Manager 의 인증은 *외부* 의 정책. 같은 도메인이거나 SSO 로 통합되어
  있지 않다면 iframe 안에서 별도 로그인 화면이 보일 수 있음.

## 7. UX/스타일 (PR #21 변경 반영)

- 페이지 본문의 `max-width` 를 *제거* — iframe 이 가로 100% 를 사용하도록.
  대시보드 등 다른 페이지의 `max-width` 와 다르므로, 카드 안에 iframe 을 넣는
  대신 페이지 레벨에서 너비를 풀어 둠.
- 카드 헤더 라벨/버튼을 정리 (불필요한 "새로고침" 버튼 제거 — iframe 자체의
  네이티브 navigation 을 사용).

## 8. 수정 포인트 표

| 원하는 변경 | 파일 | 위치 |
|-----------|------|------|
| 임베드 URL 변경 | `.env` 또는 `app/config.py` | `EQP_IF_MANAGER_URL` |
| 페이지/카드 라벨 변경 | `.env` 또는 `app/config.py` | `EQP_IF_MANAGER_TITLE` |
| iframe 높이 / 풀스크린 토글 | `app/templates/eqp_if.html` | iframe inline style |
| 임베드 거부 시 fallback 안내 | `app/templates/eqp_if.html` | (구현 추가 필요) |
| 사이드바 표시 위치/숨김 | `app/routers/_templating.py` | `NAV_ITEMS` (현재 표시) |

## 9. 보안 고려

- iframe 안의 외부 사이트는 본 앱과 *다른 origin* 이므로, 우리 페이지의 JS 가
  iframe 내부 DOM 에 접근할 수 없다 (Same-Origin Policy). 의도된 동작.
- `sandbox` 속성을 걸지 않고 있다 — 외부 사이트가 신뢰된 사내 시스템이라는 전제.
  외부 인터넷 사이트로 변경 시 `sandbox="allow-scripts allow-forms allow-same-origin"`
  등 최소 권한으로 제한할 것.

## 10. 관련 PR

- PR #20 페이지 신규
- PR #21 카드 제목/버튼 정리 + content max-width 해제
