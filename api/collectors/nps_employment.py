#!/usr/bin/env python3
"""nps_employment — 상장사 고용 동향 (국민연금 가입 사업장 API, PM 2026-07-08 검증 후 승인).

데이터 = data.go.kr B552015/NpsBplcInfoInqireServiceV2 (국민연금 가입 사업장 내역).
  검증(2026-07-08 실호출): 삼성전자(주) 가입자 125,594명(실 임직원 정합) · 2026-05 입사 445/퇴사 421.
  🚨 2025-05 공단 전산 개편 = 파라미터 카멜케이스 (wkplNm — 스네이크는 조용히 무시되어 0건).

매칭(하청 현장 사업장 오염 차단):
  상장사명 → 사업장명 후보 정규화("이름(주)"·"(주)이름"·"주식회사 이름" 등) → 검색 결과에서
  **정규화 정확일치만** 채택 (부분일치 금지 — "삼성전자" 검색 = 하청 2,430건). 다지점(동명 사업장) 합산.

제약: 공단 = 최근 1년 창만 제공 + 매월 15일 이후 갱신 → 월 1회 스냅샷을 우리가 누적 = 축적형 자산.
쿼터: dev 10,000/일 · 초당 30tx → 스로틀. 콜 ≈ 유니버스×(검색1+상세n+기간1) ≈ 5~6K/run.

출력: data/nps_employment.json (최신 스냅샷) + data/nps_employment_history.jsonl (월별 누적).
🚨 RULE 7 — 공단 공시 사실만 · "고용 프록시(국민연금 가입 기준)" 라벨 의무. RULE 4 — cron git add data/ broad.
"""
from __future__ import annotations

import json
import os
import re
import sys
import time
from datetime import datetime, timedelta, timezone
from typing import Any, Dict, List, Optional

import requests

KST = timezone(timedelta(hours=9))
_ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
OUT_PATH = os.path.join(_ROOT, "data", "nps_employment.json")
HIST_PATH = os.path.join(_ROOT, "data", "nps_employment_history.jsonl")
REPORT_PATH = os.path.join(_ROOT, "data", "stock_report_public.json")

BASE = "http://apis.data.go.kr/B552015/NpsBplcInfoInqireServiceV2"
THROTTLE = 0.0           # 병렬화(8워커)가 동시성 상한 = rate 제어. 워커당 추가 sleep 불필요
MAX_MATCH_DETAIL = 4     # 동명 사업장 상세 조회 상한 (다지점 합산)


def _key() -> str:
    try:
        from api.config import PUBLIC_DATA_API_KEY
        k = (PUBLIC_DATA_API_KEY or "").strip()
        if k:
            return k
    except Exception:  # noqa: BLE001
        pass
    return os.environ.get("PUBLIC_DATA_API_KEY", "").strip()


def _get(op: str, params: Dict[str, Any], key: str) -> Optional[Dict[str, Any]]:
    try:
        r = requests.get(f"{BASE}/{op}", params={"serviceKey": key, "dataType": "json", **params}, timeout=15)
        time.sleep(THROTTLE)
        if r.status_code != 200:
            return None
        body = r.json().get("response", {}).get("body", {})
        return body if isinstance(body, dict) else None
    except Exception:  # noqa: BLE001
        return None


def _items(body: Optional[Dict[str, Any]]) -> List[Dict[str, Any]]:
    if not body:
        return []
    it = body.get("items")
    if isinstance(it, dict):
        arr = it.get("item")
        if isinstance(arr, list):
            return arr
        if isinstance(arr, dict):
            return [arr]
    return []


def _norm(nm: str) -> str:
    """사업장명 정규화 — 전각 괄호·공백 통일 후 비교."""
    s = str(nm or "").replace("（", "(").replace("）", ")").replace("㈜", "(주)")
    return re.sub(r"\s+", "", s)


# 🚨 표시명(영문·약칭) ≠ 국민연금 사업장 법인명(한글) → 별칭 매핑. 값 = 사업장 법인명(한글).
#   (2026-07-08 실호출 검증: 표시명 그대로면 SK/NAVER/LG 등 대형주 미매칭·오매칭(LG화학=3명).
#    검증된 법인명만 등재 — 미검증은 표시명으로 best-effort, 실패 시 graceful 부재.)
NAME_ALIAS = {
    "SK하이닉스": "에스케이하이닉스", "SK이노베이션": "에스케이이노베이션",
    "SK텔레콤": "에스케이텔레콤", "SK스퀘어": "에스케이스퀘어", "SK": "에스케이",
    "SK바이오팜": "에스케이바이오팜", "SK아이이테크놀로지": "에스케이아이이테크놀로지",
    "NAVER": "네이버", "LG화학": "엘지화학", "LG전자": "엘지전자",
    "LG에너지솔루션": "엘지에너지솔루션", "LG생활건강": "엘지생활건강",
    "LG유플러스": "엘지유플러스", "LG이노텍": "엘지이노텍", "LG디스플레이": "엘지디스플레이",
    "LG": "엘지", "KT": "케이티", "KT&G": "케이티앤지", "KB금융": "케이비금융지주",
    "현대차": "현대자동차", "기아": "기아", "포스코홀딩스": "포스코홀딩스",
    "POSCO홀딩스": "포스코홀딩스", "HD현대": "에이치디현대", "HMM": "에이치엠엠",
    "GS": "지에스", "S-Oil": "에쓰오일", "DB하이텍": "디비하이텍", "DL이앤씨": "디엘이앤씨",
    "CJ제일제당": "씨제이제일제당", "KG모빌리티": "케이지모빌리티",
    "한국전력": "한국전력공사", "한전KPS": "한전케이피에스",
}


def _candidates(name: str) -> set:
    n = _norm(name)
    return {n, f"{n}(주)", f"(주){n}", f"주식회사{n}", f"{n}주식회사"}


def _one(tk: str, name: str, key: str, ym: str) -> Optional[Dict[str, Any]]:
    """단일 종목 매칭·집계 — 스레드풀 워커 (콜당 네트워크 지연이 지배 → 병렬화로 6h→~40m)."""
    q_name = NAME_ALIAS.get(name.strip(), name)  # 영문·약칭 → 한글 법인명
    n = _norm(q_name)
    cands = _candidates(q_name)
    # 🚨 바로 이름 검색은 API substring 매칭이라 대형주 = 하청 현장 사업장 수천 건 → 본사가 페이지 밖.
    #   (2026-07-08: 삼성전자 "삼성전자"=2,430건 → 본사 60행 밖 = 미매칭. 좁은 "(주)" 쿼리 먼저,
    #    바로-이름은 최후 폴백(주 없는 사업장 커버 — 대형주는 별칭이 이미 해결).)
    raw_matches = []
    for q in (f"{n}(주)", f"(주){n}", n):
        body = _get("getBassInfoSearchV2", {"wkplNm": q, "numOfRows": 100, "pageNo": 1}, key)
        raw_matches = [it for it in _items(body)
                       if _norm(it.get("wkplNm")) in cands and str(it.get("wkplStylDvcd")) == "1"
                       and str(it.get("wkplJnngStcd")) == "1"]  # 법인 + 가입 상태만
        if raw_matches:
            break
    # 🚨 검색 결과 = 같은 사업장의 월별 스냅샷 중복 (1년 창) — (사업장명+시군구) 그룹당 최신 월 1건만
    #   (미수리 시 가입자수 N개월 합산 과대 — 2026-07-08 스모크에서 현대로템 4배 실측)
    grp: Dict[str, Dict[str, Any]] = {}
    for it in raw_matches:
        gkey = _norm(it.get("wkplNm")) + "|" + str(it.get("ldongAddrMgplSgguCd") or "")
        prev = grp.get(gkey)
        if prev is None or str(it.get("dataCrtYm") or "") > str(prev.get("dataCrtYm") or ""):
            grp[gkey] = it
    matches = list(grp.values())
    if not matches:
        return None
    total_cnt, total_amt, hire, leave = 0, 0.0, 0, 0
    seqs = []
    for m in matches[:MAX_MATCH_DETAIL]:
        seq = m.get("seq")
        if seq is None:
            continue
        det = _items(_get("getDetailInfoSearchV2", {"seq": seq}, key))
        d0 = det[0] if det else {}
        try:
            total_cnt += int(d0.get("jnngpCnt") or 0)
            total_amt += float(d0.get("crrmmNtcAmt") or 0)
        except (TypeError, ValueError):
            pass
        rec_ym = str(m.get("dataCrtYm") or ym)  # 레코드 자체의 기준월 (당월 조회 = 빈 응답)
        pd = _items(_get("getPdAcctoSttusInfoSearchV2", {"seq": seq, "dataCrtYm": rec_ym}, key))
        for p in pd:
            try:
                hire += int(p.get("nwAcqzrCnt") or 0)
                leave += int(p.get("lssJnngpCnt") or 0)
            except (TypeError, ValueError):
                pass
        seqs.append(seq)
    if total_cnt <= 0:
        return None
    data_ym = max((str(m.get("dataCrtYm") or "") for m in matches), default=ym)
    return {
        "name": name, "jnngp_cnt": total_cnt, "ntc_amt": round(total_amt),
        "hire": hire, "leave": leave, "net": hire - leave,
        "wkpl_n": len(seqs), "ym": data_ym,
    }


def collect(limit: int = 0) -> Dict[str, Any]:
    from concurrent.futures import ThreadPoolExecutor, as_completed
    key = _key()
    if not key:
        print("[nps_emp] PUBLIC_DATA_API_KEY 없음 — skip", file=sys.stderr)
        return {}
    rep = json.load(open(REPORT_PATH, encoding="utf-8"))
    universe = [(str(s.get("ticker")), str(s.get("name") or "")) for s in rep.get("stocks", [])
                if re.match(r"^\d{6}$", str(s.get("ticker") or "")) and s.get("name")]
    if limit:
        universe = universe[:limit]
    ym = datetime.now(KST).strftime("%Y%m")
    out: Dict[str, Any] = {}
    done = 0
    # API 한도 30tx/초 · 콜당 ~4초 지연 → 8워커 = 최대 8 동시(<<30), 순차 대비 ~8배
    with ThreadPoolExecutor(max_workers=8) as ex:
        futs = {ex.submit(_one, tk, name, key, ym): tk for tk, name in universe}
        for fut in as_completed(futs):
            tk = futs[fut]
            done += 1
            try:
                row = fut.result()
                if row:
                    out[tk] = row
            except Exception:  # noqa: BLE001
                pass
            if done % 200 == 0:
                print(f"[nps_emp] 진행 {done}/{len(universe)} · 매칭 {len(out)}", file=sys.stderr)
    print(f"[nps_emp] 완료 — 유니버스 {len(universe)} · 매칭 {len(out)}", file=sys.stderr)
    return out


def main() -> int:
    ok = False
    try:
        limit = int(os.environ.get("NPS_EMP_LIMIT", "0") or 0)
        stocks = collect(limit)
        if not stocks:
            # 산출 0 = 기존 스냅샷 보존 (키 부재/장애 시 데이터 손실 방지)
            print("[nps_emp] logged=True · 매칭 0 — 기존 파일 보존(no-op)", file=sys.stderr)
            ok = True
            return 0
        now = datetime.now(KST)
        doc = {
            "_meta": {
                "generated_at": now.strftime("%Y-%m-%dT%H:%M:%S+09:00"),
                "source": "국민연금공단 가입 사업장 내역 (data.go.kr B552015, 매월 15일 이후 갱신)",
                "note": "고용 프록시(국민연금 가입자 기준) · 사업장명 정확일치 매칭 · 공단 공시 사실",
                "count": len(stocks),
            },
            "stocks": stocks,
        }
        with open(OUT_PATH, "w", encoding="utf-8") as f:
            json.dump(doc, f, ensure_ascii=False)
        with open(HIST_PATH, "a", encoding="utf-8") as f:
            ym = now.strftime("%Y%m")
            for tk, v in stocks.items():
                f.write(json.dumps({"ym": ym, "ticker": tk, "cnt": v["jnngp_cnt"],
                                    "hire": v["hire"], "leave": v["leave"]}, ensure_ascii=False) + "\n")
        print(f"[nps_emp] logged=True · {len(stocks)}종목 → {os.path.relpath(OUT_PATH, _ROOT)} (+history)", file=sys.stderr)
        ok = True
        return 0
    except Exception as e:  # noqa: BLE001
        print(f"[nps_emp] FAILED: {e!r}", file=sys.stderr)
        return 1
    finally:
        if not ok:
            print("[nps_emp] logged=False", file=sys.stderr)


if __name__ == "__main__":
    sys.exit(main())
