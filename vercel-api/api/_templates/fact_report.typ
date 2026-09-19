// Evidence report: PDF and plain-text export share one deterministic dossier.
#let D = json(bytes(sys.inputs.data))
#let ink = rgb("#191f28")
#let sub = rgb("#4e5968")
#let accent = rgb("#6c5ce7")
#let hair = rgb("#e5e8eb")
#let fill = rgb("#f5f6f8")
#set page(paper: "a4", margin: (top: 15mm, bottom: 17mm, x: 15mm),
  footer: context [
    #line(length: 100%, stroke: 0.5pt + hair)
    #v(1mm)
    #grid(columns: (1fr, auto), gutter: 5mm,
      text(size: 7pt, fill: sub)[#D.disclaimer],
      text(size: 7pt, fill: sub)[#counter(page).display() / #counter(page).final().first()])
  ])
#set text(font: "Pretendard", size: 9pt, weight: 600, lang: "ko", fill: ink)
#set par(leading: 0.55em)
#set heading(numbering: none)
#show heading.where(level: 1): set text(size: 15pt, weight: 800)
#show heading.where(level: 2): set text(size: 11pt, weight: 800)
#let cell(c) = if type(c) == dictionary {
  link(c.url, text(fill: accent, weight: 700)[#c.text])
} else { text(c) }
#grid(columns: (1fr, auto), gutter: 5mm,
  [#text(size: 19pt, weight: 800)[#D.name]
   #h(2mm)#text(size: 10pt, fill: sub)[#D.ticker · #D.market]
   #if D.business != "—" [#linebreak()#text(size: 8pt, fill: sub)[#D.business]]],
  align(right)[#text(size: 10pt, weight: 800, fill: accent)[ALPHANEST]
    #linebreak()#text(size: 8pt, fill: sub)[#D.report_label]
    #linebreak()#text(size: 7pt, fill: sub)[#D.generated]])
#v(2mm)
#line(length: 100%, stroke: 1pt + ink)
#v(2mm)
#let report-table(headers, rows, widths) = table(
  columns: widths.map(w => w * 1fr), inset: (x: 3pt, y: 5pt),
  stroke: (left: none, right: none, top: none, bottom: 0.4pt + hair),
  table.header(..headers.map(h => text(size: 8pt, weight: 700, fill: sub)[#h])),
  ..rows.flatten().map(c => text(size: 8.5pt)[#cell(c)]))
#let source-row(row) = if row != none [
  #text(size: 7.5pt, fill: sub)[#row.start - #row.end · #row.currency · #(if row.fs_div == "CFS" {"연결"} else if row.fs_div == "ENTITY" {"보고기업 전체(SEC)"} else {"별도"})]
  #h(2mm)#link(row.source_url, text(size: 7.5pt, fill: accent)[공시 원문 ↗])
]
#let R = D.reader
#v(3mm)
== 어떤 사업을 하는 기업인가
#v(1mm)
#block(fill: fill, radius: 6pt, inset: 4mm, width: 100%)[
  #text(size: 9pt)[#D.business_profile.summary]
  #v(2mm)
  #text(size: 7.5pt, fill: sub)[#D.business_profile.label]
  #if D.business_profile.source != none [#h(2mm)#cell(D.business_profile.source)]
]
#v(5mm)
== 최근 실적에서 달라진 점
#if R.current != none [
  #source-row(R.current)
  #v(1mm)
  #text(size: 8pt, fill: sub)[기간 구분: #(if R.current.period_kind == "quarter" {"단일 분기"} else if R.current.period_kind == "ytd" {"누적"} else {"연간"}). #(if R.prior != none {"전년 동기는 같은 기간 길이·통화·보고 범위로 맞췄습니다."} else {"같은 기준의 전년 동기를 확보하지 못해 증감률을 계산하지 않았습니다."})]
  #v(2mm)
  #report-table(("항목", "전년 동기", "이번 기간", "증감률"), R.rows, (1, 1.3, 1.3, 0.8))
  #if R.prior != none [#v(1mm)#text(size: 7pt, fill: sub)[전년 동기: ]#source-row(R.prior)]
] else [#text(size: 8.5pt, fill: sub)[본문에 사용할 재무 근거가 충분하지 않습니다. 확인 전 수치와 누락 범위는 부록에 구분했습니다.]]
#for note in R.observations [#v(2mm)#text(size: 8.5pt)[#note]]
#v(5mm)
== 연간 흐름도 함께 보기
#if D.annual_core.len() > 0 [
  #report-table(("실제 기간", "매출", "영업이익", "순이익"), D.annual_core, (1.65, 1, 1, 1))
  #v(1mm)#text(size: 7pt, fill: sub)[연간 수치입니다. 위의 단일 분기·누적 실적과 금액 크기를 직접 비교하지 마세요. 원문과 기준은 부록 R0·R1.]
] else [#text(size: 8.5pt, fill: sub)[연간 비교에 필요한 기간·통화·보고 범위·원문을 확보하지 못했습니다.]]
#pagebreak()
= 이익이 현금으로 이어졌나
#v(2mm)
#if R.cash != none [
  #source-row(R.cash)
  #v(2mm)
  #report-table(("항목", "금액"), R.cash_rows, (2, 1))
]
#for note in R.cash_notes [#v(2mm)#text(size: 8.5pt)[#note]]
#v(5mm)
== 최근 공시와 연결하기
#if D.recent_events.len() > 0 [
  #report-table(("제출일", "공시 제목", "유형", "원문"), D.recent_events, (0.8, 2.5, 0.7, 0.7))
  #v(1mm)#text(size: 7.5pt, fill: sub)[수신된 최근 3건 이내입니다. 제목만으로 실적 영향이나 호재·악재를 판단하지 않습니다.]
] else [#text(size: 8.5pt, fill: sub)[최근 공시 자료를 받지 못했습니다. 사건이나 위험이 없다는 뜻은 아닙니다.]]
#v(5mm)
== 숫자를 읽을 때 남겨둘 질문
#block(fill: fill, radius: 6pt, inset: 4mm, width: 100%)[
  #text(size: 9pt, weight: 800)[매출과 이익이 달라진 이유]
  #v(1mm)#text(size: 8.5pt)[사업부·제품별 실적과 가격·판매량·비용 설명을 공시에서 함께 읽으세요. 이익률 변화만으로 원인을 단정할 수 없습니다.]
  #v(3mm)#text(size: 9pt, weight: 800)[비교 대상의 조건]
  #v(1mm)#text(size: 8.5pt)[업종 중앙값은 사업 구조·결산기간·계산법이 같은 기업만의 값이 아닐 수 있습니다. 그래서 본문에서 저평가·고평가 판정에 사용하지 않았습니다.]
]
#v(4mm)
#text(size: 7.8pt, fill: sub)[본문 재무: 기준을 갖춘 #(R.accepted)/#(R.received)개 기간. 보고된 숫자와 자체계산을 구분했습니다. 항목별 계정·기간·원문 및 자료 누락은 다음 부록에서 확인할 수 있습니다.]
#pagebreak()
= 부록 · 자료 범위와 확인할 빈칸
#text(size: 8.5pt, fill: sub)[수신된 자료의 한계입니다. 없는 정보를 추정으로 채우지 않습니다.]
#v(3mm)
#for g in D.gaps [
  #block(breakable: false, inset: (bottom: 2.3mm))[
    #text(fill: accent)[·] #g
  ]
]
#v(3mm)
== 자료 점검표
#text(size: 8pt, fill: sub)[수신 여부는 이 종목의 자료가 있는지를 뜻합니다. 파일 생성·공시 제출·SEC 조회 시점이며, 재무·보유·거래 기준일은 각 표에서 확인하세요.]
#v(2mm)
#table(columns: (0.35fr, 1fr, 1.25fr, 1.5fr), inset: 4pt,
  stroke: (left: none, right: none, top: none, bottom: 0.4pt + hair),
  table.header(..("ID", "자료", "조회 결과", "갱신·제출·조회").map(h => text(size: 8pt, weight: 700)[#h])),
  ..D.coverage.map(c => (c.id, c.label, c.status, c.published)).flatten().map(c => text(size: 8pt)[#c]))
#v(3mm)
#for c in D.coverage [
  #block(breakable: false, inset: (bottom: 2mm))[
    #text(size: 7.8pt, weight: 700)[#c.id · #c.label]
    #text(size: 7pt, fill: sub)[ — #c.source]
    #linebreak()
    #if c.artifact_url != "" [#text(size: 7pt, fill: accent)[#link(c.artifact_url)[발행 자료 · #c.file]]] else [#text(size: 7pt, fill: sub)[원문 위치 미수신]]
    #if c.reason != "" [#linebreak()#text(size: 7pt, fill: sub)[#c.reason]]
  ]
]
#pagebreak()
= 근거를 따라 읽는 자료
#text(size: 8pt, fill: sub)[표 제목 옆 ID는 앞의 질문과 연결됩니다. 원문 열기는 수신된 문서 URL, 출처 목록은 문서 검색 페이지입니다.]
#for s in D.sections {
  v(4mm)
  block(breakable: s.rows.len() > 8 or s.id in ("R3", "B1"))[
    #block(breakable: false, sticky: true)[
      #text(size: 11pt, weight: 800)[#s.title]
      #h(2mm)#text(size: 7.4pt, fill: accent)[#s.id · 표시 #(s.shown)/#(s.total)행]
      #v(1mm)
      #text(size: 7.8pt, fill: sub)[#s.note]
    ]
    #v(1mm)
    #table(columns: s.widths.map(w => w * 1fr),
      inset: (x: 2pt, y: 4pt), stroke: (left: none, right: none, top: none, bottom: 0.4pt + hair),
      table.header(..s.headers.map(h => text(size: 8pt, weight: 700, fill: sub)[#h])),
      ..s.rows.flatten().map(c => text(size: 8.3pt)[#cell(c)]))
  ]
}
#v(4mm)
#line(length: 100%, stroke: 0.5pt + hair)
#text(size: 8pt, fill: sub)[#D.source_line]

#if "prompt_url" in D [
  #v(3mm)#text(size: 8pt)[원하는 AI에 직접 자료를 전달할 때: ]
  #link(D.prompt_url, text(size: 8pt, fill: accent)[분석 요청문과 근거 자료 받기 ↗])
]
