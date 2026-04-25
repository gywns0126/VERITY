# ESTATE Pending — Vercel deployment 에서 분리 보관

이 디렉토리는 **VERITY (verity-chat) Vercel 프로젝트** 에 포함시키지 않을
ESTATE (부동산 도메인) 신규 endpoint 들을 보관합니다.

## 분리 사유 (2026-04-25)

Vercel Hobby plan **Serverless Functions 12개 한도** 초과로
chat / stock / order 등 VERITY 본 endpoint 까지 배포 실패.

ESTATE 는 아직 사용자에게 노출되지 않은 신규 프로젝트이므로
별도 Vercel 프로젝트로 분리해서 본격 배포하는 것이 깨끗.

## 보관 파일

### Endpoints (api/ 직속)
- `digest_publish_readiness.py`
- `estate_alerts.py`
- `estate_watchgroups.py`
- `landex_health.py`
- `landex_methodology.py`
- `landex_scores.py`

### Helper modules (라우팅 안 됨, 위 endpoint 들이 import)
- `landex/__init__.py`
- `landex/_compute.py`
- `landex/_methodology.py`
- `landex/_snapshot.py`
- `landex/_sources/__init__.py`
- `landex/_sources/_lawd.py`
- `landex/_sources/ecos.py`
- `landex/_sources/molit.py`
- `landex/_sources/seoul_subway.py`

## ESTATE 본격 시작 시 절차

1. 별도 GitHub repo 또는 monorepo 의 별 Vercel 프로젝트 생성 (예: `verity-estate`)
2. 이 디렉토리 내용을 새 프로젝트의 `api/` 로 이동
3. Vercel 프로젝트 settings 에서 새 도메인 + 환경변수 설정
4. 새 vercel.json 작성 (functions / rewrites)
5. Framer ESTATE 페이지에서 새 도메인 호출

## 가져갈 vercel.json 조각 (2026-04-25 시점 백업)

```json
{
  "functions": {
    "api/landex_health.py":          { "maxDuration": 5 },
    "api/landex_methodology.py":     { "maxDuration": 5 },
    "api/landex_scores.py":          { "maxDuration": 10 },
    "api/digest_publish_readiness.py": { "maxDuration": 5 },
    "api/estate_watchgroups.py":     { "maxDuration": 10 },
    "api/estate_alerts.py":          { "maxDuration": 10 }
  },
  "rewrites": [
    { "source": "/api/landex/health",            "destination": "/api/landex_health" },
    { "source": "/api/landex/methodology",       "destination": "/api/landex_methodology" },
    { "source": "/api/landex/scores",            "destination": "/api/landex_scores" },
    { "source": "/api/digest/publish-readiness", "destination": "/api/digest_publish_readiness" },
    { "source": "/api/estate/watchgroups",       "destination": "/api/estate_watchgroups" },
    { "source": "/api/estate/alerts",            "destination": "/api/estate_alerts" }
  ]
}
```
