import { addPropertyControls, ControlType } from "framer"
import PublicStockReport from "./PublicStockReport"

/**
 * PublicUSStockReport — 미장(US) 프리셋 래퍼. 공유 PublicStockReport 에 US 기본값 baked-in (중복 0).
 *
 * 다크모드(body[data-framer-theme] 자가감지)·US forensics 4섹션 탭(is_us)·라이브 $가격(market=us)·
 * 토스 로고 = 전부 내부 PublicStockReport 가 처리 → delegate 로 자동 연동(별도 다크모드 코드 불요).
 * KR 전용 URL(insider/flow/forensics/warn) = 빈값 → US 티커 무매칭 fetch 회피, forensics 탭이 엔드포인트로 채움.
 *
 * ⚠️ Framer: 본 래퍼는 ./PublicStockReport 를 relative import. Framer Code Files 에서 같은 폴더 두 파일
 * 모두 동기화돼야 작동. 미해결 시 = PublicStockReport 본문을 인라인한 self-contained 버전으로 교체.
 */
const US_STOCK_URL =
    "https://rte5guenhonw9fzn.public.blob.vercel-storage.com/us_stock_report_public.json"
const US_API = "https://project-yw131.vercel.app"

export default function PublicUSStockReport(props: any) {
    return (
        <PublicStockReport
            stockUrl={props.stockUrl || US_STOCK_URL}
            apiBase={props.apiBase || US_API}
            flowUrl=""
            forensicsUrl=""
            insiderUrl=""
            warnUrl=""
            dark={!!props.dark}
        />
    )
}

addPropertyControls(PublicUSStockReport, {
    stockUrl: { type: ControlType.String, title: "US Stock URL", defaultValue: US_STOCK_URL },
    apiBase: { type: ControlType.String, title: "API Base", defaultValue: US_API },
    dark: { type: ControlType.Boolean, title: "Dark (canvas)", defaultValue: false },
})
