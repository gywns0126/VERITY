# ESTATE Backend — 별도 Vercel 프로젝트 (verity-estate)

이 디렉토리는 **TERMINAL `vercel-api` 프로젝트와 분리된** ESTATE 백엔드.
별도 Vercel 프로젝트(`verity-estate`)에서 deploy. Hobby plan 12 함수 한도 우회.

> ⚠️ **디렉터리 명에 `_` prefix 금지** — Vercel 빌드가 `_` 시작 디렉터리를 hidden 처리해서
> 함수 누락. 한때 `_estate_pending` 이었으나 2026-04-26 `estate_backend` 로 변경.

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

## 구조 정리 완료 (2026-04-25)

이 디렉토리는 이제 **자체완결된 Vercel 프로젝트** 형태:
- `api/` — endpoint 6개 + lib (landex/, cors_helper.py, supabase_client.py)
- `vercel.json` — functions + rewrites (clean URL)
- `requirements.txt` — Python deps (requests)
- `.gitignore` — env / pycache 제외

## Vercel 새 프로젝트 셋업 절차

1. https://vercel.com/kim-hyojuns-projects → **Add New → Project**
2. 같은 repo (`gywns0126/VERITY`) 선택
3. **Project Name**: `verity-estate` 권장
4. **Root Directory**: `vercel-api/estate_backend` 지정 (← 핵심)
5. **Framework Preset**: `Other`
6. **Environment Variables** (필수, 모두 Vercel 대시보드 → Settings → Environment Variables):
   - `PUBLICDATA_API_KEY` (국토부 실거래가)
   - `ECOS_API_KEY` (한국은행)
   - `SEOUL_DATA_API_KEY` (서울 일반)
   - `SEOUL_SUBWAY_API_KEY` (서울 지하철)
   - `KOSIS_API_KEY` (국가통계)
   - `SUPABASE_URL`
   - `SUPABASE_ANON_KEY`
   - `SUPABASE_SERVICE_ROLE_KEY` (snapshot 워커용)
   - `API_ALLOWED_ORIGINS` (예: `https://verity-estate.framer.app,https://...`)
7. Deploy

배포 완료 후 도메인 (예: `verity-estate-kim-hyojuns-projects.vercel.app`)으로 health 검증:
```
https://<도메인>/api/landex/health
```
→ `{ "ready": true, "missing": [] }`

## Framer ESTATE 페이지 연결

LandexMapDashboard / ScoreDetailPanel / WatchGroupsDashboard / AlertDashboard / DigestPublishPanel 의 `apiUrl` prop 에 위 도메인 입력.
