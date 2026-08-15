"""
OpenDART 상장사 고유번호 매핑 생성 및 조회 모듈

dart-fss 라이브러리로 전체 상장사의 {종목코드: 고유번호} 매핑을 빌드하여
data/mapping.json에 저장한다. 이후 OpenDART API 호출 시 get_corp_code()로
종목코드 → 고유번호를 즉시 조회할 수 있다.
"""
import datetime as _dt
import json
import os
import sys
from typing import Dict, Optional

import dart_fss

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", ".."))
from api.config import DART_API_KEY, DATA_DIR

MAPPING_PATH = os.path.join(DATA_DIR, "mapping.json")
# {종목코드: 종목명} — 챗 name_resolver 가 역맵으로 종목명→코드 결정적 변환 (L2, 2026-06-03).
# corp_list 를 어차피 순회하므로 추가 API 호출 0. 챗(Vercel)은 publish 된 이 파일만 읽음.
NAME_MAP_PATH = os.path.join(DATA_DIR, "kr_stock_names.json")
# {종목코드: {"name","market"}} — 현재 상장사만 (corp_cls Y=KOSPI/.KS, K=KOSDAQ/.KQ).
# 폐지 종목(corp_cls None)·코넥스(N) 제외. group_structure resolver 가 전 KRX
# 이름→ticker_yf 역맵 빌드에 사용 (NAV listed 매칭 복구, 2026-06-16). kr_stock_names 와
# 달리 폐지 오염 없음 + market suffix 보유.
LISTED_MAP_PATH = os.path.join(DATA_DIR, "kr_listed.json")
# 맵 3종의 생성 시각 사이드카. 맵 파일 안에 넣으면 전 키를 순회하는 소비자가 깨진다.
NAME_MAP_META_PATH = os.path.join(DATA_DIR, "kr_name_map_meta.json")
_CORP_CLS_TO_SUFFIX = {"Y": "KS", "K": "KQ"}  # Y=유가증권(KOSPI), K=코스닥
_NAME_MAP_MAX_AGE_S = 30 * 24 * 3600  # 30일 — 신규 상장 흡수 주기 (월1회 갱신 등가)

_mapping_cache: Optional[Dict[str, str]] = None
_name_ensured = False


def build_mapping() -> Dict[str, str]:
    """dart-fss로 전체 상장사 목록을 받아 {종목코드: 고유번호} + {종목코드: 종목명} 동시 생성·저장."""
    if not DART_API_KEY:
        raise RuntimeError("DART_API_KEY 환경변수가 설정되지 않았습니다.")

    dart_fss.set_api_key(DART_API_KEY)
    corp_list = dart_fss.get_corp_list()

    mapping: Dict[str, str] = {}
    names: Dict[str, str] = {}
    listed: Dict[str, Dict[str, str]] = {}
    for corp in corp_list:
        stock_code = getattr(corp, "stock_code", None)
        corp_code = getattr(corp, "corp_code", None)
        if stock_code and corp_code:
            sc = stock_code.strip()
            mapping[sc] = corp_code.strip()
            nm = (getattr(corp, "corp_name", None) or "").strip()
            if nm:
                names[sc] = nm
            # corp_cls Y/K 만 현재 상장 (None=폐지, N=코넥스 제외).
            cls = (getattr(corp, "corp_cls", None) or "").strip()
            suffix = _CORP_CLS_TO_SUFFIX.get(cls)
            if suffix and nm:
                listed[sc] = {"name": nm, "market": suffix}

    os.makedirs(DATA_DIR, exist_ok=True)
    with open(MAPPING_PATH, "w", encoding="utf-8") as f:
        json.dump(mapping, f, ensure_ascii=False, indent=2)
    with open(NAME_MAP_PATH, "w", encoding="utf-8") as f:
        json.dump(names, f, ensure_ascii=False, indent=2)
    with open(LISTED_MAP_PATH, "w", encoding="utf-8") as f:
        json.dump(listed, f, ensure_ascii=False, indent=2)
    # 🚨 생성 시각을 **내용으로** 남긴다 — 파일 mtime 은 CI 에서 무의미하다(아래 참조).
    #    맵 3종은 소비자가 전 키를 순회하므로 `_generated_at` 를 그 안에 넣으면 깨진다.
    #    그래서 별도 사이드카 파일로 둔다.
    with open(NAME_MAP_META_PATH, "w", encoding="utf-8") as f:
        json.dump({"generated_at": _dt.datetime.now(_dt.timezone.utc).isoformat(),
                   "mapping": len(mapping), "names": len(names), "listed": len(listed)},
                  f, ensure_ascii=False, indent=2)

    return mapping


def ensure_name_map() -> None:
    """kr_stock_names.json 이 없거나 30일 초과면 재생성 (dart-fss). fail-safe — 실패해도 진행.

    daily_analysis_full(DART_API_KEY 보유, git add data/ broad, publish-data 호출)의
    load_mapping 경유로 발동 → 생성·커밋·publish 자동 (전용 cron 불필요). 프로세스당 1회.
    """
    global _name_ensured
    if _name_ensured:
        return
    _name_ensured = True
    try:
        # 🚨 신선도 판정을 **파일 mtime 에서 내용 타임스탬프로** 옮긴다 (2026-08-15 감사).
        #    GitHub Actions 는 매 run 마다 repo 를 새로 체크아웃하므로 모든 파일의 mtime 이
        #    "방금" 이다. 즉 `time() - getmtime(...) > 30일` 은 CI 에서 **영원히 거짓**이고,
        #    30일 갱신 게이트가 한 번도 발동한 적이 없다. 위 docstring 이 설계 의도로
        #    "daily_analysis_full 경유로 발동 → 생성·커밋 자동" 이라 적어 둔 그 경로가
        #    조용히 죽어 있었다.
        #    증거: kr_stock_names.json 마지막 커밋 2026-06-03 · kr_listed.json 2026-06-17.
        #    증상: 신규 상장(예 476710)이 맵에 영영 안 들어온다 — 조인의 상장정보·이름
        #    검증 축이 신규 종목에 대해 침묵한다. 에러·경보 0 이라 미탐지되는 계열이다.
        need = True
        meta_age = None
        if os.path.exists(NAME_MAP_META_PATH):
            try:
                with open(NAME_MAP_META_PATH, encoding="utf-8") as _mf:
                    gen = json.load(_mf).get("generated_at")
                if gen:
                    born = _dt.datetime.fromisoformat(gen)
                    if born.tzinfo is None:
                        born = born.replace(tzinfo=_dt.timezone.utc)
                    meta_age = (_dt.datetime.now(_dt.timezone.utc) - born).total_seconds()
                    need = meta_age > _NAME_MAP_MAX_AGE_S
            except (OSError, ValueError, TypeError):
                need = True          # 메타를 못 읽으면 재생성 — 조용히 옛 맵을 쓰지 않는다
        # 맵 자체가 없으면 무조건 재생성 (2026-06-16 self-heal 유지).
        if not os.path.exists(NAME_MAP_PATH) or not os.path.exists(LISTED_MAP_PATH):
            need = True
        if need:
            sys.stderr.write(
                "[name_map] 갱신 필요 — "
                + ("메타 부재(최초 1회)" if meta_age is None else f"생성 후 {meta_age / 86400:.1f}일")
                + "\n")
        if need and DART_API_KEY:
            sys.stderr.write("[name_map] kr_stock_names.json 생성/갱신 (dart-fss, ~1분)\n")
            build_mapping()
    except Exception as _e:  # 분석 파이프라인을 깨지 않음
        sys.stderr.write(f"[name_map] ensure 실패(무시): {type(_e).__name__}: {_e}\n")


def load_mapping() -> Dict[str, str]:
    """mapping.json을 로드하여 모듈 레벨에 캐싱한다.

    2026-05-18 — 부재 시 자동 build fallback (dart-fss ~1분 fetch).
    옛: FileNotFoundError → 모든 KR 종목 corp_code None → STEP 5.88 영구 skip.
    신: build_mapping() 시도 후 성공 시 cascade 정상화.
    """
    global _mapping_cache
    if _mapping_cache is not None:
        return _mapping_cache

    if not os.path.exists(MAPPING_PATH):
        sys.stderr.write(
            f"[mapping] {MAPPING_PATH} 부재 → 자동 build 시도 (dart-fss, ~1분)\n"
        )
        try:
            mapping = build_mapping()
            _mapping_cache = mapping
            sys.stderr.write(f"[mapping] 자동 build 성공 ({len(mapping)} entries)\n")
            return mapping
        except Exception as _be:
            sys.stderr.write(
                f"[mapping] 자동 build 실패: {type(_be).__name__}: {_be}\n"
            )
            raise FileNotFoundError(
                f"{MAPPING_PATH} 파일이 없고 자동 build 도 실패. "
                f"수동: python api/collectors/dart_corp_code.py. 원인: {_be}"
            )

    with open(MAPPING_PATH, "r", encoding="utf-8") as f:
        _mapping_cache = json.load(f)
    ensure_name_map()  # 이름맵 동반 보장 (fail-safe, 프로세스당 1회)
    return _mapping_cache


def get_corp_code(ticker: str) -> Optional[str]:
    """yfinance 형식 티커(예: '005930.KS')에서 DART 고유번호를 반환한다.

    ticker에서 '.KS', '.KQ' 등 suffix를 자동 제거하며,
    6자리 종목코드를 직접 넘겨도 동작한다.
    매핑에 없으면 None을 반환한다.
    """
    stock_code = ticker.split(".")[0]
    mapping = load_mapping()
    return mapping.get(stock_code)


if __name__ == "__main__":
    print("DART 상장사 고유번호 매핑 생성 시작...")
    result = build_mapping()
    print(f"완료: 총 {len(result)}개 상장사 매핑 → {MAPPING_PATH}")
