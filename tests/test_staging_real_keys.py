"""`VERITY_STAGING_REAL_KEYS` 가 실제 `@mockable` 키와 일치하는지 고정한다 (2026-08-19).

## 왜

`VERITY_MODE` 하나가 **AI 와 데이터를 같이 끈다.** 기본값 `dev` 는 `@mockable` 이 붙은 것을
전부 막으므로, AI 비용을 아끼려던 설정이 finnhub 수급·컨센서스까지 mock 으로 만든다.

실측(2026-08-19) — quick 파이프라인이 mock **64건**을 냈고 전부 finnhub 4키 × 16종목이다.
🚨 그 16종목이 `portfolio.json` 의 Finnhub 계열 미보유 16과 **정확히 일치**했고,
그중에 **실제 보유 종목이 몰려 있었다**(EXE·GOOGL·DVN·KMT·ALB·NEM). 판단에 쓰는 종목일수록
가짜 데이터를 받고 있었다.

해법은 축 신설이 아니라 **이미 있던 `staging`** 이다 — allowlist 만 실호출
(`api/mocks/__init__.py:58 _should_mock`). 데이터 키를 넣고 AI 키는 빼면 갈린다.

🚨 **이 방식의 유일한 실패 모드 = 오타.** 키 이름이 한 글자만 틀려도 allowlist 매칭이
빗나가 조용히 mock 으로 돌아가고, 알림도 에러도 안 난다
([[feedback_cluster_silent_defect]] "성공 종료 + 내용 결손"). 그래서 기계로 막는다.
"""
from __future__ import annotations

import pathlib
import re

import yaml

_ROOT = pathlib.Path(__file__).resolve().parent.parent
_WF = _ROOT / ".github" / "workflows" / "daily_analysis.yml"

# AI 제공자 접두사 — allowlist 에 들어가면 비용 차단이 무너진다
_AI_PREFIXES = ("gemini.", "claude.", "perplexity.")


def _mockable_keys() -> set:
    """코드에서 `@mockable("...")` 인자를 전수 수집."""
    keys = set()
    for p in (_ROOT / "api").rglob("*.py"):
        for m in re.finditer(r'@mockable\(\s*["\']([^"\']+)["\']', p.read_text(encoding="utf-8")):
            keys.add(m.group(1))
    return keys


def _allowlist() -> list:
    d = yaml.safe_load(_WF.read_text(encoding="utf-8"))
    for job in d["jobs"].values():
        for st in job.get("steps", []):
            if st.get("name") == "Run analysis":
                raw = (st.get("env") or {}).get("VERITY_STAGING_REAL_KEYS", "")
                return [k.strip() for k in raw.split(",") if k.strip()]
    raise AssertionError("Run analysis 스텝을 찾지 못했다")


def test_quick_runs_in_staging_not_dev():
    """🚨 dev 로 되돌아가면 데이터까지 mock 이 된다."""
    d = yaml.safe_load(_WF.read_text(encoding="utf-8"))
    mode = None
    for job in d["jobs"].values():
        for st in job.get("steps", []):
            if st.get("name") == "Run analysis":
                mode = (st.get("env") or {}).get("VERITY_MODE")
    assert mode == "staging", f"quick 의 VERITY_MODE 가 {mode!r} — staging 이어야 한다"


def test_every_allowlist_key_exists_in_code():
    """🚨 오타 = 조용한 mock 복귀. 실패 신호가 없으므로 여기서 잡는다."""
    known = _mockable_keys()
    assert known, "@mockable 키를 하나도 수집하지 못했다 — 수집 로직 파손"
    unknown = [k for k in _allowlist() if k not in known]
    assert not unknown, (
        f"allowlist 에 존재하지 않는 키: {unknown}\n"
        f"→ 이 키들은 매칭되지 않아 **조용히 mock 으로 돌아간다**.\n"
        f"코드의 실제 키 예: {sorted(known)[:8]}")


def test_no_ai_provider_in_allowlist():
    """AI 는 차단이 목적 — allowlist 에 들어가면 비용 절감이 무너진다."""
    leaked = [k for k in _allowlist() if k.startswith(_AI_PREFIXES)]
    assert not leaked, f"AI 키가 allowlist 에 있다(실호출됨): {leaked}"


def test_finnhub_data_keys_are_covered():
    """실측으로 mock 되던 4키가 반드시 포함돼야 한다 (2026-08-19 사고 재발 방지)."""
    need = {"finnhub.analyst_consensus", "finnhub.earnings_surprises",
            "finnhub.insider_sentiment", "finnhub.institutional_ownership"}
    missing = need - set(_allowlist())
    assert not missing, f"2026-08-19 에 mock 되던 키가 빠졌다: {sorted(missing)}"
