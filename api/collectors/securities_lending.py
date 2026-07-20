#!/usr/bin/env python3
"""
securities_lending — 금융위원회 주식 대차거래 정보 (data.go.kr 1160100, 2026-06-29).

🚨 공매도 잔고 아님 — KR 진짜 공매도 잔고는 KRX 봇차단으로 free 접근 불가(검증 6소스). 대차잔고 = 빌려준 주식
   (공매도의 재료 = 공매도 압력 proxy). RULE 7 = 사실만, "대차잔고·공매도 관련" 정직 라벨. 판단·신호 0.

소스 = data.go.kr 금융위 주식대차/공매도정보 GetStocLendBorrInfoService_V2 (활용신청 15059612).
  · getStLendAndBorrItemRank_V2 = 종목별 대차 현황 전 종목(~2,769). basDt(YYYYMMDD) 일별, T+1.
  · 표준 param(serviceKey/numOfRows/pageNo/resultType=xml/basDt). 키 = PUBLIC_DATA_API_KEY(국민연금·관세청과 동일).
  · KSD(B552481) 폐기 — top100 한정 + stdDt/rankTpcd 까다로움. FSC가 전 종목·풍부·표준 param 우위.
응답 필드(실호출 검증): isinCd(종목코드) isinCdNm(종목명) lnbBal(대차잔고금액) lnbRmanStckCnt(대차잔고수량)
  lnbCclStckCnt(당일 신규체결) rdptStckCnt(상환) rcalRdptStckCnt(리콜상환) lnbScrtDcdNm(증권구분).
라이선스 = data.go.kr 표준(출처표시). KIS 0 / DART 0 (RULE 1 무관). 출력 = data/securities_lending.json (대차잔고 상위 N).
"""
from __future__ import annotations

import json
import os
import sys
import xml.etree.ElementTree as ET
from datetime import datetime, timedelta, timezone
from pathlib import Path

import requests

_ROOT = Path(os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))
sys.path.insert(0, str(_ROOT))

KST = timezone(timedelta(hours=9))
ENDPOINT = ("https://apis.data.go.kr/1160100/GetStocLendBorrInfoService_V2/"
            "getStLendAndBorrItemRank_V2")
OUTPUT_PATH = _ROOT / "data" / "securities_lending.json"
TOP_N = 3000         # 사이트 노출용 대차잔고 상위 (2026-07-17 1000→3000 — 소스 전 universe 2768종 이미 수집, 노출 컷만 상향. report∩1000=58%→전량 노출. 파일 ~150KB→~415KB. 소비자 4곳=ticker 조회형 무회귀)
PAGE_SIZE = 1000


def _now_kst() -> datetime:
    return datetime.now(KST)


def _service_key() -> str:
    try:
        from api.config import PUBLIC_DATA_API_KEY
        if PUBLIC_DATA_API_KEY:
            return PUBLIC_DATA_API_KEY
    except Exception:  # noqa: BLE001
        pass
    return os.environ.get("PUBLIC_DATA_API_KEY", "").strip() or os.environ.get("DATA_GO_KR_KEY", "").strip()


def _int(v) -> int:
    try:
        return int(float(str(v).replace(",", "").strip()))
    except (TypeError, ValueError):
        return 0


def _local(tag: str) -> str:
    return tag.split("}", 1)[-1] if "}" in tag else tag


def _parse(xml_bytes: bytes):
    """(result_code, total_count, items[])."""
    try:
        root = ET.fromstring(xml_bytes)
    except ET.ParseError:
        return "PARSE_ERR", 0, []
    code = ""
    total = 0
    for el in root.iter():
        t = _local(el.tag)
        if t == "resultCode" and not code:
            code = (el.text or "").strip()
        elif t == "totalCount":
            total = _int(el.text)
    items = [{_local(c.tag): (c.text or "").strip() for c in el}
             for el in root.iter() if _local(el.tag) == "item"]
    return code or "?", total, items


def _recent_business_days(n: int = 7):
    """T+1 지연 감안 — 오늘 KST 기준 최근 영업일 후보 YYYYMMDD (오늘 -1일부터)."""
    out = []
    d = _now_kst().date() - timedelta(days=1)
    while len(out) < n:
        if d.weekday() < 5:
            out.append(d.strftime("%Y%m%d"))
        d -= timedelta(days=1)
    return out


def _fetch_all(service_key: str, bas_dt: str):
    """basDt 전 종목 페이지네이션 수집. 첫 페이지 code!=00 이면 ([], code)."""
    sess = requests.Session()
    collected = []
    page = 1
    first_code = "?"
    while True:
        r = sess.get(ENDPOINT, params={
            "serviceKey": service_key, "numOfRows": PAGE_SIZE, "pageNo": page,
            "resultType": "xml", "basDt": bas_dt,
        }, timeout=20)
        code, total, items = _parse(r.content)
        if page == 1:
            first_code = code
            if code != "00" or not items:
                return [], code
        if not items:
            break
        collected.extend(items)
        if len(collected) >= total or len(items) < PAGE_SIZE:
            break
        page += 1
        if page > 12:  # 안전장치 (~12K 종목 상한)
            break
    return collected, first_code


def fetch_lending(service_key: str):
    """최근 영업일 probe — 첫 정상 basDt 의 전 종목 반환."""
    for bas_dt in _recent_business_days():
        try:
            items, code = _fetch_all(service_key, bas_dt)
        except Exception as e:  # noqa: BLE001
            print(f"[lending] {bas_dt} 호출 실패: {str(e)[:70]}", file=sys.stderr)
            continue
        if items:
            return bas_dt, items
        print(f"[lending] {bas_dt} code={code} — 다음 영업일 probe", file=sys.stderr)
    return None, []


def build(service_key: str) -> dict:
    bas_dt, items = fetch_lending(service_key)
    rows = []
    total_bal = 0
    for it in items:
        tk = (it.get("isinCd") or "").strip()
        if not tk:
            continue
        bal = _int(it.get("lnbBal"))
        total_bal += bal
        rows.append({
            "ticker": tk,
            "name": (it.get("isinCdNm") or "").strip(),
            "lending_amt": bal,                                  # 대차잔고 금액(원)
            "lending_qty": _int(it.get("lnbRmanStckCnt")),       # 대차잔고 수량(빌려준 주식)
            "new_qty": _int(it.get("lnbCclStckCnt")),            # 당일 신규체결
            "redemption_qty": _int(it.get("rdptStckCnt")),       # 당일 상환
        })
    rows.sort(key=lambda s: -s["lending_amt"])
    return {
        "_meta": {
            "generated_at": _now_kst().isoformat(),
            "source": "금융위원회 주식대차거래 (data.go.kr 1160100 GetStocLendBorrInfoService_V2)",
            "as_of": bas_dt,
            "universe_count": len(rows),
            "top_count": min(TOP_N, len(rows)),
            "total_lending_amt": total_bal,
            "license": "data.go.kr 표준 · 출처표시 의무",
            "note": "대차잔고 = 시장에 빌려준 주식 = 공매도 재료/압력 proxy. 진짜 공매도 잔고 아님(KRX 봇차단). RULE 7 사실만 — 판단·신호 0.",
        },
        "stocks": rows[:TOP_N],
    }


def main() -> int:
    ok = False
    try:
        key = _service_key()
        if not key:
            print("[lending] PUBLIC_DATA_API_KEY 부재 — skip", file=sys.stderr)
            return 0
        out = build(key)
        if not out["stocks"] and OUTPUT_PATH.exists():
            print("[lending] 0 종목(휴장/지연) — 기존 보존", file=sys.stderr)
            ok = True
            return 0
        OUTPUT_PATH.parent.mkdir(parents=True, exist_ok=True)
        with open(OUTPUT_PATH, "w", encoding="utf-8") as f:
            json.dump(out, f, ensure_ascii=False)
        m = out["_meta"]
        print(f"[lending] logged=True · universe {m['universe_count']} · top {m['top_count']} · "
              f"as_of {m['as_of']} -> {OUTPUT_PATH.name}", file=sys.stderr)
        ok = True
        return 0
    except Exception as e:  # noqa: BLE001
        print(f"[lending] FAILED: {e!r}", file=sys.stderr)
        return 1
    finally:
        if not ok:
            print("[lending] logged=False", file=sys.stderr)


if __name__ == "__main__":
    sys.exit(main())
