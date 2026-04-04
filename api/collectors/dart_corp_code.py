"""
OpenDART 상장사 고유번호 매핑 생성 및 조회 모듈

dart-fss 라이브러리로 전체 상장사의 {종목코드: 고유번호} 매핑을 빌드하여
data/mapping.json에 저장한다. 이후 OpenDART API 호출 시 get_corp_code()로
종목코드 → 고유번호를 즉시 조회할 수 있다.
"""
import json
import os
import sys
from typing import Dict, Optional

import dart_fss

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", ".."))
from api.config import DART_API_KEY, DATA_DIR

MAPPING_PATH = os.path.join(DATA_DIR, "mapping.json")

_mapping_cache: Optional[Dict[str, str]] = None


def build_mapping() -> Dict[str, str]:
    """dart-fss로 전체 상장사 목록을 받아 {종목코드: 고유번호} dict를 생성·저장한다."""
    if not DART_API_KEY:
        raise RuntimeError("DART_API_KEY 환경변수가 설정되지 않았습니다.")

    dart_fss.set_api_key(DART_API_KEY)
    corp_list = dart_fss.get_corp_list()

    mapping: Dict[str, str] = {}
    for corp in corp_list:
        stock_code = getattr(corp, "stock_code", None)
        corp_code = getattr(corp, "corp_code", None)
        if stock_code and corp_code:
            mapping[stock_code.strip()] = corp_code.strip()

    os.makedirs(DATA_DIR, exist_ok=True)
    with open(MAPPING_PATH, "w", encoding="utf-8") as f:
        json.dump(mapping, f, ensure_ascii=False, indent=2)

    return mapping


def load_mapping() -> Dict[str, str]:
    """mapping.json을 로드하여 모듈 레벨에 캐싱한다."""
    global _mapping_cache
    if _mapping_cache is not None:
        return _mapping_cache

    if not os.path.exists(MAPPING_PATH):
        raise FileNotFoundError(
            f"{MAPPING_PATH} 파일이 없습니다. "
            "먼저 python api/collectors/dart_corp_code.py 를 실행하세요."
        )

    with open(MAPPING_PATH, "r", encoding="utf-8") as f:
        _mapping_cache = json.load(f)
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
