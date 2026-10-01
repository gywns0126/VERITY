import * as React from "react"
import { createRoot } from "react-dom/client"
import AlphaNestAuth, { getVeritySession } from "./Auth.snapshot"
import PublicPortfolioMapReview from "./Map.snapshot"

declare const __PUBLIC_AUTH__: { url: string; anon: string }
const RETURN_URL = "https://project-yw131.vercel.app/member-map-review"

function Review() {
    const [signedIn, setSignedIn] = React.useState(false)
    const [accountOpen, setAccountOpen] = React.useState(false)
    React.useEffect(() => {
        // PublicAuth owns normal login. Never transfer sessions across origins.
        const sync = () => setSignedIn(Boolean(getVeritySession()?.user?.id))
        sync()
        window.addEventListener("verity_auth_change", sync)
        window.addEventListener("storage", sync)
        return () => {
            window.removeEventListener("verity_auth_change", sync)
            window.removeEventListener("storage", sync)
        }
    }, [])
    return <>
        <header className="review-bar">
            <strong><i aria-hidden="true">α</i> ALPHANEST <span>회원 검수</span></strong>
            {signedIn ? <button type="button" aria-expanded={accountOpen} onClick={() => setAccountOpen(value => !value)}>
                계정
            </button> : <span>로그인 필요</span>}
        </header>
        <section className="review-auth" hidden={signedIn && !accountOpen} aria-label="알파네스트 로그인">
            <p className="review-boundary">회원 검수용 작업판입니다. 여기서 기존 보유종목은 변경하지 않아요.</p>
            <AlphaNestAuth supabaseUrl={__PUBLIC_AUTH__.url} supabaseAnonKey={__PUBLIC_AUTH__.anon}
                redirectUrl={RETURN_URL} afterLoginPath="/member-map-review" dark={false}
                termsUrl="https://www.alphanest.kr/policy" privacyUrl="https://www.alphanest.kr/policy" />
        </section>
        {signedIn ? <main><PublicPortfolioMapReview /></main> :
            <p className="review-help">기존 알파네스트 계정으로 로그인하면 내 보유종목과 비공개 지도 기록을 불러와요.</p>}
    </>
}

createRoot(document.getElementById("root")!).render(<Review />)
