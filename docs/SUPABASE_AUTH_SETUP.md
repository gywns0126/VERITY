# VERITY — Supabase 설정 가이드 (처음부터 끝까지)

관리자 승인제 로그인/회원가입을 위한 Supabase 설정 전체 절차입니다.

---

## STEP 1. Supabase 프로젝트 준비

1. [https://supabase.com](https://supabase.com) 접속 → 로그인
2. **New Project** 클릭
3. 프로젝트 이름 입력 (예: `verity`)
4. DB 비밀번호 설정 (기억해두세요, 잃어버리면 재설정 필요)
5. Region: **Northeast Asia (Seoul)** 권장
6. **Create new project** 클릭 → 1~2분 대기

---

## STEP 2. SQL 실행 (가장 중요)

왼쪽 메뉴에서 **SQL Editor** → **+ New query** 클릭.

아래 코드를 **통째로 복사** 해서 붙여넣고 **RUN** (Ctrl/Cmd+Enter).

**⚠️ 주의: 첫 줄과 마지막 줄의 삼중 백틱(` ``` `)은 복사하지 마세요. 그 안의 내용만 복사하세요.**

```
-- ═══════════════════════════════════════════════
-- VERITY Auth: profiles 테이블 + 승인 시스템
-- ═══════════════════════════════════════════════

-- 1) profiles 테이블 (auth.users 와 1:1 매핑)
create table if not exists public.profiles (
  id uuid references auth.users on delete cascade primary key,
  email text,
  display_name text,
  phone text,
  consent_given_at timestamptz,
  status text not null default 'pending'
    check (status in ('pending', 'approved', 'rejected')),
  created_at timestamptz default now(),
  approved_at timestamptz,
  notes text
);

-- 2) 이미 테이블이 있을 경우 컬럼 추가
alter table public.profiles add column if not exists phone text;
alter table public.profiles add column if not exists consent_given_at timestamptz;
-- (구버전에서 signup_reason 을 만들었다면 삭제)
alter table public.profiles drop column if exists signup_reason;

-- 3) RLS (Row Level Security) 활성화
alter table public.profiles enable row level security;

-- 4) 본인 row 만 조회 가능
drop policy if exists "users can view own profile" on public.profiles;
create policy "users can view own profile" on public.profiles
  for select using (auth.uid() = id);

-- 5) 본인 row 최초 insert 만 허용 (fallback 용)
drop policy if exists "users can insert own profile" on public.profiles;
create policy "users can insert own profile" on public.profiles
  for insert with check (auth.uid() = id);

-- 6) 회원가입 시 자동으로 profiles 생성하는 trigger
create or replace function public.handle_new_user()
returns trigger
language plpgsql
security definer
set search_path = public
as $$
begin
  insert into public.profiles (
    id, email, display_name, phone, consent_given_at, status
  )
  values (
    new.id,
    new.email,
    coalesce(new.raw_user_meta_data->>'name', split_part(new.email, '@', 1)),
    new.raw_user_meta_data->>'phone',
    case
      when coalesce((new.raw_user_meta_data->>'consent')::boolean, false)
      then now()
      else null
    end,
    'pending'
  )
  on conflict (id) do nothing;
  return new;
end;
$$;

drop trigger if exists on_auth_user_created on auth.users;
create trigger on_auth_user_created
  after insert on auth.users
  for each row execute function public.handle_new_user();
```

실행 후 `Success. No rows returned` 메시지가 뜨면 성공.

---

## STEP 3. Authentication 설정

### 3-1. Email Provider 설정

좌측 메뉴 → **Authentication** → **Providers** → **Email**

- **Enable Email provider**: **ON**
- **Confirm email**: **OFF** (권장 — 관리자가 직접 승인하므로 이메일 확인 불필요)
- **Secure email change**: ON (기본값)
- **Save** 클릭

### 3-2. Site URL 설정

좌측 메뉴 → **Authentication** → **URL Configuration**

- **Site URL**: Framer 사이트 URL 입력
  - 개발 중: `http://localhost:3000` 또는 Framer 프리뷰 URL
  - 배포 후: `https://당신의도메인.framer.website`
- **Redirect URLs**: 위와 같은 도메인 추가 → **Save**

### 3-3. (선택) Google OAuth 설정

Google 로그인을 쓸 계획이 있으면:
- **Authentication** → **Providers** → **Google** → **Enable**
- Google Cloud Console에서 OAuth Client ID/Secret 발급받아 입력
- 안 쓸 거면 OFF 유지

---

## STEP 4. API Key 복사 (Framer에 넣을 값)

좌측 메뉴 → **Project Settings** (톱니바퀴) → **API**

두 값을 복사:

| 항목 | 어디에 쓰나 |
|---|---|
| **Project URL** (예: `https://abcd1234.supabase.co`) | Framer `supabaseUrl` 프로퍼티 |
| **Project API keys → anon public** (긴 eyJ... 문자열) | Framer `supabaseAnonKey` 프로퍼티 |

**⚠️ `service_role` 키는 절대 클라이언트에 넣지 마세요.** anon key 만 사용합니다.

---

## STEP 5. Framer 컴포넌트에 값 입력

Framer Code Components `AuthPage` / `MobileApp` / `AuthGate` 프로퍼티에:
- **Supabase URL**: STEP 4에서 복사한 Project URL
- **Supabase Anon Key**: STEP 4에서 복사한 anon public 키

## STEP 5-1. 사이트 전체 접근 제한 구조 (중요)

```
/login   →  AuthPage 컴포넌트만 배치 (누구나 접근 가능)
/        →  AuthGate + StockDashboard + 기타 컴포넌트
/market  →  AuthGate + MacroSentimentPanel + ...
/m       →  MobileApp (자체 게이트 내장, AuthGate 선택)
그 외 보호 페이지 → 상단에 AuthGate 한 개씩 배치
```

### AuthGate 동작
- 페이지 로드 시 세션 확인
- 세션 없거나 만료된 refresh 실패 → `/login` 으로 자동 리다이렉트 (원래 경로는 `?next=` 로 전달)
- 세션 유효 → 투명하게 숨어서 컨텐츠 노출
- 만료 임박 시 refresh_token 으로 자동 갱신 (자동 로그인)
- 1분마다 주기적 재검사

### AuthPage 자동 복귀
- AuthGate 가 리다이렉트할 때 `?next=/market` 같은 쿼리를 붙여 보냄
- AuthPage 는 로그인 성공 시 `next` 경로가 있으면 그리로 자동 이동, 없으면 `defaultNextPath` (기본 `/`) 로 이동

### 자동 로그인
- 로그인 성공 시 `access_token` + `refresh_token` 이 localStorage 에 저장됨
- 이후 재방문 시 AuthGate 가 자동으로 `refresh_token` 으로 새 `access_token` 발급 → 사용자는 로그인 화면 없이 즉시 진입
- Supabase 기본 refresh_token 수명: 30일 (Auth → Policies 에서 조정 가능)

---

## STEP 6. 첫 회원가입 테스트

1. Framer 프리뷰에서 "가입 신청" 탭 → 이메일/비번/이름/전화번호 입력 → 동의 체크 → 가입
2. "가입 신청이 접수되었습니다. 관리자 승인 후 로그인 가능합니다." 메시지 확인
3. Supabase Studio → **Table Editor** → **profiles** 테이블 열기
4. 방금 가입한 row 가 보이면 정상 (`status = pending`)

---

## STEP 7. 관리자 승인 (가장 자주 쓸 작업)

### 방법 A — Table Editor (GUI)
1. Supabase Studio → **Table Editor** → **profiles**
2. 승인할 row 의 `status` 컬럼 더블클릭
3. `pending` → `approved` 로 변경 → Save
4. (선택) `approved_at` 에 현재 시각 입력

### 방법 B — SQL Editor (빠름)

아래 SQL 을 **SQL Editor** 에 붙여넣고 `user@example.com` 부분만 수정:

```
update public.profiles
set status = 'approved', approved_at = now()
where email = 'user@example.com';
```

### 방법 C — 여러 명 한 번에 승인 (초기 운영)

```
update public.profiles
set status = 'approved', approved_at = now()
where status = 'pending';
```

### 거절하려면

```
update public.profiles
set status = 'rejected'
where email = 'user@example.com';
```

거절된 사용자는 로그인 시도 시 "가입이 거절되었습니다" 메시지를 봅니다.

---

## STEP 8. 승인 대기자 목록 조회

```
select email, display_name, phone, consent_given_at, created_at
from public.profiles
where status = 'pending'
order by created_at desc;
```

**⚠️ `consent_given_at` 이 null 인 요청은 승인하지 마세요** (개인정보 동의 없이 가입된 것).

---

## STEP 9. 회원 탈퇴 (삭제)

```
delete from auth.users where email = 'user@example.com';
```

`profiles` row 는 `on delete cascade` 로 자동 삭제됩니다.

---

## 자주 겪는 문제

### Q1. "syntax error at or near ```" 에러
- 마크다운의 **삼중 백틱**(` ``` `)을 같이 복사한 경우입니다. SQL 내용만 복사하세요.

### Q2. 가입했는데 profiles 테이블에 row 가 안 생김
- STEP 2 의 trigger 가 제대로 실행되지 않았을 가능성. SQL Editor 에서 아래 확인:
  ```
  select * from pg_trigger where tgname = 'on_auth_user_created';
  ```
  결과가 없으면 STEP 2 SQL 을 다시 실행.

### Q3. 로그인 시 "관리자 승인 대기 중" 만 계속 뜸
- `profiles.status` 가 `approved` 가 아닙니다. STEP 7 로 승인해주세요.

### Q4. "Invalid login credentials"
- 이메일/비밀번호 오류, 또는 Confirm email ON 상태에서 확인 안 한 경우.

### Q5. 전화번호 포맷 검증하고 싶음
- 현재는 자유 텍스트. 필요하면 profiles 에 CHECK 제약 추가:
  ```
  alter table public.profiles
  add constraint phone_format_check
  check (phone ~ '^01[0-9]-[0-9]{3,4}-[0-9]{4}$');
  ```

---

## 개인정보 보호 체크리스트

- ✅ `phone` 은 RLS 로 본인만 조회 가능
- ✅ `consent_given_at` 으로 동의 시점 감사로그 유지
- ✅ `service_role` 키는 Framer 에 절대 넣지 않음 (anon key 만 사용)
- ✅ 회원 탈퇴 시 cascade 로 전 데이터 삭제
- ⚠️ 프로덕션 공개 전 개인정보처리방침 페이지 작성 권장

---

## 수집하는 정보 요약

| 필드 | 필수 | 저장 위치 | RLS |
|---|---|---|---|
| 이메일 | ✅ | `auth.users.email` + `profiles.email` | 본인+관리자 |
| 비밀번호 | ✅ | `auth.users` (bcrypt 해시) | Supabase 내부 |
| 이름 | ✅ | `profiles.display_name` | 본인+관리자 |
| 전화번호 | ✅ | `profiles.phone` | 본인+관리자 |
| 개인정보 동의 시각 | ✅ | `profiles.consent_given_at` | 본인+관리자 |
