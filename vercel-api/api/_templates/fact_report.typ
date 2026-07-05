// AlphaNest 팩트 리포트 — Typst 조판 템플릿 (fact_report.py 가 sys_inputs.data 로 JSON 주입).
// 설계: 파이썬 = 데이터 조립·포맷(단위·콤마), Typst = 조판만. 섹션 = 제네릭 테이블 스키마
//   { title, note, headers[], aligns[]("l"|"r"|"c"), widths[](fr 배수), rows[][] }
// RULE 7 — 전부 공시·수집 사실. 점수·추천 문구는 파이썬 쪽에서 원천 배제.

#let D = json(bytes(sys.inputs.data))

#let ink = rgb("#191f28")
#let sub = rgb("#4e5968")
#let faint = rgb("#8b95a1")
#let hair = rgb("#e5e8eb")
#let accent = rgb("#6c5ce7")

#set page(
  paper: "a4",
  margin: (top: 16mm, bottom: 18mm, x: 15mm),
  footer: context [
    #line(length: 100%, stroke: 0.5pt + hair)
    #v(1.5mm)
    #set text(size: 7pt, fill: faint)
    #grid(columns: (1fr, auto), column-gutter: 6mm,
      [#D.disclaimer],
      [#counter(page).display() / #counter(page).final().first()],
    )
  ],
)
#set text(font: "Pretendard", size: 9pt, lang: "ko", fill: ink)
#set par(leading: 0.55em)

// ─── 헤더 ───
#grid(columns: (1fr, auto), column-gutter: 6mm,
  [
    #text(size: 17pt, weight: 800)[#D.name]
    #h(2.5mm)
    #text(size: 9.5pt, fill: sub, weight: 600)[#D.ticker · #D.market]
    #v(0.5mm)
    #text(size: 8pt, fill: faint)[#D.business]
  ],
  align(right)[
    #text(size: 9.5pt, weight: 800, fill: accent)[ALPHANEST]
    #linebreak()
    #text(size: 7.5pt, fill: faint)[팩트 리포트 · #D.generated]
  ],
)
#v(1mm)
#line(length: 100%, stroke: 1pt + ink)

// ─── 개요 (kv) ───
#if D.kv.len() > 0 {
  v(2.5mm)
  grid(
    columns: (auto, 1fr, auto, 1fr),
    column-gutter: 4mm, row-gutter: 2.2mm,
    ..D.kv.map(p => (
      text(size: 8pt, fill: faint, weight: 600)[#p.at(0)],
      text(size: 8.6pt, weight: 600)[#p.at(1)],
    )).flatten()
  )
}

// ─── 섹션 (제네릭 테이블) ───
#let alignof(a) = if a == "r" { right } else if a == "c" { center } else { left }

#for s in D.sections {
  v(4mm)
  block(breakable: false)[
    #text(size: 10.5pt, weight: 800)[#s.title]
    #if s.note != "" [ #h(2mm) #text(size: 7.2pt, fill: faint)[#s.note] ]
    #v(1.2mm)
    #line(length: 100%, stroke: 0.5pt + hair)
  ]
  v(0.8mm)
  table(
    columns: s.widths.map(w => w * 1fr),
    align: (col, row) => alignof(s.aligns.at(col)) + horizon,
    stroke: (x, y) => if y == 0 { (bottom: 0.5pt + hair) } else { (bottom: 0.3pt + rgb("#f1f3f5")) },
    inset: (x: 1.5pt, y: 3pt),
    ..s.headers.map(h => text(size: 7.6pt, weight: 700, fill: faint)[#h]),
    ..s.rows.flatten().map(c => text(size: 8.4pt)[#c]),
  )
}

// ─── 출처 ───
#v(5mm)
#block(breakable: false)[
  #text(size: 8pt, weight: 700, fill: sub)[출처]
  #v(1mm)
  #text(size: 7.5pt, fill: faint)[#D.source_line]
]
