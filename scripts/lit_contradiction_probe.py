#!/usr/bin/env python3
"""문헌 모순 탐지 실험 — 크립토(영역 15) 파일럿.

## 사전등록 (2026-08-17, 실행 전 고정)

**가설**: 자체 학술 라이브러리(717줄·논문 90건)에 후속 문헌을 자동 대조하면,
우리 **라이브 config 와 상충하는 근거**가 사람 손보다 빠르게 나온다.

**왜 크립토부터**: 영역 15 는 오늘 하루 검정 15건을 돌린 영역이라 우리 주장이 가장
날카롭게 특정돼 있다. 모순이 있다면 여기서 가장 잘 보인다.

🚨 **성공 기준 (측정 전 고정, 결과 보고 바꾸지 않는다)**
- 모순 후보 **3건 이상** → 아이디어 값어치 증명. 전 영역 확장 + 사이트 논의
- **0~1건** → 우리 라이브러리가 이미 충분. **기각**, 만들지 않는다
- 2건 → 경계. 비용 대비 판단을 PM 에게

**모순의 정의** (느슨하게 세면 아무 숫자나 나온다):
아래 7개 config 축 중 하나에 대해, 논문이 **우리 선택과 다른 방향의 실증**을 보고한 경우.
단순히 "관련 있는 논문" 은 모순이 아니다. 축을 명시하지 못하면 후보에서 제외한다.

**한계 신고**
- 수집원 = arXiv q-fin **워킹페이퍼**. 게재본 전문은 유료라 텍스트 마이닝 라이선스 밖이다.
  → 여기서 나온 것은 전부 **preprint 등급**이며 확증 근거로 쓸 수 없다(영역 15 §⑦ 규율).
- 초록만 읽는다. 초록이 결론을 왜곡하는 경우가 있어 **후보 = 사람이 읽을 목록**이지 판정이 아니다.
  (RULE 10 — 자동 판정을 그대로 전달하지 않는다)

---

## 🚨 결과 (2026-08-17 실행) — **기각**. 코퍼스가 접근 밖이다

**수집** 195편(중복 제거) · **자동 후보 6편** · **원문 확인 후 생존 1편** (위양성 83%).

생존 1편 = **AdaptiveTrend** (arXiv 2602.11708, 2026-02-12)
"Systematic Trend-Following with Adaptive Portfolio Construction". 6시간 봉 추세추종 +
월간 적응형 포트폴리오 + **비대칭 롱숏** + **일중 변동성 레짐에 맞춘 동적 트레일링 스톱**.
→ 우리가 2026-08-17 에 기각한 **세 결정(트레일링·롱숏·일 1회 주기)을 동시에 반대 방향으로** 쓴다.
   진짜 대조 사례이며 라이브러리에 없던 것이다.

탈락 5편 = 상관 클러스터링 2 · 예측시장 조작 1 · LOB 미시구조 1 · ML 극값예측 감사 1.
전부 "크립토 + 매칭어" 로 걸렸을 뿐 우리 config 축을 다루지 않는다.

**🚨 그러나 진짜 발견은 후보 수가 아니다 — 코퍼스 도달률이다.**

영역 15 인용 6편의 arXiv 존재 여부를 직접 조회한 결과:

| 논문 | arXiv |
|---|---|
| Moskowitz-Ooi-Pedersen 2012 (JFE) | ❌ (제목만 겹치는 **다른** 논문이 걸림) |
| Liu & Tsyvinski 2021 (RFS) | ❌ |
| Liu, Tsyvinski, Wu 2022 (JF) | ❌ |
| Barroso & Santa-Clara 2015 (JFE) | ❌ |
| Grobys et al. 2025 (FMPM) | ❌ |
| Sadaqat & Butt 2023 (JBEF) | ❌ |

**0/6.** 우리가 실제로 의지하는 문헌은 전부 유료 저널 게재본이고 arXiv 에 없다.
즉 arXiv 기반 자동 수집은 **튜닝 문제가 아니라 구조적으로** 우리 코퍼스를 못 본다.
질의 `abs:"cryptocurrency momentum"` 이 **0건**을 낸 것도 같은 이유다.

**대조군**: 같은 날 퍼플렉시티 Pro 질의는 Sadaqat-Butt(2023, JBEF)를 찾아냈다 —
정확히 우리 청산 결론과 정면 상충하는 근거였고, arXiv 경로는 이걸 원리적으로 못 찾는다.

**판정**: 사전등록 기준(생존 ≤1 → 기각) 적용. **자동 수집 랩은 만들지 않는다.**
현행 경로(축이 다투어질 때 퍼플렉시티 Pro 질의 + 사람 대조)가 더 낫다.
단 생존 1편은 라이브러리 영역 15 에 편입한다 — 실험이 실패해도 산출물은 남긴다.
"""
from __future__ import annotations

import json
import re
import time
import urllib.parse
import urllib.request
import xml.etree.ElementTree as ET
from datetime import datetime

ARXIV = "http://export.arxiv.org/api/query?"
NS = {"a": "http://www.w3.org/2005/Atom"}
SINCE_YEAR = 2023          # 라이브러리 감사(2026-06) 이후 + 최근 3년

# ── 우리 라이브 config 주장 7축 (TIDE origin/main:tide/config.py 정합) ──
AXES = [
    {
        "id": "lookback",
        "our": "dual-lookback 30/90일 (MOP 1~12개월 범위 안, Liu-Tsyvinski 1~4주보다 김)",
        "hit": [r"lookback", r"formation period", r"holding period", r"horizon"],
        "contra": [r"short.{0,20}horizon", r"weekly", r"1.{0,3}week", r"optimal lookback",
                   r"reversal"],
    },
    {
        "id": "vol_target",
        "our": "vol-targeting 연 40% · de-risk only (레버리지 없음)",
        "hit": [r"volatility.{0,10}(target|manag|scal)", r"vol.{0,5}target"],
        "contra": [r"leverage", r"does not improve", r"no improvement", r"underperform",
                   r"fails to"],
    },
    {
        "id": "regime_gate",
        "our": "200일 SMA 레짐 게이트 (3일 확인, non-bull 시 비중 0.5)",
        "hit": [r"regime", r"moving average", r"200.{0,5}day", r"trend filter"],
        "contra": [r"whipsaw", r"no benefit", r"ineffective", r"underperform"],
    },
    {
        "id": "universe",
        "our": "BTC/ETH 2종만 (유니버스 확장은 2026-08-17 자체 기각)",
        "hit": [r"cross.section", r"universe", r"large.?cap", r"altcoin", r"portfolio of"],
        "contra": [r"diversif", r"more coins", r"breadth", r"number of assets"],
    },
    {
        "id": "long_only",
        "our": "롱-플랫 (숏 없음. 업비트 현물 전용)",
        "hit": [r"long.?short", r"short.?sell", r"perpetual", r"futures"],
        "contra": [r"short leg", r"long.?short outperform", r"shorting"],
    },
    {
        "id": "exit_rules",
        "our": "손절·익절·트레일링 전부 없음 (신호 소멸 시 청산). 재난 브레이커도 기각",
        "hit": [r"stop.?loss", r"take.?profit", r"trailing", r"exit rule"],
        "contra": [r"stop.?loss improv", r"enhanc", r"risk.?adjusted", r"outperform"],
    },
    {
        "id": "costs_decay",
        "our": "왕복 0.10% · 알파 잔존 가정 (2025~26 부진은 국면 부재로 해석)",
        "hit": [r"transaction cost", r"slippage", r"decay", r"declin", r"disappear",
                r"out.?of.?sample"],
        "contra": [r"no longer", r"vanish", r"insignificant", r"unprofitable", r"after cost"],
    },
]

QUERIES = [
    'cat:q-fin.PM AND (abs:"cryptocurrency" OR abs:"bitcoin")',
    'cat:q-fin.TR AND (abs:"cryptocurrency" OR abs:"bitcoin")',
    'cat:q-fin.ST AND abs:"cryptocurrency"',
    'abs:"cryptocurrency momentum"',
    'abs:"time series momentum" AND abs:"crypto"',
    'abs:"bitcoin" AND abs:"trend following"',
    'abs:"crypto" AND abs:"volatility targeting"',
    'abs:"cryptocurrency" AND abs:"stop-loss"',
]


def fetch(query: str, max_results: int = 100) -> list[dict]:
    url = ARXIV + urllib.parse.urlencode({
        "search_query": query, "start": 0, "max_results": max_results,
        "sortBy": "submittedDate", "sortOrder": "descending",
    })
    for attempt in range(4):
        try:
            with urllib.request.urlopen(url, timeout=30) as r:
                root = ET.fromstring(r.read())
            break
        except Exception:
            if attempt == 3:
                return []
            time.sleep(1.5 * (attempt + 1))
    out = []
    for e in root.findall("a:entry", NS):
        pub = e.findtext("a:published", "", NS)[:10]
        if not pub or int(pub[:4]) < SINCE_YEAR:
            continue
        out.append({
            "id": e.findtext("a:id", "", NS).rsplit("/", 1)[-1],
            "title": " ".join(e.findtext("a:title", "", NS).split()),
            "abstract": " ".join(e.findtext("a:summary", "", NS).split()),
            "published": pub,
            "url": e.findtext("a:id", "", NS),
        })
    return out


def score(paper: dict) -> list[dict]:
    """축별 매칭. hit(주제 관련) AND contra(반대 방향 표현) 둘 다 있어야 후보."""
    text = (paper["title"] + " " + paper["abstract"]).lower()
    flags = []
    for ax in AXES:
        if not any(re.search(p, text) for p in ax["hit"]):
            continue
        hits = [p for p in ax["contra"] if re.search(p, text)]
        if hits:
            flags.append({"axis": ax["id"], "our": ax["our"], "matched": hits})
    return flags


def main() -> None:
    print("문헌 모순 탐지 — 크립토(영역 15) 파일럿")
    print(f"  수집원 = arXiv q-fin 워킹페이퍼 · {SINCE_YEAR}년 이후")
    print(f"  대조 축 {len(AXES)}개 · 질의 {len(QUERIES)}개")
    print("  🚨 성공 기준(사전등록) = 모순 후보 3건 이상 → 확장 / 0~1건 → 기각")
    print()

    seen, papers = set(), []
    for q in QUERIES:
        got = fetch(q)
        new = [p for p in got if p["id"] not in seen]
        for p in new:
            seen.add(p["id"])
        papers.extend(new)
        print(f"  [{len(got):>3}건 → 신규 {len(new):>3}] {q[:64]}")
        time.sleep(3.2)          # arXiv 권장 3초 간격

    print()
    print(f"════ 수집 {len(papers)}편 (중복 제거) ════")
    print()

    cands = []
    for p in papers:
        fl = score(p)
        if fl:
            cands.append({**p, "flags": fl})

    axis_count = {}
    for c in cands:
        for f in c["flags"]:
            axis_count[f["axis"]] = axis_count.get(f["axis"], 0) + 1

    print("## 축별 후보 수")
    for ax in AXES:
        n = axis_count.get(ax["id"], 0)
        print(f"  {ax['id']:>12}  {n:>3}편   ← 우리: {ax['our'][:52]}")
    print()
    print(f"## 모순 후보 {len(cands)}편 (사람이 읽을 목록 — 자동 판정 아님)")
    print()
    for c in sorted(cands, key=lambda x: -len(x["flags"]))[:20]:
        axes = ", ".join(f["axis"] for f in c["flags"])
        print(f"  [{c['published']}] {c['title'][:88]}")
        print(f"      축: {axes} · {c['url']}")

    out = {
        "run_at": datetime.now().isoformat(timespec="seconds"),
        "source": "arxiv q-fin (working papers — preprint 등급)",
        "since_year": SINCE_YEAR,
        "collected": len(papers),
        "candidates": len(cands),
        "axis_count": axis_count,
        "prereg": {"threshold_expand": 3, "threshold_reject": 1,
                   "note": "초록 매칭은 후보 생성용. 판정은 사람이 원문 확인 후."},
        "papers": cands,
    }
    path = "data/metadata/lit_contradiction_probe_crypto.json"
    with open(path, "w", encoding="utf-8") as f:
        json.dump(out, f, ensure_ascii=False, indent=1)
    print()
    print(f"저장 → {path}")
    print()
    verdict = ("✅ 3건 이상 — 확장 검토" if len(cands) >= 3 else
               "❌ 1건 이하 — 기각" if len(cands) <= 1 else "◐ 2건 — 경계, PM 판단")
    print(f"🏁 1차 판정(초록 기준): {verdict}")
    print("   🚨 단 이건 **후보 수**다. 원문 확인 후 살아남는 수가 진짜 결과다.")


if __name__ == "__main__":
    main()
