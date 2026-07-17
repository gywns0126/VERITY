import { addPropertyControls, ControlType, RenderTarget } from "framer"
import { useEffect, useRef, useState, type CSSProperties } from "react"

/**
 * 약관 문서 — 이용약관 / 개인정보처리방침 (탭 토글). AlphaNest 결: 흰 카드/외곽선 없음/토스 미니멀.
 * 텍스트 = solo-counsel(law.go.kr) 검토 반영(2026-06-27): 자본시장법 §101·§102, 약관규제법 §6·§9,
 *   개인정보보호법 §30·§28의8·§31. 무료·점수미제공·정보only 포지셔닝.
 * 🚨 보호책임자 연락처·시행일은 prop 으로 주입(실명 아닌 운영 전용 이메일 권장 — 현역 신상 최소화).
 * 다크모드 = body[data-framer-theme] 자가감지.
 */

const LIGHT = { bg: "#f2f4f6", card: "#ffffff", ink: "#191f28", sub: "#4e5968", faint: "#8b95a1", line: "#f0f1f3", accent: "#6c5ce7", accentSoft: "#f0edff" }
const DARK = { bg: "#0f1318", card: "#171c23", ink: "#e3e7ec", sub: "#9aa4b1", faint: "#828d9b", line: "#222730", accent: "#a98bff", accentSoft: "#2a2440" }
const FONT = "Pretendard, -apple-system, BlinkMacSystemFont, 'Apple SD Gothic Neo', sans-serif"

function readBodyDark(): boolean {
    try {
        const _lsPref = (typeof localStorage !== "undefined") ? localStorage.getItem("verity_theme") : null
        if (_lsPref === "dark") return true
        if (_lsPref === "light") return false
    } catch (e) {}
    if (typeof document === "undefined" || !document.body) return false
    return document.body.dataset.framerTheme === "dark"
}

type Sec = { h: string; body: string[] }

const TERMS: Sec[] = [
  { h: "제1조 (목적)", body: ["본 약관은 운영자가 제공하는 정보 서비스(이하 \"서비스\")의 이용 조건과 운영자·이용자의 권리·의무를 정함을 목적으로 합니다."] },
  { h: "제2조 (서비스의 성격)", body: [
    "1. 서비스는 공개된 공시·공공데이터를 기계적으로 가공한 사실과 패턴을 제공하는 정보 서비스이며, 투자자문·투자권유·투자추천·투자일임이 아닙니다.",
    "2. 서비스는 특정 종목·자산의 매매를 권유하거나 투자 판단(점수·등급·순위·매매신호)을 제공하지 않습니다.",
    "3. 서비스는 무료로 제공되며 개별 투자상담을 수행하지 않습니다.",
  ] },
  { h: "제3조 (투자 위험 고지)", body: [
    "1. 본 서비스는 개별적인 투자상담을 제공하지 않습니다.",
    "2. 모든 투자의 최종 판단과 그에 따른 원금 손실 등 모든 책임은 이용자 본인에게 있습니다.",
    "3. 콘텐츠는 공개 자료를 기계적으로 가공한 통계·사실 정보이며, 투자 추천이 아닙니다.",
  ] },
  { h: "제4조 (데이터 출처·정확성)", body: [
    "1. 콘텐츠는 DART·공정거래위원회·공공데이터·CoinGecko·SoSoValue·DefiLlama 등 외부 출처에 기반하며 출처를 표기합니다.",
    "2. 운영자는 콘텐츠의 정확성·완전성·적시성을 보증하지 않으며, 데이터는 지연·오류·중단될 수 있습니다.",
  ] },
  { h: "제5조 (지식재산권·이용 제한)", body: [
    "1. 콘텐츠의 권리는 각 원출처 및 운영자에게 있습니다.",
    "2. 이용자는 콘텐츠를 무단으로 복제·크롤링·재배포·상업적으로 이용할 수 없습니다.",
  ] },
  { h: "제6조 (이용자의 의무)", body: ["이용자는 무단 수집·재배포·상업적 이용, 서비스 운영 방해, 관계 법령·공서양속 위반 행위를 하여서는 안 됩니다."] },
  { h: "제6조의2 (이용자 게시물)", body: [
    "1. 이용자가 공개로 설정한 관점 메모 등 게시물은 해당 이용자 개인의 의견이며, 운영자의 분석·판단·투자권유가 아닙니다.",
    "2. 게시물 내용에 대한 책임은 게시한 이용자 본인에게 있습니다. 이용자는 게시물로 특정 종목의 매매를 권유·유인하거나, 허위사실 유포, 시세에 영향을 줄 목적의 풍문 유포, 유료 리딩 등 관계 법령에 위반되는 행위를 하여서는 안 됩니다.",
    "3. 운영자는 신고가 접수되거나 본 조 위반이 확인된 게시물을 사전 통지 없이 숨김 또는 삭제할 수 있습니다.",
    "4. 이용자는 게시물이 서비스 내 표시 목적으로 저장·노출되는 것을 허락합니다. 공개 설정 해제 또는 삭제 시 게시물은 공개 화면에서 제거됩니다.",
  ] },
  { h: "제7조 (개인정보)", body: ["개인정보의 처리는 별도의 개인정보처리방침에 따릅니다."] },
  { h: "제8조 (서비스 변경·중단)", body: ["운영자는 서비스를 변경하거나 운영·기술상 필요에 따라 중단할 수 있으며, 무료 서비스의 변경·중단에 별도 보상 책임을 지지 않습니다."] },
  { h: "제9조 (책임의 제한)", body: [
    "1. 운영자는 무료로 제공되는 서비스와 관련하여 관련 법령이 허용하는 범위에서 책임을 지지 않습니다.",
    "2. 운영자는 이용자가 콘텐츠에 기반하여 내린 투자 판단의 결과에 대하여 책임을 지지 않습니다.",
    "3. 단, 본 조의 책임 제한은 운영자의 고의 또는 중대한 과실로 인한 손해에는 적용되지 않습니다.",
    "4. 본 책임 제한은 자본시장법 등 강행규정의 적용을 배제하지 않습니다.",
  ] },
  { h: "제10조 (준거법·관할)", body: ["본 약관은 대한민국 법령에 따르며, 분쟁은 민사소송법상 관할 법원을 제1심 관할로 합니다."] },
]

const PRIVACY: Sec[] = [
  { h: "1. 총칙", body: ["운영자는 개인정보 보호법 제30조에 따라 정보주체의 개인정보를 보호하기 위하여 본 개인정보처리방침을 수립·공개합니다."] },
  { h: "2. 수집 항목", body: [
    "· 소셜 로그인 시: 이메일 주소, 소셜 제공자 식별자(필수), 프로필 이름·이미지(선택)",
    "· 이용 중 생성: 관심종목, 별명·프로필 사진, 관점 메모(공개 설정 시 별명·사진과 함께 다른 이용자에게 노출) 등 이용자가 저장한 설정",
    "· 자동 수집: 접속 로그·쿠키·IP·기기 정보(운영·보안)",
  ] },
  { h: "3. 처리 목적", body: ["회원 식별·인증, 개인화 설정 제공, 서비스 운영·보안·부정이용 방지, 문의 응대. 목적 외 처리하지 않습니다."] },
  { h: "4. 보유·파기", body: ["회원 정보는 탈퇴 시까지 보유하며 탈퇴 시 지체 없이 복구 불가능한 방법으로 파기합니다(법령상 보존 의무 제외)."] },
  { h: "5. 제3자 제공", body: ["법령 근거 또는 정보주체 동의가 있는 경우를 제외하고 제3자에게 제공하지 않습니다."] },
  { h: "6. 처리 위탁", body: ["인증·저장(Supabase), 호스팅(Vercel)을 위탁하며 수탁자가 법령을 준수하도록 관리·감독합니다."] },
  { h: "6의2. 국외 이전 (개인정보보호법 §28의8)", body: [
    "Supabase(미국)·Vercel(미국) 서버에 회원 정보가 저장되어 개인정보가 국외로 이전됩니다.",
    "· 이전받는 자: Supabase Inc.(미국) — 이메일·식별자·관심종목 / 인증·저장",
    "· 이전받는 자: Vercel Inc.(미국) — 접속로그 등 / 호스팅",
    "이전 시점: 회원가입·서비스 이용 시 네트워크 전송. 가입 시 본 국외 이전에 동의한 것으로 봅니다.",
  ] },
  { h: "7. 정보주체의 권리", body: ["정보주체는 언제든지 열람·정정·삭제·처리정지를 요구할 수 있으며, 아래 보호책임자에게 행사할 수 있습니다. 회원은 직접 탈퇴(삭제)할 수 있습니다."] },
  { h: "8. 쿠키", body: ["로그인 유지·이용 분석을 위해 쿠키 및 브라우저 저장소를 사용하며, 이용자는 브라우저 설정으로 거부할 수 있습니다(일부 기능 제한)."] },
  { h: "9. 개인정보 보호책임자", body: ["__CPO__"] },
  { h: "10. 안전성 확보", body: ["접근권한 관리, 전송구간 암호화(HTTPS), 수탁자 보안 점검 등 합리적 보호조치를 취합니다."] },
]

export default function PublicLegalDoc(props: { doc?: "terms" | "privacy"; dark?: boolean; cpoContact?: string; effectiveDate?: string }) {
  const onCanvas = RenderTarget.current() === RenderTarget.canvas
  const [themeDark, setThemeDark] = useState<boolean>(() => (RenderTarget.current() === RenderTarget.canvas ? !!props.dark : (typeof document !== "undefined" && !!document.body && document.body.dataset.framerTheme === "dark")))
  const isDark = onCanvas ? !!props.dark : themeDark
  const C = isDark ? DARK : LIGHT
  const [tab, setTab] = useState<"terms" | "privacy">(props.doc === "privacy" ? "privacy" : "terms")
  const rootRef = useRef<HTMLDivElement>(null)

  useEffect(() => {
    if (onCanvas) return
    const read = () => setThemeDark(readBodyDark())
    read()
    if (typeof MutationObserver === "undefined" || typeof document === "undefined" || !document.body) return
    const obs = new MutationObserver(read)
    obs.observe(document.body, { attributes: true, attributeFilter: ["data-framer-theme"] })
    return () => obs.disconnect()
  }, [onCanvas])

  // 미설정 placeholder("게시 시 기입")는 canvas 편집 화면에만 노출 — 라이브엔 중립 fallback(내부 메모 누출 차단).
  // ⚠ 실제 게시 전 Framer prop 로 시행일·보호책임자 연락처를 반드시 설정할 것.
  const cpo = props.cpoContact || (onCanvas ? "운영 전용 이메일 (게시 시 기입)" : "사이트 문의 경로로 접수")
  const eff = props.effectiveDate || (onCanvas ? "(게시 시 기입)" : "게시일 기준")
  const secs = (tab === "privacy" ? PRIVACY : TERMS).map((s) => ({ h: s.h, body: s.body.map((b) => b.replace("__CPO__", "보호책임자 연락처: " + cpo)) }))

  const wrap: CSSProperties = { width: "100%", boxSizing: "border-box", fontFamily: FONT, color: C.ink, background: C.bg, borderRadius: 18, padding: 22, display: "flex", flexDirection: "column", gap: 14 }

  return (
    <div ref={rootRef} style={wrap}>
      {/* 탭 */}
      <div style={{ display: "inline-flex", alignSelf: "flex-start", background: C.line, borderRadius: 10, padding: 3 }}>
        {([["terms", "이용약관"], ["privacy", "개인정보처리방침"]] as const).map(([k, lab]) => (
          <button key={k} onClick={() => setTab(k)} style={{ border: "none", cursor: "pointer", fontFamily: FONT, fontSize: 12.5, fontWeight: 700, padding: "7px 14px", borderRadius: 8, background: tab === k ? C.card : "transparent", color: tab === k ? C.accent : C.sub }}>{lab}</button>
        ))}
      </div>

      <div style={{ fontSize: 21, fontWeight: 800, letterSpacing: "-0.5px" }}>{tab === "privacy" ? "개인정보처리방침" : "이용약관"}</div>
      <div style={{ fontSize: 11.5, color: C.faint, fontWeight: 500, marginTop: -8 }}>시행일 {eff} · 무료 정보 서비스 · 투자자문·추천 아님</div>

      <div style={{ background: C.card, borderRadius: 16, padding: "6px 18px 14px" }}>
        {secs.map((s, i) => (
          <div key={i} style={{ padding: "14px 0", borderTop: i === 0 ? "none" : "1px solid " + C.line }}>
            <div style={{ fontSize: 14, fontWeight: 700, color: C.ink, marginBottom: 7, letterSpacing: "-0.2px" }}>{s.h}</div>
            {s.body.map((b, j) => (
              <div key={j} style={{ fontSize: 12.5, color: C.sub, fontWeight: 500, lineHeight: 1.65, letterSpacing: "-0.2px", marginTop: j === 0 ? 0 : 3 }}>{b}</div>
            ))}
          </div>
        ))}
      </div>

      <div style={{ fontSize: 11, color: C.faint, fontWeight: 500, lineHeight: 1.6 }}>
        본 서비스는 신고된 유사투자자문업자가 아니며 무료로 사실·통계 정보만 제공합니다. 투자 판단과 책임은 이용자 본인에게 있습니다.
      </div>
    </div>
  )
}

addPropertyControls(PublicLegalDoc, {
  doc: { type: ControlType.Enum, title: "기본 문서", options: ["terms", "privacy"], optionTitles: ["이용약관", "개인정보처리방침"], defaultValue: "terms" },
  dark: { type: ControlType.Boolean, title: "Dark (canvas)", defaultValue: false },
  cpoContact: { type: ControlType.String, title: "보호책임자 연락처", defaultValue: "" },
  effectiveDate: { type: ControlType.String, title: "시행일", defaultValue: "" },
})
