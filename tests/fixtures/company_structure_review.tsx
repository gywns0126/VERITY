// Isolated local acceptance host. Uses the actual canvas, public companies and
// historical announcement; only this host's note and saved record are synthetic.
import * as React from "react"
import { createRoot } from "react-dom/client"
import CompanyStructureView, { useCompanyStructureBridge } from "../../review/member-map/company-structure-view"

const nonce = "company-structure-local-review"
const model = {
    nodes: [
        { id: "KR:000660", name: "SK하이닉스", ticker: "000660", code: "000660", market: "KR", kind: "stock", x: .38, y: .28, logo: "SK", color: "#e50032" },
        { id: "US:TSM", name: "TSMC", ticker: "TSM", code: "TSM", market: "US", kind: "stock", x: .64, y: .28, logo: "T", color: "#334155" },
        { id: "reviewed:events:skh-tsmc-hbm4", name: "HBM4 기술 협력 발표", kind: "event", recordKind: "event", layer: "events", topic: "supply", code: "검토 완료 공통 사건", asOf: "2024-04-19", reason: "당시 HBM4 개발·패키징 협력 MOU 발표", source: "SK하이닉스", x: .5, y: .52, evidence: [{ source: "SK하이닉스 공식 발표", url: "https://news.skhynix.com/en/sk-hynix-partners-with-tsmc-to-strengthen-hbm-technological-leadership/" }] }
    ],
    edges: ["KR:000660", "US:TSM"].map((id, i) => ({ id: "cooperation-" + i, from: "reviewed:events:skh-tsmc-hbm4", to: id, type: "documented", confirmation: "confirmed", strength: 0, impact: "미확인", verb: "기술 협력 발표" })),
    notes: { "review-note": { id: "review-note", target: "", x: .25, y: .64, text: "합성 검수 메모 · 위치 유지 확인", done: false, todo: false, pinned: false } },
    marks: {}, writable: true, originGeneration: 1, introHidden: true, coverageNotice: "로컬 검수 · 공개 회사·과거 발표 / 합성 메모만 사용"
}

function Fixture() {
    const frame = React.useRef<HTMLIFrameElement>(null), port = React.useRef<MessagePort | null>(null)
    const [draft, setDraft] = React.useState<unknown>(null), [saves, setSaves] = React.useState(0)
    const structure = useCompanyStructureBridge("synthetic-review")
    React.useEffect(() => {
        const receive = (event: MessageEvent) => {
            if (event.source !== frame.current?.contentWindow || event.data?.type !== "alphanest-member-ready" || event.data.nonce !== nonce) return
            if (port.current) return
            const channel = new MessageChannel(); port.current = channel.port1
            channel.port1.onmessage = event => {
                if (event.data?.type === "edit") setDraft(event.data.draft)
                if (event.data?.type === "save") { setSaves(n => n + 1); channel.port1.postMessage({ type: "status", writable: true, saving: false, message: "합성 검수 기록 저장" }) }
            }
            frame.current!.contentWindow!.postMessage({ type: "alphanest-member-connect", nonce }, "*", [channel.port2])
            channel.port1.postMessage({ type: "init", model })
        }
        window.addEventListener("message", receive)
        return () => { window.removeEventListener("message", receive); port.current?.close() }
    }, [])
    return <>
        <header style={{ height: 42, display: "flex", alignItems: "center", gap: 16, padding: "0 16px", fontFamily: "sans-serif" }}><strong>기업 구조 · 로컬 검수</strong><button type="button" onClick={structure.open}>기업 구조</button><span role="status">합성 저장 {saves}회</span></header>
        <iframe ref={frame} title="핵심 지도 검수" sandbox="allow-scripts" src={"/member-map-canvas#" + nonce} style={{ width: "100%", height: "calc(100vh - 80px)", border: 0 }} onLoad={() => frame.current?.contentWindow?.postMessage({ type: "alphanest-member-start", nonce }, "*")} />
        <details><summary>합성 검수 기록</summary><output id="review-draft">{JSON.stringify(draft)}</output></details>
        {structure.snapshot && <CompanyStructureView snapshot={structure.snapshot} onClose={structure.close} />}
    </>
}
createRoot(document.getElementById("root")!).render(<Fixture />)
