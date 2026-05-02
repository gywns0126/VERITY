// WatchGroupsDashboard — 관심지역 그룹 관리 페이지
// VERITY ESTATE 페이지급 컴포넌트 (TERMINAL 패턴 정합).
// 흡수: WatchGroupCard.
//
// 구성: 헤더(전체 tally) + 그룹 카드 그리드 + 새 그룹 추가 + 그룹별 CRUD.

import { addPropertyControls, ControlType } from "framer"
import React, { useEffect, useState, useMemo } from "react"

/* ◆ DESIGN TOKENS START ◆ */
const C = {
    bgPage: "#0E0F11", bgCard: "#171820", bgElevated: "#22232B", bgInput: "#2A2B33",
    border: "#23242C", borderStrong: "#34353D", borderHover: "#B8864D",
    textPrimary: "#F2F3F5", textSecondary: "#A8ABB2", textTertiary: "#6B6E76", textDisabled: "#4A4C52",
    accent: "#B8864D", accentHover: "#D4A063", accentSoft: "rgba(184,134,77,0.12)",
    gradeHOT: "#EF4444", gradeWARM: "#F59E0B", gradeNEUT: "#A8ABB2", gradeCOOL: "#5BA9FF", gradeAVOID: "#6B6E76",
    statusPos: "#22C55E", statusNeut: "#A8ABB2", statusNeg: "#EF4444",
    info: "#5BA9FF",
}
const T = { cap: 12, body: 14, sub: 16, title: 18, h2: 22, h1: 28,
    w_reg: 400, w_med: 500, w_semi: 600, w_bold: 700 }
const S = { xs: 4, sm: 8, md: 12, lg: 16, xl: 20, xxl: 24, xxxl: 32 }
const R = { sm: 6, md: 10, lg: 14, pill: 999 }
const X = { fast: "120ms ease", base: "180ms ease" }
const FONT = "'Pretendard', 'Inter', -apple-system, sans-serif"
const FONT_MONO = "'SF Mono', 'JetBrains Mono', 'Fira Code', 'Menlo', monospace"
const MONO: React.CSSProperties = { fontFamily: FONT_MONO, fontVariantNumeric: "tabular-nums" }
/* ◆ DESIGN TOKENS END ◆ */


/* ◆ TYPES ◆ */
type GradeLabel = "HOT" | "WARM" | "NEUT" | "COOL" | "AVOID"
type SensitivityLevel = "L0" | "L1" | "L2" | "L3"

interface WatchGroupMember {
    gu: string
    grade: GradeLabel
}

interface WatchGroup {
    id: string
    name: string
    members: WatchGroupMember[]
}

interface Tally { HOT: number; WARM: number; NEUT: number; COOL: number; AVOID: number }


/* ◆ PRIVACY HOOK ◆ */
function usePrivacyMode() {
    const [privacyMode, setPM] = useState(() =>
        typeof window !== "undefined" && (window as any).__VERITY_PRIVACY__ === true
    )
    useEffect(() => {
        if (typeof window === "undefined") return
        const onChange = () => setPM((window as any).__VERITY_PRIVACY__ === true)
        const onKey = (e: KeyboardEvent) => {
            if ((e.metaKey || e.ctrlKey) && e.shiftKey && e.key.toLowerCase() === "p") {
                e.preventDefault()
                ;(window as any).__VERITY_PRIVACY__ = !((window as any).__VERITY_PRIVACY__ === true)
                window.dispatchEvent(new Event("verity:privacy-change"))
            }
        }
        window.addEventListener("verity:privacy-change", onChange)
        window.addEventListener("keydown", onKey)
        return () => {
            window.removeEventListener("verity:privacy-change", onChange)
            window.removeEventListener("keydown", onKey)
        }
    }, [])
    const shouldMask = (s: SensitivityLevel) => s !== "L0" && privacyMode
    return { privacyMode, shouldMask }
}


/* ◆ MOCK DATA ◆ */
const MOCK_GROUPS: WatchGroup[] = [
    {
        id: "g1", name: "출퇴근권",
        members: [
            { gu: "강남구", grade: "HOT" }, { gu: "서초구", grade: "HOT" },
            { gu: "송파구", grade: "WARM" }, { gu: "성동구", grade: "WARM" },
            { gu: "마포구", grade: "NEUT" },
        ],
    },
    {
        id: "g2", name: "재개발 모니터링",
        members: [
            { gu: "용산구", grade: "HOT" }, { gu: "성북구", grade: "WARM" },
            { gu: "동대문구", grade: "WARM" }, { gu: "노원구", grade: "COOL" },
        ],
    },
    {
        id: "g3", name: "서북부",
        members: [
            { gu: "은평구", grade: "NEUT" }, { gu: "서대문구", grade: "NEUT" },
            { gu: "강북구", grade: "COOL" }, { gu: "도봉구", grade: "AVOID" },
        ],
    },
]

const ALL_GU = [
    "강남구", "서초구", "송파구", "강동구", "마포구", "용산구",
    "성동구", "광진구", "중구", "종로구", "서대문구", "은평구",
    "강서구", "양천구", "영등포구", "구로구", "금천구", "관악구",
    "동작구", "성북구", "동대문구", "중랑구", "노원구", "도봉구", "강북구",
]


/* ◆ DATA FETCH ◆ */
// /api/estate/watchgroups (vercel-api). 인증 토큰은 window.__VERITY_TOKEN__ 또는 localStorage 에서.
async function fetchGroups(apiUrl: string, signal?: AbortSignal): Promise<WatchGroup[]> {
    if (!apiUrl) return MOCK_GROUPS
    try {
        const token = (typeof window !== "undefined" &&
            ((window as any).__VERITY_TOKEN__ || localStorage.getItem("verity_access_token"))) || ""
        if (!token) return MOCK_GROUPS  // 로그인 전에는 mock
        const res = await fetch(`${apiUrl.replace(/\/$/, "")}/api/estate/watchgroups`, {
            signal, headers: { Authorization: `Bearer ${token}` },
        })
        if (!res.ok) throw new Error()
        const j = await res.json()
        // 백엔드 응답: { groups: [{ id, name, color, members:[{gu, grade?}] }] }
        const arr: any[] = Array.isArray(j?.groups) ? j.groups : []
        if (!arr.length) return MOCK_GROUPS
        return arr.map((g) => ({
            id: g.id, name: g.name,
            members: (g.members ?? []).map((m: any) => ({
                gu: m.gu,
                // 백엔드는 grade 를 별도 산출 — 지금은 mock 매핑
                grade: pickGradeForMock(m.gu),
            })),
        }))
    } catch {
        return MOCK_GROUPS
    }
}


/* ◆ UTIL ◆ */
function computeTally(members: WatchGroupMember[]): Tally {
    const t: Tally = { HOT: 0, WARM: 0, NEUT: 0, COOL: 0, AVOID: 0 }
    members.forEach((m) => { t[m.grade]++ })
    return t
}

function gradeColor(g: GradeLabel): string {
    return g === "HOT" ? C.gradeHOT : g === "WARM" ? C.gradeWARM : g === "NEUT" ? C.gradeNEUT : g === "COOL" ? C.gradeCOOL : C.gradeAVOID
}


/* ◆ INTERNAL: GradePill ◆ */
function GradePill({ grade, count }: { grade: GradeLabel; count?: number }) {
    const c = gradeColor(grade)
    return (
        <span style={{
            display: "inline-flex", alignItems: "center", gap: S.xs,
            padding: "2px 8px", borderRadius: R.sm,
            background: c + "1A", color: c,
            fontSize: T.cap, fontWeight: T.w_semi, fontFamily: FONT,
            lineHeight: 1, letterSpacing: 0.2,
        }}>
            {grade}
            {count !== undefined && (
                <span style={{ color: C.textTertiary, fontWeight: T.w_med, ...MONO }}>{count}</span>
            )}
        </span>
    )
}


/* ◆ INTERNAL: TallyHeader (전체 합계) ◆ */
function TallyHeader({ groups, masked }: { groups: WatchGroup[]; masked: boolean }) {
    const total = useMemo(() => {
        const t: Tally = { HOT: 0, WARM: 0, NEUT: 0, COOL: 0, AVOID: 0 }
        groups.forEach((g) => g.members.forEach((m) => { t[m.grade]++ }))
        return t
    }, [groups])
    const totalGu = Object.values(total).reduce((a, b) => a + b, 0)

    return (
        <div style={{
            display: "flex", alignItems: "center", justifyContent: "space-between",
            padding: S.lg, backgroundColor: C.bgCard,
            border: `1px solid ${C.border}`, borderRadius: R.md,
        }}>
            <div style={{ display: "flex", alignItems: "baseline", gap: S.md }}>
                <span style={{ fontSize: T.h2, fontWeight: T.w_bold, color: C.textPrimary }}>WatchGroups</span>
                <span style={{ fontSize: T.body, color: C.textSecondary }}>· {groups.length}개 그룹 / {totalGu}구</span>
            </div>
            <div style={{ display: "flex", gap: S.sm, flexWrap: "wrap" }}>
                {(["HOT", "WARM", "NEUT", "COOL", "AVOID"] as GradeLabel[]).map((g) => (
                    <GradePill key={g} grade={g} count={masked ? undefined : total[g]} />
                ))}
            </div>
        </div>
    )
}


/* ◆ INTERNAL: WatchGroupCard ◆ */
function WatchGroupCard({ group, onRename, onDelete, onAddMember, onRemoveMember, masked }: {
    group: WatchGroup
    onRename: (id: string, name: string) => void
    onDelete: (id: string) => void
    onAddMember: (id: string, gu: string) => void
    onRemoveMember: (id: string, gu: string) => void
    masked: boolean
}) {
    const [expanded, setExpanded] = useState(false)
    const [editing, setEditing] = useState(false)
    const [nameDraft, setNameDraft] = useState(group.name)
    const [addPickerOpen, setAddPickerOpen] = useState(false)
    const tally = useMemo(() => computeTally(group.members), [group.members])
    const memberSet = useMemo(() => new Set(group.members.map((m) => m.gu)), [group.members])
    const addable = ALL_GU.filter((gu) => !memberSet.has(gu))

    const commitName = () => {
        const next = nameDraft.trim()
        if (next && next !== group.name) onRename(group.id, next)
        else setNameDraft(group.name)
        setEditing(false)
    }

    return (
        <div style={{
            padding: S.md, backgroundColor: C.bgCard,
            border: `1px solid ${C.border}`, borderRadius: R.md,
            display: "flex", flexDirection: "column", gap: S.sm,
        }}>
            {/* Header row */}
            <div style={{ display: "flex", alignItems: "center", justifyContent: "space-between", gap: S.sm }}>
                <button
                    onClick={() => setExpanded((v) => !v)}
                    style={{
                        display: "flex", alignItems: "center", gap: S.sm, flex: 1,
                        background: "transparent", border: "none", padding: 0, cursor: "pointer", textAlign: "left",
                    }}
                >
                    <span style={{
                        color: C.textSecondary, fontSize: T.body,
                        transform: expanded ? "rotate(90deg)" : "rotate(0deg)", transition: X.fast,
                    }}>▸</span>
                    {editing ? (
                        <input
                            autoFocus
                            value={nameDraft}
                            onChange={(e) => setNameDraft(e.target.value)}
                            onBlur={commitName}
                            onKeyDown={(e) => { if (e.key === "Enter") commitName() }}
                            onClick={(e) => e.stopPropagation()}
                            style={{
                                background: C.bgInput, color: C.textPrimary, border: `1px solid ${C.accent}`,
                                borderRadius: R.sm, padding: `${S.xs}px ${S.sm}px`,
                                fontSize: T.body, fontWeight: T.w_semi, fontFamily: FONT, outline: "none",
                            }}
                        />
                    ) : (
                        <span style={{ fontSize: T.body, fontWeight: T.w_semi, color: C.textPrimary }}>{group.name}</span>
                    )}
                    <span style={{ fontSize: T.cap, color: C.textTertiary, ...MONO }}>({group.members.length}구)</span>
                </button>
                <div style={{ display: "flex", gap: S.xs }}>
                    <IconBtn label="이름 수정" onClick={(e) => { e.stopPropagation(); setEditing(true); setNameDraft(group.name) }}>✎</IconBtn>
                    <IconBtn label="그룹 삭제" onClick={(e) => { e.stopPropagation(); if (confirm(`"${group.name}" 삭제?`)) onDelete(group.id) }} danger>×</IconBtn>
                </div>
            </div>

            {/* Tally summary row */}
            <div style={{ display: "flex", gap: S.xs, flexWrap: "wrap" }}>
                {(["HOT", "WARM", "NEUT", "COOL", "AVOID"] as GradeLabel[])
                    .filter((g) => tally[g] > 0)
                    .map((g) => (
                        <GradePill key={g} grade={g} count={masked ? undefined : tally[g]} />
                    ))}
            </div>

            {/* Expanded: member list + add button */}
            {expanded && (
                <div style={{ display: "flex", flexDirection: "column", gap: S.xs, marginTop: S.xs }}>
                    {group.members.map((m) => (
                        <div key={m.gu} style={{
                            display: "flex", alignItems: "center", justifyContent: "space-between",
                            padding: `${S.xs}px ${S.sm}px`, borderRadius: R.sm,
                            background: C.bgElevated,
                        }}>
                            <span style={{ fontSize: T.body, color: C.textPrimary }}>{m.gu}</span>
                            <div style={{ display: "flex", alignItems: "center", gap: S.sm }}>
                                <GradePill grade={m.grade} />
                                <IconBtn label="제거" onClick={() => onRemoveMember(group.id, m.gu)}>−</IconBtn>
                            </div>
                        </div>
                    ))}
                    {addPickerOpen ? (
                        <div style={{
                            display: "flex", flexWrap: "wrap", gap: S.xs, padding: S.sm,
                            background: C.bgElevated, borderRadius: R.sm,
                            maxHeight: 160, overflowY: "auto",
                        }}>
                            {addable.length === 0 && (
                                <span style={{ fontSize: T.cap, color: C.textTertiary }}>모든 구가 이미 추가됨</span>
                            )}
                            {addable.map((gu) => (
                                <button
                                    key={gu}
                                    onClick={() => { onAddMember(group.id, gu); setAddPickerOpen(false) }}
                                    style={{
                                        padding: `${S.xs}px ${S.sm}px`,
                                        background: "transparent", color: C.textPrimary,
                                        border: `1px solid ${C.border}`, borderRadius: R.sm,
                                        fontSize: T.cap, fontFamily: FONT, cursor: "pointer",
                                    }}
                                >{gu}</button>
                            ))}
                        </div>
                    ) : (
                        <button
                            onClick={() => setAddPickerOpen(true)}
                            style={{
                                padding: `${S.xs}px ${S.sm}px`, marginTop: S.xs,
                                background: "transparent", color: C.accent,
                                border: `1px dashed ${C.accent}`, borderRadius: R.sm,
                                fontSize: T.cap, fontWeight: T.w_med, fontFamily: FONT, cursor: "pointer",
                            }}
                        >+ 구 추가</button>
                    )}
                </div>
            )}
        </div>
    )
}

function IconBtn({ children, onClick, label, danger }: {
    children: React.ReactNode
    onClick: (e: React.MouseEvent) => void
    label: string
    danger?: boolean
}) {
    return (
        <button
            aria-label={label} title={label} onClick={onClick}
            style={{
                width: 24, height: 24, borderRadius: R.sm,
                background: "transparent",
                color: danger ? C.statusNeg : C.textTertiary,
                border: `1px solid ${C.border}`, cursor: "pointer",
                fontSize: T.body, fontFamily: FONT, lineHeight: 1,
                display: "flex", alignItems: "center", justifyContent: "center",
                flexShrink: 0,
            }}
        >{children}</button>
    )
}


/* ◆ INTERNAL: NewGroupCard ◆ */
function NewGroupCard({ onCreate }: { onCreate: (name: string) => void }) {
    const [name, setName] = useState("")
    const submit = () => {
        const v = name.trim()
        if (!v) return
        onCreate(v)
        setName("")
    }
    return (
        <div style={{
            padding: S.md, backgroundColor: "transparent",
            border: `1px dashed ${C.border}`, borderRadius: R.md,
            display: "flex", flexDirection: "column", gap: S.sm,
            alignItems: "stretch", justifyContent: "center", minHeight: 96,
        }}>
            <span style={{ fontSize: T.cap, color: C.textTertiary, textTransform: "uppercase", letterSpacing: 1 }}>
                + 새 그룹
            </span>
            <div style={{ display: "flex", gap: S.xs }}>
                <input
                    value={name} onChange={(e) => setName(e.target.value)}
                    onKeyDown={(e) => { if (e.key === "Enter") submit() }}
                    placeholder="그룹명 (예: 학군지)"
                    style={{
                        flex: 1, padding: `${S.sm}px ${S.md}px`,
                        background: C.bgInput, color: C.textPrimary,
                        border: `1px solid ${C.border}`, borderRadius: R.sm,
                        fontSize: T.body, fontFamily: FONT, outline: "none",
                    }}
                />
                <button
                    onClick={submit}
                    disabled={!name.trim()}
                    style={{
                        padding: `${S.sm}px ${S.md}px`,
                        background: name.trim() ? C.accent : C.bgElevated,
                        color: name.trim() ? C.bgPage : C.textTertiary,
                        border: "none", borderRadius: R.sm,
                        fontSize: T.body, fontWeight: T.w_semi, fontFamily: FONT,
                        cursor: name.trim() ? "pointer" : "not-allowed",
                    }}
                >추가</button>
            </div>
        </div>
    )
}


/* ◆ MAIN ◆ */
interface Props {
    apiUrl: string
    sensitivity: SensitivityLevel
}

function WatchGroupsDashboard({ apiUrl = "", sensitivity = "L1" }: Props) {
    const [groups, setGroups] = useState<WatchGroup[]>(MOCK_GROUPS)
    const [loading, setLoading] = useState(false)
    const { shouldMask } = usePrivacyMode()
    const masked = shouldMask(sensitivity)

    useEffect(() => {
        const ac = new AbortController()
        setLoading(true)
        fetchGroups(apiUrl, ac.signal)
            .then((g) => { setGroups(g); setLoading(false) })
            .catch(() => setLoading(false))
        return () => ac.abort()
    }, [apiUrl])

    const handleCreate = (name: string) => {
        setGroups((gs) => [...gs, { id: `g${Date.now()}`, name, members: [] }])
    }
    const handleRename = (id: string, name: string) => {
        setGroups((gs) => gs.map((g) => (g.id === id ? { ...g, name } : g)))
    }
    const handleDelete = (id: string) => {
        setGroups((gs) => gs.filter((g) => g.id !== id))
    }
    const handleAddMember = (id: string, gu: string) => {
        setGroups((gs) => gs.map((g) => g.id === id
            ? { ...g, members: [...g.members, { gu, grade: pickGradeForMock(gu) }] }
            : g
        ))
    }
    const handleRemoveMember = (id: string, gu: string) => {
        setGroups((gs) => gs.map((g) => g.id === id
            ? { ...g, members: g.members.filter((m) => m.gu !== gu) }
            : g
        ))
    }

    return (
        <div style={{
            width: "100%", height: "100%", display: "flex", flexDirection: "column", gap: S.md, padding: S.md,
            backgroundColor: C.bgPage, fontFamily: FONT, color: C.textPrimary,
            boxSizing: "border-box", minWidth: 720, minHeight: 480, overflowY: "auto",
        }}>
            <TallyHeader groups={groups} masked={masked} />

            {loading && <span style={{ fontSize: T.cap, color: C.info, ...MONO }}>· 로딩 중</span>}

            <div style={{
                display: "grid",
                gridTemplateColumns: "repeat(auto-fill, minmax(320px, 1fr))",
                gap: S.md,
            }}>
                {groups.map((g) => (
                    <WatchGroupCard
                        key={g.id} group={g} masked={masked}
                        onRename={handleRename} onDelete={handleDelete}
                        onAddMember={handleAddMember} onRemoveMember={handleRemoveMember}
                    />
                ))}
                <NewGroupCard onCreate={handleCreate} />
            </div>
        </div>
    )
}

// 결정적 mock 등급 (구별 고정 매핑)
function pickGradeForMock(gu: string): GradeLabel {
    const idx = ALL_GU.indexOf(gu)
    const grades: GradeLabel[] = ["HOT", "WARM", "NEUT", "COOL", "AVOID"]
    return grades[Math.abs(idx) % grades.length]
}

addPropertyControls(WatchGroupsDashboard, {
    apiUrl: { type: ControlType.String, defaultValue: "", description: "WatchGroup API base URL. 비우면 mock 데이터." },
    sensitivity: { type: ControlType.Enum, options: ["L0", "L1", "L2", "L3"], defaultValue: "L1" },
})

export default WatchGroupsDashboard
