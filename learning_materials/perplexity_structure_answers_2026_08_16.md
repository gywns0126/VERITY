# 퍼플렉시티 답변 — 파일 구조 재배치 (2026-08-16) · 원문 보존

질문 출처 = `docs/STRUCTURE_REVIEW_2026_08_16.md` §8 (Q1~Q6). PM 이 붙여넣어 받아온 답변 전문.
🚨 **원문 무손실 보존 — 요약·편집 금지.** 우리 판단·검증 결과는 문서 하단 "수신 측 검증" 절에만 적는다.

---

현재 구조에서는 **디렉터리 물리 분리 + 매니페스트 선언 + CI 기계 검증**을 기본 경계로 두고, 발행 스크립트의 allowlist는 마지막 방어선으로만 쓰는 것이 가장 안전합니다. 또한 1.6GB 작업트리와 1.3GB Git 이력에서 핵심 개선은 "데이터를 Git에 계속 커밋"하는 구조를 끊고, Git에는 코드·메타데이터·재현 가능한 snapshot manifest만 남기는 것입니다.

## 권장 목표 구조

공개 monorepo를 계속 유지하되, **public repo는 배포 가능한 공개 산출물만**, private data plane은 별도 저장소/오브젝트 스토리지에 두는 구조를 권합니다.

```text
repo/
├─ apps/
│  ├─ public-site/                 # 공개 웹·정적 사이트 생성기
│  ├─ api/                         # 공개 API 또는 Supabase 연동 코드
│  └─ admin-tools/                 # 로컬/비공개 실행용, 비밀값 제외
├─ packages/
│  ├─ domain/
│  ├─ factor-library/
│  ├─ data-contracts/
│  ├─ publish-policy/
│  └─ pipeline-core/
├─ pipelines/
│  ├─ ingest/
│  ├─ transform/
│  ├─ research/
│  └─ publish/
├─ config/
│  ├─ datasets/
│  │  ├─ prices_kr.yaml
│  │  ├─ factor_ic.yaml
│  │  └─ site_company_summary.yaml
│  ├─ publication/
│  │  └─ public-assets.yaml        # 공개 가능 dataset/artifact 선언
│  └─ retention/
│     └─ policies.yaml
├─ docs/
│  ├─ architecture/
│  ├─ runbooks/
│  └─ data-catalog/
├─ tests/
│  ├─ contracts/
│  ├─ publication/
│  └─ regression/
├─ public/
│  └─ generated/                   # 배포 대상 공개 산출물만
├─ manifests/
│  ├─ releases/
│  └─ snapshots/
└─ .github/
   ├─ workflows/
   └─ policies/
```

반대로 아래 경로는 public Git repository에 **원본 또는 장기 이력 자체를 두지 않는 것**이 좋습니다.

```text
private-data/
├─ raw/
├─ restricted/
├─ point_in_time/
├─ vendor_licensed/
├─ research_runs/
├─ model_outputs/
└─ full_snapshots/
```

VERITY처럼 장기 시계열·팩터·공시·LLM 산출물이 계속 증가하는 플랫폼에서는, 코드 저장소와 데이터 저장소를 동일한 versioning 모델로 다루면 결국 Git 히스토리와 워크플로가 병목이 됩니다. Git은 코드와 작은 선언 파일에 강하고, 대규모 append-only 시계열·스냅샷 저장소에는 적합하지 않습니다.

## Q1. 공개/비공개 경계

### 결론: 셋 중 하나가 아니라 계층형 통제

| 방식 | 장점 | 치명적 약점 | 권장 역할 |
|---|---|---|---|
| 발행 스크립트 allowlist | "무엇을 배포할지" 명확함 | 스크립트 우회·신규 workflow 누락·경로 오타에 취약 | 최종 publish gate |
| 디렉터리 물리 분리 | 인간이 이해하기 쉽고 accidental commit 감소 | 경로만으로는 비공개 데이터의 Git 추적·복제·외부 업로드를 완전히 막지 못함 | 기본 권한·경계 |
| 매니페스트 + 기계 검증 | 선언과 실제 상태를 비교하고 drift 탐지 가능 | 잘못된 manifest를 승인하면 함께 실패 | **정책 source of truth** |

가장 낮은 유출·누락 사고율을 노리려면 다음 4중 구조가 좋습니다.

```text
1. 물리적 경계:
   public/generated/ 외에는 publish output 경로로 사용할 수 없음

2. 선언적 경계:
   config/publication/public-assets.yaml에 공개 대상만 선언

3. 생성 경계:
   publish job은 manifest의 artifact_id만 받아 public/generated/에 생성

4. CI 검증:
   새 파일·새 workflow·새 public route가 manifest와 policy를 위반하면 merge 차단
```

Google SRE와 GitOps 계열의 기본 원칙은 desired state를 선언적으로 두고, 실제 상태와 선언 사이의 drift를 감지·복구하는 것입니다. Config Sync도 source of truth와 실제 리소스 간 차이를 감시하고 수정하는 self-healing/drift control을 제공합니다. (docs.cloud.google — kubernetes-engine/config-sync/docs/how-to/prevent-config-drift)

### 권장 공개 매니페스트

```yaml
# config/publication/public-assets.yaml
version: 1

artifacts:
  - id: company_profile_summary
    owner: public-site
    source_dataset: company_profile_private_v4
    output_path: public/generated/company/profile-summary.json
    visibility: public
    pii_classification: none
    license_classification: redistributable
    retention: latest-only
    schema_version: 2
    publish_job: publish-company-profile
    approval_required: false

  - id: factor_overview
    owner: factor-library
    source_dataset: factor_metrics_private_v7
    output_path: public/generated/factors/overview.json
    visibility: public
    pii_classification: none
    license_classification: derived-only
    retention: 90d
    schema_version: 3
    publish_job: publish-factor-overview
    approval_required: true
```

여기서 중요한 점은 `path`만 선언하지 않는 것입니다. 최소한 아래를 함께 선언해야 합니다.

- `artifact_id`
- owner
- 원본 dataset ID
- 공개 가능 라이선스 분류
- visibility
- output path
- schema version
- retention
- 생성 workflow/job
- 공개 전 변환 규칙
- approval 필요 여부
- 민감도 및 재식별 위험 등급

### CI에서 막아야 할 규칙

```text
- public/generated/** 아래의 파일은 manifest에 반드시 존재해야 한다.
- manifest의 public artifact는 output_path가 public/generated/** 밖이면 실패한다.
- public artifact가 private/raw/restricted source를 직접 복사하면 실패한다.
- vendor/licensed/restricted 데이터가 public output에 포함되면 실패한다.
- 모든 scheduled workflow는 outputs와 write scope를 등록해야 한다.
- workflow가 git add -A 또는 git add . 을 실행하면 실패한다.
- workflow가 public 브랜치에 직접 push하면 실패한다.
- publish는 release PR 또는 bot PR을 통해서만 가능하다.
```

특히 78개 workflow가 산출물을 커밋한다면 `git add .`, `git add -A`, `git commit -am`은 즉시 제거할 대상입니다. 각 workflow는 **명시된 artifact path만 stage**해야 합니다.

```bash
git add -- public/generated/factors/overview.json
git diff --cached --quiet || git commit -m "chore(data): publish factor overview"
```

아래는 금지합니다.

```bash
git add .
git add -A
git commit -am "update"
```

### 공개 저장소에서의 비공개 데이터 원칙

한 번 public Git history에 들어간 데이터는 삭제 커밋만으로 제거되지 않습니다. GitHub도 이전 커밋에 들어간 대용량 파일 또는 민감 파일을 제거하려면 `git filter-repo`로 history를 재작성해야 한다고 안내합니다. (docs.github — repositories/working-with-files/managing-large-files/about-large-files-on-github)

따라서 비공개 파일은 `.gitignore`만으로 보호하면 안 됩니다. 최소한:

- 실제 private data root는 repo 밖 또는 private storage에 둠
- public repo의 CI credential은 public output write-only 권한만 부여
- raw/point-in-time/vendor data credential은 public-site deployment workflow에 주지 않음
- public deployment에는 derived artifact만 전달
- 비밀키는 Git history, Framer CMS, public JSON, build log에 넣지 않음

## Q2. 경로 규약 변경: 전면 이관 vs grandfathering

### 결론: 데이터 경로는 전면 이관, 코드 import는 단계적 이관

당신의 경우에는 **"영구 grandfathering"은 피하고, 짧고 명시적인 migration window가 있는 단계적 전면 이관**이 가장 안전합니다.

수천 개 파일이 있는 상황에서 한 번에 모든 파일을 수동 이동하는 것은 위험합니다. 하지만 신규 산출물만 새 규약을 적용하고 기존 산출물은 영구적으로 옛 규약에 남기는 방식은 시간이 갈수록 더 위험합니다.

| 선택지 | 단기 위험 | 장기 위험 | 권장 여부 |
|---|---:|---:|---|
| 즉시 전면 이관 | 높음 | 낮음 | 데이터가 적고 자동 변환 가능할 때 |
| 영구 grandfathering | 낮음 | **매우 높음** | 비권장 |
| 단계적 전면 이관 | 중간 | 낮음 | **권장** |
| 신규 규약만 적용 + 무기한 legacy 유지 | 낮음 | 높음 | 비권장 |

### 왜 두 규약 공존이 실패하는가

두 규약이 공존하면 보통 다음 문제가 생깁니다.

- workflow A는 `data/daily/`, workflow B는 `outputs/daily/`에 기록
- publish script는 새 경로만 읽어 누락이 발생
- cleanup job은 옛 경로를 모르게 되어 retention이 적용되지 않음
- 동일 dataset이 old/new 양쪽에 존재해 stale copy가 공개됨
- 신규 개발자가 어느 경로가 정답인지 몰라 세 번째 경로를 만듦
- 백테스트는 legacy snapshot을 읽고 production은 새 snapshot을 읽는 split-brain 발생
- Git rename detection이 완벽하지 않아 파일 이력이 추적하기 어려워짐

즉 실패 원인은 "두 경로가 있다"가 아니라, **canonical location이 하나가 아니게 되는 것**입니다.

### 추천 마이그레이션 방식

1. **새 canonical contract를 먼저 정의** — dataset ID / 공개 여부 / retention / owner / canonical URI / schema version / point-in-time semantics
2. **legacy 경로를 registry에 등록** — "이 경로는 2026-12-31 폐기" / "read-only" / "새 write 금지" / "새 publish 금지"
3. **write는 먼저 새 경로만 허용** — legacy는 읽기 호환만 유지, CI가 legacy path 신규 파일을 차단
4. **읽기 경로는 adapter로 일시 통합** — production code가 경로를 직접 참조하지 않게 함. `dataset_uri("kr_prices_daily", as_of=...)` 같은 resolver를 사용
5. **자동 migration + checksum 검증** — 파일 수 / row count / schema / partition / hash / 공개 산출물 diff / backtest result tolerance
6. **cutover date 후 legacy read도 종료** — legacy storage는 archive로 이동, manifest에는 historical locator만 남김

### 실전 규칙

```text
새 파일은 legacy 경로에 write할 수 없다.
legacy 경로는 새 workflow의 output으로 지정할 수 없다.
모든 dataset은 canonical dataset_id 하나를 가진다.
경로는 구현 세부사항이고, 코드에서는 dataset_id만 참조한다.
legacy 호환은 종료일과 owner가 없는 한 허용하지 않는다.
```

## Q3. Git에 누적되는 시계열 스냅샷

### 결론

백테스트 재현성을 위해 **모든 원본 시계열 스냅샷을 Git에 영구 커밋할 필요는 없습니다.** 오히려 Git에는 snapshot manifest, schema, checksum, code version, data-as-of time만 남기고, 실제 데이터 blob은 versioned object storage 또는 private data repository에 두는 것이 표준적인 방향입니다.

GitHub는 일반 Git 파일 100MiB 초과를 막으며, 큰 파일 추적에는 Git LFS를 요구합니다. 그러나 LFS는 대형 immutable data lake를 대체하는 도구가 아니라, 비교적 제한된 대형 binary의 versioned 협업을 위한 도구입니다. (docs.github — managing-large-files/about-large-files-on-github)

### 선택지 비교

| 방식 | 장점 | 단점 | 적합한 대상 |
|---|---|---|---|
| 일반 Git | diff, review, 작은 JSON/CSV에 편리 | history가 계속 비대해짐, clone·CI 느려짐 | 설정, schema, 작은 공개 snapshot |
| Git LFS | Git tree를 가볍게 유지, binary pointer 관리 | 저장·bandwidth 비용, 대규모 partition query 불가, history는 여전히 운영 부담 | 모델 파일, 작은 수의 대형 release asset |
| 롤링 보존 | 비용·용량을 즉시 통제 | 오래된 backtest 재현이 어려움 | 재생성 가능한 임시 산출물 |
| 별도 private Git repo | 접근권한 분리·운영 이해 쉬움 | 대규모 data versioning에는 여전히 Git 한계 | 작은 private config·curated dataset |
| Object storage + versioning | 대량·append-only·partitioned snapshot에 적합 | 초기 setup 필요 | **원본 시계열, PIT snapshots, parquet, LLM corpus** |
| 데이터 레이크 + catalog | lineage·time-travel·query·retention에 강함 | 복잡도·비용 증가 | 장기 대형 플랫폼 |

GitHub Actions cache는 기본적으로 repository당 10GB 수준이고, 최근 7일 미접근 cache는 제거됩니다. cache는 재현성 저장소가 아니라 빌드 속도용 일시 저장소입니다. (docs.github — actions/reference/workflows-and-actions/dependency-caching)

Actions artifact도 기본 보존기간이 90일이며, public repository는 1~90일 범위로만 설정할 수 있습니다. 장기 백테스트 입력이나 규제성 audit snapshot을 artifact에 맡기면 안 됩니다. (docs.github — actions/tutorials/store-and-share-data)

### 당신에게 권장하는 4층 데이터 보존

```text
Tier 0 — Git
  코드, 파이프라인 정의, schema, manifest, checksum, data contract,
  release note, 공개용 소형 정적 산출물

Tier 1 — Object storage hot
  최근 30~90일 raw/derived partition,
  일별 갱신 price/factor/publication input,
  빠른 재실행 대상

Tier 2 — Object storage warm/versioned
  백테스트에 필요한 point-in-time parquet snapshot,
  DART 실제 접수시각 기준 data,
  universe/security master,
  월별/분기별 immutable checkpoint

Tier 3 — Archive/cold
  과거 원문, 장기 raw snapshot, 폐기 모델 결과,
  드물지만 재현·감사 시 필요한 보관본
```

### 백테스트 재현성의 최소 단위

각 backtest run은 실제 데이터 파일을 Git에 넣는 대신 다음 manifest를 남기면 됩니다.

```yaml
run_id: bt_kr_factor_2026_08_16_001
strategy_version: git:ab12cd34
environment_lock: sha256:...
universe_snapshot:
  uri: s3://private-data/snapshots/universe/2026-08-15.parquet
  sha256: ...
market_data_snapshot:
  uri: s3://private-data/snapshots/prices/2026-08-15/
  content_hash: ...
fundamental_data_snapshot:
  uri: s3://private-data/snapshots/dart-pit/2026-08-15/
  content_hash: ...
as_of_cutoff: "2026-08-15T15:30:00+09:00"
calendar_version: krx_calendar_v2
corporate_action_version: ca_v4
result_hash: sha256:...
```

이 방식의 핵심은 재현성 = code version + environment + data snapshot identity + as-of semantics 이지,
반드시 "모든 데이터 blob이 Git commit 안에 존재한다"가 아닙니다.

### 롤링 보존 정책

| 데이터 유형 | 권장 보존 |
|---|---|
| CI intermediate output | 1~14일 |
| 일별 재생성 가능 raw fetch | 30~90일 hot, 이후 archive 또는 삭제 |
| 공개 사이트 build artifact | latest + 최근 10~30 releases |
| EOD 가격·corporate action | 장기 보존, 월별/분기별 immutable snapshot |
| DART·재무 PIT 데이터 | 장기 보존, 수정본과 최초 공시본 분리 |
| 백테스트 승인 run input | 해당 전략 수명 + 최소 3~7년 archive |
| LLM 원문·score | 라이선스·개인정보·저작권 정책에 맞춘 별도 retention |
| cache | 7일 내외, 재현성 용도 금지 |

현재 `.git`만 1.3GB라는 것은, 파일을 최근 커밋에서 삭제해도 과거 blob이 남아 있을 가능성이 큽니다. GitHub도 history에서 제거하려면 `git filter-repo`를 권장합니다.

## Q4. "1건 추가 = 7곳 등재" 제거

### 결론: codegen을 기본으로, lint를 독립 안전장치로

둘 중 하나만 고르면 **codegen이 운영 누락에 더 강합니다.** 사람이 7개 위치를 업데이트해야 하는 구조에서 lint는 "누락을 발견"할 뿐이고, codegen은 "중복 입력 자체를 제거"합니다.

다만 codegen만 쓰면 generator bug나 잘못된 source declaration이 여러 산출물을 동시에 망칠 수 있으므로, 최종 구조는 다음이 좋습니다.

```text
Canonical manifest
   ↓
Code generation
   ├─ workflow matrix
   ├─ dataset registry
   ├─ publish allowlist
   ├─ docs/catalog page
   ├─ retention rule
   └─ site route/index
   ↓
Independent linter / reconciliation test
   ├─ manifest ↔ filesystem
   ├─ manifest ↔ workflows
   ├─ manifest ↔ public output
   ├─ manifest ↔ docs
   └─ manifest ↔ object-store metadata
```

### 권장 구분

| 항목 | codegen | lint/reconciliation |
|---|---:|---:|
| GitHub Actions workflow matrix | 예 | 생성 결과가 실제 등록 workflow와 일치하는지 |
| publish allowlist | 예 | publish output에 rogue file 없는지 |
| data catalog 문서 | 예 | docs에 manual-only dataset 없는지 |
| site navigation/index | 예 | deployed route가 manifest와 일치하는지 |
| retention policy | 예 | 실제 object lifecycle/tag와 일치하는지 |
| schema contract | 선언 중심 | 실제 output schema validation |
| owner/review date | 선언 중심 | overdue review 탐지 |
| data sensitivity | 선언 중심 | 공개 output scan 및 secret/PII 검사 |

### anti-pattern

```text
새 dataset을 추가할 때:
- workflow YAML 수정
- README 수정
- publish.py 수정
- site route 수정
- ignore rule 수정
- retention script 수정
- dashboard 목록 수정
```

이 구조는 필연적으로 누락됩니다. 특히 혼자 운영할수록 컨텍스트 스위칭 비용이 커서 "이번에는 docs만 나중에"가 영구화됩니다.

### manifest 기반 예시

```yaml
id: kr_factor_daily
kind: derived_dataset
owner: factor-library
schedule: "20 8 * * 1-5"
storage:
  backend: object_store
  prefix: derived/factors/kr/daily
  partition_by: [date]
  retention_policy: factor_daily_v2
publication:
  enabled: true
  artifact_id: factor_overview
  transform: publish_factor_summary_v3
  route: /factors
quality:
  minimum_rows: 500
  max_staleness_hours: 30
  schema_contract: schemas/kr_factor_daily.json
governance:
  visibility: private-derived
  review_due: "2026-12-31"
```

이 하나에서 workflow, catalog, publish policy, quality test, documentation section을 생성하게 하십시오.
그러나 아래 lint는 generator와 별개로 유지해야 합니다.

```bash
python -m tools.verify_manifest_files
python -m tools.verify_manifest_workflows
python -m tools.verify_public_artifacts
python -m tools.verify_schema_contracts
python -m tools.verify_no_unregistered_outputs
```

## Q5. Framer–Git–문서의 세 갈래 분열

### 결론: "세 곳을 동기화"하려 하지 말고, 각 자산의 authoritative source를 하나씩 정해야 합니다.

Framer live editor, Git mirror, 문서가 모두 같은 컴포넌트의 정답본이라고 생각하는 순간 split-brain이 시작됩니다. 다음처럼 역할을 분리하세요.

| 자산 | 단일 source of truth | 다른 위치의 역할 |
|---|---|---|
| 공개 사이트의 최종 시각 디자인·레이아웃 | Framer project | Git은 snapshot/export/reference |
| 코드 기반 데이터·API·계산·콘텐츠 payload | Git + Supabase/object storage | Framer는 consumer |
| 운영 정책·컴포넌트 계약·변경 기록 | Git docs/manifest | Framer는 링크/표시 대상 |
| 이미지·아이콘·브랜드 asset | asset registry 또는 Git LFS/object store | Framer는 참조 |
| 사이트 release 상태 | release manifest | Framer publish history는 보조 증거 |

Framer는 version history와 staging environment를 제공하며, live site를 복제한 staging에서 변경을 검증한 후 production에 publish하는 방식을 권장합니다. (framer help — how-can-i-revert-to-a-previous-working-version-of-my-file)

### 권장 패턴: Framer를 presentation plane으로 한정

```text
Git manifest / Supabase / object storage
             │
             ├─ public JSON/API
             │
             ▼
Framer production component
             │
             ▼
Framer staging publish
             │
             ├─ smoke test
             ├─ screenshot / route check
             └─ release approval
             ▼
Framer production publish
```

### 실무 규칙

1. **Framer live edit는 production branch가 아니다** — 위험한 변경은 staging에서 먼저 검증, major release 전 checkpoint/version-history milestone을 남김
2. **Git mirror는 write-back 하지 않는다** — Framer에서 수정한 내용을 Git이 자동 덮어쓰지 않음, Git export가 Framer production을 자동 overwrite하지 않음
3. **컴포넌트 계약은 Git에 둔다** — component name / prop·API schema / data source / route / owner / Framer project URL 또는 ID / 현재 production version / rollback version / 마지막 검증일
4. **배포 전 release manifest를 만든다**

```yaml
release_id: web_2026_08_16_01
framer_project: verity-public-site
framer_version_checkpoint: "2026-08-16-pre-factor-card"
git_commit: ab12cd34
public_data_manifest: release-data-2026-08-16.json
supabase_migration: 2026081601
status: staged
rollback_target: web_2026_08_09_02
```

5. **되돌림은 한 곳만 되돌리는 것이 아니다** — Framer canvas rollback / public data manifest rollback / Supabase·API schema compatibility 확인 / cache purge 여부 판단 / release note와 incident log 업데이트

### Framer의 안전한 rollback

Framer는 version history에서 이전 상태를 찾아 복원할 수 있고, staging environment에서 live site에 영향을 주지 않고 변경을 시험할 수 있습니다. 다만 restore 뒤 다시 publish해야 live가 바뀌므로, "Framer 복원"과 "production release 복원"을 동일시하면 안 됩니다.

## Q6. 놓치기 쉬운 구조적 개선

### 1. 산출물 commit 구조를 바꾸기

78개 workflow가 산출물을 직접 Git commit하는 방식은 repo growth, merge conflict, run 재현성, accidental publish 위험을 동시에 키웁니다.

```text
Workflow
  → private object storage에 immutable run output 저장
  → manifest/catalog update 또는 release PR 생성
  → publish workflow가 승인된 public subset만 생성
  → public artifact만 별도 release commit 또는 deploy
```

즉, "각 workflow가 데이터 파일을 커밋"하는 구조에서 "각 workflow가 run manifest를 기록하고, 별도 publication pipeline이 선택적으로 발행"하는 구조로 바꾸는 것이 핵심입니다.

### 2. 데이터와 결과를 구분하기

```text
raw source data
point-in-time research input
derived internal feature
public website artifact
```

| 분류 | Git 여부 | 공개 여부 | 보존 기준 |
|---|---|---|---|
| Raw | 메타데이터만 | 원칙적으로 비공개 | 계약·재수집 가능성 기준 |
| PIT input | manifest만 | 비공개 | 전략 재현 기간 |
| Internal derived | manifest·소형 샘플 | 비공개 | 재생성 비용·연구 가치 기준 |
| Public artifact | 가능하나 제한 | 공개 | latest + release history |
| CI temporary | 금지 | 비공개 | 1~14일 |
| Model binary | LFS 또는 object store | 원칙적으로 비공개 | model lifecycle 기준 |

### 3. "dataset ID, not file path"

840개 Python module이 파일 경로를 문자열로 직접 참조하기 시작하면 경로 변경은 대형 사고가 됩니다.

나쁜 형태: `pd.read_parquet("data/factors/daily/2026-08-15.parquet")`

좋은 형태:

```python
dataset = registry.resolve("kr_factor_daily", as_of="2026-08-15", purpose="backtest")
df = dataset.read()
```

경로·backend·partition·legacy migration·권한은 registry가 해결하고, 비즈니스 코드는 dataset ID만 압니다.

### 4. 산출물 품질 계약

```text
- freshness / completeness / uniqueness / validity / schema
- PIT integrity: as_of cutoff 이후 정보가 없는가
- lineage: input snapshot과 code hash가 기록됐는가
- publication: 공개 가능한 field만 포함하는가
```

### 5. 공개물은 별도 release artifact로 취급

```text
private data snapshot
    → sanitization / aggregation / licensing filter
    → schema validation
    → public artifact manifest
    → staging deployment
    → production deployment
```

### 6. 공개 repo의 과거 데이터 정리

1. 전체 Git history에서 민감·비공개·vendor 데이터 경로를 inventory
2. 공개 가능/비공개/판단보류로 분류
3. 비공개 blob은 `git filter-repo`로 history에서 제거
4. force-push 전 mirror backup과 release tag backup 생성
5. GitHub에 cloned fork·cached reference·LFS orphan 정리 절차 문의
6. 새로운 `.gitignore`만이 아니라 CI policy와 pre-commit secret/data scanner 적용
7. GitHub token, Supabase key, vendor key는 모두 rotate

GitHub도 민감 정보를 history에서 제거한 후에는 history rewrite, remote update, 기존 clone 정리, 재발 방지 절차가 추가로 필요하다고 명시합니다.

### 90일 실행 우선순위

1. **1주차:** artifact/data inventory를 만들고 모든 workflow의 write path와 publish path를 표로 정리
2. **2주차:** `public/generated/`만 배포 가능하도록 publish boundary를 고정하고 `git add .`를 제거
3. **3~4주차:** `public-assets.yaml`과 CI manifest lint를 도입
4. **5~6주차:** raw/PIT/internal/public 데이터를 물리 분리하고 private object storage를 연결
5. **7~8주차:** 신규 write를 새 registry 경로로 전환하고 legacy write를 차단
6. **9~10주차:** backtest snapshot manifest와 checksum 기반 재현성 체계를 구축
7. **11~12주차:** Git history 정리 필요성을 audit하고, 필요하면 별도 migration branch에서 `git filter-repo` 리허설

---

## 수신 측 검증 (2026-08-16 · 우리 실측)

| 답변의 주장 | 우리 실측 | 판정 |
|---|---|---|
| "78개 workflow가 `git add .`/`-A` 를 쓴다면 즉시 제거" | 광범위 add **0건** (`grep -rnE "git add (-A\|--all\|\.)" .github/workflows/*.yml`). 8/16 PreToolUse 게이트가 추가로 차단 | **이미 준수** |
| "매니페스트 = 정책 SoT" | 8/16 `data/manifest.json` 215건 시행 | **일치** |
| "물리 분리 = 기본 경계" | 우리 제안은 신규분만 점진 (§4-②) | **부분 반박** — 발행 경계는 즉시 고정 권고 |
| "codegen 이 lint 보다 누락에 강하다" | 우리는 검증형 채택(§5 P3) | **반박** — §7 반증조건 ① 발동 |
| "영구 grandfathering 비권장" | 우리 §4-② 가 종료일 없는 grandfathering | **반박** — cutover date 필요 |
| "1.3GB 는 과거 blob 잔존 가능성" | 대형 blob 실측 = `data/stock_history/2026-Q3.jsonl` 75MB × 53커밋(최근 7일 8회). `data/runs` 32MB 는 주범이 아님 | **우리 진단 오류 확인** |
| "public repo 에 vendor/restricted 데이터를 두지 말 것" | 🚨 `data/consensus_data.json` = 7/21 발행 제외 결정(us_analyst_consensus 와 동일 법적 class)인데 **지금도 추적·커밋 중**(1,295 커밋, 최종 8/15). `us_analyst_consensus.json` 은 8/2 봉인(이력 8건 잔존) | **신규 P0 후보** |

관련 = `docs/STRUCTURE_REVIEW_2026_08_16.md` (질문 출처 · §7 반증 조건 · §9 시행 기록)
