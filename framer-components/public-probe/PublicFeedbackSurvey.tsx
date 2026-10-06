import * as React from "react"
import { addPropertyControls, ControlType, RenderTarget } from "framer"
import { ChatCircle, CaretLeft, CaretRight, Check, X } from "@phosphor-icons/react"

// AlphaNest Design v1: .cursor/rules/alphanest-interaction.mdc
// Keep: menu-family bold icons, optional questions, private server-side persistence.
// Never show completion before the API confirms storage. No response text in browser storage.
const VERSION = "2026-10-v1"
const CLIENT_KEY = "an_survey_client_v1"
const DONE_KEY = `an_survey_done_${VERSION}`
const UUID = /^[0-9a-f]{8}-[0-9a-f]{4}-4[0-9a-f]{3}-[89ab][0-9a-f]{3}-[0-9a-f]{12}$/i
type Answers = { purpose: string | null; features: string[]; outcome: string | null; discovery: string | null; comment: string }
const emptyAnswers = (): Answers => ({ purpose: null, features: [], outcome: null, discovery: null, comment: "" })
const QUESTIONS = [
    { key: "purpose", title: ["오늘, 무엇을", "살펴보러 오셨나요?"], hint: "가장 큰 방문 이유 하나를 골라주세요.", choices: [["company", "종목·기업 정보 확인"], ["market", "시장 흐름 살펴보기"], ["gurus", "거장 포트폴리오 확인"], ["learn", "투자 공부하기"], ["browse", "그냥 둘러보기"], ["other", "기타"]] },
    { key: "features", title: ["이번 방문에서", "어떤 기능을 써보셨나요?"], hint: "사용한 기능을 모두 골라주세요.", choices: [["report", "기업 리포트"], ["map", "종목지도"], ["market", "시장·캘린더"], ["gurus", "거장 포트폴리오"], ["education", "교육 콘텐츠"], ["other", "기타"], ["not_used", "아직 이용하지 않았어요"]] },
    { key: "outcome", title: ["찾으려던 정보를", "찾으셨나요?"], hint: "이번 방문에서의 경험을 알려주세요.", choices: [["yes", "찾았어요"], ["partly", "일부만 찾았어요"], ["no", "찾지 못했어요"], ["not_yet", "아직 충분히 살펴보지 않았어요"], ["no_goal", "정해둔 목적 없이 둘러봤어요"]] },
    { key: "discovery", title: ["알파네스트를", "어디에서 알게 되셨나요?"], hint: "처음 알게 된 경로를 골라주세요.", choices: [["search", "검색"], ["community", "커뮤니티·SNS"], ["friend", "지인 소개"], ["unknown", "기억나지 않아요"], ["other", "기타"]] },
    { key: "comment", title: ["마지막으로,", "들려주고 싶은 이야기가 있나요?"], hint: "도움이 됐거나 불편했던 점, 무엇이든 좋아요. (선택)", choices: [] },
] as const

const CSS = `
.an-survey{--s-card:#ffffff;--s-stack:#f8f9fb;--s-hover:#f1f3f5;--s-focus:#e9edf2;--s-ink:#191f28;--s-sub:#6b7684;--s-accent:#6c5ce7;--s-brand:#6c5ce7;width:100%;min-width:0;font:600 13px/1.65 Pretendard,-apple-system,BlinkMacSystemFont,'Apple SD Gothic Neo',sans-serif;color:var(--s-ink);color-scheme:light}
.an-survey[data-theme=dark]{--s-card:#171c23;--s-stack:#1d242c;--s-hover:#252c35;--s-focus:#303945;--s-ink:#e3e7ec;--s-sub:#9aa4b1;--s-accent:#a99bff;color-scheme:dark}
.an-survey *{box-sizing:border-box}.an-survey button,.an-survey input,.an-survey textarea{font:inherit;color:inherit}.an-survey button{border:0;cursor:pointer;text-decoration:none;transition:background-color 160ms,color 160ms}.an-survey button:disabled{cursor:default}.an-survey svg{flex:none}
.an-survey .s-invite{display:flex;align-items:center;justify-content:space-between;gap:20px;background:var(--s-card);border-radius:24px;padding:24px}.an-survey .s-intro{display:flex;gap:14px;align-items:center;min-width:0}.an-survey .s-icon{width:44px;height:44px;flex:none;display:flex;align-items:center;justify-content:center;border-radius:14px;background:var(--s-stack);color:var(--s-accent)}
.an-survey h2{font:800 20px/1.5 Pretendard,-apple-system,BlinkMacSystemFont,'Apple SD Gothic Neo',sans-serif;letter-spacing:-.6px;margin:0;word-break:keep-all;overflow-wrap:anywhere}.an-survey .s-invite h2{font-size:16px;letter-spacing:-.3px}.an-survey p{margin:6px 0 0;color:var(--s-sub);word-break:keep-all}.an-survey .s-button{display:inline-flex;align-items:center;justify-content:center;gap:8px;min-height:44px;padding:10px 16px;border-radius:12px;font-size:14px;font-weight:700;line-height:1.6;background:var(--s-stack);white-space:nowrap}.an-survey .s-primary{background:var(--s-brand);color:#fff;flex:1}.an-survey .s-primary:disabled{background:var(--s-focus);color:var(--s-sub)}
.an-survey .s-panel{width:100%;max-width:480px;margin:0 auto;padding:24px;background:var(--s-card);border-radius:24px}.an-survey .s-top{display:flex;align-items:center;justify-content:space-between;gap:12px;margin-bottom:20px}.an-survey .s-brand{font-size:14px;font-weight:800}.an-survey .s-brand span{color:var(--s-accent)}.an-survey .s-close{width:44px;height:44px;flex:none;border-radius:12px;display:flex;align-items:center;justify-content:center;background:transparent;color:var(--s-sub)}
.an-survey .s-progress-label{display:flex;justify-content:space-between;gap:12px;font-size:12px;color:var(--s-sub);margin-bottom:12px}.an-survey .s-count{color:var(--s-accent);font-weight:800;font-variant-numeric:tabular-nums}.an-survey .s-progress{display:flex;gap:5px;margin-bottom:28px}.an-survey .s-progress span{flex:1;height:4px;border-radius:4px;background:var(--s-focus)}.an-survey .s-progress span[data-filled=true]{background:var(--s-accent)}.an-survey .s-hint{margin:8px 0 22px}
.an-survey fieldset{border:0;margin:0;padding:0;min-width:0;display:grid;gap:8px}.an-survey .s-choice{display:flex;align-items:center;gap:12px;min-height:48px;border-radius:12px;padding:12px 16px;background:var(--s-stack);font-size:14px;font-weight:700;line-height:1.6;cursor:pointer;transition:background-color 160ms}.an-survey .s-choice:has(input:checked){background:var(--s-focus)}.an-survey .s-choice input{appearance:none;-webkit-appearance:none;margin:0;width:18px;height:18px;flex:0 0 18px;border:2px solid var(--s-sub);border-radius:50%;background:var(--s-card);position:relative}.an-survey .s-choice input[type=checkbox]{border-radius:5px}.an-survey .s-choice input:checked{background:var(--s-brand);border-color:var(--s-brand)}.an-survey .s-choice input:checked:after{content:'';position:absolute;width:6px;height:6px;left:4px;top:4px;background:#fff;border-radius:50%}.an-survey .s-choice input[type=checkbox]:checked:after{width:5px;height:8px;left:4px;top:1px;border:solid #fff;border-width:0 2px 2px 0;transform:rotate(45deg);border-radius:0;background:none}.an-survey .s-choice input:focus-visible{outline:none}.an-survey .s-choice:has(input:focus-visible){background:var(--s-focus);outline:2px solid var(--s-sub);outline-offset:2px}
.an-survey textarea{display:block;width:100%;min-height:196px;resize:vertical;border:0;border-radius:14px;background:var(--s-stack);padding:16px;font-size:16px;line-height:1.7}.an-survey textarea::placeholder{color:var(--s-sub);opacity:1}.an-survey textarea:focus-visible{outline:2px solid var(--s-sub);outline-offset:2px;background:var(--s-focus)}.an-survey .s-text-meta{display:flex;justify-content:space-between;gap:12px;font-size:11px;color:var(--s-sub);margin-top:10px}.an-survey .s-actions{display:flex;gap:10px;margin-top:24px}.an-survey .s-foot{display:flex;justify-content:center;margin-top:8px}.an-survey .s-skip{min-height:44px;border-radius:10px;padding:8px 12px;background:transparent;color:var(--s-sub);font-size:12px;font-weight:700}
.an-survey .s-note{font-size:11px;line-height:1.7;margin-top:16px;color:var(--s-sub)}.an-survey .s-error{background:var(--s-stack);padding:14px 16px;border-radius:12px;margin-top:16px;font-size:13px;color:var(--s-ink)}.an-survey .s-done{text-align:center;padding:24px 0 8px}.an-survey .s-done .s-icon{margin:0 auto 20px}.an-survey .s-done .s-button{width:100%;margin-top:24px}.an-survey .s-done p{margin-top:12px}.an-survey .s-question:focus{outline:none}.an-survey .s-button:focus-visible,.an-survey .s-close:focus-visible,.an-survey .s-skip:focus-visible{outline:2px solid var(--s-sub);outline-offset:3px}.an-survey .s-button:not(.s-primary):focus-visible,.an-survey .s-close:focus-visible,.an-survey .s-skip:focus-visible{background:var(--s-focus)}
@media(hover:hover){.an-survey .s-button:not(.s-primary):not(:disabled):hover,.an-survey .s-close:not(:disabled):hover,.an-survey .s-skip:not(:disabled):hover,.an-survey .s-choice:not(:has(input:checked)):not(:has(input:disabled)):hover{background:var(--s-hover)}}
@media(max-width:600px){.an-survey .s-invite{align-items:stretch;flex-direction:column;gap:16px}.an-survey .s-invite,.an-survey .s-panel{padding:20px;border-radius:20px}.an-survey .s-choice{padding-inline:12px}.an-survey .s-progress{margin-bottom:24px}.an-survey .s-top{margin-bottom:16px}}
@media(prefers-reduced-motion:reduce){.an-survey button,.an-survey .s-choice{transition:none}}
`

function readDark(): boolean {
    if (typeof document === "undefined") return false
    for (const explicit of [document.documentElement.dataset.anTheme, document.body?.dataset.framerTheme]) {
        if (explicit === "dark" || explicit === "light") return explicit === "dark"
    }
    try { return localStorage.getItem("verity_theme") === "dark" } catch { return false }
}

type Props = { apiBase?: string; theme?: "auto" | "light" | "dark"; enabled?: boolean; style?: React.CSSProperties }
/**
 * @framerIntrinsicWidth 680
 * @framerIntrinsicHeight 108
 * @framerSupportedLayoutWidth any
 * @framerSupportedLayoutHeight auto
 */
export default function PublicFeedbackSurvey({ apiBase = "https://project-yw131.vercel.app", theme = "auto", enabled = true, style }: Props) {
    const [open, setOpen] = React.useState(false)
    const [done, setDone] = React.useState(false)
    const [step, setStep] = React.useState(0)
    const [answers, setAnswers] = React.useState<Answers>(emptyAnswers)
    const [busy, setBusy] = React.useState(false)
    const [error, setError] = React.useState("")
    const [dark, setDark] = React.useState(false)
    const heading = React.useRef<HTMLHeadingElement>(null)
    const errorMessage = React.useRef<HTMLParagraphElement>(null)
    const trigger = React.useRef<HTMLButtonElement>(null)
    const flight = React.useRef<AbortController | null>(null)
    const attempt = React.useRef<{ json: string; id: string } | null>(null)
    const client = React.useRef<string>("")
    const mounted = React.useRef(true)
    const prefix = React.useId()
    React.useEffect(() => {
        mounted.current = true
        const sync = () => setDark(readDark())
        sync()
        const observer = new MutationObserver(sync)
        observer.observe(document.documentElement, { attributes: true, attributeFilter: ["data-an-theme"] })
        if (document.body) observer.observe(document.body, { attributes: true, attributeFilter: ["data-framer-theme"] })
        window.addEventListener("storage", sync)
        try { setDone(localStorage.getItem(DONE_KEY) === "1") } catch {}
        return () => { mounted.current = false; flight.current?.abort(); observer.disconnect(); window.removeEventListener("storage", sync) }
    }, [])
    React.useEffect(() => { if (open) heading.current?.focus({ preventScroll: true }) }, [open, step, done])
    React.useEffect(() => { if (error) errorMessage.current?.focus({ preventScroll: true }) }, [error])
    const close = () => { if (flight.current) return; setOpen(false); requestAnimationFrame(() => trigger.current?.focus({ preventScroll: true })) }
    function choose(value: string) {
        setError("")
        const key = QUESTIONS[step].key
        setAnswers(prev => {
            if (key !== "features") return { ...prev, [key]: value }
            const old = prev.features
            const features = old.includes(value) ? old.filter(v => v !== value) : value === "not_used" ? [value] : [...old.filter(v => v !== "not_used"), value]
            return { ...prev, features }
        })
    }
    async function submit(value: Answers) {
        if (flight.current) return
        if (RenderTarget.current() === RenderTarget.canvas) { setError("편집 화면에서는 의견을 전송하지 않아요."); return }
        const normalized = { ...value, features: [...value.features].sort(), comment: value.comment.trim() }
        if (!normalized.purpose && !normalized.features.length && !normalized.outcome && !normalized.discovery && !normalized.comment) {
            setError("답변이 비어 있어요. 하나만 남겨주셔도 좋아요."); return
        }
        const controller = new AbortController()
        flight.current = controller
        setBusy(true); setError("")
        const timeout = setTimeout(() => controller.abort(), 15000)
        try {
            const base = new URL(apiBase)
            if (base.protocol !== "https:" && !(base.protocol === "http:" && ["localhost", "127.0.0.1"].includes(base.hostname))) throw new Error("unavailable")
            if (!client.current) {
                try { const saved = localStorage.getItem(CLIENT_KEY); if (saved && UUID.test(saved)) client.current = saved } catch {}
                if (!client.current) client.current = crypto.randomUUID()
                try { localStorage.setItem(CLIENT_KEY, client.current) } catch {}
            }
            const json = JSON.stringify(normalized)
            if (attempt.current?.json !== json) attempt.current = { json, id: crypto.randomUUID() }
            const response = await fetch(new URL("/api/survey", base).href, {
                method: "POST", credentials: "omit", signal: controller.signal,
                headers: { "Content-Type": "application/json" },
                body: JSON.stringify({ survey_version: VERSION, request_id: attempt.current.id, client_id: client.current, ...normalized }),
            })
            const result = await response.json().catch(() => null)
            if (![200, 201].includes(response.status) || result?.ok !== true) {
                if (response.status === 429) throw new Error(result?.error === "already_submitted" ? "already" : "limited")
                if (response.status === 409) { attempt.current = null; throw new Error("conflict") }
                throw new Error("unavailable")
            }
            if (!mounted.current) return
            try { localStorage.setItem(DONE_KEY, "1") } catch {}
            setDone(true); setAnswers(emptyAnswers()); attempt.current = null
        } catch (e) {
            if (!mounted.current) return
            setError(e instanceof Error && e.message === "already"
                ? "이 브라우저에서는 이미 참여한 설문이에요. 추가 제출은 받지 않아요."
                : e instanceof Error && e.message === "limited"
                    ? "요청이 잠시 몰렸어요. 답변은 그대로 두었으니 잠시 후 다시 보내주세요."
                    : "의견을 저장했는지 확인하지 못했어요. 입력한 내용은 유지돼요. 잠시 후 다시 보내주세요.")
        } finally {
            clearTimeout(timeout); flight.current = null
            if (mounted.current) setBusy(false)
        }
    }
    function advance(skip = false) {
        if (busy) return
        const key = QUESTIONS[step].key
        const next = skip ? { ...answers, [key]: key === "features" ? [] : key === "comment" ? "" : null } : answers
        if (skip) setAnswers(next)
        setError("")
        if (step < 4) setStep(step + 1)
        else void submit(next)
    }
    if (!enabled) return null
    const q = QUESTIONS[step]
    const selected = answers[q.key]
    const ready = step === 4 || (Array.isArray(selected) ? selected.length > 0 : Boolean(selected))
    const appliedTheme = theme === "auto" ? dark ? "dark" : "light" : theme
    return <section className="an-survey" data-theme={appliedTheme} style={style} aria-label="알파네스트 의견 보내기" onKeyDown={e => { if (e.key === "Escape" && open && !busy) { e.stopPropagation(); close() } }}>
        <style>{CSS}</style>
        {!open ? <div className="s-invite">
            <div className="s-intro"><span className="s-icon"><ChatCircle size={22} weight="bold" aria-hidden /></span><div><h2>{done ? "소중한 의견, 고마워요" : "알파네스트를 써보니 어떠셨나요?"}</h2><p>{done ? "다음 개선에 참고할게요." : "좋았던 점도, 아쉬웠던 점도 들려주세요."}</p></div></div>
            <button ref={trigger} className="s-button" type="button" aria-expanded={open} aria-controls={`${prefix}-panel`} onClick={() => setOpen(true)}>{done ? "참여 완료" : "의견 보내기"}<CaretRight size={16} weight="bold" aria-hidden /></button>
        </div> : <div id={`${prefix}-panel`} className="s-panel">
            <div className="s-top"><div className="s-brand"><span>알파네스트</span> · 의견 보내기</div><button type="button" className="s-close" aria-label="설문 닫기" onClick={close} disabled={busy}><X size={18} weight="bold" aria-hidden /></button></div>
            {done ? <div className="s-done"><span className="s-icon"><Check size={22} weight="bold" aria-hidden /></span><h2 className="s-question" ref={heading} tabIndex={-1}>의견을 남겨주셔서<br />고마워요.</h2><p>더 쉽고 편한 알파네스트를<br />만드는 데 참고할게요.</p><button className="s-button s-primary" type="button" onClick={close}>계속 살펴보기<CaretRight size={16} weight="bold" aria-hidden /></button></div> : <>
                <div className="s-progress-label"><span className="s-count">{step + 1} / 5</span><span>편하게, 건너뛰어도 괜찮아요</span></div>
                <div className="s-progress" role="progressbar" aria-label="설문 진행" aria-valuemin={1} aria-valuemax={5} aria-valuenow={step + 1}>{QUESTIONS.map((_, i) => <span key={i} data-filled={i <= step} />)}</div>
                <h2 id={`${prefix}-question`} className="s-question" ref={heading} tabIndex={-1}>{q.title[0]}<br />{q.title[1]}</h2><p className="s-hint" id={`${prefix}-hint`}>{q.hint}</p>
                <div role="form" aria-labelledby={`${prefix}-question`} aria-describedby={`${prefix}-hint`} aria-busy={busy}>
                    {step < 4 ? <fieldset disabled={busy} aria-labelledby={`${prefix}-question`}>
                        {q.choices.map(([value, label]) => <label className="s-choice" key={value}><input type={step === 1 ? "checkbox" : "radio"} name={`${prefix}-${q.key}`} value={value} checked={Array.isArray(selected) ? selected.includes(value) : selected === value} onChange={() => choose(value)} /><span>{label}</span></label>)}
                    </fieldset> : <><textarea aria-label="알파네스트에 남길 의견" maxLength={500} value={answers.comment} disabled={busy} onChange={e => { setAnswers(prev => ({ ...prev, comment: e.target.value })); setError("") }} placeholder={"어떤 화면에서 무엇이 도움이 됐나요?\n불편했던 점을 남겨주셔도 좋아요."} /><div className="s-text-meta"><span>이름·연락처는 적지 말아주세요.</span><span>{answers.comment.length} / 500</span></div></>}
                    {error && <p className="s-error" role="alert" ref={errorMessage} tabIndex={-1}>{error}</p>}
                    <div className="s-actions">{step > 0 && <button className="s-button" type="button" disabled={busy} onClick={() => { setError(""); setStep(step - 1) }}><CaretLeft size={16} weight="bold" aria-hidden />이전</button>}<button type="button" className="s-button s-primary" disabled={!ready || busy} onClick={() => advance()}>{busy ? "보내는 중…" : step === 4 ? error ? "다시 보내기" : "의견 보내기" : "다음"}{!busy && <CaretRight size={16} weight="bold" aria-hidden />}</button></div>
                    <div className="s-foot"><button className="s-skip" type="button" disabled={busy} onClick={() => advance(true)}>{step === 4 ? "글 없이 보내기" : "이 질문 건너뛰기"}</button></div>
                    {step === 0 && <p className="s-note">5개 질문 · 로그인 없이 참여해요.<br />답변은 서비스 개선을 위해 운영자만 확인하며, 90일이 지나면 자동 삭제해요. 이름·연락처는 묻지 않아요.</p>}
                </div>
            </>}
        </div>}
    </section>
}

addPropertyControls(PublicFeedbackSurvey, {
    apiBase: { type: ControlType.String, title: "API", defaultValue: "https://project-yw131.vercel.app" },
    theme: { type: ControlType.Enum, title: "테마", options: ["auto", "light", "dark"], optionTitles: ["자동", "라이트", "다크"], defaultValue: "auto" },
    enabled: { type: ControlType.Boolean, title: "표시", defaultValue: true },
})
