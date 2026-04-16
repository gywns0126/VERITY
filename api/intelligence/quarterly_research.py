"""
Perplexity API 기반 분기 딥리서치 엔진
periodic_quarterly 모드 / strategy_evolver 패턴 재사용
"""
import os, re, json, logging, requests
from datetime import datetime, date
from pathlib import Path
from typing import Optional

logger = logging.getLogger(__name__)

PERPLEXITY_API_KEY = os.getenv("PERPLEXITY_API_KEY", "")
PERPLEXITY_MODEL   = os.getenv("PERPLEXITY_MODEL", "sonar-pro")
PERPLEXITY_URL     = "https://api.perplexity.ai/chat/completions"
ARCHIVE_DIR        = Path("data/research_archive")
CONSTITUTION_PATH  = Path("data/verity_constitution.json")


def _load_analysis_protocol() -> str:
    """verity_constitution.json에서 분석 프로토콜+전망 시간대를 로드하여 텍스트 블록 반환."""
    try:
        with open(CONSTITUTION_PATH, "r", encoding="utf-8") as f:
            const = json.load(f)
        si = const.get("gemini_system_instruction", {})
        sections = []
        tone = si.get("tone", "")
        if tone:
            sections.append(f"[Tone] {tone}")
        principles = si.get("principles", [])
        if principles:
            sections.append("[Core Principles]\n" + "\n".join(f"- {p}" for p in principles))
        protocol = si.get("analysis_protocol", [])
        if protocol:
            sections.append("[Analysis Protocol]\n" + "\n".join(f"- {a}" for a in protocol))
        horizons = si.get("forecast_horizons", [])
        if horizons:
            sections.append("[Forecast Horizons]\n" + "\n".join(f"- {h}" for h in horizons))
        return "\n\n".join(sections)
    except Exception:
        return ""

def build_prompt(constitution: dict, performance: dict,
                 postmortem: dict, market_ctx: dict) -> str:
    fw = json.dumps(constitution.get("fact_score",{}).get("weights",{}), indent=2)
    return f"""
[VERITY 분기 딥리서치 — {date.today().isoformat()}]

당신은 월스트리트 상위 0.01% 퀀트 헤지펀드 수석 애널리스트입니다.
아래 컨텍스트 기반으로 VERITY 전략 분기 리포트를 작성하세요.

━━━ Constitution 현황 ━━━
Fact Score 가중치: {fw}
Hit Rate: {performance.get('hit_rate','N/A')} | Sharpe: {performance.get('sharpe_ratio','N/A')} | MDD: {performance.get('max_drawdown','N/A')}
최근 실패 패턴: {postmortem.get('top_lesson','없음')}
매크로 레짐: {market_ctx.get('economic_quadrant','UNKNOWN')} | F&G: {market_ctx.get('fear_greed_score','N/A')} | VIX: {market_ctx.get('vix','N/A')}
━━━━━━━━━━━━━━━━━━━━━━━━

## 1. 유지할 원칙 (5개) — 표: 원칙명 | 근거 | 수치
## 2. 수정 제안 (5개) — 표: 파라미터 | 현재값 | 제안값 | 이유 | 파일명
## 3. Constitution JSON 패치 초안
```json
{{{{ 변경 파라미터만 포함 }}}}
```
## 4. 위험 시나리오 (3개) — 표: 시나리오 | 확률 | 트리거 | VERITY 대응
## 5. 다음 분기 KPI — 표: KPI | 목표값 | 측정 방법
## 6. 즉시적용 / 검증후적용 / 보류 분류표

규칙: 한국어, 표 중심, 수치 근거 없는 주장 금지, 추측 시 '추가 검증 필요' 명시
""".strip()

def call_perplexity(prompt: str) -> dict:
    if not PERPLEXITY_API_KEY:
        raise ValueError("PERPLEXITY_API_KEY 미설정")

    protocol_block = _load_analysis_protocol()
    system_content = (
        "VERITY 수석 퀀트 전략 애널리스트. 추측 금지, 불확실 시 '추가 검증 필요' 명시.\n\n"
        + protocol_block
    )

    resp = requests.post(
        PERPLEXITY_URL,
        headers={"Authorization": f"Bearer {PERPLEXITY_API_KEY}",
                 "Content-Type": "application/json"},
        json={
            "model": PERPLEXITY_MODEL,
            "messages": [
                {"role": "system", "content": system_content},
                {"role": "user", "content": prompt}
            ],
            "temperature": 0.2, "max_tokens": 4096,
            "search_recency_filter": "month",
            "return_citations": True,
        },
        timeout=120
    )
    resp.raise_for_status()
    data = resp.json()
    return {
        "content":           data["choices"][0]["message"]["content"],
        "citations":         data.get("citations", []),
        "prompt_tokens":     data.get("usage",{}).get("prompt_tokens", 0),
        "completion_tokens": data.get("usage",{}).get("completion_tokens", 0),
        "total_tokens":      data.get("usage",{}).get("total_tokens", 0),
    }

def extract_patch(content: str) -> Optional[dict]:
    for match in re.findall(r'```json\s*(\{[\s\S]*?\})\s*```', content):
        try:
            p = json.loads(match)
            if isinstance(p, dict) and len(p) > 0:
                return p
        except json.JSONDecodeError:
            continue
    return None

def _deep_merge(base: dict, override: dict) -> dict:
    result = base.copy()
    for k, v in override.items():
        if k in result and isinstance(result[k], dict) and isinstance(v, dict):
            result[k] = _deep_merge(result[k], v)
        else:
            result[k] = v
    return result

def apply_patch(patch: dict) -> bool:
    """Telegram /approve_strategy 승인 후 호출"""
    try:
        with open(CONSTITUTION_PATH, "r", encoding="utf-8") as f:
            current = json.load(f)
        backup = CONSTITUTION_PATH.with_suffix(
            f".backup_{datetime.now().strftime('%Y%m%d_%H%M%S')}.json")
        backup.write_text(json.dumps(current, ensure_ascii=False, indent=2))
        merged = _deep_merge(current, patch)
        merged["_last_updated"] = datetime.now().isoformat()
        with open(CONSTITUTION_PATH, "w", encoding="utf-8") as f:
            json.dump(merged, f, ensure_ascii=False, indent=2)
        logger.info("[QuarterlyResearch] 패치 적용 완료")
        return True
    except Exception as e:
        logger.error(f"[QuarterlyResearch] 패치 실패: {e}")
        return False

def build_research_context_for_evolution() -> Optional[str]:
    """strategy_evolver가 Claude 프롬프트에 분기 인사이트를 포함할 수 있도록 요약 텍스트 반환."""
    try:
        archive_files = sorted(ARCHIVE_DIR.glob("*.json"), reverse=True)
        if not archive_files:
            return None

        with open(archive_files[0], "r", encoding="utf-8") as f:
            latest = json.load(f)

        content = latest.get("content", "")
        quarter = latest.get("quarter", "?")
        generated = latest.get("generated_at", "?")
        patch = latest.get("constitution_patch_proposal")

        summary = content[:1500] if len(content) > 1500 else content

        sections = [
            f"═══ 분기 딥리서치 인사이트 ({quarter}, {generated[:10]}) ═══",
            summary,
        ]

        if patch:
            sections.append(f"\n제안된 Constitution 패치 키: {', '.join(patch.keys())}")

        return "\n".join(sections)
    except Exception:
        return None


def load_pending_quarterly_patch() -> Optional[dict]:
    """가장 최근 아카이브에서 pending_review 상태의 패치 제안을 로드."""
    try:
        archive_files = sorted(ARCHIVE_DIR.glob("*.json"), reverse=True)
        for af in archive_files:
            with open(af, "r", encoding="utf-8") as f:
                data = json.load(f)
            if data.get("status") == "pending_review" and data.get("constitution_patch_proposal"):
                return {
                    "patch": data["constitution_patch_proposal"],
                    "quarter": data.get("quarter", "?"),
                    "archive_path": str(af),
                    "generated_at": data.get("generated_at", "?"),
                }
        return None
    except Exception:
        return None


def mark_patch_applied(archive_path: str):
    """아카이브 파일의 status를 applied로 변경."""
    try:
        p = Path(archive_path)
        if not p.exists():
            return
        with open(p, "r", encoding="utf-8") as f:
            data = json.load(f)
        data["status"] = "applied"
        data["applied_at"] = datetime.now().isoformat()
        with open(p, "w", encoding="utf-8") as f:
            json.dump(data, f, ensure_ascii=False, indent=2)
    except Exception:
        pass


def run_quarterly_research(
    performance_path: str = "data/performance_stats.json",
    postmortem_path:  str = "data/postmortem_latest.json",
    market_context:   Optional[dict] = None,
) -> dict:
    """api/main.py periodic_quarterly 경로에서 호출"""
    def _load(path, default):
        try:
            with open(path, "r", encoding="utf-8") as f: return json.load(f)
        except FileNotFoundError: return default

    constitution = _load(str(CONSTITUTION_PATH), {})
    performance  = _load(performance_path,  {"hit_rate":"N/A","sharpe_ratio":"N/A","max_drawdown":"N/A"})
    postmortem   = _load(postmortem_path,   {"top_lesson":"없음"})
    market_ctx   = market_context or {}

    prompt  = build_prompt(constitution, performance, postmortem, market_ctx)
    result  = call_perplexity(prompt)
    patch   = extract_patch(result["content"])

    today   = date.today()
    quarter = f"{today.year}Q{(today.month-1)//3+1}"

    ARCHIVE_DIR.mkdir(parents=True, exist_ok=True)
    archive = {
        "quarter": quarter,
        "generated_at": datetime.now().isoformat(),
        "content": result["content"],
        "citations": result["citations"],
        "constitution_patch_proposal": patch,
        "token_usage": {
            "prompt": result["prompt_tokens"],
            "completion": result["completion_tokens"],
            "total": result["total_tokens"],
        },
        "status": "pending_review"
    }
    path = ARCHIVE_DIR / f"{quarter}_{datetime.now().strftime('%Y%m%d_%H%M%S')}.json"
    path.write_text(json.dumps(archive, ensure_ascii=False, indent=2))

    cost = (result["prompt_tokens"] * 3 + result["completion_tokens"] * 15) / 1_000_000

    return {
        "status": "success",
        "quarter": quarter,
        "archive_path": str(path),
        "constitution_patch_proposal": patch,
        "summary": result["content"][:500] + "...",
        "citations_count": len(result["citations"]),
        "token_cost_usd": round(cost, 4),
        "patch_status": "pending_review",
        "apply_command": "/approve_strategy quarterly",
    }
