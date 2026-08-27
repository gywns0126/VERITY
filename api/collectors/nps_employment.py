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

# 원천 최신월 탐침용 대표 법인. 전체 수집 전에 월 공개 여부만 확인하므로 상세 API는 호출하지 않는다.
# 서로 다른 대형 법인 3곳이 같은 월을 제공할 때만 그 월을 원천 최신월로 채택한다.
SOURCE_MONTH_PROBES = ("삼성전자", "현대자동차", "엘지전자")


def _key() -> str:
    try:
        from api.config import PUBLIC_DATA_API_KEY
        k = (PUBLIC_DATA_API_KEY or "").strip()
        if k:
            return k
    except Exception:  # noqa: BLE001
        pass
    return os.environ.get("PUBLIC_DATA_API_KEY", "").strip()


# 호출 결과 계측 (2026-08-07) — 종전엔 비200도 예외도 전부 None 으로 삼켜서
#   "API 가 죽음" 과 "조건에 맞는 결과가 없음" 이 구분되지 않았다. 실제로 2026-08-07
#   만회 수집이 1595종목 전부 매칭 0 으로 끝났는데, 로그에는 정상 완료로만 남아
#   원인을 사후에 특정할 수 없었다. 이제 실패 유형을 세고 표본을 남긴다.
_CALL_STATS: Dict[str, int] = {"ok": 0, "http_error": 0, "exception": 0, "bad_body": 0,
                               "consecutive_conn_fail": 0}
_ERR_SAMPLE: List[str] = []

# 연결 실패 대응 (2026-08-07). 재시도는 일시적 흔들림용, 서킷은 지속 차단용.
CONN_RETRIES = 2         # 연결 계열만 재시도 (HTTP 오류는 재시도 무의미 — 서버가 답한 것)
CONN_BACKOFF_S = 1.5     # 1.5s → 3s. 차단 상태를 더 자극하지 않도록 짧게 끝낸다
CONN_FAIL_CIRCUIT = 30   # 연속 30회 연결 실패 = 호스트 차단으로 보고 즉시 중단


def _note_err(kind: str, detail: str) -> None:
    _CALL_STATS[kind] = _CALL_STATS.get(kind, 0) + 1
    if len(_ERR_SAMPLE) < 3:
        _ERR_SAMPLE.append(detail[:300])


class _HostDown(RuntimeError):
    """연결 차단 서킷 — 더 두드리지 말고 즉시 중단."""


def _get(op: str, params: Dict[str, Any], key: str) -> Optional[Dict[str, Any]]:
    # 🚨 서킷 브레이커 (2026-08-07) — 연결이 연속으로 막히면 즉시 포기한다.
    #   사고: 호스트가 TCP 연결을 거부하기 시작했는데 코드가 1595종목을 끝까지 시도해
    #   **2시간 반 동안 4791회 헛발질**(ok 0)을 했다. 차단된 상태에서 계속 두드리는 것은
    #   복구를 늦출 뿐이고, 러너 시간도 통째로 버린다. 1분 안에 실패해야 진단이 빠르다.
    if _CALL_STATS.get("consecutive_conn_fail", 0) >= CONN_FAIL_CIRCUIT:
        raise _HostDown(f"연결 실패 {CONN_FAIL_CIRCUIT}회 연속 — 호스트 차단/장애로 판단, 중단")

    last_err = None
    for attempt in range(CONN_RETRIES + 1):
        try:
            r = requests.get(f"{BASE}/{op}",
                             params={"serviceKey": key, "dataType": "json", **params}, timeout=15)
            time.sleep(THROTTLE)
            _CALL_STATS["consecutive_conn_fail"] = 0
            if r.status_code != 200:
                # data.go.kr 은 인증/한도 오류를 비200 으로도, 200+오류코드로도 준다.
                # 양쪽 다 표본을 남겨야 진단이 된다.
                _note_err("http_error", f"{op} HTTP {r.status_code}: {r.text[:200]}")
                return None
            body = r.json().get("response", {}).get("body", {})
            if not isinstance(body, dict):
                _note_err("bad_body", f"{op}: {r.text[:200]}")
                return None
            _CALL_STATS["ok"] += 1
            return body
        except (requests.ConnectionError, requests.Timeout) as e:
            # 연결 계열만 재시도한다 — 일시적 네트워크 흔들림은 넘기고, 지속 차단은
            # 위 서킷이 잡는다. 지수 백오프로 차단 상태를 더 자극하지 않는다.
            last_err = e
            if attempt < CONN_RETRIES:
                time.sleep(CONN_BACKOFF_S * (2 ** attempt))
                continue
        except Exception as e:  # noqa: BLE001
            _note_err("exception", f"{op}: {e!r}")
            return None

    _CALL_STATS["consecutive_conn_fail"] = _CALL_STATS.get("consecutive_conn_fail", 0) + 1
    _note_err("exception", f"{op}: {last_err!r}")
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


def probe_source_latest_month(key: Optional[str] = None) -> Optional[str]:
    """공단 원천이 공통으로 제공하는 최신 귀속월을 소수 호출로 확인한다.

    한 법인만 먼저 갱신되는 부분 공개를 전체 공개로 오인하지 않도록 3개 대표 법인의
    정확일치 레코드에 모두 존재하는 가장 최신 월을 반환한다.
    """
    key = key or _key()
    if not key:
        return None
    month_sets = []
    for name in SOURCE_MONTH_PROBES:
        norm_name = _norm(name)
        cands = _candidates(name)
        body = _get("getBassInfoSearchV2", {
            "wkplNm": f"{norm_name}(주)", "numOfRows": 100, "pageNo": 1,
        }, key)
        rows = [it for it in _items(body) if _norm(it.get("wkplNm")) in cands]
        months = {str(it.get("dataCrtYm") or "") for it in rows
                  if re.match(r"^20\d{4}$", str(it.get("dataCrtYm") or ""))}
        if not months:
            return None
        month_sets.append(months)
    common = set.intersection(*month_sets)
    return max(common) if common else None


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


MKTCAP_PATH = os.path.join(_ROOT, "data", "krx_mktcap.json")
# 1인당 시총 상한. 전 종목 중앙값이 11.2억(2026-08-17 실측 1,495종목)이라 500억 = 약 45배다.
_SUSPECT_CAP_PER_HEAD = 500 * 1e8


def _flag_suspect(stocks: Dict[str, Any]) -> int:
    """계통 과소집계 의심 레코드에 suspect 플래그. 값을 지우지 않고 **표시하지 말라고 알린다**.

    🚨 왜 필요한가 (2026-08-17 발견 — PM 이 알파네스트에서 테스 3명 보고 물어봄):
      이 수집기는 사업장명 **정확일치**만 채택한다. 부분일치를 쓰면 "삼성전자" 검색이
      하청 현장 2,430건을 물어오기 때문인데(원 설계 의도, 옳다), 반대 방향으로 과교정된다 —
      주력 사업장이 "풍산 안강공장"·"현대건설 ○○현장" 처럼 접미가 붙어 등록되면
      정확일치에서 전부 탈락하고, 회사명과 글자 그대로 같은 소규모 사무소 하나만 남는다.
      거기에 numOfRows=100(1페이지)·MAX_MATCH_DETAIL=4 상한이 겹친다.

      실측: 테스(095610) 3명 / 풍산 3명 / 대우건설 4명 / 현대건설 8명 / GS 3명.
      대조군으로 삼성전자 125,592 · 현대차 66,299 는 정확하다(사업장이 회사명 그대로 등록).
      즉 집계 로직이 아니라 매칭 커버리지 결함이고, 종목별로 갈린다.

      틀린 값을 공개 사이트에 그대로 내보내는 것이 가장 나쁘다. 근본 수정(접두일치 +
      법인번호 대조)은 매칭 정확도 검증이 필요하므로, 그 전까지 의심분을 표시에서 뺀다.
    """
    try:
        with open(MKTCAP_PATH, encoding="utf-8") as f:
            mc = (json.load(f) or {}).get("map") or {}
    except (OSError, ValueError):
        return 0
    n = 0
    for tk, v in stocks.items():
        cnt = v.get("jnngp_cnt")
        cap = (mc.get(tk) or {}).get("mktcap")
        if not isinstance(cnt, int) or cnt <= 0 or not cap:
            continue
        per = cap / cnt
        if per > _SUSPECT_CAP_PER_HEAD:
            v["suspect"] = True
            v["suspect_reason"] = (f"1인당 시총 {per / 1e8:,.0f}억 — 사업장명 정확일치 매칭이 "
                                   f"지점을 놓쳤을 가능성. 표시 보류")
            n += 1
        else:
            v.pop("suspect", None)
            v.pop("suspect_reason", None)
    return n


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
    # 🚨 워커 수 = 이 수집기의 **유일한 rate 제어 장치**다 (THROTTLE=0.0, 워커당 sleep 없음).
    #   따라서 워커를 올리는 것은 곧 호출 속도를 그만큼 올리는 것이다.
    #
    # 사고 (2026-08-07, 자책): timeout 대응이라며 8 → 20 으로 올렸다가 전량 수집이
    #   1595종목 **전부 매칭 0** 으로 끝났다. 같은 날 8종목 스모크는 정상(매칭 4/8, 202606
    #   수신)이었으므로 소스·키·주말 문제가 아니라 **대량 구간에서만 나는 rate 거절**이다.
    #   근거가 된 산식 자체가 틀렸다 — "콜당 ~4초 → 20워커=5 tx/s" 로 계산했으나 종목 1개가
    #   호출 1개가 아니다(검색 1~3회 + 매칭 사업장당 2회). 실제 버스트는 추정의 수 배였다.
    #   원래 문제였던 90분 timeout 은 워커가 아니라 timeout 180분 상향으로 이미 해결됐다.
    #   → 8 로 되돌린다. 속도가 필요하면 워커가 아니라 THROTTLE 과 함께 조정하고,
    #     반드시 소량 스모크(workflow_dispatch limit=8)로 먼저 확인할 것.
    with ThreadPoolExecutor(max_workers=int(os.environ.get("NPS_EMP_WORKERS", "8"))) as ex:
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
            # 🚨 서킷이 걸리면 남은 작업을 취소하고 **그때까지 모은 것만** 들고 나간다.
            #   main() 의 병합 로직이 종목별 최신 월을 유지하므로 부분 결과도 진척으로 남는다
            #   (전량 실패로 0 을 반환해 아무것도 못 건지는 것보다 낫다).
            if _CALL_STATS.get("consecutive_conn_fail", 0) >= CONN_FAIL_CIRCUIT:
                print(f"[nps_emp] 🚨 연결 차단 감지 — {done}/{len(universe)} 에서 중단, "
                      f"수집분 {len(out)}종목 보존", file=sys.stderr)
                for f2 in futs:
                    f2.cancel()
                break
    print(f"[nps_emp] 완료 — 유니버스 {len(universe)} · 매칭 {len(out)}", file=sys.stderr)
    return out


def main() -> int:
    ok = False
    try:
        limit = int(os.environ.get("NPS_EMP_LIMIT", "0") or 0)
        stocks = collect(limit)
        if not stocks:
            # 기존 스냅샷은 계속 보존한다 (키 부재/장애 시 데이터 손실 방지 — 이 부분은 유지).
            # 🚨 다만 **성공으로 끝내지 않는다** (2026-08-07). 종전엔 exit 0 이라 워크플로가
            #   초록으로 끝났고, 1595종목 전부 매칭 0 인 전면 장애가 "정상 완료" 와 구분되지
            #   않았다. 신선도 보드도 파일 시각만 보므로 어디에서도 드러나지 않는다.
            #   매칭 0 = 정상 상태가 아니다(2026-07-08 에는 1313종목 매칭). 시끄럽게 실패시킨다.
            print(f"[nps_emp] 🚨 매칭 0 — 기존 파일 보존하되 실패 처리. 호출 통계: {_CALL_STATS}",
                  file=sys.stderr)
            for s in _ERR_SAMPLE:
                print(f"[nps_emp]   err: {s}", file=sys.stderr)
            if not _ERR_SAMPLE and _CALL_STATS.get("ok"):
                # 호출은 200 인데 결과가 비었다 = 인증 만료보다 필터/스펙 변경 쪽 의심.
                print("[nps_emp]   HTTP 는 정상 — 응답이 비었거나 필터 조건 불일치. "
                      "getBassInfoSearchV2 응답 스펙 변경 여부 확인 필요.", file=sys.stderr)
            else:
                print("[nps_emp]   data.go.kr 활용신청 만료/일일 트래픽 초과 우선 확인 "
                      "(키는 API 별로 따로 승인됨 — 다른 공공데이터 수집기가 살아 있어도 "
                      "국민연금 서비스만 만료될 수 있음).", file=sys.stderr)
            return 1
        now = datetime.now(KST)

        # 🚨 부분 수집 병합 (2026-08-07) — 이전 스냅샷을 밑에 깔고 이번 결과로 덮는다.
        #   사고: 2026-07-15 정기 run 이 90분 timeout 으로 죽어 6월분을 통째로 놓쳤고,
        #   데이터가 5월에 한 달간 묶여 있었다. 통짜 교체 방식이면 중간에 끊긴 run 의
        #   성과가 0 이 되고, 부분 결과를 그대로 쓰면 미수집 종목이 화면에서 사라진다.
        #   레코드마다 자기 기준월(ym)을 들고 있으므로, 종목별로 가장 최신 월을 유지하면
        #   끊긴 run 도 진척이 남고 사라지는 종목도 없다.
        merged: Dict[str, Any] = {}
        try:
            with open(OUT_PATH, encoding="utf-8") as f:
                merged = dict((json.load(f).get("stocks") or {}))
        except (FileNotFoundError, json.JSONDecodeError):
            merged = {}
        for tk, v in stocks.items():
            prev = merged.get(tk)
            # 더 오래된 월로 덮어쓰지 않는다(소스가 과거월을 되돌려주는 경우 방어).
            if prev and str(v.get("ym") or "") < str(prev.get("ym") or ""):
                continue
            merged[tk] = v

        suspect_n = _flag_suspect(merged)

        yms = sorted({str(v.get("ym") or "") for v in merged.values() if v.get("ym")})
        doc = {
            "_meta": {
                "generated_at": now.strftime("%Y-%m-%dT%H:%M:%S+09:00"),
                "source": "국민연금공단 가입 사업장 내역 (data.go.kr B552015, 매월 15일 이후 갱신)",
                "note": "고용 프록시(국민연금 가입자 기준) · 사업장명 정확일치 매칭 · 공단 공시 사실",
                "count": len(merged),
                # 🚨 정확일치 매칭의 구조적 한계 신고 — 아래 _flag_suspect 주석 참조.
                "suspect_count": suspect_n,
                "suspect_rule": f"시총 ÷ 가입자 > {_SUSPECT_CAP_PER_HEAD / 1e8:,.0f}억/인",
                # 신선도 관측 — 종목마다 기준월이 다를 수 있어 범위로 노출한다.
                "data_ym_latest": yms[-1] if yms else None,
                "data_ym_oldest": yms[0] if yms else None,
                "fetched_this_run": len(stocks),
            },
            "stocks": merged,
        }
        with open(OUT_PATH, "w", encoding="utf-8") as f:
            json.dump(doc, f, ensure_ascii=False)
        with open(HIST_PATH, "a", encoding="utf-8") as f:
            # 🚨 ym = **데이터 기준월**(레코드의 dataCrtYm). 실행 월이 아니다.
            #   종전엔 실행 월을 적어, 7월에 돌며 받은 5월 데이터가 202507 로 기록됐다
            #   = 시계열 오염(2개월 밀린 값이 최신 월로 둔갑). 이번 run 결과만 적재한다.
            run_ym = now.strftime("%Y%m")
            for tk, v in stocks.items():
                f.write(json.dumps({"ym": str(v.get("ym") or run_ym), "run_ym": run_ym,
                                    "ticker": tk, "cnt": v["jnngp_cnt"],
                                    "hire": v["hire"], "leave": v["leave"]}, ensure_ascii=False) + "\n")
        print(f"[nps_emp] logged=True · 이번 run {len(stocks)} · 누적 {len(merged)}종목 · "
              f"기준월 {yms[0] if yms else '?'}~{yms[-1] if yms else '?'} "
              f"→ {os.path.relpath(OUT_PATH, _ROOT)} (+history)", file=sys.stderr)
        ok = True
        return 0
    except Exception as e:  # noqa: BLE001
        print(f"[nps_emp] FAILED: {e!r}", file=sys.stderr)
        return 1
    finally:
        if not ok:
            print("[nps_emp] logged=False", file=sys.stderr)


if __name__ == "__main__":
    if "--source-latest" in sys.argv:
        latest = probe_source_latest_month()
        if latest:
            print(latest)
            sys.exit(0)
        print("[nps_emp] 원천 최신월 탐침 실패", file=sys.stderr)
        sys.exit(1)
    sys.exit(main())
