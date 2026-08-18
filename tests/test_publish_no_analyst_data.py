"""발행본에 애널리스트 컨센서스가 실리지 않는지 기계로 고정한다.

## 왜 (2026-08-18 신설)

PM 결정 = "애널리스트는 공개용으로 안올리는걸로. 백엔드에만 냅둬서 오퍼레이터 산식에만 넣는 걸로."

그 전에 같은 결정이 **두 번** 있었는데도 숫자는 계속 나갔다:
  · 2026-07-10 `us_analyst_consensus.json` 재배포 금지 → 파일 봉인(8/02, blob 404 실측)
  · 2026-07-21 `consensus_data.json` = "KR 브로커 목표가·투자의견, 동일 법적 class" → 봉인(8/16)
  · 그런데 **같은 숫자가 `portfolio.json` / `recommendations.json` 경로로 계속 발행**됐다.
    라이브 blob 실측(8/18) — target_price 63 · kis_target_price 18 · investment_opinion 56.

🚨 **파일을 봉인하고 통로를 안 막은 형태.** 봉인 대상을 `banned` 목록으로만 관리하면
같은 데이터가 다른 그릇에 담겨 나가는 것을 못 잡는다. 그래서 **필드 이름**으로 막는다.

원본 `data/` 는 대상이 아니다 — 오퍼레이터·백엔드 산식은 계속 쓴다. 막는 것은 발행뿐이다.
"""
from __future__ import annotations

import json
import pathlib
import subprocess
import sys

_ROOT = pathlib.Path(__file__).resolve().parent.parent
_ACTION = _ROOT / ".github" / "actions" / "publish-data"

# 라이선스 데이터(애널리스트 목표가·투자의견)를 가리키는 필드
BANNED_FIELDS = (
    "target_price", "price_target", "kis_target_price", "single_consensus_target_price",
    "investment_opinion", "investment_opinion_numeric", "kis_opinion", "kis_analyst_firm",
    "analyst_consensus", "target_price_source",
)


def _run(script: str, path: pathlib.Path) -> None:
    r = subprocess.run([sys.executable, str(_ACTION / script), str(path)],
                       capture_output=True, text=True)
    assert r.returncode == 0, f"{script} 실패: {r.stderr[:300]}"


def _leaks(path: pathlib.Path) -> list:
    text = path.read_text(encoding="utf-8")
    return [f for f in BANNED_FIELDS if f'"{f}"' in text]


def test_sanitizer_strips_analyst_fields_from_portfolio(tmp_path):
    src = _ROOT / "data" / "portfolio.json"
    if not src.exists():
        return  # 데이터 없는 환경(CI 체크아웃) — 아래 계약 테스트가 커버
    dst = tmp_path / "portfolio.json"
    dst.write_text(src.read_text(encoding="utf-8"), encoding="utf-8")
    _run("sanitize_recommendations.py", dst)
    _run("sanitize_portfolio_public.py", dst)
    assert not _leaks(dst), f"발행본에 애널리스트 필드가 남았다: {_leaks(dst)}"


def test_sanitizer_strips_analyst_fields_from_recommendations(tmp_path):
    src = _ROOT / "data" / "recommendations.json"
    if not src.exists():
        return
    dst = tmp_path / "recommendations.json"
    dst.write_text(src.read_text(encoding="utf-8"), encoding="utf-8")
    _run("sanitize_recommendations.py", dst)
    assert not _leaks(dst), f"발행본에 애널리스트 필드가 남았다: {_leaks(dst)}"


def test_strip_keys_contract_holds():
    """🚨 데이터 파일이 없는 환경에서도 계약 자체는 검사한다.

    위 두 테스트는 `data/` 가 있어야 도는데, CI 체크아웃에는 없을 수 있다.
    그때 조용히 통과하면 가드가 사라진 것과 같다 ([[feedback_cluster_silent_defect]]).
    """
    sys.path.insert(0, str(_ACTION))
    import importlib
    mod = importlib.import_module("sanitize_recommendations")
    for k in ("consensus", "analyst_consensus", "analyst_report_summary",
              "equity_research_brief"):
        assert k in mod.STRIP_KEYS, f"STRIP_KEYS 에서 {k} 가 빠졌다 (PM 2026-08-18 결정)"


def test_sanitizer_does_not_touch_source_data():
    """원본 `data/` 는 건드리지 않는다 — 오퍼레이터 산식이 계속 써야 한다."""
    src = _ROOT / "data" / "recommendations.json"
    if not src.exists():
        return
    doc = json.loads(src.read_text(encoding="utf-8"))
    recs = doc if isinstance(doc, list) else (doc.get("recommendations") or [])
    assert any(isinstance(r, dict) and r.get("consensus") for r in recs), \
        "원본에서 consensus 가 사라졌다 — 발행본만 strip 해야 한다"
