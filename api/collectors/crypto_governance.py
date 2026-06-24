"""DAO 거버넌스 제안/투표 라이브 피드 — 코인판 "공시" (주식 공시피드 대응).

주요 DAO 의 현재 열린 거버넌스 제안(투표 진행 중)을 구조화 수집한다.
LLM·CoinGecko 가 못 가지는 구조화 cron 자산 — title/메타 팩트만 적재.

🚨 RULE 6 (LLM narrative STOP): title/space/state/투표 메타만. LLM 요약·sentiment·prose 0.
   choices/scores/votes 는 온체인 집계 그대로(2차 가공 없음).

소스: Snapshot Hub GraphQL  https://hub.snapshot.org/graphql  (무인증, MIT/IPFS 기반 off-chain 투표 허브)
      https://github.com/snapshot-labs/snapshot.js  (라이선스 MIT)
      proposal 링크 = https://snapshot.org/#/{space_id}/proposal/{id}  (실호출 200 확인)

스키마/링크 실호출 검증 완료 (2026-06-24). 실패 시 항상 dict 반환, raise 0 (graceful).
"""
from __future__ import annotations

from typing import Any, Dict, List

import requests

_TIMEOUT = 12
_ENDPOINT = "https://hub.snapshot.org/graphql"
_HEADERS = {
    "User-Agent": "Verity-Terminal/1.0",
    "Content-Type": "application/json",
}

# 현재 열린(투표 진행 중) 제안. end asc = 마감 임박 순(가장 actionable, 공시 마감일 대응).
# 마감 임박 제안일수록 이미 투표가 누적되어 신호가 강함(신규 created 제안은 votes 0).
_QUERY_ACTIVE = """
query ActiveProposals($n: Int!) {
  proposals(
    first: $n
    where: { state: "active" }
    orderBy: "end"
    orderDirection: asc
  ) {
    id
    title
    state
    start
    end
    scores
    scores_total
    votes
    choices
    space { id name }
  }
}
""".strip()


def _fetch(query: str, variables: Dict[str, Any]) -> List[Dict[str, Any]]:
    """Snapshot GraphQL 1회 호출 → proposals 리스트. 실패 시 빈 리스트."""
    r = requests.post(
        _ENDPOINT,
        json={"query": query, "variables": variables},
        headers=_HEADERS,
        timeout=_TIMEOUT,
    )
    r.raise_for_status()
    payload = r.json()
    if payload.get("errors"):
        # GraphQL level error — 메시지 보존, raise 하지 않음
        raise RuntimeError(str(payload["errors"])[:160])
    return (payload.get("data") or {}).get("proposals") or []


def _shape(p: Dict[str, Any]) -> Dict[str, Any]:
    """raw proposal → 안정 스키마 (팩트만)."""
    space = p.get("space") or {}
    space_id = space.get("id") or ""
    pid = p.get("id") or ""
    return {
        "id": pid,
        "title": (p.get("title") or "").strip(),
        "space_id": space_id,
        "space_name": (space.get("name") or "").strip(),
        "state": p.get("state") or "",
        "start": p.get("start"),
        "end": p.get("end"),
        "scores_total": p.get("scores_total"),
        "votes": p.get("votes"),
        "choices": p.get("choices") or [],
        "scores": p.get("scores") or [],
        # 실동작 URL 확인됨 (HTTP 200)
        "link": f"https://snapshot.org/#/{space_id}/proposal/{pid}" if (space_id and pid) else "",
    }


def collect_crypto_governance(limit: int = 20) -> Dict[str, Any]:
    """주요 DAO 거버넌스 제안/투표 라이브 피드 (Snapshot).

    현재 투표 진행 중(active)인 제안을 마감 임박 순으로 가져온 뒤,
    신호 강도(scores_total → votes) 순으로 정렬해 상위 `limit` 개를 반환한다.

    항상 dict 반환 (raise 0). 실패 시 {"ok": False, "error": ...}.
    """
    try:
        limit = max(1, min(int(limit), 100))
    except (TypeError, ValueError):
        limit = 20

    # 신호 정렬 위해 넉넉히 가져온 뒤 상위 limit 컷
    fetch_n = min(limit * 3, 100)

    try:
        raw = _fetch(_QUERY_ACTIVE, {"n": fetch_n})
    except Exception as e:  # noqa: BLE001
        return {"ok": False, "error": str(e)[:160], "proposals": []}

    proposals = [_shape(p) for p in raw if (p.get("id") and p.get("space"))]

    # 신호 강한 것 우선 (온체인 투표력 합 → 투표 인원 수)
    def _sig(x: Dict[str, Any]) -> tuple:
        return (x.get("scores_total") or 0.0, x.get("votes") or 0)

    proposals.sort(key=_sig, reverse=True)
    proposals = proposals[:limit]

    return {
        "ok": True,
        "source": "snapshot",
        "endpoint": _ENDPOINT,
        "state_filter": "active",
        "count": len(proposals),
        "proposals": proposals,
    }
