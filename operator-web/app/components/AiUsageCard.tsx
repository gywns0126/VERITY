"use client"
// AiUsageCard — AI 사용량 + Brain 표본 상태 (구 프레이머 `pages/admin/AdminDashboard.tsx` 부분 이관, PM 2026-08-12).
//
// 🚨 통째 이관하지 않은 이유 — 원본 1,441줄의 절반이 죽은 의존이다. 실측(2026-08-12):
//   · `brain_kb_usage.json` → 404 (은퇴 발행물). 책 인용 통계 카드 = 폐기
//   · `admin_todos.json` → 404 (은퇴 발행물). [메모] 카드 = 폐기
//   · Supabase 가입 승인 RPC + action_queue_heartbeat = 알파네스트 /admin 의 MemberAdminCard 와 중복 → 미이관
//   살아있는 건 portfolio 의 `cost_monitor` · `brain_quality` 뿐이라 그것만 옮겼다.
//   ([[feedback_mass_removal_dangling_ref_audit]] · [[feedback_component_overlap_audit]] 정합)
//
// 표시 규율(원본 유지): 내부 카운터는 **호출 수만 정확**하다. USD 추정은 ±25~50% 오차라 표시하지 않고
// 각 provider 콘솔 진입점만 제공한다.
import { useDark, palette, cardStyle, CARD_TITLE, RAIL_PAD, FONT, NUM } from "@/lib/theme"
import type { BrainQuality, CostMonitor } from "@/lib/types"

const CONSOLES: Array<{ name: string; url: string }> = [
    { name: "Claude — Cost", url: "https://platform.claude.com/workspaces/default/cost" },
    { name: "Google AI Studio — Spend", url: "https://aistudio.google.com/app/spend" },
    { name: "Perplexity — Billing", url: "https://console.perplexity.ai/group/ac387575-4266-40d5-96cc-d1e31462525f/billing" },
]

export default function AiUsageCard({ cost, brainQuality, status = "ok" }: { cost?: CostMonitor; brainQuality?: BrainQuality; status?: "loading" | "ok" | "error" }) {
    const dark = useDark()
    const c = palette(dark)
    const m = cost?.monthly_usage || {}
    const claude = (m.claude_deep_calls || 0) + (m.claude_light_calls || 0)
    const bq = brainQuality || {}
    const samples = bq.metrics?.total_samples || 0

    const note =
        bq.status === "no_data"
            ? "brain_quality 미산출 — 다음 Full cron 후 자동 채워짐"
            : bq.status === "insufficient_data" || (bq.status === "ok" && samples < 5)
              ? `Brain 등급별 표본 누적 대기 — ${samples}/5건`
              : null

    const row = (label: string, value: string) => (
        <div key={label} style={{ display: "flex", justifyContent: "space-between", gap: 10, fontSize: 11.5, padding: "3px 0" }}>
            <span style={{ color: c.sub, fontWeight: 600 }}>{label}</span>
            <span style={{ color: c.ink, fontWeight: 800, ...NUM }}>{value}</span>
        </div>
    )

    return (
        <div style={{ ...cardStyle(c, RAIL_PAD), fontFamily: FONT, display: "flex", flexDirection: "column", gap: 9 }}>
            <div style={{ display: "flex", alignItems: "baseline", gap: 8, flexWrap: "wrap" }}>
                <span style={{ ...CARD_TITLE, color: c.ink }}>AI 사용량</span>
                {cost?.month_key ? <span style={{ fontSize: 10, color: c.faint, ...NUM }}>{cost.month_key}</span> : null}
                <span style={{ marginLeft: "auto", fontSize: 10, color: c.faint }}>호출 수만 정확 · 청구액은 콘솔에서</span>
            </div>

            {status === "error" ? (
                <span style={{ fontSize: 11.5, color: c.down }}>AI 사용량 원천을 불러오지 못했습니다.</span>
            ) : !cost ? (
                <span style={{ fontSize: 11.5, color: c.faint }}>사용량 로딩…</span>
            ) : (
                <div style={{ background: c.hi, borderRadius: 12, padding: "9px 11px" }}>
                    {row("Claude 호출", `${claude.toLocaleString()}회`)}
                    {row("Claude 토큰", (m.claude_tokens || 0).toLocaleString())}
                    {row("Gemini (stock/report/Pro)", `${m.gemini_stock_calls || 0} / ${m.gemini_report_calls || 0} / ${m.gemini_pro_calls || 0}`)}
                    {/* 🚨 2026-08-26 — 이 값은 main run 내부 카운트다. 배치 워크플로(브리프·테마 등,
                        8월 실측 ~130회)는 빠진다. 전수는 llm_cost.jsonl 원장 — 라벨 없이 두면
                        "8월 퍼플렉시티 전체" 로 읽힌다(실제 그렇게 읽혔다). 되돌리지 말 것. */}
                    {row("Perplexity 호출 (run 내 · 배치 별도)", `${(m.perplexity_calls || 0).toLocaleString()}회`)}
                </div>
            )}

            {note ? <div style={{ fontSize: 10.5, color: c.amber, fontWeight: 700 }}>{note}</div> : null}

            <div style={{ display: "flex", gap: 6, flexWrap: "wrap" }}>
                {CONSOLES.map((x) => (
                    <a
                        key={x.name}
                        href={x.url}
                        target="_blank"
                        rel="noopener noreferrer"
                        style={{ fontSize: 10.5, fontWeight: 800, color: c.vt, background: c.vtS, borderRadius: 999, padding: "4px 10px", textDecoration: "none" }}
                    >
                        {x.name} ↗
                    </a>
                ))}
            </div>
        </div>
    )
}
