"""`kr_chart_daily.yml` 산출물이 신선도 SLA 에 전부 등재됐는지 고정한다 (2026-08-20).

## 왜

같은 워크플로가 4개를 만드는데 **2개만 등재**돼 있었다:

| 산출물 | 내용 | 등재 |
|---|---|---|
| `kr_index_daily.json` | 코스피·코스닥 지수 | P1 ✅ |
| `hot_stock.json` | 급등주 | P2 ✅ |
| `kr_close_latest.json` | 🚨 **보유종목 평가 기준가** | ❌ 없었음 |
| `kr_chart_daily/chunk_*.json` | 🚨 **일봉 41청크 약 3,000종목** | ❌ 없었음 |

**중요도가 거꾸로였다.** `kr_close_latest` 는 VAMS 평가·decision_journal·urgent_alerts +
공개 컴포넌트 4종이 읽는다 — 낡으면 수익률과 판단 기준가가 조용히 옛 값이 된다.
그런데 신선도 게이트 밖이라 낡아도 아무도 울리지 않았다.

계기 = 2026-08-20 `kr_chart_daily` 17:23·20:23 슬롯 반복 실패(timed out×3 + 403,
러너 IP 드롭) 조사. 그때 "2일 지연" 으로 보였던 것은 내 로컬 stale 오독이었고
실제 데이터는 정상이었지만, **미등재라는 사실은 그대로 남았다.**

🚨 신규 등재는 P0 미배정 — 첫 롤아웃 FAIL 폭주 차단 (`freshness_sla._meta` 규약).
승격은 관측 후 PM 결정.
"""
from __future__ import annotations

import json
import pathlib
import re

_ROOT = pathlib.Path(__file__).resolve().parent.parent
_SLA = _ROOT / "data" / "freshness_sla.json"
_WF = _ROOT / ".github" / "workflows" / "kr_chart_daily.yml"


def _streams():
    return json.loads(_SLA.read_text(encoding="utf-8"))["streams"]


def test_all_kr_chart_outputs_are_registered():
    """🚨 워크플로가 커밋하는 산출물 전부가 SLA 에 있어야 한다."""
    src = _WF.read_text(encoding="utf-8")
    m = re.search(r"git add ([^\n]+)", src)
    assert m, "워크플로에서 git add 대상을 찾지 못했다"
    committed = [p.replace("data/", "").strip()
                 for p in m.group(1).split() if p.startswith("data/")]
    files = {s["file"] for s in _streams()}
    missing = []
    for c in committed:
        c = c.rstrip("/")
        if any(c == f or f.startswith(c + "/") for f in files):
            continue
        missing.append(c)
    assert not missing, (
        f"kr_chart_daily.yml 산출물이 신선도 SLA 미등재: {missing}\n"
        "→ 낡아도 아무도 울리지 않는다")


def test_close_latest_registered_with_data_date_basis():
    """T+1 소스라 '쓴 시각' 이 아니라 '데이터 날짜' 로 나이를 재야 한다."""
    s = next((x for x in _streams() if x["id"] == "kr_close_latest"), None)
    assert s, "kr_close_latest 미등재"
    assert s["ts_field"] == "_meta.as_of", s
    assert "data_date" in s.get("age_basis", ""), (
        "age_basis 가 data_date 가 아니다 — 커밋 시각으로 재면 T+1 지연을 못 잡는다")


def test_new_entries_are_not_p0():
    """🚨 신규 등재 P0 미배정 (freshness_sla._meta 규약 — 첫 롤아웃 FAIL 폭주 차단)."""
    for sid in ("kr_close_latest", "kr_chart_daily"):
        s = next((x for x in _streams() if x["id"] == sid), None)
        assert s and s["criticality"] != "P0", f"{sid} 가 P0 로 등재됐다"


def test_registered_thresholds_are_realistic_for_t_plus_1():
    """🚨 임계가 현실적인지 — T+1 + 주말이면 최악 며칠이 뜬다.

    라이브 산출물을 읽지 않는다. `tests/conftest.py` 가 매 테스트마다 `DATA_DIR` 을
    tmp 로 격리하므로(실제 `data/` 보호) 여기서 실데이터를 보면 빈 디렉터리를 보게 된다 —
    최초 판본이 그렇게 실패했다. **격리 규약을 어기지 말고 계약만 검사한다.**

    T+1 소스라 금요일 데이터가 월요일까지 살아 있어야 한다:
      금 데이터(as_of=금) → 토·일 → 월 오후 갱신 = 최악 약 72h.
      여기에 공휴일 하루가 겹치면 96h. 그래서 4320분(=72h)이 **하한**이고
      kr_index_daily 선례와 같은 값을 쓴다.
    """
    for sid in ("kr_close_latest", "kr_chart_daily"):
        s = next((x for x in _streams() if x["id"] == sid), None)
        assert s, f"{sid} 미등재"
        assert s["max_age_minutes"] >= 4320, (
            f"{sid} 임계 {s['max_age_minutes']}분 — 주말(T+1 최악 72h)에 오탐한다")
        assert s.get("schedule") == "weekday", (
            f"{sid} schedule 이 weekday 가 아니다 — 주말 유효 age 보정이 안 걸린다")


def test_same_workflow_siblings_share_age_basis():
    """같은 워크플로 산출물끼리 나이 기준이 갈리면 안 된다.

    넷 다 T+1 소스인데 하나만 '쓴 시각' 으로 재면 그 하나만 다른 세계를 산다.
    """
    sibs = [s for s in _streams() if "kr_chart_daily.yml" in str(s.get("cadence", ""))]
    assert len(sibs) >= 4, f"형제 스트림이 {len(sibs)}건 — 등재가 빠졌다"
    bases = {s["id"]: ("data_date" in s.get("age_basis", "")) for s in sibs}
    assert all(bases.values()), f"age_basis 가 갈린다: {bases}"
