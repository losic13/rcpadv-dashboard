"""개발자 user_id 화이트리스트.

============================================================
사용자(운영자)가 직접 수정하는 파일입니다.
============================================================

목적:
  "사용자 접속 이력" 페이지(/login-history)에서, 고객 접속 통계만
  보고 싶을 때 **이 리스트에 들어 있는 user_id 들의 로그인은 차트에서
  제외**한다. 전체(개발자 포함) 차트와 고객만(개발자 제외) 차트를
  나란히 보여주기 위해 필요한 정보.

수정 방법:
  1) 아래 DEVELOPER_USER_IDS 리스트에 user_id 를 추가/삭제한다.
  2) 서버를 재시작한다. 끝.

매칭 정책:
  - 정확 일치(case-insensitive). 예: "Alice" 와 "alice" 는 동일하게 처리.
  - 와일드카드/접두사 매칭은 의도적으로 제외 — 운영 중 의도치 않은 ID 가
    개발자로 잡히는 사고를 막기 위함.
  - 공백, 빈 문자열은 무시한다.
"""
from __future__ import annotations

# ------------------------------------------------------------
# 이 곳을 직접 편집하세요.
# ------------------------------------------------------------
DEVELOPER_USER_IDS: list[str] = [
    # 예시:
    # "alice",
    # "bob.kim",
    # "dev01",
]


# ------------------------------------------------------------
# 내부 유틸 (서비스 단계에서 사용)
# ------------------------------------------------------------
def _normalize(uid: str | None) -> str:
    """user_id 정규화: 양끝 공백 제거 + 소문자."""
    if uid is None:
        return ""
    return str(uid).strip().lower()


def get_developer_id_set() -> set[str]:
    """정규화된(소문자) 개발자 user_id 집합. 비어 있을 수 있다."""
    out: set[str] = set()
    for raw in DEVELOPER_USER_IDS:
        norm = _normalize(raw)
        if norm:
            out.add(norm)
    return out


def is_developer(user_id: str | None) -> bool:
    """user_id 가 개발자 화이트리스트에 속하는지 여부."""
    if user_id is None:
        return False
    return _normalize(user_id) in get_developer_id_set()
