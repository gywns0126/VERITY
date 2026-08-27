# -*- coding: utf-8 -*-
"""사업의 개요는 메인 리포트에서 분리 발행한다 (2026-08-25 신설).

## 왜 — Vercel 8월 청구서

Aug 1–26 인프라 $112.12 중 **Fast Origin Transfer $63.79 (236 GB)** 가 최대 축이다.
`vercel-api/api/stock_slice.py` 는 콜드 인스턴스마다 blob 원본을 **통째로** 받는데,
2026-08-24 에 사업의 개요를 메인 리포트에 실으면서 KR 리포트가 **12.85 → 16.16 MB** 로
커졌다(+26%). 목록·검색 화면까지 개요 2.50MB 를 받는 구조였다.

분리 실측: 메인 16.16 → **13.61 MB**(−15.8%) · 개요 별 blob 2.57 MB(1,747종목).

## 규약

- 메인 `stock_report_public.json` 에 `business_overview` **필드를 싣지 않는다**.
- 🚨 대신 `_meta.business_overview_count` 와 `business_overview_file` 을 남긴다 —
  하류가 **"없다"** 와 **"다른 파일에 있다"** 를 구분할 수 있어야 한다.
- 개요 blob 은 발행 목록과 CDN 캐시 규칙에 **둘 다** 등록한다. 하나만 하면
  발행은 되는데 캐시가 기본군(600s)에 남아 분리 효과가 상쇄된다(8/18 3차 정렬의 교훈).
"""
from __future__ import annotations

import importlib.util
import re
from pathlib import Path

_ROOT = Path(__file__).resolve().parent.parent
BUILDER = _ROOT / "api" / "builders" / "stock_report_public_builder.py"
ACTION = _ROOT / ".github" / "actions" / "publish-data" / "action.yml"
BLOBJS = _ROOT / ".github" / "actions" / "publish-data" / "blob_upload.js"
STOCK_SLICE = _ROOT / "vercel-api" / "api" / "stock_slice.py"
FNAME = "kr_business_overview_public.json"


def test_builder_does_not_attach_overview_to_main_report():
    """🚨 회귀 방지 — 다시 `s["business_overview"] = ...` 를 넣으면 전송량이 돌아온다."""
    src = BUILDER.read_text(encoding="utf-8")
    assert not re.search(r's\["business_overview"\]\s*=', src), \
        "개요를 메인 리포트 종목에 다시 붙였다 — 분리 이유는 Vercel 전송량이다"


def test_meta_distinguishes_absent_from_relocated():
    """하류가 '없다' 와 '다른 파일에 있다' 를 구분할 수 있어야 한다."""
    src = BUILDER.read_text(encoding="utf-8")
    assert '"business_overview_count"' in src
    assert '"business_overview_file"' in src


def test_new_blob_is_registered_in_publish_list():
    assert FNAME in ACTION.read_text(encoding="utf-8"), \
        "발행 목록 미등록 — 파일은 만들어지는데 blob 에 안 올라간다"


def test_new_blob_has_an_explicit_cdn_cache_rule():
    """🚨 발행만 하고 캐시 규칙을 빼면 기본군(600s)에 남아 분리 효과가 상쇄된다."""
    js = BLOBJS.read_text(encoding="utf-8")
    m = re.search(r"kr_business_overview_public\\?\.json\$/,\s*(\d+)", js)
    assert m, "CDN 캐시 규칙 미등록 — 기본 600s 로 떨어진다"
    assert int(m.group(1)) >= 3600, f"캐시가 너무 짧다({m.group(1)}s) — 갱신은 일 1.4회다"


def test_stock_slice_returns_only_the_requested_overview():
    """브라우저가 개요 원장 전체를 받지 않고 종목 1건만 받는다."""
    src = STOCK_SLICE.read_text(encoding="utf-8")
    assert '"overview": "kr_business_overview_public.json"' in src
    assert 'out["business_overview"] = _slice(docs.get("overview"), ticker)' in src
    assert 'out["business_overview_as_of"] = _meta_field(docs.get("overview"), "generated_at")' in src

    spec = importlib.util.spec_from_file_location("stock_slice_overview_contract", STOCK_SLICE)
    assert spec and spec.loader
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    row = {"text": "반도체 제품을 제조한다.", "fiscal_year": 2025}
    assert mod._slice({"rows": {"005930": row}}, "005930") == row


def test_published_payload_shape_if_present():
    """산출물이 있으면 계약을 본다(CI 경량 환경에서는 스킵)."""
    import json
    p = _ROOT / "data" / FNAME
    if not p.exists():
        return
    d = json.loads(p.read_text(encoding="utf-8"))
    assert d["_meta"]["count"] == len(d["rows"])
    assert d["_meta"]["publish_chars"] > 0
    row = next(iter(d["rows"].values()))
    for k in ("text", "chars", "truncated", "source", "fiscal_year"):
        assert k in row, f"출처 추적 필드 누락: {k}"
    assert row["chars"] <= d["_meta"]["publish_chars"] + 2   # 문장 경계 절단 여유
