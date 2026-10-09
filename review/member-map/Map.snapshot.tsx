var __defProp = Object.defineProperty;
var __defNormalProp = (obj, key, value) => key in obj ? __defProp(obj, key, { enumerable: true, configurable: true, writable: true, value }) : obj[key] = value;
var __publicField = (obj, key, value) => __defNormalProp(obj, typeof key !== "symbol" ? key + "" : key, value);

// output/member-map-integration-20260927/PortfolioMapReview.entry.tsx
import * as React6 from "react";
import { addPropertyControls, ControlType, useIsStaticRenderer } from "framer";

// framer-components/public-probe/PublicPortfolioPrototype.tsx
import * as React5 from "react";

// framer-components/public-probe/StockInfoMapData.tsx
var SECTION_ORDER = [
  { id: "business", title: "사업·경쟁력" },
  { id: "finance", title: "실적·재무" },
  { id: "valuation", title: "가격·가치 비교" },
  { id: "events", title: "최근 변화·일정" },
  { id: "holders", title: "주주·자본 배분" },
  { id: "risks", title: "위험·확인할 질문" }
];
var sectionTitle = (id) => SECTION_ORDER.find((section) => section.id === id).title;
var text = (value) => typeof value === "string" ? value.trim() : value == null ? "" : String(value).trim();
var record = (value) => value && typeof value === "object" && !Array.isArray(value) ? value : {};
var list = (value) => Array.isArray(value) ? value.filter((item) => item && typeof item === "object") : [];
var hasValue = (value) => value !== void 0 && value !== null && text(value) !== "";
var isFailure = (value) => !!record(value).__infoMapError;
var factTitle = (key) => ({ PER: "PER (주가수익비율)", PBR: "PBR (주가순자산비율)", PSR: "PSR (주가매출비율)", ROE: "ROE (자기자본이익률)", BPS: "BPS (주당순자산)", EPS: "EPS (주당순이익)", FCF: "FCF (잉여현금흐름)", "D/E": "D/E (부채비율)" })[key] || key;
var factExplanation = (note) => typeof note === "string" ? text(note) : text(record(note).description) || text(record(note).explanation) || text(record(note).note);
var factAsOf = (note) => {
  const value = record(note);
  return text(value.as_of) || text(value.asOf) || text(value.period_end) || text(value.end) || text(value.date) || void 0;
};
var factSection = (key) => /^(PER|PBR|PSR|BPS|EPS|PEG|EV\/EBITDA|시가총액)$/.test(key) ? "valuation" : /배당|자사주|주주환원/.test(key) ? "holders" : /Altman|위험|소송|희석/.test(key) ? "risks" : "finance";
function factItems(report, sectionId) {
  const notes = record(report.facts_note), calculations = record(report.facts_calc);
  return Object.entries(record(report.facts)).map(([key, value], index) => ({ key, value, index })).filter(({ key, value }) => factSection(key) === sectionId && hasValue(value)).map(({ key, value, index }) => {
    const note = notes[key], calculation = text(calculations[key]);
    return {
      id: `fact-${index}`,
      title: factTitle(key),
      value: text(value),
      topic: sectionId === "valuation" ? "가격과 비교하는 지표" : sectionId === "holders" ? "주주 환원" : sectionId === "risks" ? "위험 참고 지표" : "수익성·재무 지표",
      explanation: [factExplanation(note) || "발행 종목 리포트에 제공된 지표입니다.", calculation && `계산 기준: ${calculation}`, key === "Altman-Z" && "통계모형 지표이며 기업의 안전이나 부도를 확정하지 않습니다."].filter(Boolean).join("\n"),
      asOf: factAsOf(note),
      source: sourceLabel(record(note).source, "발행 종목 리포트"),
      url: safeHttpLink(record(note).source_url || record(note).url),
      relationship: "unknown"
    };
  });
}
function readySection(id, items, message) {
  return { id, title: sectionTitle(id), items, state: items.some((item) => item.kind !== "question") ? "ready" : "empty", ...message ? { message } : {} };
}
var periodOrder = (row5) => `${text(row5.end) || "0000-00-00"}\0${text(row5.year).padStart(8, "0")}`;
function uniqueAnnual(rows2) {
  const unique3 = /* @__PURE__ */ new Map();
  for (const row5 of rows2.slice().sort((a, b) => periodOrder(a).localeCompare(periodOrder(b)))) unique3.set(`${text(row5.start)}\0${text(row5.end)}\0${text(row5.year)}`, row5);
  return [...unique3.values()].sort((a, b) => periodOrder(a).localeCompare(periodOrder(b)));
}
function safeHttpLink(value) {
  const raw = text(value);
  if (!raw || /[\r\n]/.test(raw)) return void 0;
  try {
    const url = new URL(raw);
    return (url.protocol === "https:" || url.protocol === "http:") && !url.username && !url.password ? url.href : void 0;
  } catch {
    return void 0;
  }
}
function errorSection(id, message) {
  const title = sectionTitle(id);
  return { id, title, items: [], state: "error", message };
}
function sourceLabel(value, fallback) {
  const source = text(value);
  return source || fallback;
}
function money(value, currency) {
  if (typeof value !== "number" || !Number.isFinite(value)) return "";
  const unit = text(currency);
  return unit ? `${new Intl.NumberFormat("en-US", { maximumFractionDigits: 0 }).format(value)} ${unit}` : "";
}
function businessSection(slice, failed) {
  if (failed) return errorSection("business", "종목 정보 요청에 실패했습니다.");
  const overview = record(slice.business_overview);
  const report = record(slice.report);
  const excerpt = text(overview.text);
  const items = excerpt ? [{
    id: "business-overview",
    title: "사업 개요",
    topic: "무엇으로 돈을 버나",
    explanation: excerpt,
    asOf: text(overview.filed_at) || void 0,
    source: sourceLabel(overview.source, "DART 사업보고서"),
    url: safeHttpLink(overview.url),
    relationship: "direct"
  }] : [];
  const business = text(report.business);
  if (!excerpt && business) items.push({ id: "business-report", title: "사업 설명", topic: "무엇으로 돈을 버나", explanation: business, source: "발행 종목 리포트", relationship: "unknown" });
  const peer = record(report.peer), company = record(report.overview);
  const industry = [text(peer.sector) || text(company.sector) || text(report.gics_ko) || text(report.gics), text(peer.industry)].filter(Boolean);
  if (industry.length) items.push({ id: "industry", title: "업종 분류", topic: "어떤 시장에 속하나", explanation: industry.join(" · "), source: "발행 종목 리포트", relationship: "unknown" });
  const chain = record(report.supply_chain), seen = /* @__PURE__ */ new Set();
  list(chain.snippets).forEach((row5, index) => {
    const snippet = text(row5.snippet);
    if (!snippet || seen.has(snippet)) return;
    seen.add(snippet);
    items.push({ id: `customer-${index}`, title: `${text(row5.anchor) || "고객·공급망"} · 발췌 ${index + 1}`, topic: "누구와 거래하나", explanation: snippet, source: [text(chain.report_nm), text(chain.note) || "사업보고서 발췌"].filter(Boolean).join(" · "), asOf: text(chain.rcept_dt) || void 0, url: safeHttpLink(chain.source_url), relationship: "direct" });
  });
  return readySection("business", items, items.length ? "사업 설명·거래처 발췌입니다. 경쟁 우위가 입증됐다는 뜻은 아닙니다." : "사업 원문이 제공되지 않았습니다.");
}
function financeSection(slice, failed) {
  if (failed) return errorSection("finance", "종목 정보 요청에 실패했습니다.");
  const report = record(slice.report);
  const periods = list(record(report.financial_evidence).periods);
  const annual = periods.filter((row5) => text(row5.period_kind) === "annual" && text(row5.currency) && text(row5.fs_div) && (Number.isFinite(row5.revenue) || Number.isFinite(row5.op) || Number.isFinite(row5.net)));
  const evidenceGroups = annual.reduce((groups2, row5) => {
    const key = `${text(row5.currency)}\0${text(row5.fs_div)}`;
    groups2[key] = [...groups2[key] || [], row5];
    return groups2;
  }, {});
  const evidenceSeries = Object.values(evidenceGroups).map(uniqueAnnual).sort((a, b) => b.length - a.length || periodOrder(b[b.length - 1] || {}).localeCompare(periodOrder(a[a.length - 1] || {})))[0] || [];
  const latestEvidence = evidenceSeries[evidenceSeries.length - 1];
  const legacyUSAnnual = /^(US|NASDAQ|NYSE|AMEX)$/.test(text(slice.market).toUpperCase());
  const fallbackGroups = list(report.fin_series).filter((row5) => (text(row5.period_kind) === "annual" || legacyUSAnnual && !text(row5.period_kind) && Number.isInteger(row5.year)) && text(row5.currency) && (Number.isFinite(row5.revenue) || Number.isFinite(row5.op) || Number.isFinite(row5.net))).reduce((groups2, row5) => {
    const currency = text(row5.currency);
    groups2[currency] = [...groups2[currency] || [], row5];
    return groups2;
  }, {});
  const fallbackSeries = Object.values(fallbackGroups).map(uniqueAnnual).sort((a, b) => b.length - a.length || periodOrder(b[b.length - 1] || {}).localeCompare(periodOrder(a[a.length - 1] || {})))[0] || [];
  const verifiedSeries = latestEvidence ? evidenceSeries : fallbackSeries;
  const latest = latestEvidence || verifiedSeries[verifiedSeries.length - 1];
  const income = latest ? [{
    id: "annual-income",
    title: "최근 연간 실적",
    topic: "얼마나 벌었나",
    explanation: [text(latest.fs_div) === "CFS" ? "연결 재무제표" : text(latest.fs_div) === "OFS" ? "별도 재무제표" : "", text(latest.filed) ? `제출 ${text(latest.filed)}` : ""].filter(Boolean).join(" · ") || "회계연도별 금액입니다. 원문 통화를 유지하며 정확한 금액은 자세히 보기에서 확인할 수 있어요.",
    asOf: text(latest.start) && text(latest.end) ? `${text(latest.start)} ~ ${text(latest.end)}` : hasValue(latest.year) ? `${text(latest.year)} 회계연도` : void 0,
    source: latestEvidence ? sourceLabel(record(report.financial_evidence).source, "재무제표 원문") : "발행 종목 리포트",
    url: safeHttpLink(latest.source_url),
    relationship: latestEvidence ? "direct" : "unknown",
    rows: [["매출", latest.revenue], ["영업이익", latest.op], ["순이익", latest.net]].filter(([, value]) => Number.isFinite(value)).map(([label2, value]) => ({ label: label2, value: money(value, latest.currency) })),
    chart: verifiedSeries.slice(-6).filter((row5) => Number.isFinite(row5.revenue)).map((row5) => ({ label: text(row5.year), value: row5.revenue })),
    unit: text(latest.currency)
  }] : [];
  const financials = record(report.financials);
  const groups = list(financials.groups).map((group, index) => ({
    id: `statement-${index}`,
    title: text(group.title) || "재무제표",
    topic: /현금/.test(text(group.title)) ? "현금이 남나" : /상태/.test(text(group.title)) ? "재무 구조는 어떤가" : "실적의 세부 항목",
    explanation: "발행 리포트의 재무제표 요약입니다. 표시 단위와 기준 기간을 원자료와 함께 확인하세요.",
    asOf: text(financials.period) || void 0,
    source: "발행 종목 리포트",
    relationship: "unknown",
    rows: list(group.rows).filter((row5) => text(row5.k) && hasValue(row5.v)).map((row5) => ({ label: text(row5.k), value: text(row5.v) }))
  })).filter((item) => item.rows.length > 0);
  const items = [...income, ...factItems(report, "finance"), ...groups];
  return readySection("finance", items, items.length ? void 0 : "재무 지표가 제공되지 않았습니다.");
}
function valuationSection(slice, failed) {
  if (failed) return errorSection("valuation", "종목 정보 요청에 실패했습니다.");
  const report = record(slice.report), peer = record(report.peer);
  const items = factItems(report, "valuation");
  const rows2 = list(peer.rows).filter((row5) => text(row5.key) && hasValue(row5.value) && hasValue(row5.median));
  if (rows2.length) items.push({
    id: "peer-comparison",
    title: "같은 분류 기업의 중앙값",
    topic: "무엇과 비교하나",
    explanation: [text(peer.sector), hasValue(peer.n) ? `지표별 비교 표본 최대 ${text(peer.n)}개 기업 (각 지표의 표본 수는 미제공)` : "비교 기업 수 미제공", text(peer.note), "중앙값은 크기순 가운데 값입니다. 개별 지표의 동일 기준일·기간은 확인되지 않았으며, 낮거나 높다는 이유만으로 저평가·고평가로 판단하지 않습니다."].filter(Boolean).join("\n"),
    rows: rows2.map((row5) => ({ label: factTitle(text(row5.key)), value: `기업 ${text(row5.value)} / 중앙값 ${text(row5.median)}` })),
    source: "발행 종목 리포트 · 비교 집계",
    asOf: text(peer.as_of) || void 0,
    relationship: "unknown"
  });
  return readySection("valuation", items, "이 조회에는 시각이 확인된 주가·과거 가치평가 비교가 없습니다. 지표별 가격·실적 기준이 다를 수 있어요.");
}
function eventsSection(slice, news, sliceFailed, newsFailed) {
  const report = record(slice.report);
  const disclosures = list(report.disclosures).map((item, index) => ({
    id: `disclosure-${index}`,
    title: text(item.title) || "공시",
    topic: "기업이 알린 변화",
    explanation: text(item.filer) ? `제출인: ${text(item.filer)}` : "발행 종목 리포트의 공시 항목입니다.",
    asOf: text(item.date) || void 0,
    source: "공시 원문",
    url: safeHttpLink(item.source_url),
    relationship: "direct",
    ...item.is_correction ? { reason: "정정공시" } : {}
  }));
  const articles = list(news.items).map((item, index) => {
    const linkedDisclosure = text(record(item.related_disclosure).title);
    return {
      id: `news-${index}`,
      title: text(item.title) || "뉴스",
      topic: "보도된 소식 · 관계 확인 필요",
      explanation: linkedDisclosure ? `연결 공시 후보: ${linkedDisclosure}. 가까운 날짜로 연결된 후보이며 같은 사건으로 확인되지 않았습니다.` : "제목 회사명 일치 기준으로 수집된 기사입니다. 실제 사업 관련성은 원문에서 확인하세요.",
      asOf: text(item.datetime) || void 0,
      source: sourceLabel(item.source, "뉴스 원문"),
      url: safeHttpLink(item.url),
      relationship: "unknown"
    };
  });
  const schedules = list(report.calendar).map((item, index) => ({
    id: `schedule-${index}`,
    title: text(item.event) || "일정",
    topic: "확인할 일정",
    explanation: [text(item.basis) || "발행 종목 리포트에 제공된 일정입니다.", /예상|패턴|자체계산/.test(text(item.event) + text(item.basis)) ? "예상 일정이며 확정 발표일이 아닙니다." : "확정 여부는 원문에서 확인하세요."].join("\n"),
    asOf: text(item.date) || void 0,
    source: "발행 종목 리포트",
    url: safeHttpLink(item.source_url),
    relationship: "unknown"
  }));
  const documentItems = /* @__PURE__ */ new Map(), documents = [];
  for (const item of [...disclosures, ...articles]) {
    const previous = item.url ? documentItems.get(item.url) : void 0;
    const source = { title: item.title, source: item.source, asOf: item.asOf, url: item.url };
    if (previous) {
      previous.sources = [...previous.sources || [{ title: previous.title, source: previous.source, asOf: previous.asOf, url: previous.url }], source];
      if (item.reason) previous.reason = item.reason;
    } else {
      documents.push(item);
      if (item.url) documentItems.set(item.url, item);
    }
  }
  const dateOrder = (item) => (item.asOf || "").replace(/[^0-9]/g, "").slice(0, 12).padEnd(12, "0");
  const items = [...schedules, ...documents.sort((a, b) => dateOrder(b).localeCompare(dateOrder(a)))];
  const problems = [sliceFailed && "공시·일정을 불러오지 못했습니다.", newsFailed && "뉴스를 불러오지 못했습니다. 이 종목의 뉴스 제공 범위도 확인이 필요합니다."].filter(Boolean).join(" ");
  if (!items.length && (sliceFailed || newsFailed)) return errorSection("events", problems);
  return readySection("events", items, problems || "같은 원문 주소만 한 항목으로 묶습니다. 날짜·제목이 비슷한 자료는 같은 사건으로 단정하지 않아요.");
}
function holdersSection(slice, failed, events) {
  if (failed) return errorSection("holders", "종목 정보 요청에 실패했습니다.");
  const report = record(slice.report), ownership = record(report.ownership), dividends = record(report.dividends);
  const shareholders = list(ownership.shareholders).filter((holder) => text(holder.name) && hasValue(holder.pct));
  const keys2 = ["family_pct", "latest_pct", "n_13d", "n_13g", "total", "window_total"].filter((key) => hasValue(ownership[key]));
  const summaryRows = keys2.map((key) => ({ label: key === "family_pct" ? "총수일가 지분" : key === "latest_pct" ? "최신 지분율" : key === "n_13d" ? "13D 건수" : key === "n_13g" ? "13G 건수" : key === "total" ? "공시 건수" : "조회 창 공시 건수", value: key.endsWith("pct") ? `${text(ownership[key])}%` : text(ownership[key]) }));
  const holderRows = shareholders.map((holder) => ({ label: [text(holder.name), text(holder.type)].filter(Boolean).join(" · "), value: `${text(holder.pct)}%` }));
  const items = keys2.length || shareholders.length ? [{
    id: "ownership-summary",
    title: "보유·지분 요약",
    topic: "누가 보유하나",
    explanation: [text(ownership.note), hasValue(ownership.fiscal_year) ? `기준 회계연도: ${text(ownership.fiscal_year)}` : "", text(ownership.collected_at) && `자료 수집일: ${text(ownership.collected_at)} (보유 기준일과 다를 수 있음)`].filter(Boolean).join(" · ") || "발행 종목 리포트에 제공된 보유·지분 정보입니다.",
    source: text(ownership.kind) || "발행 종목 리포트",
    asOf: text(ownership.collected_at) || void 0,
    relationship: "unknown",
    rows: holderRows.length ? holderRows : summaryRows
  }] : [];
  const dividendRows = list(dividends.recent).filter((row5) => hasValue(row5.dps) && text(row5.record_date));
  if (dividendRows.length) items.push({
    id: "dividend-history",
    title: "배당 이력",
    topic: "주주에게 어떻게 돌려주나",
    explanation: [text(dividends.note), "배당기준일과 지급일을 구별합니다. 배당기준일은 배당락일이 아닙니다."].filter(Boolean).join("\n"),
    rows: dividendRows.map((row5) => ({ label: `기준 ${text(row5.record_date)} · 지급 ${text(row5.pay_date) || "미제공"}`, value: `${text(row5.dps)}원/주` })),
    asOf: text(dividends.source_bas_dt) || void 0,
    source: text(dividends.source) || "발행 종목 리포트",
    relationship: "unknown"
  });
  items.push(...factItems(report, "holders"));
  const capital = events.items.filter((item) => item.id.startsWith("disclosure-") && /배당|자기주식|유상증자|무상증자|전환사채|신주인수권|소유상황|대량보유/.test(item.title));
  if (capital.length) items.push({ id: "capital-events", title: "주주·자본 관련 공시", topic: "지분·주식 수의 변화", explanation: "공시 제목으로 분류한 항목입니다. 거래 실행·희석 규모·사업 영향은 원문 확인이 필요합니다.", source: "공시 제목", relationship: "direct", references: capital.map((item) => ({ sectionId: "events", itemId: item.id, label: `${item.title} · ${item.asOf || "날짜 미제공"}` })) });
  return readySection("holders", items, items.length ? void 0 : "보유·배당·자본 관련 자료가 제공되지 않았습니다.");
}
function risksSection(slice, failed, sections) {
  if (failed) return errorSection("risks", "기업 자료 조회에 실패해 확인 질문을 구성하지 못했습니다.");
  const report = record(slice.report), overhang = record(report.overhang);
  const items = factItems(report, "risks");
  const riskRows = [["발행결정 공시 수", overhang.count], ["잠재 희석 비율", hasValue(overhang.dilution_pct) ? `${text(overhang.dilution_pct)}%` : void 0], ["발행 가능 주식 수", overhang.issuable_shares]].filter(([, value]) => hasValue(value)).map(([label2, value]) => ({ label: text(label2), value: text(value) }));
  if (riskRows.length) items.push({ id: "potential-dilution", title: "전환사채·신주인수권부사채", topic: "주식 수가 늘어날 수 있나", explanation: [text(overhang.note), text(overhang.window) && `조회 범위: ${text(overhang.window)}`, "발행결정 기준 잠재치이며 실제 전환·발행된 수량으로 해석하지 않습니다."].filter(Boolean).join("\n"), source: "발행 종목 리포트 · 공시 집계", relationship: "unknown", rows: riskRows, reason: "잠재 희석 확인" });
  const ref = (sectionId, predicate) => (sections.find((section) => section.id === sectionId)?.items || []).filter(predicate).map((item) => ({ sectionId, itemId: item.id, label: item.title }));
  const question = (id, title, explanation, references = []) => items.push({ id, title, explanation, kind: "question", topic: "확인 질문 · 위험 발생 사실 아님", source: "알파네스트 · 자료 확인 질문", relationship: "unknown", references });
  const corrections = ref("events", (item) => item.reason === "정정공시");
  if (corrections.length) question("question-correction", "정정 전후 무엇이 달라졌나요?", "정정 사유·금액·기간을 원문에서 비교하세요. 정정 사실만으로 악재라고 판단하지 않습니다.", corrections);
  const customers = ref("business", (item) => item.id.startsWith("customer-"));
  if (customers.length) question("question-customers", "특정 고객에 매출이 집중돼 있나요?", "거래처 이름만으로 매출 비중을 알 수 없습니다. 고객별 비중·계약 조건을 확인하세요.", customers);
  const financials = ref("finance", (item) => item.id === "annual-income" || /현금|부채|D\/E|FCF/.test(item.title));
  question("question-cash", "이익이 현금으로 이어지고, 부채를 감당할 수 있나요?", "실적·현금흐름·부채 만기 자료를 함께 확인하세요. 자료가 없거나 비율 하나가 낮다는 이유로 위험이 없다고 판단하지 않습니다.", financials);
  const undated = sections.flatMap((section) => section.items.filter((item) => item.value && !item.asOf).map((item) => ({ sectionId: section.id, itemId: item.id, label: item.title })));
  if (undated.length) question("question-basis", "숫자의 기준일·계산 기간이 같나요?", "기준일이 따로 제공되지 않은 지표가 있습니다. 리포트 생성 시각은 가격·재무의 기준일이 아닙니다. 각 계산 설명을 확인하세요.", undated);
  const peer = record(report.peer), classification = [peer.sector, peer.industry, record(report.overview).sector, report.gics, report.gics_ko].map(text).join(" ");
  if (/은행|\bbank(?:s|ing)?\b/i.test(classification)) question("question-industry", "대출 건전성과 자본 여력은 어떤가요?", "은행 업종 확인 질문: 연체율·부실채권·충당금·자본비율을 같은 기간으로 확인하세요. 해당 수치가 이번 지도에 있다고 가정하지 않습니다.");
  else if (/소프트웨어|software/i.test(classification)) question("question-industry", "반복 매출과 고객 유지가 확인되나요?", "소프트웨어 업종 확인 질문: 구독 매출·계약 잔액·고객 유지율의 정의와 기간을 원문에서 확인하세요.");
  else if (/반도체|제조|가전|Semiconductor|Manufactur|Consumer Electronics/i.test(classification)) question("question-industry", "재고·설비투자가 수요와 함께 움직이나요?", "제조업 확인 질문: 재고·가동률·설비투자·수주 기간을 함께 확인하세요. 투자 규모만으로 미래 매출을 추정하지 않습니다.");
  return readySection("risks", items, "확인 질문은 조사 안내이며 위험 발생 사실이 아닙니다. 소송·만기·반대 근거를 빠짐없이 검토한 결과도 아닙니다.");
}
function normalizeInfoMap(ticker, slice, news, usDetail) {
  const requested = text(ticker).toUpperCase(), rawSlice = record(slice), rawNews = record(news);
  const rawReport = record(rawSlice.report);
  const mismatched = (value) => !!text(value) && text(value).toUpperCase() !== requested;
  const sliceFailure = isFailure(slice) ? text(slice.__infoMapError) : text(rawSlice.status) && text(rawSlice.status) !== "ok" ? `응답 상태: ${text(rawSlice.status)}` : mismatched(rawSlice.ticker) || mismatched(rawReport.ticker) ? "응답 티커 불일치" : "";
  const newsFailure = isFailure(news) ? text(news.__infoMapError) : text(rawNews.error) ? text(rawNews.error) : text(rawNews.status) && text(rawNews.status) !== "ok" ? `응답 상태: ${text(rawNews.status)}` : mismatched(rawNews.code) || mismatched(rawNews.ticker) ? "응답 티커 불일치" : "";
  const sliceFailed = !!sliceFailure, newsFailed = !!newsFailure;
  const sliceData = sliceFailed ? {} : rawSlice, newsData = newsFailed ? {} : rawNews, report = record(sliceData.report), extra = record(usDetail);
  const market2 = text(report.market) || text(sliceData.market);
  const marketUpper = market2.toUpperCase();
  const country = /KR|KOSPI|KOSDAQ/.test(marketUpper) ? "kr" : /US|NASDAQ|NYSE|AMEX/.test(marketUpper) ? "us" : void 0;
  const events = eventsSection(sliceData, newsData, sliceFailed, newsFailed);
  const sections = [
    businessSection(sliceData, sliceFailed),
    financeSection(sliceData, sliceFailed),
    valuationSection(sliceData, sliceFailed),
    events,
    holdersSection(sliceData, sliceFailed, events)
  ];
  sections.push(risksSection(sliceData, sliceFailed, sections));
  const missing2 = sections.filter((section) => section.state !== "ready").map((section) => section.title);
  return {
    ticker: requested,
    name: text(report.name) || text(newsData.name) || text(extra.name) || requested,
    market: market2,
    country,
    sections,
    coverage: { ok: sections.length - missing2.length, total: sections.length, missing: missing2 }
  };
}

// framer-components/public-probe/PortfolioMapSources.tsx
var PUBLIC_DATA_BASE = "https://rte5guenhonw9fzn.public.blob.vercel-storage.com";
var record2 = (value) => value && typeof value === "object" && !Array.isArray(value) ? value : {};
var text2 = (value) => typeof value === "string" ? value.trim() : "";
var rows = (value) => Array.isArray(value) ? value.map(record2) : [];
var flag = (value) => typeof value === "boolean" ? value : null;
var label = (value) => typeof value === "string" && !/[\u0000-\u001f\u007f]/.test(value) ? value.trim() || void 0 : void 0;
function sourceUrl(value) {
  if (typeof value !== "string" || /[\u0000-\u0020\u007f]/.test(value)) return void 0;
  try {
    const url = new URL(value);
    return url.protocol === "https:" && !url.username && !url.password ? url.href : void 0;
  } catch {
    return void 0;
  }
}
function observation(value) {
  if (typeof value !== "string" || !/^\d{4}-\d{2}-\d{2}T(?:[01]\d|2[0-3]):[0-5]\d:[0-5]\d(?:\.\d+)?(?:Z|[+-](?:[01]\d|2[0-3]):?[0-5]\d)$/.test(value)) return void 0;
  const date2 = /* @__PURE__ */ new Date(`${value.slice(0, 10)}T00:00:00Z`);
  if (!Number.isFinite(date2.getTime()) || date2.toISOString().slice(0, 10) !== value.slice(0, 10)) return void 0;
  return value;
}
function acceptedPayload(value, ticker, family) {
  const raw = record2(value), report = record2(raw.report);
  const mismatch = (value2) => !!text2(value2) && text2(value2).toUpperCase() !== ticker;
  if (raw.__infoMapError || text2(raw.status) && text2(raw.status) !== "ok" || family === "news" && raw.error || mismatch(raw.ticker) || mismatch(family === "slice" ? report.ticker : raw.code)) return {};
  return raw;
}
function disclosureSource(row5, url) {
  const supplied = text2(row5.source);
  if (supplied) return supplied;
  if (url.hostname === "dart.fss.or.kr") return "DART 전자공시";
  if (url.hostname === "sec.gov" || url.hostname.endsWith(".sec.gov")) return "SEC EDGAR";
  return "공시 원문";
}
function publication(row5) {
  for (const key of ["datetime", "published_at", "time", "as_of", "date"])
    if (label(row5[key])) return label(row5[key]);
  return void 0;
}
function newsRecord(row5, collection) {
  const url = sourceUrl(row5.url) || sourceUrl(row5.link);
  if (!url) return void 0;
  return {
    kind: "news",
    title: text2(row5.title) || "뉴스",
    ...label(row5.title_ko) ? { translatedTitle: label(row5.title_ko) } : {},
    source: text2(row5.source) || "뉴스 원문",
    url,
    publishedAt: publication(row5),
    sourceCollection: collection,
    isCorrection: null,
    isBackfill: null
  };
}
function normalizePortfolioSources(ticker, slice, news) {
  const code = text2(ticker).toUpperCase(), map = normalizeInfoMap(code, slice, news);
  const report = record2(acceptedPayload(slice, code, "slice").report);
  const articles = acceptedPayload(news, code, "news"), newsCandidates = [];
  const eventSources = [];
  for (const row5 of rows(report.disclosures)) {
    const url = sourceUrl(row5.source_url);
    if (!url) continue;
    const parsed = new URL(url), receipts = parsed.searchParams.getAll("rcpNo");
    const dartMain = parsed.hostname === "dart.fss.or.kr" && !parsed.port && parsed.pathname === "/dsaf001/main.do";
    const dartReceipt = dartMain && receipts.length === 1 && /^\d{14}$/.test(receipts[0]) ? receipts[0] : void 0;
    const receipt = typeof row5.rcept_no === "string" && /^\d{14}$/.test(row5.rcept_no) ? row5.rcept_no : void 0;
    const receiptConflict = dartMain && !dartReceipt || row5.rcept_no != null && row5.rcept_no !== "" && (!receipt || receipt !== dartReceipt);
    eventSources.push({
      kind: "disclosure",
      title: text2(row5.title) || "공시",
      source: disclosureSource(row5, parsed),
      url,
      publishedAt: receiptConflict ? void 0 : label(row5.date),
      observedAt: receiptConflict ? void 0 : observation(row5.detected_at),
      ...label(row5.label) ? { label: label(row5.label) } : {},
      ...label(row5.filer) ? { filer: label(row5.filer) } : {},
      sourceCollection: "stock_slice.disclosures",
      receiptNumber: receiptConflict ? void 0 : receipt,
      ...receiptConflict ? { receiptConflict: true } : {},
      isCorrection: receiptConflict ? null : flag(row5.is_correction),
      isBackfill: receiptConflict ? null : flag(row5.is_backfill)
    });
  }
  for (const row5 of rows(articles.items)) {
    const item = newsRecord(row5, "stock_news.items");
    if (item) eventSources.push(item);
  }
  for (const row5 of rows(articles.us_headlines)) {
    const item = newsRecord(row5, "portfolio.us_headlines");
    if (item) newsCandidates.push(item);
  }
  return { ...map, eventSources, ...newsCandidates.length ? { newsCandidates } : {} };
}
async function boundedJson(url, signal) {
  const controller = new AbortController();
  const abort = () => controller.abort(signal?.reason);
  if (signal?.aborted) throw signal.reason || new Error("요청이 취소되었습니다.");
  signal?.addEventListener("abort", abort, { once: true });
  let timedOut = false;
  const timer = setTimeout(() => {
    timedOut = true;
    controller.abort();
  }, 12e3);
  try {
    const response = await fetch(url, { signal: controller.signal });
    if (!response.ok) throw new Error(`HTTP ${response.status}`);
    return await response.json();
  } catch (error) {
    if (signal?.aborted) throw signal.reason || error;
    if (timedOut) throw new Error("정보 요청 시간이 초과되었습니다.");
    throw error;
  } finally {
    clearTimeout(timer);
    signal?.removeEventListener("abort", abort);
  }
}
var usNewsCache;
function publicUsNews(signal) {
  if (signal?.aborted) return Promise.reject(signal.reason || new Error("요청이 취소되었습니다."));
  const now = Date.now();
  if (!usNewsCache || usNewsCache.expiresAt <= now) {
    const request = boundedJson(`${PUBLIC_DATA_BASE}/portfolio.json`).catch((error) => {
      if (usNewsCache?.request === request) usNewsCache = void 0;
      throw error;
    });
    usNewsCache = { expiresAt: now + 3e5, request };
  }
  if (!signal) return usNewsCache.request;
  return new Promise((resolve, reject) => {
    const abort = () => reject(signal.reason || new Error("요청이 취소되었습니다."));
    signal.addEventListener("abort", abort, { once: true });
    usNewsCache.request.then(
      (value) => {
        signal.removeEventListener("abort", abort);
        resolve(value);
      },
      (error) => {
        signal.removeEventListener("abort", abort);
        reject(error);
      }
    );
  });
}
async function fetchPortfolioSources(ticker, apiBase, signal) {
  const code = text2(ticker).toUpperCase(), base = text2(apiBase).replace(/\/+$/, "");
  const isKr = /^\d{6}$/.test(code), overview = isKr ? "&overview=1" : "";
  const newsUrl = isKr ? `${base}/api/stock_news?code=${encodeURIComponent(code)}` : `${PUBLIC_DATA_BASE}/portfolio.json`;
  const results = await Promise.allSettled([
    boundedJson(`${base}/api/stock_slice?ticker=${encodeURIComponent(code)}${overview}`, signal),
    isKr ? boundedJson(newsUrl, signal) : publicUsNews(signal)
  ]);
  if (signal?.aborted) throw signal.reason || new Error("요청이 취소되었습니다.");
  const input = (result) => result.status === "fulfilled" ? result.value : { __infoMapError: text2(result.reason?.message) || "요청 실패" };
  return normalizePortfolioSources(code, input(results[0]), input(results[1]));
}

// framer-components/public-probe/PortfolioCloseQuote.tsx
var record3 = (value) => value && typeof value === "object" && !Array.isArray(value) ? value : null;
var finite = (value) => typeof value === "number" && Number.isFinite(value);
var positive = (value) => finite(value) && value > 0;
var text3 = (value) => typeof value === "string" ? value.trim() : "";
var missing = (reason) => ({ state: "unavailable", reason });
function dateOnly(value) {
  const raw = text3(value), parts = /^(\d{4})-?(\d{2})-?(\d{2})$/.exec(raw);
  if (!parts || !/^(\d{8}|\d{4}-\d{2}-\d{2})$/.test(raw) || Number(parts[1]) < 1900) return null;
  const normalized = `${parts[1]}-${parts[2]}-${parts[3]}`, ms = Date.parse(normalized + "T00:00:00Z");
  return Number.isFinite(ms) && new Date(ms).toISOString().slice(0, 10) === normalized ? normalized : null;
}
function marketKind(value) {
  if (/^(KR|KOSPI|KOSDAQ)$/i.test(value.trim())) return "KR";
  if (/^(US|NASDAQ|NYSE|AMEX)$/i.test(value.trim())) return "US";
  return null;
}
function verificationApproved(input, market2) {
  const approval = record3(input.verification);
  return approval?.publicDisplayApproved === true && approval.market === market2 && approval.session === "closed" && !!text3(approval.reference);
}
function verifiedMarket(input) {
  const approval = record3(input.verification), market2 = approval?.market;
  return (market2 === "KR" || market2 === "US") && verificationApproved(input, market2) ? market2 : null;
}
function verifiedOhlc(payload, ticker, priceDate, price) {
  const row5 = record3(record3(payload.ohlc)?.[ticker]);
  if (!row5) return null;
  const date2 = dateOnly(row5.date), open = row5.open, high = row5.high, low = row5.low, close = row5.close;
  if (date2 !== priceDate || !positive(open) || !positive(high) || !positive(low) || !positive(close) || close !== price || high < Math.max(open, low, close) || low > Math.min(open, high, close)) return null;
  return { date: date2, open, high, low, close };
}
function normalizePortfolioCloseQuote(ticker, market2, input) {
  if (!input) return missing("연결된 종가 자료가 없습니다.");
  const kind = marketKind(market2) || (!market2.trim() ? verifiedMarket(input) : null);
  const symbol = ticker.trim().toUpperCase();
  if (!kind || (kind === "KR" ? !/^\d{6}$/.test(symbol) : !/^[A-Z0-9][A-Z0-9.-]{0,9}$/.test(symbol)))
    return missing("이 시장의 종가 자료는 아직 연결하지 않았습니다.");
  if (kind === "US" && !verificationApproved(input, kind))
    return missing("공개 표시·재배포 이용 권한이 확인된 미국 종가 자료가 필요합니다.");
  if (input.verification && !verificationApproved(input, kind))
    return missing("종가 자료의 시장·장 마감·이용 권한 확인이 일치하지 않습니다.");
  const payload = record3(input.payload);
  if (!payload) return missing("종가 자료 형식을 확인할 수 없습니다.");
  const meta = record3(Object.hasOwn(payload, "_meta") ? payload._meta : payload.meta);
  if (!meta) return missing("종가의 기준 정보를 확인할 수 없습니다.");
  if (Object.hasOwn(payload, "_meta") && Object.hasOwn(payload, "meta")) {
    const legacy = record3(payload.meta);
    if (!legacy || ["as_of", "prev_as_of", "source", "basis"].some((key) => legacy[key] !== meta[key]))
      return missing("종가 자료의 기준 정보가 서로 다릅니다.");
  }
  const priceDate = dateOnly(meta.as_of), source = text3(meta.source), basis = text3(meta.basis);
  const closeBasis = /종가|(?:^|\W)close(?:d)?(?:\W|$)/i.test(basis);
  const explicitlyNotRealtime = /실시간\s*(?:아님|아니|비제공)|not\s+real[ -]?time|non[ -]?real[ -]?time/i.test(basis);
  const realtimeBasis = /장중|intraday|last trade|current price/i.test(basis) || !explicitlyNotRealtime && /실시간|real[ -]?time/i.test(basis);
  if (!priceDate || !source || !closeBasis || realtimeBasis) return missing("종가·기준일·출처를 확인할 수 없습니다.");
  const price = record3(payload.prices)?.[symbol];
  if (!positive(price)) return missing("이 종목의 종가가 제공되지 않았습니다.");
  const expectedDate = dateOnly(input.latestCompletedTradingDate);
  if (expectedDate && priceDate > expectedDate) return missing("종가 기준일이 확인된 마지막 거래일보다 뒤에 있습니다.");
  const priorDate = dateOnly(meta.prev_as_of), prior = record3(payload.prev)?.[symbol];
  const previousDate = priorDate && priorDate < priceDate && positive(prior) ? priorDate : null;
  const previousPrice = previousDate ? prior : null;
  const reported = record3(payload.chg)?.[symbol];
  const calculated = previousPrice === null ? null : Math.round((price - previousPrice) / previousPrice * 1e4) / 100;
  const changePct = finite(reported) ? reported : finite(calculated) ? calculated : null;
  return {
    state: "available",
    price,
    priceDate,
    source,
    basis,
    currency: /^[A-Z]{3}$/.test(input.currency || "") ? input.currency : null,
    previousPrice,
    previousDate,
    changePct,
    changeBasis: finite(reported) ? "reported" : changePct !== null ? "calculated" : null,
    freshness: expectedDate ? priceDate === expectedDate ? "current" : "older" : "unknown",
    expectedDate,
    ohlc: verifiedOhlc(payload, symbol, priceDate, price)
  };
}

// framer-components/public-probe/PortfolioMapData.tsx
var SECTIONS = ["business", "events"];
var DETAIL_SECTIONS = ["finance", "valuation", "holders", "risks"];
var order = (a, b) => a < b ? -1 : a > b ? 1 : 0;
var normalizedTicker = (ticker) => ticker.trim().toUpperCase();
var unique = (values) => [...new Map(values.map((value) => [JSON.stringify(value), value])).entries()].sort(([a], [b]) => order(a, b)).map(([, value]) => value);
async function sha256(value) {
  const digest = await crypto.subtle.digest("SHA-256", new TextEncoder().encode(value));
  return Array.from(new Uint8Array(digest), (byte) => byte.toString(16).padStart(2, "0")).join("");
}
async function portfolioDocumentIdentity(raw) {
  if (!raw || /[\r\n]/.test(raw)) return null;
  let url;
  try {
    url = new URL(raw);
  } catch {
    return null;
  }
  if (url.protocol !== "https:" || url.username || url.password) return null;
  const receipts = url.searchParams.getAll("rcpNo");
  if (url.hostname === "dart.fss.or.kr" && !url.port && url.pathname === "/dsaf001/main.do" && receipts.length === 1 && /^[0-9]{14}$/.test(receipts[0])) {
    return { id: `dart:${receipts[0]}`, url: `https://dart.fss.or.kr/dsaf001/main.do?rcpNo=${receipts[0]}` };
  }
  return { id: `url:${await sha256(url.href)}`, url: url.href };
}
function evidenceFor(ticker, sectionId, item, records) {
  const kind = item.id.startsWith("news-") ? "news" : item.id.startsWith("disclosure-") ? "disclosure" : item.id.startsWith("schedule-") ? "schedule" : sectionId === "business" ? "business" : "other";
  const reason = kind === "news" ? "이 종목의 뉴스 조회에 포함" : kind === "disclosure" ? "이 종목의 공시 자료에 포함" : kind === "business" ? "이 종목의 사업 자료에 포함" : "이 종목의 조회 자료에 포함";
  const sourceRecords = sectionId === "events" ? unique(records.filter((row5) => row5.url === item.url)) : [];
  const conflict = sourceRecords.some((row5) => row5.receiptConflict);
  return {
    ticker,
    sectionId,
    kind,
    title: item.title,
    source: item.source,
    asOf: item.asOf,
    url: item.url,
    explanation: kind === "news" ? reason : item.explanation,
    originalExplanation: item.explanation,
    reason,
    originalReason: item.reason,
    originalRelationship: item.relationship,
    confirmation: !conflict && (kind === "disclosure" || kind === "business") && item.relationship === "direct" ? "confirmed" : "unknown",
    isCorrection: !conflict && (item.reason === "정정공시" || /\[(?:기재|첨부|기타)?정정\]/.test(item.title)) ? true : null,
    sources: unique((item.sources || []).map((source) => ({ title: source.title, source: source.source, asOf: source.asOf, url: source.url }))),
    ...sourceRecords.length ? { sourceRecords } : {}
  };
}
function summarize(evidence) {
  const dates = evidence.flatMap((row5) => [
    row5.asOf,
    ...row5.sources.map((source) => source.asOf),
    ...(row5.sourceRecords || []).map((source) => source.publishedAt)
  ]);
  return {
    source: unique(evidence.flatMap((row5) => [row5.source, ...row5.sources.map((source) => source.source)])).join(" · "),
    // Conflicting or absent dates remain in evidence; do not invent a single representative date.
    asOf: dates.every((date2) => date2 === dates[0]) ? dates[0] : void 0,
    reason: unique(evidence.map((row5) => row5.reason)).join(" · "),
    confirmation: evidence.every((row5) => row5.confirmation === "confirmed") ? "confirmed" : "unknown",
    isCorrection: evidence.some((row5) => row5.isCorrection) ? true : null
  };
}
function companySections(maps) {
  return DETAIL_SECTIONS.flatMap((id) => {
    const sections = unique(maps.flatMap((map) => map.sections.filter((section) => section.id === id)));
    if (!sections.length) return [];
    const state = sections.some((section) => section.state === "error") ? "error" : sections.some((section) => section.state === "unsupported") ? "unsupported" : sections.some((section) => section.state === "ready") ? "ready" : "empty";
    const messages = unique(sections.flatMap((section) => section.message ? [section.message] : []));
    return [{
      id,
      title: sections[0].title,
      state,
      items: unique(sections.flatMap((section) => section.items)),
      ...messages.length ? { message: messages.join("\n") } : {}
    }];
  });
}
async function buildPortfolioMapGraph(maps, closeInput) {
  const byTicker = /* @__PURE__ */ new Map();
  for (const map of maps) {
    const ticker = normalizedTicker(map.ticker);
    if (ticker) byTicker.set(ticker, [...byTicker.get(ticker) || [], map]);
  }
  const companies = [], sources = [];
  const documentsById = /* @__PURE__ */ new Map();
  const identities = /* @__PURE__ */ new Map();
  for (const ticker of [...byTicker.keys()].sort(order)) {
    const rows2 = byTicker.get(ticker);
    const labels2 = unique(rows2.map((row5) => ({ name: row5.name, market: row5.market })));
    companies.push({
      id: `company:${ticker}`,
      ticker,
      ...labels2[0],
      sections: companySections(rows2),
      ...closeInput ? { closeQuote: normalizePortfolioCloseQuote(
        ticker,
        labels2.every((label2) => /^(KR|KOSPI|KOSDAQ)$/i.test(label2.market.trim())) ? labels2[0].market : "",
        closeInput
      ) } : {}
    });
    for (const sectionId of SECTIONS) {
      const sections = rows2.flatMap((row5) => row5.sections.filter((section) => section.id === sectionId));
      const upstreamStates = unique(sections.map((section) => section.state));
      const messages = unique(sections.flatMap((section) => section.message ? [section.message] : []));
      const items = unique(rows2.flatMap((row5) => row5.sections.filter((section) => section.id === sectionId).flatMap((section) => section.items.filter((item) => item.kind !== "question").map((item) => evidenceFor(ticker, sectionId, item, row5.eventSources || [])))));
      let linkedItems = 0;
      for (const evidence of items) {
        const raw = evidence.url || "";
        if (!identities.has(raw)) identities.set(raw, portfolioDocumentIdentity(raw));
        const identity2 = await identities.get(raw);
        if (!identity2) continue;
        linkedItems++;
        const document2 = documentsById.get(identity2.id) || { ...identity2, evidence: [] };
        document2.evidence.push(evidence);
        documentsById.set(identity2.id, document2);
      }
      const problem = upstreamStates.some((state2) => state2 === "error" || state2 === "unsupported") || messages.some((message) => /불러오지 못|실패|제공 범위.*확인/.test(message));
      const state = !sections.length ? "unknown" : problem ? items.length ? "partial" : "unavailable" : !items.length ? "empty" : !linkedItems ? "unknown" : linkedItems < items.length ? "partial" : "available";
      sources.push({
        ticker,
        sectionId,
        state,
        upstreamStates,
        messages,
        receivedItems: items.length,
        linkedItems,
        omittedItems: items.length - linkedItems,
        collectionCompleteness: "unknown"
      });
    }
  }
  const documents = [], links = [];
  for (const document2 of [...documentsById.values()].sort((a, b) => order(a.id, b.id))) {
    const evidence = unique(document2.evidence);
    const tickers = unique(evidence.map((row5) => row5.ticker));
    const content = unique(evidence.map(({ ticker: _ticker, sectionId: _section, reason: _reason, sourceRecords, ...row5 }) => ({
      ...row5,
      // Collection/backfill bookkeeping alone is not a change to source content.
      ...sourceRecords?.length ? { sourceRecords: unique(sourceRecords.map(({ observedAt: _observed, isBackfill: _backfill, ...source }) => source)) } : {}
    })));
    const contentHash = await sha256(JSON.stringify(content));
    const read_revision = Number.parseInt(contentHash.slice(0, 13), 16) + 1;
    documents.push({
      id: document2.id,
      kind: "source-document",
      title: evidence[0].title,
      url: document2.url,
      ...summarize(evidence),
      evidence,
      tickers,
      contentHash,
      read_revision
    });
    for (const ticker of tickers) {
      const associated = evidence.filter((row5) => row5.ticker === ticker);
      links.push({
        id: `link:${ticker}:${document2.id}`,
        companyId: `company:${ticker}`,
        documentId: document2.id,
        ticker,
        ...summarize(associated),
        evidence: associated
      });
    }
  }
  return {
    companies,
    documents,
    links,
    commonItems: documents.filter((document2) => document2.tickers.length >= 2),
    coverage: {
      total: sources.length,
      available: sources.filter((row5) => row5.state === "available").length,
      empty: sources.filter((row5) => row5.state === "empty").length,
      partial: sources.filter((row5) => row5.state === "partial").length,
      unavailable: sources.filter((row5) => row5.state === "unavailable").length,
      unknown: sources.filter((row5) => row5.state === "unknown").length,
      sources
    }
  };
}
async function fetchPortfolioMapGraph(tickers, apiBase, signal) {
  const codes = unique(tickers.map(normalizedTicker).filter(Boolean)), maps = [];
  let next = 0;
  const checkAbort = () => {
    if (signal?.aborted) throw signal.reason || new Error("요청이 취소되었습니다.");
  };
  checkAbort();
  await Promise.all(Array.from({ length: Math.min(4, codes.length) }, async () => {
    while (next < codes.length) {
      checkAbort();
      const ticker = codes[next++];
      try {
        maps.push(await fetchPortfolioSources(ticker, apiBase, signal));
      } catch {
        checkAbort();
        maps.push({
          ticker,
          name: ticker,
          market: "",
          sections: SECTIONS.map((id) => ({
            id,
            title: id,
            state: "error",
            items: [],
            message: "종목 자료를 불러오지 못했습니다."
          })),
          coverage: { ok: 0, total: 2, missing: [...SECTIONS] }
        });
      }
    }
  }));
  checkAbort();
  const graph = await buildPortfolioMapGraph(maps);
  checkAbort();
  return graph;
}

// framer-components/public-probe/MemberMapState.tsx
var ENDPOINT = "https://project-yw131.vercel.app/api/member_map_state";
var ID = /^[A-Za-z0-9][A-Za-z0-9_.:-]{0,127}$/;
var USER_ID = /^[a-f0-9]{8}(?:-[a-f0-9]{4}){3}-[a-f0-9]{12}$/i;
var MAP_KEY = /^[a-z0-9][a-z0-9_-]{0,31}$/;
var MAX_REVISION = Number.MAX_SAFE_INTEGER;
var copy = (value) => JSON.parse(JSON.stringify(value));
var record4 = (value) => !!value && typeof value === "object" && !Array.isArray(value);
var fields = (value, names) => record4(value) && Object.keys(value).length === names.length && names.every((key) => Object.hasOwn(value, key));
var coordinate = (value) => typeof value === "number" && Number.isFinite(value) && Math.abs(value) <= 1e6;
var identifier = (value) => typeof value === "string" && ID.test(value);
var unique2 = (values) => new Set(values).size === values.length;
function validMapDocument(value) {
  if (!fields(value, ["layouts"])) return false;
  const layouts = value.layouts;
  if (!Array.isArray(layouts) || layouts.length > 3 || !unique2(layouts.map((row5) => row5?.map_key))) return false;
  for (const layout of layouts) {
    if (!fields(layout, ["map_key", "positions", "notes", "marks"]) || typeof layout.map_key !== "string" || !MAP_KEY.test(layout.map_key)) return false;
    if (!Array.isArray(layout.positions) || layout.positions.length > 200 || !unique2(layout.positions.map((row5) => row5?.node_id))) return false;
    for (const row5 of layout.positions) {
      if (!fields(row5, ["node_id", "x", "y"]) || !identifier(row5.node_id) || !coordinate(row5.x) || !coordinate(row5.y)) return false;
    }
    if (!Array.isArray(layout.notes) || layout.notes.length > 100 || !unique2(layout.notes.map((row5) => row5?.note_id))) return false;
    for (const note of layout.notes) {
      if (!fields(note, ["note_id", "anchor", "x", "y", "text", "done"]) || !identifier(note.note_id) || !coordinate(note.x) || !coordinate(note.y)) return false;
      if (typeof note.text !== "string" || [...note.text].length > 2e3 || note.text.includes("\0") || typeof note.done !== "boolean") return false;
      if (note.anchor !== null && (!fields(note.anchor, ["kind", "id"]) || !["node", "edge"].includes(note.anchor.kind) || !identifier(note.anchor.id))) return false;
    }
    if (!record4(layout.marks) || Object.keys(layout.marks).length > 200) return false;
    for (const [key, mark] of Object.entries(layout.marks)) {
      if (!identifier(key) || !fields(mark, ["read_revision", "important", "disposition"])) return false;
      if (mark.read_revision !== null && (!Number.isSafeInteger(mark.read_revision) || mark.read_revision < 1 || mark.read_revision >= MAX_REVISION)) return false;
      if (typeof mark.important !== "boolean" || !["inbox", "later", "irrelevant"].includes(mark.disposition)) return false;
    }
  }
  return true;
}
function readMapSession(storage) {
  try {
    const source = storage || (typeof window !== "undefined" ? window.localStorage : null);
    const value = JSON.parse(source?.getItem("verity_supabase_session") || "null");
    return USER_ID.test(value?.user?.id || "") && typeof value?.access_token === "string" && value.access_token.trim() ? { userId: value.user.id, token: value.access_token } : null;
  } catch {
    return null;
  }
}
function stable(value) {
  if (Array.isArray(value)) return "[" + value.map(stable).join(",") + "]";
  if (record4(value)) return "{" + Object.keys(value).sort().map((key) => JSON.stringify(key) + ":" + stable(value[key])).join(",") + "}";
  return JSON.stringify(value);
}
function responseState(value) {
  return record4(value) && Number.isSafeInteger(value.revision) && value.revision >= 0 && value.revision <= MAX_REVISION && validMapDocument(value.document);
}
var emptyState = () => ({ phase: "signed-out", document: null, revision: null, dirty: false, error: null });
function createMemberMapStore(options) {
  const fetcher = options.fetcher || fetch;
  let state = emptyState(), owner = null, generation = 0, editVersion = 0, disposed = false;
  const pending = /* @__PURE__ */ new Set();
  const listeners = /* @__PURE__ */ new Set();
  const session = () => {
    try {
      const value = options.getSession();
      return value && USER_ID.test(value.userId) && value.token ? value : null;
    } catch {
      return null;
    }
  };
  const emit = () => listeners.forEach((listener) => listener(copy(state)));
  const clear = (nextOwner) => {
    generation += 1;
    pending.forEach((controller) => controller.abort());
    pending.clear();
    owner = nextOwner;
    editVersion = 0;
    state = { ...emptyState(), phase: nextOwner ? "loading" : "signed-out" };
    emit();
  };
  const current = (account, version) => {
    if (disposed) return false;
    const nextOwner = session()?.userId || null;
    if (nextOwner !== owner) {
      clear(nextOwner);
      return false;
    }
    return !!account && owner === account.userId && generation === version;
  };
  const request = async (account, body) => {
    const controller = new AbortController();
    pending.add(controller);
    const timer = setTimeout(() => controller.abort(), options.timeoutMs ?? 15e3);
    try {
      const response = await fetcher(ENDPOINT, {
        method: body === void 0 ? "GET" : "POST",
        headers: { Authorization: "Bearer " + account.token, ...body === void 0 ? {} : { "Content-Type": "application/json" } },
        ...body === void 0 ? {} : { body: JSON.stringify(body) },
        signal: controller.signal,
        cache: "no-store",
        credentials: "omit",
        redirect: "error"
      });
      if (!response.ok) throw new Error(response.status === 409 ? "conflict" : response.status === 401 ? "authentication-required" : "storage-unavailable");
      const payload = await response.json();
      if (!responseState(payload)) throw new Error("invalid-response");
      return payload;
    } finally {
      clearTimeout(timer);
      pending.delete(controller);
    }
  };
  const load = async (discardDraft = false) => {
    if (disposed) return false;
    const account = session();
    if ((account?.userId || null) !== owner) clear(account?.userId || null);
    if (!account || state.phase === "saving" || state.dirty && !discardDraft) return false;
    generation += 1;
    pending.forEach((controller) => controller.abort());
    const version = generation;
    state = { ...state, phase: "loading", error: null };
    emit();
    try {
      const result = await request(account);
      if (!current(account, version)) return false;
      state = { phase: "ready", document: copy(result.document), revision: result.revision, dirty: false, error: null };
      editVersion += 1;
      emit();
      return true;
    } catch (error) {
      if (!current(account, version)) return false;
      state = { ...state, phase: "error", error: error instanceof Error ? error.message : "storage-unavailable" };
      emit();
      return false;
    }
  };
  return {
    getState() {
      current(session(), generation);
      return copy(state);
    },
    subscribe(listener) {
      current(session(), generation);
      listeners.add(listener);
      listener(copy(state));
      return () => {
        listeners.delete(listener);
      };
    },
    async syncSession() {
      const nextOwner = session()?.userId || null;
      if (disposed) return false;
      if (nextOwner !== owner) {
        clear(nextOwner);
        return nextOwner ? load() : false;
      }
      if (nextOwner && state.revision === null && state.phase !== "saving") return load();
      return !!nextOwner;
    },
    load,
    update(change) {
      const account = session();
      if (!current(account, generation) || !state.document || state.revision === null || state.phase === "loading") return false;
      const document2 = change(copy(state.document));
      if (!validMapDocument(document2)) throw new Error("invalid-document");
      if (stable(document2) === stable(state.document)) return true;
      state = { ...state, document: copy(document2), dirty: true };
      editVersion += 1;
      emit();
      return true;
    },
    async save() {
      const account = session();
      if (!current(account, generation) || !account || !state.document || state.revision === null || !state.dirty || ["saving", "loading", "conflict"].includes(state.phase)) return false;
      const version = generation, edits = editVersion, expected = state.revision, document2 = copy(state.document);
      state = { ...state, phase: "saving", error: null };
      emit();
      try {
        const result = await request(account, { expected_revision: expected, document: document2 });
        if (!current(account, version)) return false;
        if (result.revision !== expected + 1 || stable(result.document) !== stable(document2)) throw new Error("invalid-save-response");
        state = { ...state, phase: "ready", revision: result.revision, dirty: edits !== editVersion, error: null };
        emit();
        return true;
      } catch (error) {
        if (!current(account, version)) return false;
        const reason = error instanceof Error ? error.message : "storage-unavailable";
        state = { ...state, phase: reason === "conflict" ? "conflict" : "error", dirty: true, error: reason };
        emit();
        return false;
      }
    },
    dispose() {
      disposed = true;
      clear(null);
      listeners.clear();
    }
  };
}
function mapReadState(mark, contentRevision) {
  if (!mark?.read_revision) return "unread";
  return mark.read_revision === contentRevision ? "read" : "changed";
}
function editMapLayout(document2, mapKey, change) {
  const layouts = copy(document2.layouts), index = layouts.findIndex((row5) => row5.map_key === mapKey);
  const initial = index < 0 ? { map_key: mapKey, positions: [], notes: [], marks: {} } : layouts[index];
  const next = change(initial);
  if (next.map_key !== mapKey) throw new Error("map-key-mismatch");
  if (index < 0) layouts.push(next);
  else layouts[index] = next;
  const result = { layouts };
  if (!validMapDocument(result)) throw new Error("invalid-document");
  return result;
}

// framer-components/public-probe/PortfolioWatchlist.ts
var record5 = (value) => !!value && typeof value === "object" && !Array.isArray(value);
var identity = (value) => typeof value === "string" && !!value.trim() && value === value.trim();
function normalizeMapWatchlist(payload, ownerId) {
  if (!identity(ownerId)) throw new Error("invalid-watchlist-owner");
  if (!Array.isArray(payload)) throw new Error("invalid-watchlist-response");
  if (payload.length > 100) throw new Error("watchlist-response-limit");
  const groups = /* @__PURE__ */ new Set(), stocks = /* @__PURE__ */ new Map(), markets = /* @__PURE__ */ new Map();
  let totalItems = 0, unsupportedCount = 0;
  for (const group of payload) {
    if (!record5(group) || !identity(group.id) || !Array.isArray(group.items)) throw new Error("invalid-watchlist-response");
    if (group.user_id !== ownerId) throw new Error("watchlist-owner-mismatch");
    if (groups.has(group.id)) throw new Error("duplicate-watchlist-group");
    groups.add(group.id);
    totalItems += group.items.length;
    if (totalItems > 3e3) throw new Error("watchlist-response-limit");
    for (const item of group.items) {
      if (!record5(item) || typeof item.ticker !== "string" || typeof item.market !== "string" || item.name != null && typeof item.name !== "string") throw new Error("invalid-watchlist-response");
      if (item.group_id !== group.id) throw new Error("watchlist-group-mismatch");
      const ticker = item.ticker.trim().toUpperCase(), market2 = item.market.trim().toUpperCase();
      if (ticker && (market2 === "KR" || market2 === "US")) {
        const prior = markets.get(ticker);
        if (prior && prior !== market2) throw new Error("ambiguous-watchlist-market");
        markets.set(ticker, market2);
      }
      const supported = market2 === "KR" ? /^\d{6}$/.test(ticker) : market2 === "US" && /^[A-Z][A-Z0-9.-]{0,15}$/.test(ticker);
      if (!supported || item.type === "commodity") {
        unsupportedCount++;
        continue;
      }
      const key = `${market2}:${ticker}`;
      if (!stocks.has(key)) stocks.set(key, {
        ticker,
        market: market2,
        name: typeof item.name === "string" && item.name.trim() ? item.name.trim() : ticker
      });
    }
  }
  return { stocks: [...stocks.values()], unsupportedCount };
}
function aborted() {
  const error = new Error("watchlist-aborted");
  error.name = "AbortError";
  return error;
}
function abortable(pending, signal) {
  return new Promise((resolve, reject) => {
    const cancel = () => reject(aborted());
    signal.addEventListener("abort", cancel, { once: true });
    pending.then(
      (value) => {
        signal.removeEventListener("abort", cancel);
        resolve(value);
      },
      (error) => {
        signal.removeEventListener("abort", cancel);
        reject(error);
      }
    );
    if (signal.aborted) {
      signal.removeEventListener("abort", cancel);
      cancel();
    }
  });
}
async function fetchMapWatchlist(options) {
  const { api, getSession, ownerId, signal } = options;
  const current = () => {
    if (signal.aborted) throw aborted();
    if (!identity(ownerId)) throw new Error("invalid-watchlist-owner");
    const session = getSession();
    if (!session || typeof session.token !== "string" || !session.token.trim()) throw new Error("authentication-required");
    if (session.userId !== ownerId) throw new Error("session-changed");
    return session;
  };
  const token = current().token, fetcher = options.fetcher || fetch;
  const request = (requestToken) => fetcher(api.replace(/\/+$/, "") + "/api/watchgroups", {
    method: "GET",
    headers: { Authorization: "Bearer " + requestToken },
    signal,
    cache: "no-store",
    credentials: "omit",
    redirect: "error"
  });
  try {
    let response = await abortable(request(token), signal);
    const refreshedToken = current().token;
    if (response.status === 401 && refreshedToken !== token) {
      response = await abortable(request(refreshedToken), signal);
      current();
    }
    if (!response.ok) throw new Error(response.status === 401 ? "authentication-required" : "watchlist-unavailable");
    const payload = await abortable(response.json(), signal);
    current();
    return normalizeMapWatchlist(payload, ownerId);
  } catch (error) {
    current();
    throw error;
  }
}

// framer-components/public-probe/PortfolioAutomaticEvidence.ts
var invalid = () => new Error("자동 근거 자료의 형식을 확인하지 못했어요.");
var object = (v) => {
  if (!v || typeof v !== "object" || Array.isArray(v)) throw invalid();
  return v;
};
var list2 = (v, max = 1e4) => {
  if (!Array.isArray(v) || v.length > max) throw invalid();
  return v;
};
var text4 = (v, max = 300) => {
  if (typeof v !== "string" || !v.trim() || v.length > max || /[\u0000-\u0008\u000b\u000c\u000e-\u001f\u007f<>]/.test(v)) throw invalid();
  return v;
};
var entity = (v) => {
  const s = text4(v, 64);
  if (!/^(?:KR:\d{6}|US:[A-Z][A-Z0-9]{0,9}(?:[.-][A-Z0-9]{1,2})?)$/.test(s)) throw invalid();
  return s;
};
var exactKeys = (value, expected) => {
  if (Object.keys(value).sort().join("\n") !== [...expected].sort().join("\n")) throw invalid();
};
var isoDate = (value) => {
  const date2 = text4(value, 10);
  if (!/^\d{4}-\d{2}-\d{2}$/.test(date2) || !Number.isFinite(Date.parse(date2)) || new Date(date2).toISOString().slice(0, 10) !== date2) throw invalid();
  return date2;
};
var publicExcerpt = (value) => {
  if (typeof value !== "string" || value.length > 1e4) throw invalid();
  text4(value.replaceAll("->", "→"), 1e4);
  return value;
};
function sourceFor(value) {
  const s = object(value);
  if (s.kind === "local-structured-relation-candidate" && s.url === null && s.as_of === null)
    return { source: "공개 구조화 자료 · 원문 확인 필요", url: null, asOf: null, title: "관계 후보" };
  if (s.kind === "dart-structured-relation") {
    const receipt2 = text4(s.receipt_no, 14), year = text4(s.business_year, 4);
    const settlement = s.settlement_date === null ? null : text4(s.settlement_date, 10);
    if (!/^[0-9]{14}$/.test(receipt2) || !/^[0-9]{4}$/.test(year) || s.report_code !== "11011" || s.as_of !== null || !["hyslrSttus", "otrCprInvstmntSttus"].includes(s.endpoint) || s.url !== `https://dart.fss.or.kr/dsaf001/main.do?rcpNo=${receipt2}` || settlement !== null && (!/^[0-9]{4}-[0-9]{2}-[0-9]{2}$/.test(settlement) || settlement.startsWith("0000-") || !Number.isFinite(Date.parse(settlement)) || new Date(settlement).toISOString().slice(0, 10) !== settlement)) throw invalid();
    return { source: "DART · 결산기준", url: s.url, asOf: settlement, title: "관계 후보" };
  }
  const receipt = text4(s.receipt_no, 14), asOf = text4(s.as_of, 10);
  if (s.kind !== "dart-filing-excerpt" || !/^\d{14}$/.test(receipt) || s.url !== `https://dart.fss.or.kr/dsaf001/main.do?rcpNo=${receipt}` || !/^\d{4}-\d{2}-\d{2}$/.test(asOf) || !Number.isFinite(Date.parse(asOf)) || new Date(asOf).toISOString().slice(0, 10) !== asOf) throw invalid();
  return { source: "DART", url: s.url, asOf, title: text4(s.report_name) };
}
function participants(value) {
  const rows2 = list2(value, 1e3).map((value2) => {
    const p = object(value2);
    return { id: entity(p.id), role: text4(p.role, 80) };
  });
  if (!rows2.length || new Set(rows2.map((p) => p.id)).size !== rows2.length) throw invalid();
  return rows2;
}
function businessNames(value) {
  return value.split(/[,、/·ㆍ]|\s+및\s+|(?<=\))(?:와|과)\s*|(?:와|과)(?=\s)/).map((name) => name.trim()).filter(Boolean);
}
function normalizedLegalName(value) {
  return value.normalize("NFKC").replace(/\(주\d+\)|\(주석\d+\)/g, "").replace(/\s+/g, "").replace(/^(?:주식회사|\(주\))|(?:주식회사|\(주\))$/g, "");
}
var genericBusinessName = /^(?:국내및해외|국내외|국내|해외|글로벌|주요|대형|중소|기타|불특정|다수|일반|각종)*(?:기업|고객사?|거래처|매출처|구매처|유통업체|공급업체|업체|회사)$/;
var businessList = /^당사의\s*(?:주요\s*)?(?<label>매출처|고객사|구매처|공급업체)(?:는|로는)\s*(?<names>.+?)(?:\s*등)?(?:입니다|(?:이|가)\s*있습니다)\.$/;
var businessPurchase = /^당사의\s*(?:주요\s*)?원재료는\s*.+?이며\s*(?<names>.+?)(?:\s*등)?에서\s*(?:안정적으로\s*)?구매하고\s*있습니다\.$/;
var businessCompoundList = /^당사의\s*(?:주요\s*)?(?<label>매출처|고객사|구매처|공급업체)(?:는|로는)\s*(?<names>.+?)(?:\s*등)?\s*(?:이)?며,\s*(?<tail>.+)\.$/;
var businessDelivery = /^당사는\s*(?:(?:(?:국내|해외|국내외)\s*)?(?:주요\s*)?[A-Za-z가-힣]+(?:\s+[A-Za-z가-힣]+)?\s*(?:제조사|업체)인\s*)?(?<names>.+?)(?:\s*등)?에\s*(?<product>[A-Za-z0-9가-힣\s·ㆍ()+/\-]+?)(?:을|를)\s*(?:공급|납품)하고\s*(?:있습니다|있으며,\s*(?<tail>.+))\.$/;
var businessFromSupplier = /^(?:[●•]\s*)?당사는\s*(?:[A-Za-z0-9가-힣\s·ㆍ(),/\-]{1,120}(?:을|를|하여)\s+)?(?<names>[A-Za-z0-9가-힣&()+\-\s、/,·ㆍ]+?)(?:\s*등)?로부터\s*(?:구입(?:\([A-Za-z0-9가-힣\s·ㆍ/\-]{1,40}\))?하고\s*(?:있습니다|있으며,\s*(?<tail>.+))|(?:(?<supply_product>[A-Za-z0-9가-힣\s·ㆍ()+/\-]{1,80}?)(?:을|를)\s*)?공급받아\s*(?<received_tail>.+))\.$/;
var unresolvedBusinessScope = /예정|계획|추진|가능|가정|예시|예를|정의|경쟁|제품명|브랜드|타사|과거|이전|(?<![A-Za-z0-9가-힣])전기(?=$|\s|말|초|대비|기준|회계|분기|에는|의|와|에)|전년|작년|향후|않|아니|아닙|없|중단|종료|해지|취소|철회|중지|미확인|제외|만약|조건|경우|하지만|그러나|반면|실제로|여부|["'“”‘’]/;
var otherBusinessSubject = /종속|연결|그룹|계열/;
var bareDeliveryName = /^[A-Za-z0-9가-힣&()+\-\s]{1,80}$/;
var deliveryNameContext = /(?:에서|으로|하여|위해|통해|하고|하며|을|를)(?:\s|$)|(?:^|\s)(?:현재|경우|것|대한)(?:\s|$)/;
var deliveryProductContext = /공급|납품|구매|매입|받|하여|통해|위해|에서|에게|(?:을|를)(?:\s|$)/;
function businessQuote(role, quote3, rawName) {
  if (quote3 !== quote3.trim() || /[\r\n]/.test(quote3) || /[.!?]/.test(quote3.slice(0, -1)) || genericBusinessName.test(normalizedLegalName(rawName)) || unresolvedBusinessScope.test(quote3)) throw invalid();
  const parsed = businessCompoundList.exec(quote3) || businessDelivery.exec(quote3) || businessList.exec(quote3) || businessPurchase.exec(quote3) || businessFromSupplier.exec(quote3);
  if (!parsed?.groups) throw invalid();
  const { names, label: label2, product, supply_product, received_tail } = parsed.groups, delivery = product !== void 0;
  const tail = received_tail || parsed.groups.tail;
  const assertion = tail ? quote3.slice(0, -(tail.length + 1)) : quote3;
  const entries = businessNames(names), parsedRole = delivery || ["매출처", "고객사"].includes(label2) ? "customer" : "supplier";
  if (otherBusinessSubject.test(assertion) || !entries.length || entries.length > 12 || parsedRole !== role || !entries.includes(rawName)) throw invalid();
  const fromSupplier = /로부터/.test(parsed[0]) && label2 === void 0 && !delivery;
  const item = product || supply_product;
  if ((delivery || fromSupplier) && (entries.some((name) => !bareDeliveryName.test(name) || deliveryNameContext.test(name)) || delivery && !item?.trim() || item && ([...item.trim()].length > 80 || deliveryProductContext.test(item.trim())))) throw invalid();
}
function parseAutomaticEvidence(payload, selected) {
  if (payload === void 0 || payload === null) return { relations: [], materials: [], commonMaterials: [] };
  const body = object(payload);
  if (body.schema !== "portfolio-auto-evidence-v1" || list2(body.verified_events).length) throw invalid();
  const ids = /* @__PURE__ */ new Set();
  const correctionSources = /* @__PURE__ */ new Set(), materialIssuers = /* @__PURE__ */ new Map();
  const relations = list2(body.relationships, 1e3).map((value) => {
    const r = object(value), id = text4(r.stable_id, 100), revision2 = text4(r.revision, 64);
    const reported = r.status === "accepted_reported";
    if (r.verification === "reported-annual-table") {
      exactKeys(r, ["stable_id", "revision", "type", "status", "verification", "snapshot_scope", "label", "participants", "source", "evidence"]);
      if (!/^relation:annual-customer:[a-f0-9]{16}$/.test(id) || !/^[a-f0-9]{64}$/.test(revision2) || ids.has(id) || r.type !== "reported-business-counterparty" || !reported || r.snapshot_scope !== "reported-fiscal-year-not-current" || r.label !== "보고서상 고객사 후보") throw invalid();
      const rawPeople = list2(r.participants, 2);
      rawPeople.forEach((p) => {
        exactKeys(object(p), ["id", "role", "name"]);
        text4(p.name, 160);
      });
      const people2 = participants(rawPeople), issuer = rawPeople.find((p) => p.role === "document_issuer");
      const target = rawPeople.find((p) => p.role === "reported_customer");
      if (people2.length !== 2 || !issuer || !target || !people2.some((p) => selected.has(p.id))) throw invalid();
      const s = object(r.source), e = object(r.evidence);
      exactKeys(s, ["id", "kind", "receipt_no", "as_of", "report_name", "document_issuer", "url", "artifact_observed_at", "revision"]);
      const receipt = text4(s.receipt_no, 14), asOf = isoDate(s.as_of), report = text4(s.report_name, 240);
      const match = report.match(/^(?:\[(?:기재정정|첨부정정|첨부추가)\])*사업보고서 \((\d{4})\.(0[1-9]|1[0-2])\)$/);
      const periodEnd = match ? new Date(Date.UTC(Number(match[1]), Number(match[2]), 0)).toISOString().slice(0, 10) : "";
      if (s.kind !== "dart-annual-report-table" || !/^\d{14}$/.test(receipt) || receipt.slice(0, 8) !== asOf.replaceAll("-", "") || s.id !== `source:dart:${receipt}` || s.document_issuer !== issuer.id || s.artifact_observed_at !== null || s.url !== `https://dart.fss.or.kr/dsaf001/main.do?rcpNo=${receipt}` || !/^[a-f0-9]{64}$/.test(text4(s.revision, 64)) || !match || asOf < periodEnd || asOf > (/* @__PURE__ */ new Date()).toISOString().slice(0, 10)) throw invalid();
      exactKeys(e, ["role", "raw_name", "quote", "owner_quote", "source_field", "field_sha256", "fiscal_year", "report_period_start", "report_period_end", "table_index", "header_row", "row_index", "column_index", "owner_row_index", "owner_rowspan", "customer_origin_row_index", "customer_rowspan", "archive_member", "archive_sha256", "xml_sha256"]);
      const name = text4(e.raw_name, 160), quote3 = text4(e.quote, 1200), owner = text4(e.owner_quote, 160);
      const start = isoDate(e.report_period_start), end = isoDate(e.report_period_end);
      if (e.role !== "customer" || e.source_field !== "annual_customer_table" || e.fiscal_year !== match[1] || start > end || end.slice(0, 7) !== `${match[1]}-${match[2]}` || end > asOf || normalizedLegalName(owner).toLowerCase() !== normalizedLegalName(issuer.name).toLowerCase() || normalizedLegalName(name).toLowerCase() !== normalizedLegalName(target.name).toLowerCase() || genericBusinessName.test(normalizedLegalName(name)) || name !== name.trim() || !businessNames(quote3.replace(/\s*등\s*$/, "")).includes(name) || !/^[a-f0-9]{64}$/.test(text4(e.archive_sha256, 64)) || !/^[a-f0-9]{64}$/.test(text4(e.xml_sha256, 64)) || e.field_sha256 !== e.xml_sha256 || text4(e.archive_member, 160) !== `${receipt}.xml`) throw invalid();
      for (const [key, max] of [["table_index", 1199], ["header_row", 499], ["row_index", 499], ["column_index", 39], ["owner_row_index", 499], ["customer_origin_row_index", 499]])
        if (!Number.isInteger(e[key]) || e[key] < 0 || e[key] > max) throw invalid();
      for (const key of ["owner_rowspan", "customer_rowspan"])
        if (!Number.isInteger(e[key]) || e[key] < 1 || e[key] > 100) throw invalid();
      if (e.row_index <= e.header_row || e.owner_row_index <= e.header_row || e.owner_row_index > e.row_index || e.row_index >= e.owner_row_index + e.owner_rowspan || e.owner_row_index + e.owner_rowspan > 500 || e.customer_origin_row_index < e.owner_row_index || e.customer_origin_row_index > e.row_index || e.row_index >= e.customer_origin_row_index + e.customer_rowspan || e.customer_origin_row_index + e.customer_rowspan > e.owner_row_index + e.owner_rowspan) throw invalid();
      ids.add(id);
      return {
        id: `automatic:${id}`,
        read_revision: Number.parseInt(revision2.slice(0, 13), 16) + 1,
        title: "보고서상 고객사",
        reported: true,
        reportedBasis: "business-period",
        reason: `공시 작성 회사: ${issuer.name}. ${e.fiscal_year} 회계연도 · ${report} · 보고기간 ${start}~${end} · 공개 공시일 ${asOf}. 표에 기재된 고객사: ${name}. 현재 유효 여부·거래 규모·주가 영향은 미확인이에요.
회사: ${owner}
주요고객: ${quote3}
원문 표 ${e.table_index + 1} · 행 ${e.row_index + 1} · 열 ${e.column_index + 1}`,
        participants: people2.map((p) => p.id === issuer.id ? { ...p, name: issuer.name, roleLabel: "고객사 공시 회사" } : { ...p, name: target.name, roleLabel: "공시상 고객사" }),
        source: "DART · 사업보고서 표",
        asOf,
        url: s.url
      };
    }
    if (r.type === "reported-business-counterparty") {
      exactKeys(r, ["stable_id", "revision", "type", "status", "verification", "snapshot_scope", "label", "participants", "source", "evidence"]);
      if (!/^relation:business-role:[a-f0-9]{16}$/.test(id) || !/^[a-f0-9]{64}$/.test(revision2) || ids.has(id) || !reported || r.verification !== "reported-business-excerpt" || r.snapshot_scope !== "reported-fiscal-year-not-current") throw invalid();
      const rawPeople = list2(r.participants, 2);
      if (rawPeople.length !== 2) throw invalid();
      rawPeople.forEach((value2) => {
        const person = object(value2);
        exactKeys(person, person.role === "document_issuer" && Object.hasOwn(person, "name") ? ["id", "role", "name"] : ["id", "role"]);
      });
      const people2 = participants(rawPeople), issuer = people2.find((p) => p.role === "document_issuer");
      const counterparties = people2.filter((p) => p.role === "reported_customer" || p.role === "reported_supplier");
      if (!issuer || counterparties.length !== 1 || people2.filter((p) => p.role === "document_issuer").length !== 1 || !people2.some((p) => selected.has(p.id))) throw invalid();
      const rawIssuer = rawPeople.find((p) => p.role === "document_issuer");
      const issuerName = Object.hasOwn(rawIssuer, "name") ? text4(rawIssuer.name, 320) : void 0;
      if (issuerName !== void 0 && [...issuerName].length > 160) throw invalid();
      const target = counterparties[0], role2 = target.role === "reported_customer" ? "customer" : "supplier";
      const expectedTitle = role2 === "customer" ? "보고서상 매출처" : "보고서상 공급처";
      if (r.label !== expectedTitle) throw invalid();
      const rawSource2 = object(r.source);
      exactKeys(rawSource2, ["id", "kind", "receipt_no", "as_of", "report_name", "url", "document_issuer", "artifact_observed_at", "revision"]);
      const receipt = text4(rawSource2.receipt_no, 14), asOf = isoDate(rawSource2.as_of), report = text4(rawSource2.report_name, 240);
      const reportMatch = report.match(/^(?:\[(?:기재정정|첨부정정|첨부추가)\])*사업보고서 \((\d{4})\.(0[1-9]|1[0-2])\)$/);
      const reportEnd = reportMatch ? `${reportMatch[1]}-${reportMatch[2]}-${String(new Date(Date.UTC(Number(reportMatch[1]), Number(reportMatch[2]), 0)).getUTCDate()).padStart(2, "0")}` : "";
      if (rawSource2.kind !== "dart-filing-excerpt" || !/^\d{14}$/.test(receipt) || rawSource2.document_issuer !== issuer.id || receipt.slice(0, 8) !== asOf.replaceAll("-", "") || asOf > (/* @__PURE__ */ new Date()).toISOString().slice(0, 10) || rawSource2.url !== `https://dart.fss.or.kr/dsaf001/main.do?rcpNo=${receipt}` || !reportMatch || asOf < reportEnd || rawSource2.id !== `source:dart:${receipt}` || rawSource2.artifact_observed_at !== null || !/^[a-f0-9]{64}$/.test(text4(rawSource2.revision, 64))) throw invalid();
      const evidence2 = object(r.evidence);
      exactKeys(evidence2, ["role", "raw_name", "quote", "char_start", "char_end", "source_field", "field_sha256", "fiscal_year", "published_excerpt_truncated"]);
      const evidenceRole = text4(evidence2.role, 8), name = text4(evidence2.raw_name, 320), quote3 = text4(evidence2.quote, 1200);
      const fiscalYear = text4(evidence2.fiscal_year, 4), quoteLength = [...quote3].length;
      if (evidenceRole !== role2 || name !== name.trim() || [...name].length > 160 || quoteLength > 600 || evidence2.source_field !== "business_overview" || !/^[a-f0-9]{64}$/.test(text4(evidence2.field_sha256, 64)) || !/^\d{4}$/.test(fiscalYear) || fiscalYear !== reportMatch[1] || Number(fiscalYear) > Number(asOf.slice(0, 4)) || typeof evidence2.published_excerpt_truncated !== "boolean" || !Number.isInteger(evidence2.char_start) || evidence2.char_start < 0 || !Number.isInteger(evidence2.char_end) || evidence2.char_end > 600 || evidence2.char_end - evidence2.char_start !== quoteLength) throw invalid();
      businessQuote(role2, quote3, name);
      ids.add(id);
      correctionSources.add(`${rawSource2.url}|${issuer.id}`);
      const issuerLabel = role2 === "customer" ? "매출처 공시 회사" : "구매처 공시 회사";
      const targetLabel = role2 === "customer" ? "공시상 매출처" : "공시상 공급처";
      return {
        id: `automatic:${id}`,
        read_revision: Number.parseInt(revision2.slice(0, 13), 16) + 1,
        title: expectedTitle,
        reported: true,
        reportedBasis: "business-period",
        reason: `공시 작성 회사: ${issuerName || issuer.id}. ${fiscalYear} 회계연도 · ${report} · 공개 공시일 ${asOf}. ${targetLabel}: ${name}. 현재 유효 여부·거래 규모·주가 영향은 미확인이에요.
${quote3}`,
        participants: people2.map((p) => p.id === issuer.id ? { ...p, ...issuerName === void 0 ? {} : { name: issuerName }, roleLabel: issuerLabel } : { ...p, name, roleLabel: targetLabel }),
        source: "DART · 사업보고서",
        asOf,
        url: rawSource2.url
      };
    }
    if (r.type === "reported-parent-company") {
      if (!/^relation:filing-parent:[a-f0-9]{8}$/.test(id) || !/^[a-f0-9]{64}$/.test(revision2) || ids.has(id) || !reported || r.verification !== "reported-filing-excerpt" || r.snapshot_scope !== "reported-period-not-current") throw invalid();
      ids.add(id);
      const people2 = participants(r.participants), rawSource2 = object(r.source), source2 = sourceFor(rawSource2), evidence2 = object(r.evidence);
      const quote3 = text4(evidence2.quote, 600), name = text4(evidence2.raw_name, 160), period = text4(evidence2.as_of_phrase, 120);
      if (people2.length !== 2 || !people2.some((p) => selected.has(p.id)) || people2.filter((p) => p.role === "from").length !== 1 || people2.filter((p) => p.role === "to").length !== 1 || rawSource2.kind !== "dart-filing-excerpt" || people2.find((p) => p.role === "to")?.id !== rawSource2.document_issuer || evidence2.role !== "reported-parent" || evidence2.source_field !== "related_party_text" || !quote3.includes(name) || !quote3.includes(period) || !quote3.includes("지배기업") || !Number.isInteger(evidence2.char_start) || evidence2.char_start < 0 || !Number.isInteger(evidence2.char_end) || evidence2.char_end - evidence2.char_start !== [...quote3].length || evidence2.char_end > 3e4 || !/^[a-f0-9]{64}$/.test(text4(evidence2.field_sha256, 64))) throw invalid();
      correctionSources.add(`${source2.url}|${rawSource2.document_issuer}`);
      return {
        id: `automatic:${id}`,
        read_revision: Number.parseInt(revision2.slice(0, 13), 16) + 1,
        title: "보고서상 지배기업",
        reported: true,
        reportedBasis: "filing-period",
        reason: `${period}의 지배기업 표를 확인했어요. 공시일 ${source2.asOf}. 현재 관계·지분율·주가 영향은 미확인이에요.
${quote3}`,
        participants: people2.map((p) => p.role === "from" ? { ...p, name } : p),
        source: source2.source,
        asOf: source2.asOf,
        url: source2.url
      };
    }
    if (!/^relation:group-structure:[a-f0-9]{8}$/.test(id) || !/^[a-f0-9]{64}$/.test(revision2) || ids.has(id) || !reported && r.status !== "accepted_candidate") throw invalid();
    ids.add(id);
    const people = participants(r.participants), source = sourceFor(r.source), evidence = object(r.evidence);
    if (people.length !== 2 || !people.some((p) => selected.has(p.id))) throw invalid();
    const title = r.type === "reported-equity-investment" ? reported ? "공시상 지분 투자" : "지분 투자 후보" : r.type === "reported-major-shareholder-entry" ? reported ? "공시상 주요 주주" : "주요 주주 후보" : null;
    if (!title) throw invalid();
    const rawSource = object(r.source);
    if (rawSource.kind === "dart-structured-relation") {
      const majorHolder = r.type === "reported-major-shareholder-entry";
      const issuer = entity(rawSource.document_issuer);
      if (r.verification !== (reported ? "reported-source-row" : "candidate-source-row-receipt") || rawSource.endpoint !== (majorHolder ? "hyslrSttus" : "otrCprInvstmntSttus") || people.find((p) => p.role === (majorHolder ? "to" : "from"))?.id !== issuer) throw invalid();
    }
    const role = text4(evidence.role, 160), pct = evidence.reported_ownership_pct;
    if (pct !== void 0 && (typeof pct !== "number" || !Number.isFinite(pct) || pct < 0 || pct > 100)) throw invalid();
    const pendingReasons = {
      "missing-source-row": "원문 표의 행을 아직 대조하지 못했어요.",
      "source-row-provenance-mismatch": "원문과 공시 식별 정보가 일치하지 않아 확인이 필요해요.",
      "missing-or-mismatched-settlement-date": "결산기준일을 일치시키지 못했어요.",
      "ambiguous-legal-name": "같은 이름의 법인이 있어 당사자를 확정하지 못했어요.",
      "source-row-identity-mismatch": "원문 회사명과 종목 식별 정보의 대조가 필요해요.",
      "missing-numeric-ownership": "기말 지분율이 비어 있어 보유 관계로 확정하지 않았어요.",
      "nonpositive-or-out-of-range-ownership": "보유 지분율로 사용할 수 없는 값이에요.",
      "ownership-projection-mismatch": "원문 지분율과 표시값이 일치하지 않아요.",
      "missing-or-mismatched-holder-role-or-stock-kind": "주주의 역할 또는 주식종류를 확인하지 못했어요."
    };
    const pendingReason = typeof r.decision_reason === "string" && Object.hasOwn(pendingReasons, r.decision_reason) ? pendingReasons[r.decision_reason] : "";
    let stockKind = "";
    let sourceOwnership;
    let reportedNames;
    const roleLabels = r.type === "reported-major-shareholder-entry" ? { from: "주주", to: "발행회사" } : { from: "출자회사", to: "피출자회사" };
    if (reported) {
      const row5 = object(evidence.source_row), fields3 = object(row5.fields), major = r.type === "reported-major-shareholder-entry";
      const keys2 = ["rcept_no", "corp_code", "corp_name", "stlm_dt", ...major ? ["nm", "relate", "stock_knd", "trmend_posesn_stock_qota_rt"] : ["inv_prm", "trmend_blce_qota_rt"]];
      if (rawSource.kind !== "dart-structured-relation" || !source.asOf || !source.url || r.decision_reason !== "bound-source-row" || r.snapshot_scope !== "reported-at-settlement-not-current" || !/^[a-f0-9]{64}$/.test(text4(r.identity_revision, 64)) || Object.keys(row5).sort().join() !== "fields,index" || !Number.isInteger(row5.index) || row5.index < 0 || Object.keys(fields3).length !== keys2.length || keys2.some((key) => !Object.hasOwn(fields3, key)) || fields3.rcept_no !== rawSource.receipt_no || fields3.corp_code !== rawSource.corp_code || !/^[0-9]{8}$/.test(fields3.corp_code) || fields3.stlm_dt !== source.asOf || people.filter((p) => p.role === "from").length !== 1 || people.filter((p) => p.role === "to").length !== 1) throw invalid();
      keys2.forEach((key) => text4(fields3[key]));
      const rawPct = fields3[major ? "trmend_posesn_stock_qota_rt" : "trmend_blce_qota_rt"].trim();
      const [whole, fraction = ""] = rawPct.replace(/,/g, "").split(".");
      if (!/^(?:[0-9]+|[0-9]{1,3}(?:,[0-9]{3})+)(?:\.[0-9]+)?$/.test(rawPct) || pct === void 0 || pct <= 0 || Number(rawPct.replace(/,/g, "")) <= 0 || Number(whole) > 100 || Number(whole) === 100 && /[1-9]/.test(fraction) || Math.abs(Number(rawPct.replace(/,/g, "")) - pct) > 5000001e-9) throw invalid();
      if (major) {
        stockKind = text4(fields3.stock_knd);
        if (fields3.relate !== role) throw invalid();
      }
      sourceOwnership = Number(rawPct.replace(/,/g, ""));
      reportedNames = major ? { from: text4(fields3.nm), to: text4(fields3.corp_name) } : { from: text4(fields3.corp_name), to: text4(fields3.inv_prm) };
    }
    return {
      id: `automatic:${id}`,
      read_revision: Number.parseInt(revision2.slice(0, 13), 16) + 1,
      title,
      ...reported ? { reported: true } : {},
      reason: `${reportedNames ? `${roleLabels.from} ${reportedNames.from} → ${roleLabels.to} ${reportedNames.to}. ` : ""}${role}${stockKind ? ` · ${stockKind}` : ""}${pct === void 0 ? "" : ` · 보고된 지분 ${pct}%`}. ${rawSource.kind === "dart-structured-relation" ? `결산기준일 ${source.asOf || "미확인"}. ` : ""}${reported ? "해당 결산기준일의 공시 행을 확인했어요. 현재 보유 여부는 미확인이에요." : pendingReason || (source.url ? "원문과 현재 유효 여부를 확인하세요." : "원문과 기준일을 아직 확인하지 못했어요.")} 주가 영향을 뜻하지 않아요.`,
      ...reported ? { measure: {
        kind: "reported-ownership",
        value: sourceOwnership,
        asOf: source.asOf,
        shareClass: stockKind || null,
        from: people.find((p) => p.role === "from").id,
        to: people.find((p) => p.role === "to").id,
        sourceField: r.type === "reported-major-shareholder-entry" ? "trmend_posesn_stock_qota_rt" : "trmend_blce_qota_rt"
      } } : {},
      participants: people.map((p) => reportedNames ? { ...p, name: reportedNames[p.role], roleLabel: roleLabels[p.role] } : p),
      source: source.source,
      asOf: source.asOf,
      url: source.url
    };
  });
  const materials = list2(body.materials).map((value) => {
    const m = object(value), id = text4(m.stable_id, 120), source = sourceFor(m.source), people = participants(m.participants);
    if (!/^event:dart:\d{14}:\d+-\d+:[a-f0-9]{8}$/.test(id) || ids.has(id) || m.kind !== "co_mention_candidate" || m.verified_event !== false || object(m.source).kind !== "dart-filing-excerpt" || !source.url) throw invalid();
    ids.add(id);
    const companyIds = list2(m.portfolio_company_ids, 30).map(entity);
    const expected = people.filter((p) => selected.has(p.id)).map((p) => p.id);
    if (!companyIds.length || new Set(companyIds).size !== companyIds.length || companyIds.length !== expected.length || companyIds.some((id2) => !expected.includes(id2))) throw invalid();
    const e = object(m.evidence), excerpt = publicExcerpt(e.excerpt);
    const sourceIssuer = people.find((p) => p.role === "document_issuer")?.id;
    if (sourceIssuer && object(m.source).document_issuer === sourceIssuer) {
      correctionSources.add(`${source.url}|${sourceIssuer}`);
      materialIssuers.set(id, sourceIssuer);
    }
    return { id, companyIds, item: {
      id: `material-${id}`,
      title: source.title,
      url: source.url,
      source: source.source,
      asOf: source.asOf,
      relationship: "unknown",
      reason: "같은 원문에서 함께 언급",
      explanation: `같은 원문에 언급된 자료예요. 거래 관계나 공통 영향이 확인된 것은 아니에요.
${excerpt}`
    } };
  });
  const byMaterial = new Map(materials.map((m) => [m.id, m]));
  const commonMaterials = list2(body.common_materials === void 0 ? [] : body.common_materials).map((value) => {
    const c = object(value), id = text4(c.stable_id, 150), materialId = text4(c.material_id, 120), revision2 = text4(c.revision, 64);
    const material = byMaterial.get(materialId), companyIds = list2(c.portfolio_company_ids, 30).map(entity);
    if (!material || id !== `common-material:${materialId}` || ids.has(id) || c.kind !== "shared-source-material" || c.verified_event !== false || !/^[a-f0-9]{64}$/.test(revision2) || companyIds.length < 2 || new Set(companyIds).size !== companyIds.length || companyIds.length !== material.companyIds.length || companyIds.some((id2) => !material.companyIds.includes(id2))) throw invalid();
    ids.add(id);
    return { id, materialId, companyIds, url: material.item.url, revision: revision2 };
  });
  const corrections = list2(body.corrections === void 0 ? [] : body.corrections, 1e3).map((value) => {
    const c = object(value), raw = object(c.source), issuer = entity(c.issuer);
    exactKeys(c, ["stable_id", "source", "issuer", "disposition", "reason", "lineage", "revision"]);
    exactKeys(raw, ["id", "kind", "url", "receipt_no", "as_of", "artifact_observed_at", "document_issuer", "report_name", "revision"]);
    const source = sourceFor(raw), receipt = text4(raw.receipt_no, 14), id = text4(c.stable_id, 100);
    if (raw.kind !== "dart-filing-excerpt" || !selected.has(issuer) && !correctionSources.has(`${source.url}|${issuer}`) || raw.document_issuer !== issuer || raw.id !== `source:dart:${receipt}` || id !== `correction:${receipt}` || ids.has(id) || !/정정/.test(source.title) || c.disposition !== "kept-distinct" || c.reason !== "explicit-correction-title-distinct-receipt" || c.lineage !== "not-provided-by-source" || !/^[a-f0-9]{64}$/.test(text4(c.revision, 64)) || !/^[a-f0-9]{64}$/.test(text4(raw.revision, 64)) || raw.artifact_observed_at !== null && (typeof raw.artifact_observed_at !== "string" || !/^\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}(?:\.\d{1,6})?(?:Z|[+-]\d{2}:\d{2})$/.test(raw.artifact_observed_at) || !Number.isFinite(Date.parse(raw.artifact_observed_at)))) throw invalid();
    ids.add(id);
    return { id, companyId: issuer, item: {
      id: `disclosure-${id}`,
      title: source.title,
      url: source.url,
      source: source.source,
      asOf: source.asOf,
      relationship: "unknown",
      reason: "정정공시",
      explanation: "제목에 정정이 표시된 별도 공시예요. 원공시 연결 정보는 이 자료에 없어 기존 공시를 자동 대체하지 않아요. 정정 내용·현재 계약 상태·주가 영향은 원문 확인이 필요해요."
    } };
  });
  for (const correction of corrections) {
    for (const material of materials.filter((m) => m.item.url === correction.item.url && materialIssuers.get(m.id) === correction.companyId)) {
      if (material.item.title !== correction.item.title || material.item.asOf !== correction.item.asOf) throw invalid();
      material.item.reason = "정정공시";
      material.item.explanation += `

${correction.item.explanation}`;
    }
  }
  return { relations, materials, commonMaterials, ...body.corrections === void 0 ? {} : { corrections } };
}

// framer-components/public-probe/PortfolioAnalysisPrices.ts
function parseAnalysisPrices(input, selected) {
  const output = /* @__PURE__ */ new Map();
  if (input === void 0) return output;
  const invalid8 = () => new Error("종가 자료의 형식을 확인하지 못했어요.");
  if (!Array.isArray(input) || input.length !== selected.size) throw invalid8();
  for (const q of input) {
    if (!q || typeof q !== "object" || Array.isArray(q)) throw invalid8();
    const position2 = selected.get(q.id);
    if (!position2 || q.ticker !== position2.ticker || q.market !== position2.market || output.has(q.id)) throw invalid8();
    if (q.status === "restricted") {
      output.set(q.id, { state: "unavailable", reason: "공개 표시 이용 권한이 확인되지 않은 가격 자료예요." });
      continue;
    }
    if (q.status === "missing") {
      output.set(q.id, { state: "unavailable", reason: "이 종목의 종가 자료를 아직 연결하지 못했어요." });
      continue;
    }
    const existingKrDisplay = position2.market === "KR" && q.currency === "KRW" && q.rights?.status === "existing-public-display" && q.source?.id === "fsc-kr-daily-price" && q.source?.file === "kr_close_latest.json" && q.rights.reference === "https://www.data.go.kr/data/15094808/openapi.do";
    if (q.status !== "available" || !(q.rights?.status === "permitted" || existingKrDisplay) || typeof q.source?.name !== "string" || !q.source.name.trim() || q.source.name.length > 200 || /[\u0000-\u001f\u007f<>]/.test(q.source.name) || typeof q.currency !== "string" || !/^[A-Z]{3}$/.test(q.currency)) throw invalid8();
    let reference;
    try {
      reference = new URL(q.rights.reference);
    } catch {
      throw invalid8();
    }
    if (reference.protocol !== "https:" || reference.username || reference.password) throw invalid8();
    const quote3 = normalizePortfolioCloseQuote(position2.ticker, position2.market, {
      payload: {
        _meta: { as_of: q.close_date, prev_as_of: q.prev_as_of, source: q.source.name, basis: "직전 거래일 종가 · 실시간 아님" },
        prices: { [position2.ticker]: q.close },
        ...q.previous_close !== void 0 ? { prev: { [position2.ticker]: q.previous_close } } : {},
        ...q.change_pct !== void 0 ? { chg: { [position2.ticker]: q.change_pct } } : {},
        ...q.ohlc ? { ohlc: { [position2.ticker]: { date: q.close_date, open: q.ohlc.open, high: q.ohlc.high, low: q.ohlc.low, close: q.ohlc.close } } } : {}
      },
      currency: q.currency,
      // KR's original artifact contract needs no invented legal grant.
      ...existingKrDisplay ? {} : { verification: { publicDisplayApproved: true, market: position2.market, session: "closed", reference: reference.href } }
    });
    if (quote3.state !== "available") throw invalid8();
    output.set(q.id, quote3);
  }
  return output;
}

// framer-components/public-probe/PortfolioRelationshipJudgment.ts
var rules = {
  "input-cost": {
    channel: "원재료 매입 비용",
    condition: "해당 원료의 실제 매입가격이 변하고, 사용량·환율·판매가격 전가 등 다른 조건이 같다면",
    rise: "비용 부담 가능",
    fall: "비용 완화 가능"
  },
  "product-sales": {
    channel: "제품 판매 단가",
    condition: "해당 제품의 실제 판매단가가 변하고, 판매량·원가·환율 등 다른 조건이 같다면",
    rise: "매출 증가 가능",
    fall: "매출 감소 가능"
  }
};
function judgeMarketChannels(item, companyId, companyName = "") {
  const scenarios = [];
  const seen = /* @__PURE__ */ new Set();
  for (const ref of item.kind === "commodity" && item.basis === "filing-context" ? item.filing_refs || [] : []) {
    if (ref.company_id !== companyId || !item.company_ids.includes(companyId)) continue;
    for (const channel of ref.channels || []) {
      const rule = rules[channel.kind];
      const quote3 = channel.quote?.trim() || "";
      const ownName = companyName.replace(/[.*+?^${}()|[\]\\]/g, "\\$&");
      const subject = /^(?:당사|우리회사|연결회사|지배기업|종속회사|자회사)(?:는|은|가|의)?\s/.test(quote3) || !!ownName && new RegExp(`^${ownName}(?:은|는|이|가|의)\\s`).test(quote3);
      const tail = quote3.slice(quote3.indexOf(ref.term) + ref.term.length);
      const activity = channel.kind === "input-cost" ? /(?:매입|구매|구입|조달|사용|투입)(?:합니다|하고|하였|했|하며|하여)/.test(tail) : /(?:판매|공급|납품)(?:합니다|하고|하였|했|하며|하여)/.test(tail);
      if (!rule || !subject || !activity || seen.has(channel.kind) || !channel.quote || !ref.excerpt.includes(channel.quote) || !channel.quote.includes(ref.term) || !/[.!。]$/.test(channel.quote.trim()) || /않|아니|없|예정|계획|검토|가정|만약|예시|중단|종료|향후|가능성|전망|예상|추진|조건부|할 수|고객사|고객|경쟁사|타사|업계|수요처|거래처|납품처|전방산업|공급업체|협력사/.test(channel.quote)) continue;
      seen.add(channel.kind);
      scenarios.push({ ...rule, quote: channel.quote, sourceURL: ref.url, asOf: ref.as_of });
    }
  }
  return {
    // Never promote a channel scenario into a current stock-impact verdict.
    impact: "미확인",
    scenarioSummary: scenarios.length > 1 ? "상반된 사업 경로 함께 존재" : scenarios.length ? "조건부 사업 경로" : "판단 근거 부족",
    scenarios,
    limitation: "보고기간의 사업 경로를 이용한 조건부 해석이에요. 시장 지표와 실제 적용 가격이 같다는 뜻은 아니에요. 현재 순노출·헤지·규모는 미확인이며 종목 전체의 실적·주가 예측이 아니에요."
  };
}

// framer-components/public-probe/PortfolioMarketContext.ts
var PUBLIC = "https://rte5guenhonw9fzn.public.blob.vercel-storage.com/";
var FX = /* @__PURE__ */ new Set(["usd_krw", "usd_jpy", "eur_usd"]);
var COMMODITIES = /* @__PURE__ */ new Set([
  "wti_oil",
  "copper",
  "gold",
  "silver",
  "brent",
  "natural_gas",
  "corn",
  "wheat",
  "soybean",
  "coffee",
  "sugar",
  "cotton"
]);
var POWER = { "electricity-input": "power-use", "electricity-supply": "power-supply", "electricity-equipment": "power-equipment" };
var CALENDARS = {
  Fed: ["https://www.federalreserve.gov/monetarypolicy/fomccalendars.htm", "미국"],
  ECB: ["https://www.ecb.europa.eu/press/calendars/mgcgc/html/index.en.html", "유럽"],
  BOJ: ["https://www.boj.or.jp/en/mopo/mpmsche_minu/index.htm", "일본"],
  BOK: ["https://www.bok.or.kr/portal/main/contents.do?menuNo=200755", "한국"],
  ISM: ["https://www.ismworld.org/supply-management-news-and-reports/reports/rob-report-calendar/", "미국"],
  UMich: ["https://data.sca.isr.umich.edu/survey-info.php", "미국"]
};
var CHANNEL_LABELS = {
  "input-cost": "원재료·매입 비용",
  "product-sales": "제품 생산·판매",
  "fx-pricing": "환율에 따른 제품 가격",
  "fx-input-cost": "환율에 따른 매입 비용",
  "fx-revenue": "매출의 환율 효과",
  "risk-management": "위험관리 언급",
  "floating-rate-borrowing": "변동금리 차입 위험",
  "power-use": "전력 구매·사용",
  "power-supply": "발전·전력 공급",
  "power-equipment": "전력설비 생산·공급",
  "port-operation": "항만·터미널 운영"
};
var channelLabels = (ref) => (ref.channels || []).filter((c) => c.kind !== "risk-management").map((c) => CHANNEL_LABELS[c.kind]);
var invalid2 = () => new Error("시장 자료 형식을 확인하지 못했어요.");
var record6 = (v) => {
  if (!v || typeof v !== "object" || Array.isArray(v)) throw invalid2();
  return v;
};
var text5 = (v, max = 700) => {
  if (typeof v !== "string" || !v.trim() || v.length > max || /[<>\u0000-\u001f\u007f]/.test(v)) throw invalid2();
  return v;
};
function stamp(v) {
  if (v === null) return null;
  const value = text5(v, 40);
  if (!/^\d{4}-\d{2}-\d{2}(?:T\d{2}:\d{2}:\d{2}(?:\.\d{1,6})?(?:Z|[+-]\d{2}:\d{2}))?$/.test(value) || !Number.isFinite(Date.parse(value)) || new Date(value.slice(0, 10)).toISOString().slice(0, 10) !== value.slice(0, 10)) throw invalid2();
  return value;
}
function publicURL(value) {
  const raw = text5(value, 2048), url = new URL(raw);
  if (url.protocol !== "https:" || url.username || url.password || url.port || url.hash || !url.hostname.includes(".") || /^(?:localhost|127\.|10\.|192\.168\.|169\.254\.|172\.(?:1[6-9]|2\d|3[01])\.)/.test(url.hostname) || /(?:^|[?&])(?:token|access_token|key|api_key|password|secret|signature|auth)=/i.test(url.search) || /[\u0000-\u0020\u007f<>]/.test(decodeURIComponent(raw))) throw invalid2();
  return url.href;
}
var numeric = (v) => {
  if (v === null) return null;
  if (typeof v !== "number" || !Number.isFinite(v) || Math.abs(v) > 1e20) throw invalid2();
  return v;
};
var digestHex = async (value) => [...new Uint8Array(await crypto.subtle.digest("SHA-256", new TextEncoder().encode(value)))].map((b) => b.toString(16).padStart(2, "0")).join("");
function reportKey(report) {
  const suffix = " - " + report.source;
  const title = new URL(report.url).hostname === "news.google.com" && report.title.endsWith(suffix) ? report.title.slice(0, -suffix.length) : report.title;
  const normalize = (s) => s.normalize("NFKC").toLowerCase().replace(/[\s\u0085]+/gu, " ").trim();
  return [normalize(report.source), normalize(title), new Date(report.as_of).toISOString().slice(0, 10)].join("\n");
}
function powerQuoteBound(quote3, term, names) {
  if (!/[.!。]$/.test(quote3) || /(?:고객사|고객|경쟁사|타사|업계|수요처|거래처|납품처|전방산업|공급업체|협력사)(?:는|은|가|이|의|\s)/.test(quote3)) return false;
  const followedByTerm = (subject) => [...quote3.matchAll(subject)].some((match) => quote3.indexOf(term, match.index + match[0].length) >= 0);
  if (followedByTerm(/당사|우리회사|연결회사|지배기업|종속회사|자회사|회사의/g)) return true;
  return names.some((name) => followedByTerm(new RegExp(`(?<![가-힣A-Za-z0-9])${name.replace(/[.*+?^${}()|[\]\\]/g, "\\$&")}(?:은|는|이|가|의)(?=\\s|$)`, "g")));
}
function portQuoteBound(quote3, term, names) {
  return /^(?:항만\s*터미널|컨테이너\s*터미널|항만|부두)$/.test(term) && quote3.includes(term) && powerQuoteBound(quote3, term, names) && /(?:항만\s*터미널|컨테이너\s*터미널|항만|부두)(?:을|를)\s*운영(?:합니다|하고\s*있(?:습니다|으며)|하였습니다|했습니다|하며|하는\s*(?:항만하역\s*)?사업(?:을\s*영위|과))/.test(quote3) && !/않|아니|없|중단|제외|종료|폐지|전망|예상|예정|계획|가정|검토|추진|가능성|조건부|조건.{0,24}(?:면|경우)|(?<![가-힣])[가-힣]+(?:으면|되면|하면|라면|다면|이면)(?=\s|[,.;])|(?:할|될)\s*수\s*있|과거|전년도|만약|예를\s*들어|예시|예문|인용|문구|["'“”‘’]/.test(quote3);
}
async function parseMarketContext(value, wanted, companyNames = /* @__PURE__ */ new Map()) {
  if (value === void 0) return [];
  const body = record6(value);
  if (body.schema !== "alphaconsole-market-context-v1" || !Array.isArray(body.items) || body.items.length > FX.size + COMMODITIES.size + 26 + Object.keys(POWER).length + 12 + 1 + 1) throw invalid2();
  if (body.items.filter((row5) => row5?.kind === "news").length > 25 || body.items.filter((row5) => row5?.kind === "release-calendar").length > 12) throw invalid2();
  const seen = /* @__PURE__ */ new Set();
  return Promise.all(body.items.map(async (raw) => {
    const row5 = record6(raw), id = text5(row5.id, 128), kind = row5.kind;
    if (seen.has(id)) throw invalid2();
    seen.add(id);
    const prefix = `market:${kind}:`, key = id.slice(prefix.length);
    if (!id.startsWith(prefix) || !(kind === "fx" ? FX.has(key) : kind === "commodity" ? COMMODITIES.has(key) : kind === "interest-risk" ? key === "floating-borrowing" : kind === "power-context" ? Object.hasOwn(POWER, key) : kind === "infrastructure-context" ? key === "port-operation" : kind === "policy-rate" ? key === "korea-base" : (kind === "news" || kind === "release-calendar") && /^[a-f0-9]{64}$/.test(key))) throw invalid2();
    const operatingGroup = kind === "power-context" || kind === "infrastructure-context";
    const filingGroup = kind === "interest-risk" || operatingGroup;
    const calendar = kind === "release-calendar";
    const policy = kind === "policy-rate";
    const ids = row5.company_ids;
    if (!Array.isArray(ids) || ids.length > 30 || new Set(ids).size !== ids.length || ids.some((v) => typeof v !== "string" || !wanted.has(v))) throw invalid2();
    if (!(row5.basis === "market-context" ? !ids.length : row5.basis === "industry-membership" ? kind === "commodity" && ids.length > 0 : row5.basis === "filing-context" ? kind !== "news" && ids.length > 0 : row5.basis === "name-mention" && kind === "news" && ids.length > 0)) throw invalid2();
    const url = publicURL(row5.url);
    if (filingGroup ? url !== "https://dart.fss.or.kr/" : policy ? url !== "https://ecos.bok.or.kr/" : kind !== "news" && !calendar && url !== PUBLIC + "macro_snapshot.json") throw invalid2();
    const item = {
      id,
      kind,
      title: text5(row5.title, 300),
      summary: text5(row5.summary),
      source: text5(row5.source, 100),
      url,
      as_of: stamp(row5.as_of),
      observed_at: stamp(row5.observed_at),
      value: numeric(row5.value),
      change_pct: numeric(row5.change_pct),
      unit: row5.unit === null ? null : text5(row5.unit, 40),
      company_ids: ids.slice(),
      basis: row5.basis,
      reason: text5(row5.reason)
    };
    if ((kind === "news" || filingGroup || calendar) && (item.value !== null || item.change_pct !== null || item.unit !== null)) throw invalid2();
    if (filingGroup && (item.as_of !== null || item.observed_at !== null || item.basis !== "filing-context")) throw invalid2();
    if (operatingGroup && item.source !== "DART · 보고기간별 공시") throw invalid2();
    const extra = {};
    if (policy) {
      const observation3 = record6(row5.observation), period = text5(observation3.period, 7);
      if (!/^[0-9]{4}-(?:0[1-9]|1[0-2])$/.test(period) || period.startsWith("0000") || observation3.stat_code !== "722Y001" || observation3.item_code !== "0101000" || observation3.frequency !== "M" || observation3.series_id !== "ECOS/722Y001/0101000" || !["preserved-source", "collector-contract"].includes(observation3.identity_basis) || item.as_of !== null || !item.observed_at || item.observed_at.length === 10 || Date.parse(item.observed_at) > Date.now() + 3e5 || period > new Date(Date.parse(item.observed_at) + 9 * 36e5).toISOString().slice(0, 7) || item.value === null || item.change_pct !== null || item.unit !== "연%" || item.basis !== "market-context" || ids.length || row5.verified_common_event !== false || item.source !== "한국은행 ECOS · 공개 스냅샷" || item.title !== "한국은행 기준금리" || row5.reports !== void 0 || row5.grouping !== void 0 || row5.filing_refs !== void 0) throw invalid2();
      Object.assign(extra, { observation: {
        period,
        stat_code: "722Y001",
        item_code: "0101000",
        frequency: "M",
        series_id: "ECOS/722Y001/0101000",
        identity_basis: observation3.identity_basis
      }, verified_common_event: false });
    } else if (row5.observation !== void 0) throw invalid2();
    if (calendar) {
      const schedule = record6(row5.schedule), country = text5(schedule.country, 40);
      const source_kind = schedule.source_kind, release_id = schedule.release_id;
      if (item.basis !== "market-context" || ids.length || !item.as_of || item.as_of.length !== 10 || !item.observed_at || Date.parse(item.observed_at) > Date.now() + 3e5 || row5.verified_common_event !== false || row5.reports !== void 0 || row5.grouping !== void 0) throw invalid2();
      if (source_kind === "release") {
        if (item.source !== "FRED" || country !== "미국" || !Number.isSafeInteger(release_id) || release_id <= 0 || release_id > 1e6 || url !== `https://fred.stlouisfed.org/release?rid=${release_id}`) throw invalid2();
      } else if (source_kind === "schedule") {
        const known = Object.hasOwn(CALENDARS, item.source) ? CALENDARS[item.source] : null;
        if (!known || url !== known[0] || country !== known[1] || release_id !== null) throw invalid2();
      } else throw invalid2();
      const identity2 = JSON.stringify([item.source, source_kind, url, item.title, item.as_of, country, release_id]);
      if (key !== await digestHex(identity2)) throw invalid2();
      Object.assign(extra, { schedule: { country, source_kind, release_id }, verified_common_event: false });
    } else if (row5.schedule !== void 0) throw invalid2();
    if (filingGroup) {
      const revision2 = text5(row5.evidence_revision, 64);
      if (!/^[a-f0-9]{64}$/.test(revision2)) throw invalid2();
      extra.evidence_revision = revision2;
    }
    if (row5.filing_refs !== void 0 || row5.industry_company_ids !== void 0 || row5.basis === "filing-context") {
      if (row5.basis !== "filing-context" || !Array.isArray(row5.filing_refs) || !row5.filing_refs.length || row5.filing_refs.length > 30 || !Array.isArray(row5.industry_company_ids) || kind !== "commodity" && row5.industry_company_ids.length) throw invalid2();
      const industry = row5.industry_company_ids;
      if (industry.length > 30 || new Set(industry).size !== industry.length || industry.some((v) => !ids.includes(v))) throw invalid2();
      const refs = row5.filing_refs.map((raw2) => {
        const ref = record6(raw2), company_id = text5(ref.company_id, 32), term = text5(ref.term, 50), excerpt = text5(ref.excerpt, 600);
        const url2 = publicURL(ref.url), as_of = stamp(ref.as_of), year = text5(ref.fiscal_year, 4);
        if (!/^KR:\d{6}$/.test(company_id) || !ids.includes(company_id) || !excerpt.includes(term) || !/^https:\/\/dart\.fss\.or\.kr\/dsaf001\/main\.do\?rcpNo=\d{14}$/.test(url2) || !as_of || as_of.length !== 10 || !/^\d{4}$/.test(year) || typeof ref.truncated !== "boolean") throw invalid2();
        let channels;
        if (ref.channels !== void 0) {
          if (!Array.isArray(ref.channels) || !ref.channels.length || ref.channels.length > 4) throw invalid2();
          channels = ref.channels.map((raw3) => {
            const channel = record6(raw3), key2 = channel.kind, quote3 = text5(channel.quote, 600);
            if (!(kind === "interest-risk" ? key2 === "floating-rate-borrowing" : kind === "power-context" ? key2 === POWER[id.slice(prefix.length)] : kind === "infrastructure-context" ? key2 === "port-operation" : key2 === "risk-management" || (kind === "fx" ? ["fx-pricing", "fx-input-cost", "fx-revenue"].includes(key2) : key2 === "input-cost" || key2 === "product-sales")) || !excerpt.includes(quote3)) throw invalid2();
            return { kind: key2, quote: quote3 };
          });
          if (new Set(channels.map((c) => c.kind)).size !== channels.length || !channels.some((c) => c.kind !== "risk-management")) throw invalid2();
        }
        if (kind === "interest-risk" && (!channels || channels.length !== 1 || channels[0].kind !== "floating-rate-borrowing")) throw invalid2();
        const source = text5(ref.source, 240);
        if (operatingGroup && (!channels || channels.length !== 1 || !(kind === "infrastructure-context" ? portQuoteBound : powerQuoteBound)(channels[0].quote, term, companyNames.get(company_id) || []) || kind === "power-context" && new URL(url2).searchParams.get("rcpNo").slice(0, 8) !== as_of.replaceAll("-", "") || as_of > (/* @__PURE__ */ new Date()).toISOString().slice(0, 10) || !new RegExp(`^(?:\\[(?:기재정정|첨부정정|정정)\\]\\s*)?사업보고서\\s*\\(${year}\\.(?:0[1-9]|1[0-2])\\)$`).test(source))) throw invalid2();
        return {
          company_id,
          term,
          excerpt,
          url: url2,
          as_of,
          fiscal_year: year,
          truncated: ref.truncated,
          source,
          ...channels ? { channels } : {}
        };
      }).sort((a, b) => a.company_id.localeCompare(b.company_id));
      if (new Set(refs.map((r) => r.company_id)).size !== refs.length || ids.some((id2) => !industry.includes(id2) && !refs.some((r) => r.company_id === id2))) throw invalid2();
      Object.assign(extra, { filing_refs: refs, industry_company_ids: industry.slice().sort() });
    }
    if (!calendar && !policy && (row5.reports !== void 0 || row5.grouping !== void 0 || row5.verified_common_event !== void 0)) {
      if (kind !== "news" || row5.grouping !== "same-publisher-headline-day" || row5.verified_common_event !== false || !Array.isArray(row5.reports) || row5.reports.length < 1 || row5.reports.length > 8) throw invalid2();
      const reports = row5.reports.map((raw2) => {
        const report = record6(raw2), as_of = stamp(report.as_of);
        if (!as_of || as_of.length === 10) throw invalid2();
        return { title: text5(report.title, 300), source: text5(report.source, 100), url: publicURL(report.url), as_of };
      }).sort((a, b) => a.url < b.url ? -1 : a.url > b.url ? 1 : 0);
      if (new Set(reports.map((r) => r.url)).size !== reports.length || new Set(reports.map(reportKey)).size !== 1 || !reports.some((r) => r.url === item.url && r.title === item.title && r.source === item.source && r.as_of === item.as_of)) throw invalid2();
      if (id !== "market:news:" + await digestHex("same-publisher-headline-day\n" + reportKey(reports[0]))) throw invalid2();
      Object.assign(extra, {
        reports,
        grouping: row5.grouping,
        verified_common_event: false,
        legacyIds: await Promise.all(reports.map(async (r) => "market:news:" + await digestHex(r.url)))
      });
    }
    const { observed_at: _observed, company_ids: _ids, basis: _basis, reason: _reason, ...content } = item;
    const { legacyIds: _legacy, filing_refs: _filings, industry_company_ids: _industry, observation: observation2, ...reportContent } = extra;
    if (observation2) {
      const { identity_basis: _identity, ...seriesContent } = observation2;
      Object.assign(reportContent, { observation: seriesContent });
    }
    const hash = await digestHex(JSON.stringify({ ...content, ...reportContent }));
    return { ...item, ...extra, read_revision: Number.parseInt(hash.slice(0, 13), 16) + 1 };
  }));
}
function projectMarketPrototype(graph) {
  const items = graph?.marketContext || [];
  const companies = new Map(graph?.companies.map((c) => [`${c.market}:${c.ticker}`, c]));
  const filingEvidence = (item, ref) => ({
    url: ref.url,
    source: `${companies.get(ref.company_id)?.name || ref.company_id} · ${ref.source}`,
    asOf: ref.as_of,
    explanation: [
      `${ref.fiscal_year} 회계연도 · 공시일 ${ref.as_of} · ${item.kind === "interest-risk" ? "위험관리" : "사업의 개요"}${ref.truncated ? " · 공개 발췌(일부)" : " · 공개 발췌"}`,
      ref.excerpt,
      ...ref.channels ? [
        `공시상 ${item.kind === "interest-risk" ? "금융위험" : "사업 경로"}: ${channelLabels(ref).join(" · ")}. 규모와 현재 영향은 미확인이에요.`,
        ...ref.channels.some((c) => c.kind === "fx-revenue") ? ["보고기간 매출에 대한 설명이에요. 환율만의 기여분이나 현재 매출·주가 전망을 뜻하지 않아요."] : [],
        ...ref.channels.some((c) => c.kind === "risk-management") ? ["원문에 위험관리도 언급돼 있어요. 위험이 전부 상쇄된다는 뜻은 아니에요."] : []
      ] : [],
      item.kind === "interest-risk" ? "보고 당시의 변동금리 차입 위험이에요. 특정 기준금리·통화·현재 잔액·순이자비용·주가 영향은 확인되지 않았어요." : item.kind === "power-context" ? "보고 당시 원문에 명시된 전력 관련 사업 경로예요. 기업 간 거래 관계나 같은 사건의 증거는 아니며, 전력요금·사용 및 매출 비중·현재 상태·주가 영향은 미확인이에요." : item.kind === "infrastructure-context" ? "보고 당시 원문에 명시된 항만·터미널 운영이에요. 같은 사건·기업 간 거래 관계나 현재 정책 수혜를 뜻하지 않아요. 현재 운영권·사업 규모·주가 영향은 미확인이에요." : item.kind === "fx" ? "환율 관련 표현을 참고 연결했어요. 이 통화쌍의 실제 노출과 현재 영향은 미확인이에요." : item.id.endsWith(":wti_oil") ? "원유 관련 표현을 WTI 참고 지표와 연결했어요. 실제 유종·계약 기준가격·현재 영향은 미확인이에요." : item.kind === "commodity" ? "원문에 관련 원재료·제품이 언급돼 있어요. 품종·가공 단계·지역·실제 계약가격은 이 시장 지표와 다를 수 있어요. 사용·판매 비중과 현재 영향 방향은 미확인이에요." : "보고서에 관련 소재가 언급돼 있어요. 사용·판매 비중과 현재 영향 방향은 미확인이에요."
    ].join("\n")
  });
  const nodes = items.map((item, index) => {
    const value = item.value === null ? "" : `${item.value.toLocaleString("ko-KR", { maximumFractionDigits: 8 })} ${item.unit || "단위 미제공"}`;
    const change = item.change_pct === null ? "" : `${item.change_pct > 0 ? "+" : ""}${item.change_pct.toFixed(2)}%`;
    const bundled = (item.reports?.length || 0) > 1;
    const filingGroup = item.kind === "interest-risk" || item.kind === "power-context" || item.kind === "infrastructure-context";
    const calendar = item.kind === "release-calendar";
    const policy = item.kind === "policy-rate";
    const qualifier = calendar ? "발표 일정 · 결과 미확인" : policy ? "월 단위 지표 · 정책 결정 아님" : filingGroup ? "보고기간별 공시 묶음 · 같은 사건 아님" : bundled ? `동일 제목 보도 묶음 · ${item.reports.length}개 원문 · 사건 확정 아님` : item.basis === "filing-context" ? "사업보고서 참고 연결 · 영향 미확인" : item.basis === "industry-membership" ? "산업 분류 후보 · 영향 미확인" : item.basis === "name-mention" ? "기사에 종목명 언급 · 영향 미확인" : "시장 참고 · 개별 연결 미확인";
    const dates = calendar ? `예정일 ${item.as_of} · ${item.schedule.country} · 일정 수집 ${item.observed_at}` : policy ? `자료 기준월 ${item.observation.period} · 수집 ${item.observed_at}` : filingGroup ? "각 공시의 보고기간·공시일은 아래 원문 근거에서 확인할 수 있어요." : `${item.as_of ? "자료 기준 " + item.as_of : "자료 기준일 미제공"}${item.observed_at ? " · 수집 " + item.observed_at : ""}`;
    const series = policy ? `시계열 ${item.observation.series_id} · 주기 M · ${item.observation.identity_basis === "preserved-source" ? "식별자 보존" : "수집기 설정 참고 · 보존 식별자 일부 미제공"}` : "";
    const explanation = [item.summary, item.reason, bundled ? "같은 매체·같은 제목·같은 UTC 발행일로 묶었어요. 독립된 여러 매체의 확인이나 동일 사건의 확정을 뜻하지 않아요." : "", dates, series].filter(Boolean).join("\n");
    const evidence = item.reports ? item.reports.map((report) => ({
      url: report.url,
      source: report.source,
      asOf: report.as_of,
      explanation: [report.title, report.source, "게시 " + report.as_of].join(" · ")
    })) : [{ url: item.url, source: item.source, asOf: calendar ? null : item.as_of, explanation }];
    if (item.basis === "industry-membership" || item.industry_company_ids?.length) evidence.push({
      url: PUBLIC + "commodity_exposure.json",
      source: "산업 분류 연결 자료",
      asOf: null,
      explanation: "공개 산업 분류에 포함된 종목만 연결했어요. 실제 원가·매출 비중과 영향 방향은 확인되지 않았어요."
    });
    evidence.push(...(item.filing_refs || []).map((ref) => filingEvidence(item, ref)));
    return {
      id: item.id,
      kind: "event",
      recordKind: "market-context",
      layer: calendar ? "calendar" : filingGroup ? "filing" : policy ? "government" : item.kind,
      topic: item.kind === "commodity" ? "commodity" : item.kind === "fx" || filingGroup || calendar || policy ? "macro" : "general",
      name: item.title,
      code: calendar ? `예정 ${item.as_of} · ${item.schedule.country}` : [value, change].filter(Boolean).join(" · ") || qualifier,
      logo: "",
      priority: 1,
      proofLabel: qualifier,
      reason: explanation,
      source: item.source,
      asOf: calendar ? null : item.as_of,
      evidence,
      ...item.legacyIds ? { legacyIds: item.legacyIds } : {},
      read_revision: item.read_revision,
      x: 1.05 + index % 3 * 0.2,
      y: 0.6 + Math.floor(index / 3) * 0.18
    };
  });
  const edges = items.flatMap((item) => item.company_ids.flatMap((id) => {
    const company = companies.get(id), node = nodes.find((n) => n.id === item.id);
    const ref = item.filing_refs?.find((ref2) => ref2.company_id === id);
    const channels = ref ? channelLabels(ref) : [];
    const proof = ref ? filingEvidence(item, ref) : null;
    const assessment = judgeMarketChannels(item, id, company?.name);
    const reason = proof ? proof.explanation : item.basis === "filing-context" ? "산업 분류 후보이며 매출 노출이나 영향은 미확인이에요." : item.reason;
    return company ? [{
      id: `market-link:${item.id}:${id}`,
      from: item.id,
      to: company.id,
      type: "unknown",
      strength: 0,
      assessment,
      impact: assessment.impact,
      impactReason: channels.length ? `공시상 ${channels.join(" · ")} · 현재 영향 미확인` : ref ? `사업보고서에 ‘${ref.term}’ 언급 · 현재 영향 미확인` : reason,
      reason,
      verb: channels.length ? channels.join(" · ") : ref ? "공시에서 관련 표현" : item.kind === "commodity" ? "산업 분류 후보" : "기사에 이름 언급",
      source: proof?.source || item.source,
      asOf: proof?.asOf || item.as_of,
      evidence: proof ? [node.evidence[0], proof] : node.evidence.filter((e) => !(item.filing_refs || []).some((r) => r.url === e.url))
    }] : [];
  }));
  const recordsMap = Object.fromEntries(nodes.map((n) => [n.id, { id: n.id, read_revision: n.read_revision, sourceURLs: n.evidence.map((e) => e.url), ...n.legacyIds ? { legacyIds: n.legacyIds } : {} }]));
  return { nodes, edges, recordsMap };
}

// framer-components/public-probe/PortfolioEventLineage.ts
var DART = "https://dart.fss.or.kr/dsaf001/main.do?rcpNo=";
var invalid3 = () => new Error("공시 변경 이력을 확인하지 못했어요.");
var text6 = (v, pattern) => {
  if (typeof v !== "string" || !pattern.test(v)) throw invalid3();
  return v;
};
var titleKey = (v) => v.normalize("NFKC").replace(/\[(?:기재|첨부|기타)?정정\]/g, "").replace(/[ㆍ·ᆞ]/g, "·").trim();
function parseDocumentLineage(value, doc) {
  if (value === void 0) return null;
  if (!value || typeof value !== "object" || Array.isArray(value)) throw invalid3();
  const row5 = value;
  const issuer = text6(row5.issuer_id, /^KR:[0-9]{6}$/), root = text6(row5.root_receipt, /^[0-9]{14}$/);
  const current = text6(row5.current_receipt, /^[0-9]{14}$/);
  const id = text6(row5.id, /^dart-family:[0-9]{8}:[0-9]{14}$/);
  if (row5.kind !== "official-dart-document-family" || row5.verified_common_event !== false || row5.current_economic_status !== "unverified" || !id.endsWith(":" + root) || doc.id !== "DART:" + current || doc.source !== "DART" || doc.url !== DART + current || doc.company_ids.length !== 1 || doc.company_ids[0] !== issuer || !Array.isArray(row5.members) || row5.members.length < 1 || row5.members.length > 100) throw invalid3();
  const members = row5.members.map((raw) => {
    if (!raw || typeof raw !== "object" || Array.isArray(raw)) throw invalid3();
    const m = raw, receipt = text6(m.receipt_no, /^[0-9]{14}$/);
    const title = text6(m.title, /^[^<>\u0000-\u001f\u007f]{1,300}$/), day4 = text6(m.published_on, /^[0-9]{4}-[0-9]{2}-[0-9]{2}$/);
    if (titleKey(title) !== "단일판매·공급계약체결" || typeof m.amendment !== "boolean" || !Number.isFinite(Date.parse(day4)) || new Date(day4).toISOString().slice(0, 10) !== day4) throw invalid3();
    return { receipt, title, day: day4, amendment: m.amendment };
  }).sort((a, b) => a.day.localeCompare(b.day) || a.receipt.localeCompare(b.receipt));
  const originals = members.filter((m) => !m.amendment), selected = members.find((m) => m.receipt === current);
  if (new Set(members.map((m) => m.receipt)).size !== members.length || originals.length !== 1 || originals[0].receipt !== root || members.some((m) => m.day < originals[0].day) || !selected || selected.day !== doc.as_of || titleKey(doc.title) !== titleKey(selected.title) || doc.title.includes("정정") !== selected.amendment) throw invalid3();
  const history = members.map((m) => `${m.day} ${m.amendment ? "정정공시" : "최초 공시"}`).join(" → ");
  return {
    explanation: `DART가 직접 연결한 공시 이력이에요. ${history}. 정정 내용·계약 상대방·현재 유효 상태·주가 영향은 본문 확인이 필요해요. 다른 계약이나 공통 경제사건으로 자동 합치지 않아요.`,
    sources: members.map((m) => ({
      title: `${m.amendment ? "정정공시" : "최초 공시"} · ${m.title}`,
      source: "DART 공시 이력",
      asOf: m.day,
      url: DART + m.receipt
    }))
  };
}

// framer-components/public-probe/PortfolioContractFacts.ts
var invalid4 = () => new Error("계약공시 본문 자료를 확인하지 못했어요.");
var row = (v) => {
  if (!v || typeof v !== "object" || Array.isArray(v)) throw invalid4();
  return v;
};
var text7 = (v, max = 2e3) => {
  if (typeof v !== "string" || !v.trim() || v.length > max || /[<>\u0000-\u001f\u007f]/.test(v)) throw invalid4();
  return v;
};
var day = (v) => {
  const value = text7(v, 10);
  if (!/^\d{4}-\d{2}-\d{2}$/.test(value) || !Number.isFinite(Date.parse(value)) || new Date(value).toISOString().slice(0, 10) !== value) throw invalid4();
  return value;
};
var titleKey2 = (v) => v.normalize("NFKC").replace(/^\[(?:기재|첨부|기타)?정정\]/, "").replace(/[\sㆍ·ᆞ•]/g, "");
var field = (v) => {
  const item = row(v);
  return { label: text7(item.label), value: text7(item.value) };
};
var quote = (v) => {
  const item = field(v);
  return `${item.label}: ${item.value}`;
};
var quotedContractDay = (value) => {
  const match = text7(value, 12).match(/^(\d{4})[.-](\d{1,2})[.-](\d{1,2})\.?$/);
  if (!match) throw invalid4();
  return day(`${match[1]}-${match[2].padStart(2, "0")}-${match[3].padStart(2, "0")}`);
};
function parseContractFacts(value, doc) {
  if (value === void 0) return null;
  const facts = row(value), issuer = row(facts.issuer), filing = row(facts.filing);
  const receipt = text7(facts.receipt_no, 14), issuerId = text7(issuer.id, 9);
  const url = `https://dart.fss.or.kr/dsaf001/main.do?rcpNo=${receipt}`;
  if (facts.schema !== "dart-contract-fact-v1" || !/^\d{14}$/.test(receipt) || !/^KR:\d{6}$/.test(issuerId) || doc.id !== `DART:${receipt}` || doc.source !== "DART" || doc.url !== url || doc.company_ids.length !== 1 || doc.company_ids[0] !== issuerId || day(filing.filed_on) !== doc.as_of || titleKey2(text7(filing.title, 300)) !== "단일판매공급계약체결" || titleKey2(doc.title) !== titleKey2(text7(filing.title, 300)) || facts.counterparty_company_id !== null || facts.verified_common_event !== false || facts.current_contract_status !== "not-inferred") throw invalid4();
  text7(issuer.name, 160);
  const contract = row(facts.contract), period = row(contract.period);
  const lines = [
    "공시 본문 발췌",
    quote(contract.type),
    quote(contract.name),
    quote(contract.counterparty),
    `${text7(period.label)} · ${quote(period.start)} / ${quote(period.end)}`,
    quote(contract.signed_on)
  ];
  if (facts.correction === null) {
    if (doc.title.includes("정정")) throw invalid4();
  } else {
    const correction = row(facts.correction);
    const corrected = field(correction.corrected_on), related = field(correction.related_filing_date);
    if (!doc.title.includes("정정") || quotedContractDay(corrected.value) > doc.as_of || quotedContractDay(related.value) > doc.as_of || !Array.isArray(correction.changes) || !correction.changes.length || correction.changes.length > 20) throw invalid4();
    lines.push(quote(correction.corrected_on), quote(correction.related_filing_date), quote(correction.reason));
    for (const raw of correction.changes) {
      const change = row(raw);
      lines.push(`${text7(change.field)} · 정정 전: ${text7(change.before)} → 정정 후: ${text7(change.after)}`);
    }
  }
  lines.push("공시의 표현 그대로예요. ‘-’·일반 명칭은 특정 기업으로 연결하지 않으며 현재 계약 유효성이나 주가 영향을 뜻하지 않아요.");
  return {
    explanation: lines.join("\n"),
    sources: [{ title: "계약공시 본문", source: "DART", asOf: doc.as_of, url }]
  };
}

// framer-components/public-probe/PortfolioContractTermination.ts
var invalid5 = () => new Error("계약 해지 공시의 근거를 확인하지 못했어요.");
var row2 = (value) => {
  if (!value || typeof value !== "object" || Array.isArray(value)) throw invalid5();
  return value;
};
var text8 = (value, max = 2e3) => {
  if (typeof value !== "string" || !value.trim() || value.length > max || /[<>\u0000-\u001f\u007f]/.test(value)) throw invalid5();
  return value;
};
var day2 = (value) => {
  const result = text8(value, 10);
  if (!/^\d{4}-\d{2}-\d{2}$/.test(result) || !Number.isFinite(Date.parse(result)) || new Date(result).toISOString().slice(0, 10) !== result) throw invalid5();
  return result;
};
var titleKey3 = (value) => value.normalize("NFKC").trim().replace(/^\[(?:기재|첨부|기타)?정정\]/, "").replace(/[\sㆍ·ᆞ•]/g, "");
var correctionTitle = (value) => /^\[(?:기재|첨부|기타)?정정\]/.test(value.normalize("NFKC").trim());
var relatedTitleKey = (value) => value.normalize("NFKC").replace(/[\sㆍ·ᆞ•]/g, "");
var field2 = (value) => {
  const item = row2(value);
  return { label: text8(item.label), value: text8(item.value) };
};
var quote2 = (value) => {
  const item = field2(value);
  return `${item.label}: ${item.value}`;
};
var dart = (receipt) => `https://dart.fss.or.kr/dsaf001/main.do?rcpNo=${receipt}`;
function parseContractTermination(value, doc, knownNames) {
  if (value === void 0) return null;
  const facts = row2(value), issuer = row2(facts.issuer), receipt = text8(facts.receipt_no, 14);
  const issuerId = text8(issuer.id, 9), name = text8(issuer.name, 160), sourceName = text8(issuer.source_name, 160);
  if (facts.schema !== "dart-contract-termination-v1" || facts.proves !== "termination-notice" || facts.current_contract_status !== "not-inferred" || !/^\d{14}$/.test(receipt) || !/^KR:\d{6}$/.test(issuerId) || doc.id !== `DART:${receipt}` || doc.source !== "DART" || doc.url !== dart(receipt) || doc.company_ids.length !== 1 || doc.company_ids[0] !== issuerId || day2(facts.as_of) !== doc.as_of || titleKey3(text8(facts.filing_title, 300)) !== "단일판매공급계약해지" || titleKey3(doc.title) !== "단일판매공급계약해지" || correctionTitle(facts.filing_title) !== correctionTitle(doc.title) || knownNames && (!knownNames.includes(name) || !knownNames.includes(sourceName))) throw invalid5();
  const contract = row2(facts.contract), period = row2(contract.period), notice = row2(facts.termination);
  if (quotedContractDay(field2(period.start).value) > quotedContractDay(field2(period.end).value)) throw invalid5();
  quotedContractDay(field2(notice.date).value);
  const lines = [
    "계약 해지 통보 공시 · 현재 종료 여부는 미확인",
    quote2(contract.name),
    quote2(contract.counterparty),
    `${text8(period.label)} · ${quote2(period.start)} / ${quote2(period.end)}`,
    quote2(notice.date),
    quote2(notice.reason),
    quote2(notice.other_matters)
  ];
  const links = notice.related_filings, documents = notice.related_documents === void 0 ? [] : notice.related_documents;
  if (!Array.isArray(links) || !Array.isArray(documents) || links.length + documents.length < 1 || links.length + documents.length > 20) throw invalid5();
  const seen = /* @__PURE__ */ new Set(), sources = [
    { title: "계약 해지 공시", source: "DART", asOf: doc.as_of, url: doc.url }
  ];
  const addRelated = (raw, contract2) => {
    const link = row2(raw), previous = text8(link.receipt_no, 14), published = day2(link.filed_on), title = text8(link.title, 300);
    const isContract = relatedTitleKey(title) === "단일판매공급계약체결";
    if (!/^\d{14}$/.test(previous) || seen.has(previous) || previous === receipt || published > doc.as_of || previous.slice(0, 8) !== published.replaceAll("-", "") || isContract !== contract2 || link.href !== `/dsaf001/main.do?rcpNo=${previous}`) throw invalid5();
    seen.add(previous);
    sources.push({ title: `공시가 명시한 ${contract2 ? "계약 원문" : "기타 원문"} · ${title}`, source: "DART", asOf: published, url: dart(previous) });
  };
  for (const raw of links) addRelated(raw, true);
  for (const raw of documents) addRelated(raw, false);
  lines.push("통보일과 효력일은 다를 수 있어요. 계약 범위·효력 발생 여부를 임의로 판단하지 않아요. 관련 원문 링크는 해지 공시에 명시된 연결이에요.");
  return { explanation: lines.join("\n"), sources };
}

// framer-components/public-probe/PortfolioContractEvents.ts
var invalid6 = () => new Error("계약 사건의 연결 근거를 확인하지 못했어요.");
var row3 = (v) => {
  if (!v || typeof v !== "object" || Array.isArray(v)) throw invalid6();
  return v;
};
var text9 = (v, max = 2e3) => {
  if (typeof v !== "string" || !v.trim() || v.length > max || /[<>\u0000-\u001f\u007f]/.test(v)) throw invalid6();
  return v;
};
var list3 = (v, max) => {
  if (!Array.isArray(v) || v.length > max) throw invalid6();
  return v;
};
var day3 = (v) => {
  const s = text9(v, 10);
  if (!/^\d{4}-\d{2}-\d{2}$/.test(s) || !Number.isFinite(Date.parse(s)) || new Date(s).toISOString().slice(0, 10) !== s) throw invalid6();
  return s;
};
var legal = (s) => s.normalize("NFKC").toLowerCase().replace(/\s+/g, "").replace(/^(?:주식회사|\(주\))|(?:주식회사|\(주\))$/g, "");
function projectContractEventMeasure(facts) {
  if (!facts.length) return null;
  const latestDate = facts.reduce((latest2, fact) => fact.date > latest2 ? fact.date : latest2, "");
  const latest = facts.filter((fact) => fact.date === latestDate);
  const periods = new Set(latest.map((fact) => JSON.stringify([fact.start, fact.end])));
  return periods.size === 1 ? {
    kind: "reported-contract-period",
    label: "계약기간",
    value: `${latest[0].start} ~ ${latest[0].end}`,
    sourceLabel: latest[0].label,
    start: latest[0].start,
    end: latest[0].end,
    asOf: latestDate,
    sourceUrl: latest[0].sourceUrl
  } : null;
}
async function parseContractEvents(value, companies) {
  if (value === void 0) return [];
  const payload = row3(value), rawItems = list3(payload.items, 20), coverage = row3(payload.coverage);
  if (!Number.isSafeInteger(coverage.selected) || coverage.selected < rawItems.length || coverage.returned !== rawItems.length || coverage.omitted !== coverage.selected - rawItems.length) throw invalid6();
  if (coverage.oversized_history !== void 0 && (!Number.isSafeInteger(coverage.oversized_history) || coverage.oversized_history < 0 || coverage.oversized_history > coverage.omitted)) throw invalid6();
  const seen = /* @__PURE__ */ new Set(), usedDocuments = /* @__PURE__ */ new Set(), out = [];
  const named = (id, value2) => {
    const supplied = companies.get(id), names = typeof supplied === "string" ? [supplied] : list3(supplied, 4);
    return names.some((name) => legal(text9(name, 180)) === legal(value2));
  };
  for (const raw of rawItems) {
    const e = row3(raw), id = text9(e.id, 80), root = text9(e.root_receipt, 14), asOf = day3(e.as_of);
    const participants2 = list3(e.participants, 2).map((v) => {
      const p = row3(v), id2 = text9(p.id, 9);
      if (!/^KR:\d{6}$/.test(id2) || !["supplier", "counterparty"].includes(p.role)) throw invalid6();
      return { id: id2, role: p.role };
    });
    if (participants2.length !== 2 || participants2[0].role !== "supplier" || participants2[1].role !== "counterparty" || participants2[0].id === participants2[1].id || !/^\d{14}$/.test(root) || id !== `contract:${participants2[0].id}:${root}` || seen.has(id) || e.kind !== "reported-contract" || e.identity_basis !== "explicit-contract-parties" || e.current_status !== "not-inferred" || JSON.stringify(e.company_ids) !== JSON.stringify(participants2.map((p) => p.id))) throw invalid6();
    seen.add(id);
    const selectedIds = participants2.map((p) => p.id).filter((id2) => companies.has(id2)).sort();
    if (!selectedIds.length || JSON.stringify(selectedIds) !== JSON.stringify(e.selected_company_ids)) throw invalid6();
    const documents = list3(e.documents, 100), legacyIds = [], sourceDocumentIds = [];
    const evidence = [], terms = [];
    const corrections = [];
    const periodFacts = [];
    let latestDay = "", latestTitle = "", archivedDocumentCount = 0, correctionCount = 0;
    const archive = (d) => {
      if (d.capture_archive === void 0) return;
      if (d.capture_archive !== "retained-public-capture") throw invalid6();
      archivedDocumentCount++;
    };
    for (const rawDoc of documents) {
      const d = row3(rawDoc), doc = {
        id: text9(d.id, 40),
        source: text9(d.source, 20),
        url: text9(d.url),
        title: text9(d.title, 300),
        as_of: day3(d.as_of),
        company_ids: list3(d.company_ids, 1).map((id2) => text9(id2, 9))
      };
      const fact = parseContractFacts(d.contract_facts, doc), lineage = parseDocumentLineage(d.event_lineage, doc);
      if (!fact || doc.company_ids[0] !== participants2[0].id || usedDocuments.has(doc.id) || (lineage ? d.event_lineage.root_receipt !== root : doc.id !== `DART:${root}`)) throw invalid6();
      usedDocuments.add(doc.id);
      archive(d);
      const f = row3(d.contract_facts), c = row3(f.contract), period = row3(c.period);
      const name = text9(row3(c.name).value), signed = quotedContractDay(row3(c.signed_on).value);
      const periodStart = quotedContractDay(row3(period.start).value), periodEnd = quotedContractDay(row3(period.end).value);
      if (signed !== day3(e.signed_on) || signed > doc.as_of || periodStart > periodEnd || /미정|미확정|예정|협의|의향|양해|MOU|LOI|가계약/i.test(name) || companies.has(participants2[0].id) && !named(participants2[0].id, text9(row3(f.issuer).name)) || companies.has(participants2[1].id) && !named(participants2[1].id, text9(row3(c.counterparty).value))) throw invalid6();
      terms.push(legal(name));
      const correction = f.correction === null ? null : row3(f.correction);
      if (correction) correctionCount++;
      const measureDate = correction ? quotedContractDay(row3(correction.corrected_on).value) : doc.as_of;
      if (correction) corrections.push({
        asOf: measureDate,
        filedOn: doc.as_of,
        sourceUrl: doc.url,
        reason: correction.reason.value,
        changes: correction.changes.map((change) => ({
          field: change.field,
          before: change.before,
          after: change.after
        }))
      });
      periodFacts.push({ date: measureDate, start: periodStart, end: periodEnd, label: text9(period.label), sourceUrl: doc.url });
      if (doc.as_of >= latestDay) {
        latestDay = doc.as_of;
        latestTitle = name;
      }
      const identity2 = await portfolioDocumentIdentity(doc.url);
      if (!identity2) throw invalid6();
      legacyIds.push(identity2.id);
      sourceDocumentIds.push(doc.id);
      evidence.push({ url: doc.url, source: "DART", asOf: doc.as_of, explanation: fact.explanation });
      for (const s of lineage?.sources || []) {
        if (s.url) {
          const legacy = await portfolioDocumentIdentity(s.url);
          if (legacy && !legacyIds.includes(legacy.id)) legacyIds.push(legacy.id);
        }
        if (s.url && s.asOf && !evidence.some((proof) => proof.url === s.url))
          evidence.push({ url: s.url, source: "DART", asOf: s.asOf, explanation: "DART가 연결한 공시 이력 · 현재 계약 상태·주가 영향은 미확인" });
      }
    }
    if (!documents.length || new Set(terms).size !== 1 || latestDay !== asOf || latestTitle !== e.title) throw invalid6();
    const measure = projectContractEventMeasure(periodFacts);
    const notices = list3(e.termination_notices === void 0 ? [] : e.termination_notices, 100);
    const priorReferences = /* @__PURE__ */ new Map();
    for (const d of documents) {
      priorReferences.set(d.id.slice(5), d.as_of);
      for (const m of d.event_lineage?.members || []) priorReferences.set(m.receipt_no, m.published_on);
    }
    const noticeIds = /* @__PURE__ */ new Set();
    for (const rawNotice of notices) {
      const d = row3(rawNotice), doc = {
        id: text9(d.id, 40),
        source: text9(d.source, 20),
        url: text9(d.url),
        title: text9(d.title, 300),
        as_of: day3(d.as_of),
        company_ids: list3(d.company_ids, 1).map((id2) => text9(id2, 9))
      };
      const declared = companies.get(participants2[0].id), names = typeof declared === "string" ? [declared] : declared;
      const notice = parseContractTermination(d.contract_termination, doc, names);
      if (!notice || doc.company_ids[0] !== participants2[0].id || noticeIds.has(doc.id) || !d.contract_termination.termination.related_filings.some((link) => priorReferences.get(link.receipt_no) === link.filed_on)) throw invalid6();
      noticeIds.add(doc.id);
      archive(d);
      const identity2 = await portfolioDocumentIdentity(doc.url);
      if (!identity2) throw invalid6();
      legacyIds.push(identity2.id);
      sourceDocumentIds.push(doc.id);
      evidence.push({ url: doc.url, source: "DART", asOf: doc.as_of, explanation: notice.explanation });
      for (const source of notice.sources) if (source.url && source.asOf && !evidence.some((e2) => e2.url === source.url))
        evidence.push({ url: source.url, source: "DART", asOf: source.asOf, explanation: "해지 공시가 명시한 관련 원문 · 현재 종료 여부는 별도 확인" });
    }
    const fingerprint = JSON.stringify([id, latestTitle, participants2, evidence]);
    const hash = await crypto.subtle.digest("SHA-256", new TextEncoder().encode(fingerprint));
    const hex = Array.from(new Uint8Array(hash), (n) => n.toString(16).padStart(2, "0")).join("");
    out.push({
      id,
      title: latestTitle,
      asOf: evidence.reduce((latest, proof) => proof.asOf > latest ? proof.asOf : latest, asOf),
      participants: participants2,
      selectedIds,
      legacyIds,
      sourceDocumentIds,
      measure,
      evidence,
      terminationNoticeCount: notices.length,
      archivedDocumentCount,
      correctionCount,
      corrections,
      periodConflict: periodFacts.length > 0 && measure === null,
      read_revision: Number.parseInt(hex.slice(0, 13), 16) || 1
    });
  }
  return out;
}
function projectContractPrototype(graph) {
  const events = graph.contractEvents || [];
  const nodes = events.map((e, i) => ({
    id: e.id,
    kind: "event",
    recordKind: "event",
    layer: "filing",
    topic: "supply",
    name: e.title.slice(0, 300),
    code: "공시상 계약 사건",
    priority: 2,
    logo: "",
    proofLabel: "공시 본문에 계약 당사자 명시",
    measure: e.measure,
    lifecycle: {
      currentStatus: "unverified",
      terminationNoticeCount: e.terminationNoticeCount,
      correctionCount: e.correctionCount,
      periodConflict: e.periodConflict
    },
    reason: "공시에 명시된 계약의 공급자·상대방을 연결했어요. 현재 계약 유효성·이행 여부·주가 영향은 미확인이에요." + (e.terminationNoticeCount ? " 해지 통보 공시가 있어요. 통보일과 효력일은 원문에서 구분해 확인하세요." : "") + (e.archivedDocumentCount ? ` 최신 목록 밖의 보관한 원문 ${e.archivedDocumentCount}건이 포함돼요. 원래 공시 기준일로 표시해요.` : ""),
    source: "DART",
    asOf: e.asOf,
    evidence: e.evidence,
    corrections: e.corrections,
    legacyIds: e.legacyIds,
    read_revision: e.read_revision,
    x: 1.1 + i % 3 * 0.2,
    y: 0.7 + Math.floor(i / 3) * 0.2
  }));
  const edges = events.flatMap((e) => e.participants.filter((p) => e.selectedIds.includes(p.id)).map((p) => {
    const ticker = p.id.slice(3), reason = p.role === "supplier" ? "계약 공급자" : "계약 상대방";
    return {
      id: `contract-link:${e.id}:${p.id}`,
      from: e.id,
      to: `company:${ticker}`,
      type: "documented",
      confirmation: "confirmed",
      strength: 0,
      impact: "미확인",
      impactReason: "공시상 참여 역할이며 현재 실적·주가 영향을 뜻하지 않아요.",
      reason,
      verb: reason,
      source: "DART",
      asOf: e.asOf,
      evidence: e.evidence,
      measure: e.measure,
      legacyIds: graph.links.filter((l) => l.ticker === ticker && e.legacyIds.includes(l.documentId)).map((l) => l.id)
    };
  }));
  return {
    nodes,
    edges,
    recordsMap: Object.fromEntries(nodes.map((n) => [
      n.id,
      { id: n.id, read_revision: n.read_revision, sourceURLs: n.evidence.map((e) => e.url) }
    ])),
    replacedDocumentIds: new Set(events.flatMap((e) => e.legacyIds))
  };
}

// review/member-map/local-ai-candidates.ts
var fail = () => {
  throw Error("invalid-local-ai-review");
};
var object2 = (v) => v && typeof v === "object" && !Array.isArray(v) ? v : fail();
var keys = (v, expected) => {
  object2(v);
  if (Object.keys(v).sort().join() !== [...expected].sort().join()) fail();
};
var text10 = (v, max) => typeof v === "string" && v.trim() && v.length <= max && !/[<>\u0000-\u001f]/.test(v) ? v : fail();
var entity2 = (v) => /^(KR:[0-9]{6}|US:[A-Z][A-Z0-9.-]{0,12})$/.test(text10(v, 20)) ? v : fail();
var claimStates = { asserted: "원문 진술", planned: "계획", conditional: "조건부", negated: "부정", historical: "과거", conflicted: "상충" };
var missingLabels = { entity_scope: "회사 귀속", role: "거래 역할", object: "거래 대상", period: "적용 시점", scale: "거래 규모", denominator: "비중의 분모", structured_table: "표의 행·열 원문", counter_evidence_not_searched: "별도 반대 근거 조사", path_evidence: "간접 경로 근거", source_context: "주변 원문" };
function claimDetails(value) {
  if (!Array.isArray(value) || value.length < 1 || value.length > 4) fail();
  const lines = [], states = [];
  for (const item of value) {
    const c = object2(item);
    keys(c, ["claim_kind", "directness", "claim_state", "quote", "context", "scope_quote", "channel_quote", "counter_evidence_quotes", "missing_evidence", "review_reasons", "decision", "degree", "degree_basis"]);
    if (!["relation_fact", "conditional_exposure", "co_mention"].includes(c.claim_kind) || !["direct", "indirect", "not_applicable"].includes(c.directness) || !Object.hasOwn(claimStates, c.claim_state) || !["candidate", "needs_context", "conflict"].includes(c.decision) || c.degree !== "unrated" || c.degree_basis !== "unrated") fail();
    const quote3 = text10(c.quote, 600), label2 = claimStates[c.claim_state];
    states.push(label2);
    lines.push(`${label2} · ${c.claim_kind === "co_mention" ? "동시 언급" : c.claim_kind === "conditional_exposure" ? "조건부 영향" : "관계 진술"} · AI 해석`, quote3);
    keys(c.context, ["object_quote", "scale_quote", "time_quote"]);
    for (const [key, title] of [["object_quote", "거래 대상"], ["scale_quote", "규모 원문"], ["time_quote", "적용 시점"]]) {
      if (c.context[key] === null) continue;
      const span = text10(c.context[key], key === "scale_quote" ? 600 : 120);
      if (!quote3.includes(span)) fail();
      lines.push(`${title}: ${span}`);
    }
    for (const [key, title] of [["scope_quote", "적용 범위"], ["channel_quote", "전달 경로"]]) {
      if (c[key] === null) continue;
      const span = text10(c[key], 600);
      if (!quote3.includes(span)) fail();
      lines.push(`${title}: ${span}`);
    }
    if (!Array.isArray(c.counter_evidence_quotes) || c.counter_evidence_quotes.length > 4 || !Array.isArray(c.missing_evidence) || c.missing_evidence.length > 11 || c.missing_evidence.some((m) => !Object.hasOwn(missingLabels, m)) || !Array.isArray(c.review_reasons) || c.review_reasons.length > 10) fail();
    for (const q of c.counter_evidence_quotes) lines.push(`같은 발췌문 안의 반대 근거: ${text10(q, 600)}`);
    for (const reason of c.review_reasons) if (!/^[a-z-]{1,60}$/.test(text10(reason, 60))) fail();
    if (c.review_reasons.length) lines.push("회사 귀속·시점·방향 또는 문맥 검토가 필요해요.");
    if (c.missing_evidence.length) lines.push(`추가 확인: ${c.missing_evidence.map((m) => missingLabels[m]).join(" · ")}`);
  }
  lines.push("연결 정도 미평가 · 확인된 관계나 주가 영향으로 확정하지 않았어요.");
  return { lines, states: [...new Set(states)] };
}
function attachLocalAICandidates(graph, payload, label2 = "로컬 AI 후보") {
  if (payload === void 0) return graph;
  const body = object2(payload);
  keys(body, ["schema", "candidates", "coverage"]);
  if (body.schema !== "local-ai-review-v1" || !Array.isArray(body.candidates) || body.candidates.length > 40) fail();
  const coverage = object2(body.coverage);
  keys(coverage, ["input", "accepted", "rejected", "skipped", "matched", "returned", "omitted"]);
  if (Object.values(coverage).some((v) => !Number.isSafeInteger(v) || v < 0) || coverage.input !== coverage.accepted + coverage.rejected + coverage.skipped || coverage.matched > coverage.accepted || coverage.returned !== body.candidates.length || coverage.matched !== coverage.returned + coverage.omitted) fail();
  const selected = new Set(graph.companies.map((c) => `${c.market}:${c.ticker}`));
  const ids = new Set((graph.automaticRelations || []).map((r) => r.id));
  const relations = body.candidates.map((value) => {
    const r = object2(value);
    keys(r, [
      "id",
      "revision",
      "issuer_id",
      "issuer_name",
      "counterparty_id",
      "counterparty_name",
      "role",
      "quote",
      "source_id",
      "url",
      "as_of",
      "status",
      "verification",
      "evidence_scope",
      "current_validity",
      ..."context" in r ? ["context"] : [],
      ..."claims" in r ? ["claims"] : []
    ]);
    const id = text10(r.id, 50), revision2 = text10(r.revision, 64), issuer = entity2(r.issuer_id), target = entity2(r.counterparty_id);
    const issuerName = text10(r.issuer_name, 160), targetName = text10(r.counterparty_name, 160), quote3 = text10(r.quote, 1e4);
    const source = text10(r.source_id, 40), url = text10(r.url, 100), asOf = text10(r.as_of, 10);
    if (!/^automatic:ai:[a-f0-9]{24}$/.test(id) || ids.has(id) || !/^[a-f0-9]{64}$/.test(revision2) || issuer === target || !selected.has(issuer) && !selected.has(target) || !/^source:dart:[0-9]{14}$/.test(source) || url !== `https://dart.fss.or.kr/dsaf001/main.do?rcpNo=${source.slice(12)}` || !/^\d{4}-\d{2}-\d{2}$/.test(asOf) || !Number.isFinite(Date.parse(asOf)) || new Date(asOf).toISOString().slice(0, 10) !== asOf || !("claims" in r ? ["customer", "supplier", "partner", "other"] : ["customer", "supplier"]).includes(r.role) || r.status !== "ai_candidate" || r.verification !== "unreviewed-model-extraction" || r.current_validity !== "not-inferred" || !["historical-context", "unspecified"].includes(r.evidence_scope)) fail();
    ids.add(id);
    const detail = "claims" in r ? claimDetails(r.claims) : null;
    const roleLabel = detail ? `${detail.states.join("·")} 후보` : r.role === "customer" ? "고객 후보" : "공급업체 후보";
    const scope = r.evidence_scope === "historical-context" ? "과거 문맥의 거래 · 현재 지속 여부 미확인" : "현재 유효 여부 미확인";
    const interpretation = [];
    if (detail) interpretation.push(...detail.lines);
    if ("context" in r) {
      keys(r.context, ["object_quote", "scale_quote", "time_quote"]);
      for (const [key, label3] of [["object_quote", "거래 대상"], ["scale_quote", "규모 원문"], ["time_quote", "거래 시점 원문"]]) {
        const value2 = r.context[key];
        if (value2 === null) continue;
        const span = text10(value2, key === "scale_quote" ? 600 : 120);
        if (!quote3.includes(span)) fail();
        interpretation.push(`${label3}: ${span}`);
      }
      interpretation.unshift(`AI 해석 · ${r.role === "customer" ? "매출 연결 후보" : "조달 연결 후보"}`);
      interpretation.push("연결 정도 미평가 · 기업별 거래 규모·의존도 검토가 필요해요.");
    }
    return {
      id,
      read_revision: Number.parseInt(revision2.slice(0, 13), 16) + 1,
      reported: false,
      title: `AI ${roleLabel}`,
      source: "DART · AI 추출 후보",
      asOf,
      url,
      reason: `미검수 AI 후보 · ${issuerName} → ${targetName}. ${scope}. 관계 방향·규모·주가 영향은 확정하지 않았어요.
${interpretation.length ? interpretation.join("\n") + "\n" : ""}${detail ? "" : quote3}`,
      participants: [
        { id: issuer, name: issuerName, role: "document_issuer", roleLabel: "공시 작성 회사" },
        { id: target, name: targetName, role: `candidate_${r.role}`, roleLabel }
      ]
    };
  });
  return {
    ...graph,
    aiReviewStatus: "ready",
    automaticRelations: [...graph.automaticRelations || [], ...relations],
    analysisNotice: [graph.analysisNotice, `${label2} ${coverage.returned}/${coverage.matched}건 · 미검수`].filter(Boolean).join(" · ")
  };
}
function attachPublicAIReview(graph, payload, coverage) {
  if (coverage === void 0 && payload === void 0) return graph;
  const meta = object2(coverage);
  keys(meta, ["status"]);
  if (meta.status === "ready") {
    if (payload === void 0) fail();
    return attachLocalAICandidates(graph, payload, "AI 분석 후보");
  }
  if (!["unavailable", "rejected"].includes(meta.status) || payload !== void 0) fail();
  return {
    ...graph,
    aiReviewStatus: meta.status,
    analysisNotice: [graph.analysisNotice, meta.status === "rejected" ? "AI 분석 자료 검증 실패 · 기존 공개자료는 표시해요." : "AI 분석 자료 연결 대기 · 관계가 없다는 뜻은 아니에요."].filter(Boolean).join(" · ")
  };
}

// framer-components/public-probe/PortfolioAnalysisClient.ts
var ENDPOINT2 = "https://project-yw131.vercel.app/api/member_map_analysis";
var FACT_NAMES = {
  revenue: "매출",
  operating_income: "영업이익",
  net_income: "순이익",
  total_assets: "총자산",
  total_liabilities: "총부채",
  equity: "자기자본",
  cash: "현금성 자산",
  free_cash_flow: "잉여현금흐름",
  eps: "주당순이익",
  market_cap: "시가총액",
  per: "PER",
  pbr: "PBR",
  roe: "자기자본이익률",
  debt_ratio: "부채비율",
  operating_margin: "영업이익률",
  revenue_growth: "매출 성장률",
  revenue_growth_quarterly_yoy: "분기 매출 성장률(전년 대비)"
};
var invalid7 = () => new Error("분석 자료의 형식을 확인하지 못했어요.");
var row4 = (v) => {
  if (!v || typeof v !== "object" || Array.isArray(v)) throw invalid7();
  return v;
};
var array = (v, max = 1e4) => {
  if (!Array.isArray(v) || v.length > max) throw invalid7();
  return v;
};
var text11 = (v, max = 300) => {
  if (typeof v !== "string" || !v.trim() || v.length > max || /[\u0000-\u001f\u007f<>]/.test(v)) throw invalid7();
  return v;
};
var date = (v) => {
  const value = text11(v, 10);
  if (!/^(19|20|21)\d{2}(?:-\d{2}-\d{2})?$/.test(value)) throw invalid7();
  if (value.length === 10 && (!Number.isFinite(Date.parse(value)) || new Date(value).toISOString().slice(0, 10) !== value)) throw invalid7();
  return value;
};
function positionsOnly(input) {
  if (!Array.isArray(input) || input.length > 30) throw invalid7();
  const seen = /* @__PURE__ */ new Set();
  return input.map((position2) => {
    const { ticker, market: market2 } = position2;
    if (!(market2 === "KR" ? /^\d{6}$/.test(ticker) : market2 === "US" && /^[A-Z][A-Z0-9]{0,9}(?:[.-][A-Z0-9]{1,2})?$/.test(ticker)) || seen.has(ticker)) throw invalid7();
    seen.add(ticker);
    return { ticker, market: market2 };
  });
}
var officialDocument = (value, source) => {
  const url = text11(value, 2048);
  const valid = source === "DART" ? /^https:\/\/dart\.fss\.or\.kr\/dsaf001\/main\.do\?rcpNo=\d{14}$/.test(url) : source === "SEC" && /^https:\/\/www\.sec\.gov\/Archives\/edgar\/data\/[1-9]\d{0,9}\/\d{18}\/(?:[A-Za-z0-9][A-Za-z0-9_.-]{0,199})?$/.test(url);
  if (!valid) throw invalid7();
  return url;
};
function financialProof(fact, market2) {
  if (fact.provenance === void 0) {
    if (fact.unit === "currency-unverified") throw invalid7();
    return {};
  }
  const p = row4(fact.provenance);
  if (p.kind === "dart-annual") {
    const receipt = text11(p.rcept_no, 14), start = date(p.period_start), end = date(p.period_end), filed = date(p.filed);
    const basis = text11(p.fs_div, 3), account = text11(p.account_name, 200);
    const days = (Date.parse(end) - Date.parse(start)) / 864e5 + 1;
    if (market2 !== "KR" || fact.source !== "DART" || fact.unit !== "KRW" || !["revenue", "operating_income", "net_income"].includes(String(fact.metric)) || !/^\d{14}$/.test(receipt) || [start, end, filed].some((d) => d.length !== 10) || end.slice(0, 4) !== fact.as_of || days < 330 || days > 371 || filed < end || receipt.slice(0, 8) !== filed.replace(/-/g, "") || !["CFS", "OFS"].includes(basis) || p.source_url !== `https://dart.fss.or.kr/dsaf001/main.do?rcpNo=${receipt}`) throw invalid7();
    return {
      url: p.source_url,
      explanation: `DART ${basis === "CFS" ? "연결" : "별도"}재무제표의 연간 수치예요. 회계기간 ${start} ~ ${end} · 제출일 ${filed}.
공시 계정 ${account}`
    };
  }
  const cik = text11(p.cik, 10), accession = text11(p.accession, 20);
  const period = date(p.period_end), form = text11(p.form, 8), tag = text11(p.tag, 200);
  if (market2 !== "US" || fact.source !== "SEC" || !/^[1-9][0-9]{0,9}$/.test(cik) || !/^\d{10}-\d{2}-\d{6}$/.test(accession) || period.length !== 10 || period.slice(0, 4) !== fact.as_of || !["10-K", "10-K/A", "20-F", "20-F/A", "40-F", "40-F/A"].includes(form) || !/^[A-Za-z][A-Za-z0-9_:]{0,199}$/.test(tag) || typeof p.currency_verified !== "boolean" || (p.currency_verified ? !/^(KRW|USD|CAD|AUD|EUR|GBP|JPY|HKD|CNY|CHF|ILS|SGD|NZD|BRL)$/.test(String(fact.unit)) : fact.unit !== "currency-unverified")) throw invalid7();
  const base = `https://www.sec.gov/Archives/edgar/data/${cik}/${accession.replace(/-/g, "")}/${accession}-index`;
  if (p.source_url !== base + ".html" && p.source_url !== base + ".htm") throw invalid7();
  const url = p.source_url;
  return {
    url,
    ...p.currency_verified ? {} : { unit: "보고 통화 미확인" },
    explanation: `SEC ${form}의 연간 수치예요. 회계기간 종료일 ${period} · 제출일은 이 자료에 없어요.
XBRL 항목 ${tag}` + (p.currency_verified ? "" : "\n저장된 원자료에 통화가 없어 달러로 단정하지 않아요.")
  };
}
async function analysisToGraph(payload, input) {
  const positions = positionsOnly(input), body = row4(payload), coverage = row4(body.coverage);
  if (body.schema !== "alphaconsole-portfolio-v1" || coverage.requested !== positions.length) throw invalid7();
  const wanted = new Map(positions.map((p) => [`${p.market}:${p.ticker}`, p]));
  const companies = /* @__PURE__ */ new Map(), missing2 = /* @__PURE__ */ new Set();
  for (const value of array(body.companies, 30)) {
    const company = row4(value), id = text11(company.id);
    const expected = wanted.get(id);
    if (!expected || company.ticker !== expected.ticker || company.market !== expected.market || companies.has(id)) throw invalid7();
    companies.set(id, company);
  }
  for (const value of array(coverage.missing, 30)) {
    const company = row4(value), id = text11(company.id), expected = wanted.get(id);
    if (!expected || company.ticker !== expected.ticker || company.market !== expected.market || companies.has(id) || missing2.has(id)) throw invalid7();
    missing2.add(id);
  }
  if (companies.size + missing2.size !== wanted.size || coverage.matched !== companies.size) throw invalid7();
  const automatic = parseAutomaticEvidence(body.automatic_evidence, new Set(wanted.keys()));
  const prices = parseAnalysisPrices(body.prices, wanted);
  const companyNames = new Map([...companies].map(([id, company]) => {
    const name = text11(company.name, 180);
    const names = company.source_names === void 0 ? [name] : array(company.source_names, 4).map((v) => text11(v, 180));
    if (names[0] !== name || new Set(names).size !== names.length) throw invalid7();
    return [id, names];
  }));
  const documents = /* @__PURE__ */ new Map();
  for (const value of array(body.documents)) {
    const doc = row4(value), id = text11(doc.id), source = text11(doc.source, 30);
    const ids = array(doc.company_ids, 30).map((v) => text11(v));
    if (documents.has(id) || !ids.length || new Set(ids).size !== ids.length || ids.some((key) => !companies.has(key)) || doc.kind !== "disclosure") throw invalid7();
    const matches = array(doc.source_matches === void 0 ? [] : doc.source_matches, 30);
    const matchedTickers = /* @__PURE__ */ new Set();
    for (const value2 of matches) {
      const match = row4(value2), ticker = text11(match.ticker, 6), receipt = text11(match.receipt_no, 14);
      if (source !== "DART" || match.kind !== "same-dart-receipt" || match.source_file !== "portfolio.json" || !/^\d{6}$/.test(ticker) || !/^\d{14}$/.test(receipt) || id !== `DART:${receipt}` || doc.url !== `https://dart.fss.or.kr/dsaf001/main.do?rcpNo=${receipt}` || !ids.includes(`KR:${ticker}`) || date(match.as_of) !== doc.as_of || matchedTickers.has(ticker)) throw invalid7();
      matchedTickers.add(ticker);
    }
    const context = { id, source, url: text11(doc.url, 2048), title: text11(doc.title), as_of: date(doc.as_of), company_ids: ids };
    const lineage = parseDocumentLineage(doc.event_lineage, context);
    const contract = parseContractFacts(doc.contract_facts, context);
    const termination = parseContractTermination(doc.contract_termination, context, companyNames.get(ids[0]));
    const archived = doc.capture_archive !== void 0;
    if (archived && (doc.capture_archive !== "retained-public-capture" || source !== "DART" || !contract && !termination)) throw invalid7();
    documents.set(id, { ids, archived, item: {
      id: `disclosure-${id}`,
      title: text11(doc.title),
      source,
      url: officialDocument(doc.url, source),
      asOf: date(doc.as_of),
      relationship: "direct",
      explanation: "이 종목에 연결된 공시 원문이에요. 사업상 영향이나 주가 방향을 뜻하지 않아요." + (matches.length ? " 공시 목록·공시 알림에서 접수번호·종목·접수일·제목이 일치해 같은 원문으로 묶었어요. 동일 DART 자료의 재수집이며 독립된 추가 확인은 아니에요." : "") + (lineage ? " " + lineage.explanation : "") + (contract ? "\n\n" + contract.explanation : "") + (termination ? "\n\n" + termination.explanation : ""),
      reason: termination ? "계약 해지 통보 공시" : "공시 연결",
      ...lineage || contract || termination ? { sources: [...lineage?.sources || [], ...contract?.sources || [], ...termination?.sources || []] } : {}
    } });
  }
  const missingSources = array(coverage.missing_source_files, 11);
  if (missingSources.some((v) => typeof v !== "string" || !/^(universe_search|stock_report_public|us_stock_report_public|public_disclosure_feed|us_disclosure_feed|member_map_auto_evidence|member_map_ai_candidates|kr_business_overview_public|macro_snapshot|commodity_exposure|portfolio)\.json$/.test(v))) throw invalid7();
  const evidenceCoverage = coverage.evidence === void 0 ? {} : row4(coverage.evidence);
  const evidenceFailed = evidenceCoverage.status === "not-supplied" || evidenceCoverage.status === "rejected";
  const counts = [
    ["document_records", "공시", documents.size],
    ["automatic_relationships", "관계 후보", automatic.relations.length],
    ["automatic_materials", "원문 발췌", automatic.materials.length]
  ];
  const notices = counts.flatMap(([key, label2, received]) => {
    if (evidenceCoverage[key] === void 0) return [];
    const count = row4(evidenceCoverage[key]);
    if (!Number.isSafeInteger(count.total) || !Number.isSafeInteger(count.returned) || count.total < received || count.returned !== received || count.omitted !== count.total - received) throw invalid7();
    return count.omitted ? [`${label2} ${received}/${count.total}건 표시`] : [];
  });
  const correctionCount = body.automatic_evidence === void 0 || body.automatic_evidence === null ? void 0 : row4(body.automatic_evidence).coverage?.response_records?.corrections;
  if (correctionCount !== void 0) {
    const count = row4(correctionCount), received = automatic.corrections?.length || 0;
    if (!Number.isSafeInteger(count.total) || count.total < received || count.returned !== received || count.omitted !== count.total - received || count.truncated !== (count.omitted !== 0)) throw invalid7();
    if (count.omitted) notices.push(`정정공시 ${received}/${count.total}건 표시`);
  }
  const maps = positions.map((position2) => {
    const key = `${position2.market}:${position2.ticker}`, company = companies.get(key);
    const declared = company ? array(company.document_ids).map((v) => text11(v)) : [];
    const associated = [...documents.entries()].filter(([, doc]) => doc.ids.includes(key));
    if (new Set(declared).size !== declared.length || declared.length !== associated.length || declared.some((id) => !documents.get(id)?.ids.includes(key))) throw invalid7();
    const eventItems = associated.map(([, doc]) => doc.item);
    for (const correction of (automatic.corrections || []).filter((c) => c.companyId === key)) {
      if (!company) throw invalid7();
      const priorIndex = eventItems.findIndex((item) => item.url === correction.item.url);
      if (priorIndex < 0) eventItems.push(correction.item);
      else {
        const prior = eventItems[priorIndex];
        if (prior.source !== correction.item.source || prior.title !== correction.item.title || prior.asOf !== correction.item.asOf) throw invalid7();
        eventItems[priorIndex] = {
          ...prior,
          reason: correction.item.reason,
          explanation: `${prior.explanation}

${correction.item.explanation}`
        };
      }
    }
    const facts = (company ? array(company.facts) : []).map((value, index) => {
      const fact = row4(value), numeric2 = fact.value;
      if (typeof numeric2 !== "number" || !Number.isFinite(numeric2) || Math.abs(numeric2) > 1e30) throw invalid7();
      const unit = text11(fact.unit, 30), metric = text11(fact.metric, 80);
      return {
        id: `fact-${index}`,
        title: FACT_NAMES[metric] || metric,
        value: numeric2.toLocaleString("ko-KR"),
        explanation: "출처에 표시된 값과 기준일이에요.",
        source: text11(fact.source, 80),
        asOf: date(fact.as_of),
        unit,
        relationship: "unknown",
        ...financialProof(fact, position2.market)
      };
    });
    const failed = !company || missingSources.some((name) => name === "universe_search.json" || (position2.market === "KR" ? ["stock_report_public.json", "public_disclosure_feed.json"] : ["us_stock_report_public.json", "us_disclosure_feed.json"]).includes(name));
    const sections = [
      {
        id: "business",
        title: "사업 자료",
        state: evidenceFailed ? "error" : automatic.materials.some((m) => m.companyIds.includes(key)) ? "ready" : "empty",
        items: automatic.materials.filter((m) => m.companyIds.includes(key)).map((m) => m.item),
        message: evidenceFailed ? "자동 관계 자료를 불러오지 못했어요. 실제 관계가 없다는 뜻은 아니에요." : "원문에 함께 언급된 자료와 관계 후보를 구분해요. 언급만으로 거래 관계나 주가 영향을 판단하지 않아요."
      },
      {
        id: "finance",
        title: "공개 재무 자료",
        state: failed ? "error" : facts.length ? "ready" : "empty",
        items: facts,
        message: failed ? "공개 자료 일부를 불러오지 못했어요." : "항목마다 출처와 기준일을 함께 확인하세요."
      },
      {
        id: "events",
        title: "공시 자료",
        state: failed ? "error" : eventItems.length ? "ready" : "empty",
        items: eventItems,
        message: failed ? "공개 자료 일부를 불러오지 못했어요." : "같은 공시가 여러 종목에 연결돼도 공통 영향이 확인된 것은 아니에요."
      }
    ];
    return {
      ...position2,
      name: company ? text11(company.name, 180) : position2.ticker,
      sections,
      coverage: { ok: failed ? 0 : 1, total: 1, missing: failed ? ["공개 자료"] : [] }
    };
  });
  const graph = await buildPortfolioMapGraph(maps);
  for (const { archived, item } of documents.values()) {
    if (!archived) continue;
    const identity2 = await portfolioDocumentIdentity(item.url);
    const document2 = graph.documents.find((d) => d.id === identity2?.id);
    if (!document2) throw invalid7();
    const qualifier = " · 보관한 원문 · 최신 목록 밖의 자료";
    document2.reason += qualifier;
    for (const proof of document2.evidence) proof.reason += qualifier;
    for (const link of graph.links.filter((l) => l.documentId === document2.id)) link.reason += qualifier;
  }
  const sharedReason = "같은 원문 공동 언급 후보 · 거래 관계·공통 영향 미확인";
  for (const common of automatic.commonMaterials) {
    const identity2 = await portfolioDocumentIdentity(common.url);
    const document2 = graph.documents.find((d) => d.id === identity2?.id && d.url === common.url);
    if (!document2) throw invalid7();
    const material = automatic.materials.find((m) => m.id === common.materialId);
    const tickers = new Set(common.companyIds.map((id) => wanted.get(id).ticker));
    for (const evidence of document2.evidence) {
      if (tickers.has(evidence.ticker) && evidence.url === common.url && evidence.sectionId === "business" && evidence.originalExplanation === material.item.explanation && !evidence.reason.includes(sharedReason)) evidence.reason += ` · ${sharedReason}`;
    }
    document2.reason = [...new Set(document2.evidence.map((e) => e.reason))].join(" · ");
    for (const link of graph.links.filter((l) => l.documentId === document2.id))
      link.reason = [...new Set(link.evidence.map((e) => e.reason))].join(" · ");
  }
  graph.automaticRelations = automatic.relations;
  if (body.contract_events !== void 0) {
    Object.assign(graph, { contractEvents: await parseContractEvents(body.contract_events, companyNames) });
    const count = row4(row4(body.contract_events).coverage);
    if (count.omitted) notices.push(`계약 사건 ${count.returned}/${count.selected}건 표시`);
    if (count.oversized_history) notices.push(`긴 계약 이력 ${count.oversized_history}건은 공시 원문에서 확인`);
  }
  const marketContext = await parseMarketContext(body.market_context, new Set(wanted.keys()), companyNames);
  Object.assign(graph, { marketContext });
  const marketCoverage = body.market_context === void 0 ? void 0 : row4(body.market_context).coverage;
  if (marketCoverage !== void 0 && row4(marketCoverage).news_groups !== void 0) {
    const groups = row4(row4(marketCoverage).news_groups), received = marketContext.filter((item) => item.kind === "news").length;
    if (!Number.isSafeInteger(groups.total) || groups.total < received || groups.returned !== received || groups.omitted !== groups.total - received) throw invalid7();
    if (groups.omitted) notices.push(`뉴스 ${received}/${groups.total}묶음 표시`);
  }
  if (notices.length) graph.analysisNotice = `최근 원문 우선 · ${notices.join(" · ")}`;
  for (const company of graph.companies) {
    const quote3 = prices.get(`${company.market}:${company.ticker}`);
    if (quote3) company.closeQuote = quote3;
  }
  return attachPublicAIReview(graph, body.ai_review, coverage.ai_review);
}
async function fetchPortfolioAnalysisGraph(input, options) {
  const positions = positionsOnly(input);
  const check = () => {
    if (options.signal?.aborted) throw options.signal.reason || new Error("요청이 취소되었어요.");
    const session2 = options.getSession();
    if (!session2 || session2.userId !== options.ownerId || !session2.token) throw new Error("로그인 계정이 변경되었어요.");
    return session2;
  };
  let session = check();
  if (!positions.length) return buildPortfolioMapGraph([]);
  const request = (token) => (options.fetcher || fetch)(ENDPOINT2, {
    method: "POST",
    credentials: "omit",
    cache: "no-store",
    redirect: "error",
    signal: options.signal,
    headers: { "Content-Type": "application/json", Authorization: `Bearer ${token}` },
    body: JSON.stringify({ positions })
  });
  let response;
  try {
    response = await request(session.token);
    const current = check();
    if (response.status === 401 && current.token !== session.token) {
      session = current;
      response = await request(session.token);
      check();
    }
    if (!response.ok) throw new Error("unavailable");
    const payload = await response.json();
    check();
    const graph = await analysisToGraph(payload, positions);
    check();
    return graph;
  } catch {
    check();
    throw new Error("분석 자료를 불러오지 못했어요. 잠시 후 다시 시도해 주세요.");
  }
}

// framer-components/public-probe/PortfolioAnalysisMerge.ts
var order2 = (a, b) => a < b ? -1 : a > b ? 1 : 0;
var MAX_DOCUMENTS = 100;
var KR_MARKETS = /* @__PURE__ */ new Set(["KR", "KOSPI", "KOSDAQ", "KONEX"]);
var US_MARKETS = /* @__PURE__ */ new Set(["US", "NASDAQ", "NYSE", "AMEX", "NYSE AMERICAN", "NYSE ARCA", "BATS"]);
var uniqueSorted = (values) => [...new Map(values.map((value) => [JSON.stringify(value), value])).entries()].sort(([a], [b]) => order2(a, b)).map(([, value]) => value);
var appendUnique = (first, second) => [...new Map([...first, ...second].map((value) => [JSON.stringify(value), value])).values()];
async function sha2562(value) {
  const digest = await crypto.subtle.digest("SHA-256", new TextEncoder().encode(value));
  return Array.from(new Uint8Array(digest), (byte) => byte.toString(16).padStart(2, "0")).join("");
}
function canonicalMarket(value) {
  const normalized = value.trim().toUpperCase();
  return KR_MARKETS.has(normalized) ? "KR" : US_MARKETS.has(normalized) ? "US" : null;
}
function sourceDate(value) {
  if (!value || !/^\d{4}-\d{2}-\d{2}$/.test(value)) return null;
  const [year, month, day4] = value.split("-").map(Number);
  const parsed = new Date(Date.UTC(year, month - 1, day4));
  return parsed.getUTCFullYear() === year && parsed.getUTCMonth() === month - 1 && parsed.getUTCDate() === day4 ? value : null;
}
function latestSourceDate(evidence) {
  const dates = evidence.flatMap((row5) => [row5.asOf, ...row5.sources.map((source) => source.asOf)]).map(sourceDate).filter((value) => value !== null);
  return dates.sort(order2).at(-1) || null;
}
function summarize2(evidence) {
  const dates = evidence.flatMap((row5) => [
    row5.asOf,
    ...row5.sources.map((source) => source.asOf),
    ...(row5.sourceRecords || []).map((source) => source.publishedAt)
  ]);
  return {
    source: uniqueSorted(evidence.flatMap((row5) => [row5.source, ...row5.sources.map((source) => source.source)])).join(" · "),
    asOf: dates.every((date2) => date2 === dates[0]) ? dates[0] : void 0,
    reason: uniqueSorted(evidence.map((row5) => row5.reason)).join(" · "),
    confirmation: evidence.every((row5) => row5.confirmation === "confirmed") ? "confirmed" : "unknown",
    isCorrection: evidence.some((row5) => row5.isCorrection) ? true : null
  };
}
async function rebuildDocument(id, url, evidence) {
  const rows2 = uniqueSorted(evidence);
  if (!rows2.length) throw new Error("portfolio-document-without-evidence");
  const tickers = uniqueSorted(rows2.map((row5) => row5.ticker));
  const content = uniqueSorted(rows2.map(({ ticker: _ticker, sectionId: _section, reason: _reason, sourceRecords, ...row5 }) => ({
    ...row5,
    ...sourceRecords?.length ? { sourceRecords: uniqueSorted(sourceRecords.map(({ observedAt: _observed, isBackfill: _backfill, ...source }) => source)) } : {}
  })));
  const contentHash = await sha2562(JSON.stringify(content));
  return {
    id,
    kind: "source-document",
    title: rows2[0].title,
    url,
    ...summarize2(rows2),
    evidence: rows2,
    tickers,
    contentHash,
    read_revision: Number.parseInt(contentHash.slice(0, 13), 16) + 1
  };
}
function mergeSections(legacy = [], analysis = []) {
  const indexed = /* @__PURE__ */ new Map();
  for (const section of [...legacy, ...analysis]) {
    const prior = indexed.get(section.id);
    if (!prior) {
      indexed.set(section.id, { ...section, items: [...section.items] });
      continue;
    }
    const states = [prior.state, section.state];
    const state = states.includes("error") ? "error" : states.includes("unsupported") ? "unsupported" : states.includes("ready") ? "ready" : "empty";
    const messages = appendUnique(prior.message ? [prior.message] : [], section.message ? [section.message] : []);
    indexed.set(section.id, {
      ...prior,
      state,
      items: appendUnique(prior.items, section.items),
      ...messages.length ? { message: messages.join("\n") } : {}
    });
  }
  return [...indexed.values()];
}
function mergeCoverageRows(rows2) {
  const hasData = rows2.some((row5) => row5.state === "available" || row5.receivedItems > 0 || row5.linkedItems > 0);
  const hasProblem = rows2.some((row5) => ["partial", "unavailable", "unknown"].includes(row5.state));
  const state = hasProblem ? hasData || rows2.some((row5) => row5.state === "partial") ? "partial" : rows2.some((row5) => row5.state === "unavailable") ? "unavailable" : "unknown" : rows2.some((row5) => row5.state === "available") ? "available" : "empty";
  return {
    ticker: rows2[0].ticker,
    sectionId: rows2[0].sectionId,
    state,
    upstreamStates: uniqueSorted(rows2.flatMap((row5) => row5.upstreamStates)),
    messages: uniqueSorted(rows2.flatMap((row5) => row5.messages)),
    receivedItems: rows2.reduce((total, row5) => total + row5.receivedItems, 0),
    linkedItems: rows2.reduce((total, row5) => total + row5.linkedItems, 0),
    omittedItems: rows2.reduce((total, row5) => total + row5.omittedItems, 0),
    collectionCompleteness: "unknown"
  };
}
function mergedCoverage(legacy, analysis) {
  const groups = /* @__PURE__ */ new Map();
  for (const row5 of [...legacy.coverage.sources, ...analysis.coverage.sources]) {
    const key = `${row5.ticker}\0${row5.sectionId}`;
    groups.set(key, [...groups.get(key) || [], row5]);
  }
  const sources = [...groups.values()].map(mergeCoverageRows).sort((a, b) => order2(`${a.ticker}\0${a.sectionId}`, `${b.ticker}\0${b.sectionId}`));
  return {
    total: sources.length,
    available: sources.filter((row5) => row5.state === "available").length,
    empty: sources.filter((row5) => row5.state === "empty").length,
    partial: sources.filter((row5) => row5.state === "partial").length,
    unavailable: sources.filter((row5) => row5.state === "unavailable").length,
    unknown: sources.filter((row5) => row5.state === "unknown").length,
    sources
  };
}
function companyIndex(graph, label2) {
  const result = /* @__PURE__ */ new Map();
  for (const company of graph.companies) {
    if (result.has(company.id)) throw new Error(`duplicate-${label2}-company`);
    result.set(company.id, company);
  }
  return result;
}
function mergeAutomatic(legacy = [], analysis = []) {
  const relations = new Map(legacy.map((row5) => [row5.id, row5]));
  for (const row5 of analysis) relations.set(row5.id, row5);
  return [...relations.values()].sort((a, b) => order2(a.id, b.id));
}
function mergeNotice(legacy, analysis, totalDocuments) {
  const notices = appendUnique(legacy ? [legacy] : [], analysis ? [analysis] : []);
  if (totalDocuments > MAX_DOCUMENTS) notices.push(`통합 원문 ${MAX_DOCUMENTS}/${totalDocuments}건 표시`);
  return notices.length ? notices.join(" · ") : void 0;
}
async function mergePortfolioAnalysisGraphs(legacy, analysis) {
  const oldCompanies = companyIndex(legacy, "legacy"), newCompanies = companyIndex(analysis, "analysis");
  const universe = (companies2, label2) => [...companies2.values()].map((row5) => {
    const market2 = canonicalMarket(row5.market);
    if (!market2) throw new Error(`portfolio-${label2}-company-market-unknown`);
    return JSON.stringify([row5.id, row5.ticker, market2]);
  }).sort(order2);
  const oldUniverse = universe(oldCompanies, "legacy"), newUniverse = universe(newCompanies, "analysis");
  if (JSON.stringify(oldUniverse) !== JSON.stringify(newUniverse)) throw new Error("portfolio-company-universe-mismatch");
  const companies = [...oldCompanies.values()].sort((a, b) => order2(a.id, b.id)).map((oldCompany) => {
    const newCompany = newCompanies.get(oldCompany.id);
    const sections = mergeSections(oldCompany.sections, newCompany.sections);
    return {
      ...oldCompany,
      market: canonicalMarket(newCompany.market),
      ...sections.length ? { sections } : {},
      ...newCompany.closeQuote !== void 0 ? { closeQuote: newCompany.closeQuote } : oldCompany.closeQuote !== void 0 ? { closeQuote: oldCompany.closeQuote } : {}
    };
  });
  const documents = /* @__PURE__ */ new Map();
  for (const [label2, graph] of [["legacy", legacy], ["analysis", analysis]]) {
    const seen = /* @__PURE__ */ new Set();
    for (const document2 of graph.documents) {
      if (seen.has(document2.id)) throw new Error(`duplicate-${label2}-document`);
      seen.add(document2.id);
      const prior = documents.get(document2.id);
      if (prior && prior.url !== document2.url) throw new Error("portfolio-document-identity-conflict");
      documents.set(document2.id, { url: document2.url, evidence: [...prior?.evidence || [], ...document2.evidence] });
    }
  }
  const documentEntries = [...documents.entries()].sort(([idA, a], [idB, b]) => {
    const dateA = latestSourceDate(a.evidence), dateB = latestSourceDate(b.evidence);
    return dateA === dateB ? order2(idA, idB) : dateA === null ? 1 : dateB === null ? -1 : order2(dateB, dateA);
  });
  const rebuilt = await Promise.all(documentEntries.slice(0, MAX_DOCUMENTS).map(([id, value]) => rebuildDocument(id, value.url, value.evidence)));
  const links = rebuilt.flatMap((document2) => document2.tickers.map((ticker) => {
    const evidence = document2.evidence.filter((row5) => row5.ticker === ticker);
    return {
      id: `link:${ticker}:${document2.id}`,
      companyId: `company:${ticker}`,
      documentId: document2.id,
      ticker,
      ...summarize2(evidence),
      evidence
    };
  }));
  const automaticRelations = mergeAutomatic(legacy.automaticRelations, analysis.automaticRelations);
  const marketContext = analysis.marketContext ?? legacy.marketContext;
  const contractEvents = analysis.contractEvents ?? legacy.contractEvents;
  const analysisNotice = mergeNotice(legacy.analysisNotice, analysis.analysisNotice, documentEntries.length);
  return {
    companies,
    documents: rebuilt,
    links,
    commonItems: rebuilt.filter((document2) => document2.tickers.length >= 2),
    coverage: mergedCoverage(legacy, analysis),
    ...automaticRelations.length ? { automaticRelations } : {},
    ...marketContext ? { marketContext } : {},
    ...contractEvents ? { contractEvents } : {},
    ...analysis.aiReviewStatus ? { aiReviewStatus: analysis.aiReviewStatus } : {},
    ...analysisNotice ? { analysisNotice } : {}
  };
}
function preserveIncompletePortfolioGraph(previous, incoming) {
  const universe = (graph) => graph.companies.map((row5) => JSON.stringify([row5.id, row5.ticker, canonicalMarket(row5.market)])).sort(order2);
  if (JSON.stringify(universe(previous)) !== JSON.stringify(universe(incoming))) throw new Error("portfolio-company-universe-mismatch");
  if (incoming.aiReviewStatus !== "ready") {
    const priorAI = (previous.automaticRelations || []).filter((row5) => row5.id.startsWith("automatic:ai:"));
    if (priorAI.length) incoming = {
      ...incoming,
      automaticRelations: mergeAutomatic(priorAI, incoming.automaticRelations),
      analysisNotice: [incoming.analysisNotice, `AI 자료 갱신 미완료 · 이전 후보 ${priorAI.length}건 유지`].filter(Boolean).join(" · ")
    };
  }
  const key = (row5) => `${row5.ticker}\0${row5.sectionId}`;
  const tickers = new Set(incoming.companies.map((row5) => row5.ticker));
  const sources = /* @__PURE__ */ new Map();
  for (const row5 of incoming.coverage.sources) {
    if (!tickers.has(row5.ticker) || !["business", "events"].includes(row5.sectionId) || !["available", "empty", "partial", "unavailable", "unknown"].includes(row5.state) || sources.has(key(row5))) throw new Error("invalid-refresh-coverage");
    sources.set(key(row5), row5);
  }
  for (const row5 of previous.coverage.sources) if (!sources.has(key(row5))) {
    sources.set(key(row5), {
      ...row5,
      state: "unknown",
      upstreamStates: [],
      messages: ["이번 조회에서 이 자료의 수집 상태를 받지 못했어요."],
      receivedItems: 0,
      linkedItems: 0,
      omittedItems: 0,
      collectionCompleteness: "unknown"
    });
  }
  const incomplete = new Set([...sources.values()].filter((row5) => ["partial", "unavailable", "unknown"].includes(row5.state)).map(key));
  if (!incomplete.size) return incoming;
  const documents = new Map(incoming.documents.map((row5) => [row5.id, row5]));
  if (documents.size !== incoming.documents.length) throw new Error("duplicate-refresh-document");
  const retained = /* @__PURE__ */ new Set();
  const association = (row5) => JSON.stringify([row5.ticker, row5.sectionId, row5.kind, row5.source]);
  const counts = (evidence) => {
    const result = /* @__PURE__ */ new Map();
    for (const row5 of evidence) result.set(association(row5), (result.get(association(row5)) || 0) + 1);
    return result;
  };
  for (const old of previous.documents) {
    const next = documents.get(old.id);
    if (next && next.url !== old.url) throw new Error("portfolio-document-identity-conflict");
    const received = counts(next?.evidence || []), prior = counts(old.evidence);
    if (old.evidence.some((row5) => incomplete.has(key(row5)) && (received.get(association(row5)) || 0) < prior.get(association(row5)))) {
      documents.set(old.id, old);
      retained.add(old.id);
    }
  }
  let slots = Math.max(MAX_DOCUMENTS, retained.size) - retained.size;
  const displayed = [...documents.values()].filter((row5) => retained.has(row5.id) || slots-- > 0);
  const displayedIds = new Set(displayed.map((row5) => row5.id));
  const links = [
    ...incoming.links.filter((row5) => !retained.has(row5.documentId)),
    ...previous.links.filter((row5) => retained.has(row5.documentId))
  ].filter((row5) => displayedIds.has(row5.documentId));
  const rows2 = [...sources.values()];
  const notice = `${incomplete.size}/${rows2.length}개 자료 범위 갱신 미완료 · 이전 조회 원문 ${retained.size}건 유지`;
  const deferred = documents.size - displayed.length;
  return {
    ...incoming,
    documents: displayed,
    links,
    commonItems: displayed.filter((row5) => row5.tickers.length >= 2),
    coverage: {
      total: rows2.length,
      available: rows2.filter((row5) => row5.state === "available").length,
      empty: rows2.filter((row5) => row5.state === "empty").length,
      partial: rows2.filter((row5) => row5.state === "partial").length,
      unavailable: rows2.filter((row5) => row5.state === "unavailable").length,
      unknown: rows2.filter((row5) => row5.state === "unknown").length,
      sources: rows2
    },
    analysisNotice: [
      incoming.analysisNotice,
      notice,
      deferred ? `표시 한도로 새 원문 ${deferred}건 반영 보류` : void 0
    ].filter(Boolean).join(" · ")
  };
}

// framer-components/public-probe/PortfolioMapWorkspace.tsx
var API = "https://project-yw131.vercel.app";
var clone = (value) => JSON.parse(JSON.stringify(value));
var sameAccount = (a, b) => a?.userId === b?.userId;
var empty = (privateState) => ({
  phase: "signed-out",
  holdings: [],
  watchlist: [],
  watchlistError: null,
  watchlistUnsupportedCount: 0,
  exploratory: [],
  unsupportedCount: 0,
  selectedTickers: [],
  graph: null,
  privateState,
  error: null,
  dataRefresh: { phase: "idle", checkedAt: null, error: null }
});
function workspaceStocks(state) {
  const watched = new Set((state.watchlist || []).map((row5) => `${row5.market}:${row5.ticker}`));
  const stocks = new Map(state.holdings.map((row5) => [row5.ticker, { ticker: row5.ticker, name: row5.name, market: row5.market, held: true, watched: watched.has(`${row5.market}:${row5.ticker}`), exploring: false }]));
  for (const row5 of state.watchlist || []) if (!stocks.has(row5.ticker)) stocks.set(row5.ticker, { ...row5, held: false, watched: true, exploring: false });
  for (const row5 of state.exploratory || []) if (!stocks.has(row5.ticker)) stocks.set(row5.ticker, { ...row5, held: false, watched: false, exploring: true });
  return [...stocks.values()];
}
var finitePositive = (value) => {
  if (typeof value !== "number" && typeof value !== "string") return null;
  if (typeof value === "string" && !value.trim()) return null;
  const parsed = Number(value);
  return Number.isFinite(parsed) && parsed > 0 ? parsed : null;
};
function normalizeMapHoldings(payload) {
  const rows2 = Array.isArray(payload) ? payload : payload?.holdings;
  if (!Array.isArray(rows2)) throw new Error("invalid-holdings-response");
  const holdings = /* @__PURE__ */ new Map();
  let unsupportedCount = 0;
  for (const row5 of rows2) {
    if (!row5 || typeof row5 !== "object" || typeof row5.ticker !== "string") throw new Error("invalid-holdings-response");
    const ticker = row5.ticker.trim().toUpperCase(), market2 = String(row5.market || "").toUpperCase();
    const supported = market2 === "KR" ? /^\d{6}$/.test(ticker) : market2 === "US" && /^[A-Z][A-Z0-9.-]{0,15}$/.test(ticker);
    if (!supported || row5.type === "commodity") {
      unsupportedCount += 1;
      continue;
    }
    const prior = holdings.get(ticker);
    if (prior && prior.market !== market2) throw new Error("ambiguous-holding-market");
    if (prior) {
      const { id: _ambiguousId, ...display } = prior;
      holdings.set(ticker, { ...display, shares: null, avg_cost: null, duplicate: true });
      continue;
    }
    holdings.set(ticker, {
      ticker,
      name: typeof row5.name === "string" && row5.name.trim() ? row5.name.trim() : ticker,
      market: market2,
      shares: finitePositive(row5.shares),
      avg_cost: finitePositive(row5.avg_cost),
      duplicate: false,
      ...typeof row5.id === "string" && row5.id.trim() ? { id: row5.id.trim() } : {},
      ...typeof row5.memo === "string" ? { memo: row5.memo } : {}
    });
  }
  return { holdings: [...holdings.values()], unsupportedCount };
}
function createPortfolioMapWorkspace(options = {}) {
  const getSession = options.getSession || readMapSession, fetcher = options.fetcher || fetch;
  const graphLoader = options.graphLoader || fetchPortfolioMapGraph;
  const usePortfolioAnalysis = options.usePortfolioAnalysis === true;
  let disposed = false;
  const store = createMemberMapStore({ getSession, fetcher: (input, init) => disposed ? Promise.reject(new Error("workspace-disposed")) : fetcher(input, init) });
  let state = empty(store.getState()), account = null, generation = 0;
  let automaticSelection = true;
  let pending = null;
  let refreshController = null;
  let refreshPromise = null;
  let stagedGraph = null;
  let explorationLoading = false;
  const cancelDataRefresh = () => {
    refreshController?.abort();
    refreshController = null;
    refreshPromise = null;
    stagedGraph = null;
    explorationLoading = false;
    state = { ...state, dataRefresh: { phase: "idle", checkedAt: null, error: null } };
  };
  const listeners = /* @__PURE__ */ new Set();
  const authCleanups = /* @__PURE__ */ new Set();
  const timers = /* @__PURE__ */ new Set();
  const emit = () => {
    if (disposed) return;
    currentAccount();
    for (const listener of listeners) {
      if (disposed) break;
      currentAccount();
      listener(clone(state));
    }
  };
  const reset = (notify = true) => {
    cancelDataRefresh();
    explorationLoading = false;
    generation += 1;
    pending?.abort();
    pending = null;
    automaticSelection = true;
    state = empty({ phase: "signed-out", document: null, revision: null, dirty: false, error: null });
    if (notify) emit();
  };
  const currentAccount = () => {
    if (disposed) return false;
    if (!sameAccount(account, getSession())) {
      account = null;
      reset(false);
      return false;
    }
    return true;
  };
  const valid = (version) => {
    if (!currentAccount()) {
      emit();
      return false;
    }
    return generation === version;
  };
  const unsubscribe = store.subscribe((privateState) => {
    if (!currentAccount()) {
      emit();
      return;
    }
    state = { ...state, privateState };
    emit();
  });
  const loadGraph = (codes, signal, exploratory) => {
    if (options.graphLoader || !usePortfolioAnalysis) return graphLoader(codes, API, signal);
    const stocks = new Map(workspaceStocks(state).map((row5) => [row5.ticker, row5]));
    if (exploratory && !stocks.has(exploratory.ticker)) stocks.set(exploratory.ticker, { ...exploratory, held: false, watched: false, exploring: true });
    const positions = codes.map((ticker) => {
      const stock = stocks.get(ticker);
      if (!stock || stock.market !== "KR" && stock.market !== "US") throw new Error("invalid-analysis-position-market");
      return { ticker: stock.ticker, market: stock.market };
    });
    if (!account) return Promise.reject(new Error("authentication-required"));
    return Promise.all([
      fetchPortfolioAnalysisGraph(positions, { getSession, ownerId: account.userId, fetcher, signal }),
      (options.analysisSourceLoader || fetchPortfolioMapGraph)(codes, API, signal)
    ]).then(([analysis, legacy]) => mergePortfolioAnalysisGraphs(legacy, analysis));
  };
  const showTickers = async (tickers, fromOpen = false) => {
    if (!account || !valid(generation)) return false;
    const codes = [...new Set(tickers.map((ticker) => ticker.trim().toUpperCase()))];
    if (codes.length > 30 || codes.some((code) => !workspaceStocks(state).some((row5) => row5.ticker === code))) throw new Error("choose-up-to-30-holdings");
    if (!fromOpen) automaticSelection = false;
    cancelDataRefresh();
    pending?.abort();
    pending = new AbortController();
    const signal = pending.signal, version = ++generation;
    state = { ...state, phase: "loading", selectedTickers: codes, graph: null, error: null };
    emit();
    try {
      if (!valid(version) || signal.aborted) return false;
      const graph = await loadGraph(codes, signal);
      if (!valid(version) || signal.aborted) return false;
      if (graph.companies.length !== codes.length || new Set(graph.companies.map((row5) => row5.ticker)).size !== codes.length || graph.companies.some((row5) => !codes.includes(row5.ticker))) throw new Error("graph-holdings-mismatch");
      state = { ...state, phase: "ready", graph };
      emit();
      return valid(version);
    } catch (error) {
      if (!valid(version) || signal.aborted) return false;
      state = { ...state, phase: "error", graph: null, error: error instanceof Error ? error.message : "data-unavailable" };
      emit();
      return false;
    }
  };
  const exploreStock = async (metadata) => {
    if (!account || !valid(generation) || state.phase !== "ready" || !state.graph) return false;
    if (!metadata || typeof metadata.ticker !== "string" || typeof metadata.name !== "string" || !metadata.name.trim() || metadata.ticker !== metadata.ticker.trim() || !(metadata.market === "KR" ? /^\d{6}$/.test(metadata.ticker) : metadata.market === "US" && /^[A-Z][A-Z0-9.-]{0,15}$/.test(metadata.ticker))) throw new Error("invalid-exploratory-stock");
    const stock = { ticker: metadata.ticker, name: metadata.name.trim(), market: metadata.market };
    const known = workspaceStocks(state).find((row5) => row5.ticker === stock.ticker);
    if (known && known.market !== stock.market) throw new Error("ambiguous-exploratory-market");
    const codes = [.../* @__PURE__ */ new Set([...state.selectedTickers, stock.ticker])];
    if (codes.length > 30) throw new Error("choose-up-to-30-holdings");
    if (state.selectedTickers.includes(stock.ticker)) return true;
    cancelDataRefresh();
    explorationLoading = true;
    pending?.abort();
    const controller = new AbortController();
    pending = controller;
    const version = ++generation, signal = controller.signal;
    try {
      const graph = await loadGraph([...codes], signal, stock);
      if (!valid(version) || signal.aborted) return false;
      if (graph.companies.length !== codes.length || new Set(graph.companies.map((row5) => row5.ticker)).size !== codes.length || graph.companies.some((row5) => !codes.includes(row5.ticker) || typeof row5.id !== "string" || !row5.id.trim()) || new Set(graph.companies.map((row5) => row5.id)).size !== codes.length) throw new Error("graph-exploration-mismatch");
      const companies = graph.companies.map((company) => company.ticker === stock.ticker && (!company.name.trim() || company.name.trim() === company.ticker) ? { ...company, name: known?.name || stock.name } : company);
      automaticSelection = false;
      state = {
        ...state,
        graph: { ...graph, companies },
        selectedTickers: codes,
        exploratory: known ? state.exploratory : [...state.exploratory || [], stock]
      };
      emit();
      return valid(version);
    } catch {
      valid(version);
      return false;
    } finally {
      if (generation === version) explorationLoading = false;
      if (pending === controller) pending = null;
    }
  };
  const open = async () => {
    if (disposed) return false;
    cancelDataRefresh();
    explorationLoading = false;
    const next = getSession(), changed = !sameAccount(account, next);
    if (changed) {
      account = next;
      reset();
    } else {
      account = next;
      pending?.abort();
    }
    if (!valid(generation) || !sameAccount(account, next)) return false;
    const restore = store.syncSession();
    if (!next) {
      await restore;
      return false;
    }
    if (!valid(generation) || !sameAccount(account, next)) return false;
    const version = ++generation, controller = new AbortController();
    pending = controller;
    const timer = setTimeout(() => controller.abort(), 15e3);
    timers.add(timer);
    const watchController = new AbortController();
    const cancelWatch = () => watchController.abort();
    controller.signal.addEventListener("abort", cancelWatch, { once: true });
    const watchTimer = options.includeWatchlist ? setTimeout(cancelWatch, 5e3) : null;
    if (watchTimer) timers.add(watchTimer);
    state = { ...state, phase: "loading", error: null };
    emit();
    try {
      if (!valid(version) || controller.signal.aborted) return false;
      const watchResult = options.includeWatchlist ? fetchMapWatchlist({ api: API, getSession, ownerId: next.userId, fetcher, signal: watchController.signal }).then((value) => ({ ...value, error: null }), (error) => ({ stocks: [], unsupportedCount: 0, error: error instanceof Error ? error.message : "watchlist-unavailable" })) : Promise.resolve({ stocks: [], unsupportedCount: 0, error: null });
      const requestSession = getSession();
      if (!requestSession || !sameAccount(next, requestSession) || !valid(version) || controller.signal.aborted) return false;
      const requestHoldings = (token) => fetcher(API + "/api/holdings", {
        headers: { Authorization: "Bearer " + token },
        signal: controller.signal,
        cache: "no-store",
        credentials: "omit",
        redirect: "error"
      });
      let response = await requestHoldings(requestSession.token);
      if (!valid(version) || controller.signal.aborted) return false;
      if (response.status === 401) {
        const refreshed = getSession();
        if (refreshed?.token && sameAccount(next, refreshed) && refreshed.token !== requestSession.token && valid(version) && !controller.signal.aborted) response = await requestHoldings(refreshed.token);
      }
      if (!valid(version) || controller.signal.aborted) return false;
      if (!response.ok) throw new Error(response.status === 401 ? "authentication-required" : "holdings-unavailable");
      const result = normalizeMapHoldings(await response.json());
      if (!valid(version) || controller.signal.aborted) return false;
      const watch = await watchResult;
      if (!valid(version) || controller.signal.aborted) return false;
      state = { ...state, ...result, watchlist: watch.stocks, watchlistError: watch.error, watchlistUnsupportedCount: watch.unsupportedCount };
      const stocks = workspaceStocks(state);
      const previous = state.selectedTickers.filter((code) => stocks.some((row5) => row5.ticker === code));
      if (stocks.length > 30 && (automaticSelection || !previous.length)) {
        state = { ...state, phase: "choose-stocks", graph: null, selectedTickers: [] };
        emit();
        await restore;
        return valid(version);
      }
      const success = await showTickers(!automaticSelection && previous.length ? previous : stocks.map((row5) => row5.ticker), true);
      const graphVersion = generation;
      await restore;
      return success && valid(graphVersion) && sameAccount(next, getSession());
    } catch (error) {
      if (!valid(version)) return false;
      state = { ...state, phase: "error", holdings: [], watchlist: [], graph: null, error: error instanceof Error ? error.message : "holdings-unavailable" };
      emit();
      await restore;
      return false;
    } finally {
      clearTimeout(timer);
      timers.delete(timer);
      if (watchTimer) {
        clearTimeout(watchTimer);
        timers.delete(watchTimer);
      }
      controller.signal.removeEventListener("abort", cancelWatch);
      watchController.abort();
    }
  };
  const refreshData = () => {
    if (!account || !valid(generation) || disposed || explorationLoading || state.phase !== "ready" || !state.graph) return Promise.resolve(false);
    if (refreshPromise) return refreshPromise;
    const version = generation, codes = [...state.selectedTickers], controller = new AbortController();
    refreshController = controller;
    const current = () => !disposed && valid(version) && refreshController === controller;
    const checkedAt = state.dataRefresh?.checkedAt || null;
    state = { ...state, dataRefresh: { phase: "checking", checkedAt, error: null } };
    const task = Promise.resolve().then(async () => {
      const timer = setTimeout(() => controller.abort(), 12e4);
      timers.add(timer);
      try {
        if (!current() || controller.signal.aborted) return false;
        const received = await loadGraph(codes, controller.signal);
        if (!current()) return false;
        if (controller.signal.aborted) throw new Error("data-refresh-timeout");
        if (received.companies.length !== codes.length || new Set(received.companies.map((row5) => row5.ticker)).size !== codes.length || received.companies.some((row5) => !codes.includes(row5.ticker))) throw new Error("graph-holdings-mismatch");
        const graph = preserveIncompletePortfolioGraph(state.graph, received);
        const incompleteSources = graph.coverage.sources.filter((row5) => ["unavailable", "partial", "unknown"].includes(row5.state)).length;
        const content = (value) => JSON.stringify(value, (key, item) => key === "observedAt" ? void 0 : item);
        stagedGraph = content(graph) === content(state.graph) ? null : graph;
        state = { ...state, dataRefresh: {
          phase: stagedGraph ? "available" : "idle",
          checkedAt: (/* @__PURE__ */ new Date()).toISOString(),
          error: null,
          incompleteSources,
          totalSources: graph.coverage.sources.length
        } };
        emit();
        return true;
      } catch (error) {
        if (!current()) return false;
        stagedGraph = null;
        state = { ...state, dataRefresh: { phase: "error", checkedAt, error: error instanceof Error ? error.message : "data-refresh-unavailable" } };
        emit();
        return false;
      } finally {
        clearTimeout(timer);
        timers.delete(timer);
        if (refreshController === controller) {
          refreshController = null;
          refreshPromise = null;
        }
      }
    });
    refreshPromise = task;
    emit();
    return task;
  };
  return {
    getState() {
      currentAccount();
      return clone(state);
    },
    subscribe(listener) {
      if (disposed) return () => {
      };
      currentAccount();
      listeners.add(listener);
      listener(clone(state));
      return () => {
        listeners.delete(listener);
      };
    },
    open,
    showTickers,
    exploreStock,
    refreshData,
    applyDataUpdate() {
      if (!account || !valid(generation) || disposed || state.phase !== "ready" || state.dataRefresh?.phase !== "available" || !stagedGraph) return false;
      const graph = stagedGraph;
      stagedGraph = null;
      state = { ...state, graph, dataRefresh: { ...state.dataRefresh, phase: "idle" } };
      emit();
      return true;
    },
    /** Standalone-view opt-in. Hidden/offline tabs do not poll, focus is throttled,
     * and new evidence is never automatically applied over the active canvas.
     */
    bindDataRefresh(target) {
      if (disposed) return () => {
      };
      let stopped = false, lastAttempt = Date.now();
      const interval = 5 * 60 * 1e3;
      const check = () => {
        if (stopped || disposed || target.document.visibilityState !== "visible" || target.navigator.onLine === false || Date.now() - lastAttempt < interval || state.phase !== "ready" || state.dataRefresh?.phase === "checking" || state.dataRefresh?.phase === "available" || explorationLoading) return;
        lastAttempt = Date.now();
        void refreshData();
      };
      let timer;
      const schedule = () => {
        timer = setTimeout(() => {
          timers.delete(timer);
          check();
          if (!stopped && !disposed) schedule();
        }, interval);
        timers.add(timer);
      };
      schedule();
      target.addEventListener("focus", check);
      target.addEventListener("online", check);
      target.document.addEventListener("visibilitychange", check);
      const cleanup = () => {
        stopped = true;
        clearTimeout(timer);
        timers.delete(timer);
        target.removeEventListener("focus", check);
        target.removeEventListener("online", check);
        target.document.removeEventListener("visibilitychange", check);
        authCleanups.delete(cleanup);
      };
      authCleanups.add(cleanup);
      return cleanup;
    },
    editLayout(mapKey, change) {
      if (!valid(generation)) return false;
      return store.update((document2) => editMapLayout(document2, mapKey, change));
    },
    markDocument(mapKey, id, change) {
      if (!valid(generation)) return false;
      const document2 = state.graph?.documents.find((row5) => row5.id === id);
      if (!document2) return false;
      return store.update((value) => editMapLayout(value, mapKey, (layout) => {
        const prior = layout.marks[id] || { read_revision: null, important: false, disposition: "inbox" };
        const mark = {
          read_revision: change.read === void 0 ? prior.read_revision : change.read ? document2.read_revision : null,
          important: change.important ?? prior.important,
          disposition: change.disposition ?? prior.disposition
        };
        return { ...layout, marks: { ...layout.marks, [id]: mark } };
      }));
    },
    /** read_revision fingerprints the available evidence/excerpt set. Membership changes
     * may change that set without any source-document edit. UI label: "확인할 자료 변경",
     * never "원문 새 버전"; compare equality only, not an increasing version number.
     */
    documentsToReview(mapKey) {
      if (!valid(generation)) return [];
      const marks = state.privateState.document?.layouts.find((row5) => row5.map_key === mapKey)?.marks || {};
      return (state.graph?.documents || []).filter((row5) => marks[row5.id]?.disposition !== "irrelevant" && mapReadState(marks[row5.id], row5.read_revision) !== "read");
    },
    save: () => valid(generation) ? store.save() : Promise.resolve(false),
    reloadSaved: (discardDraft = false) => valid(generation) ? store.load(discardDraft) : Promise.resolve(false),
    /** Subscribe once from the mounted AlphaNest view. No token is sent to an iframe. */
    bindAuth(target) {
      if (disposed) return () => {
      };
      const onAuth = (event) => {
        if (event.type === "storage" && event.key && event.key !== "verity_supabase_session") return;
        const next = getSession();
        if (next && account && sameAccount(account, next) && (state.phase === "ready" || state.phase === "choose-stocks")) {
          account = next;
          void store.syncSession();
          return;
        }
        void open();
      };
      const beforeUnload = (event) => {
        if (!valid(generation)) return;
        if (store.getState().dirty) {
          event.preventDefault();
          event.returnValue = "";
        }
      };
      target.addEventListener("verity_auth_change", onAuth);
      target.addEventListener("storage", onAuth);
      target.addEventListener("beforeunload", beforeUnload);
      const cleanup = () => {
        target.removeEventListener("verity_auth_change", onAuth);
        target.removeEventListener("storage", onAuth);
        target.removeEventListener("beforeunload", beforeUnload);
        authCleanups.delete(cleanup);
      };
      authCleanups.add(cleanup);
      return cleanup;
    },
    dispose() {
      if (disposed) return;
      cancelDataRefresh();
      disposed = true;
      listeners.clear();
      authCleanups.forEach((cleanup) => cleanup());
      timers.forEach((timer) => clearTimeout(timer));
      timers.clear();
      pending?.abort();
      unsubscribe();
      store.dispose();
      account = null;
      reset(false);
    }
  };
}

// framer-components/public-probe/PortfolioPrototypeAdapter.ts
var PROTOTYPE_WORLD_WIDTH = 1e3;
var PROTOTYPE_WORLD_HEIGHT = 680;
function normalizeWorldPoint(point2) {
  return { x: 0.5 + point2.x / PROTOTYPE_WORLD_WIDTH, y: 0.5 + point2.y / PROTOTYPE_WORLD_HEIGHT };
}
function prototypeLayoutFromMember(layout) {
  return {
    mapKey: layout.map_key,
    positions: layout.positions.map((position2) => ({
      nodeId: position2.node_id,
      ...normalizeWorldPoint(position2),
      pixelX: position2.x,
      pixelY: position2.y
    })),
    notes: layout.notes.map((note) => ({
      id: note.note_id,
      anchor: note.anchor ? { ...note.anchor } : null,
      ...normalizeWorldPoint(note),
      pixelX: note.x,
      pixelY: note.y,
      text: note.text,
      done: note.done
    })),
    marks: copyMarks(layout.marks)
  };
}
function projectWorkspaceToPrototype(state, mapKey = "main") {
  if (state.phase !== "ready" || !state.graph) return { nodes: [], edges: [], layout: null };
  const memberLayout = state.privateState.document?.layouts.find((layout2) => layout2.map_key === mapKey);
  const layout = memberLayout ? prototypeLayoutFromMember(memberLayout) : null;
  const positions = new Map(layout?.positions.map((position2) => [position2.nodeId, position2]));
  const graphNodes = [...state.graph.companies, ...state.graph.documents];
  const fallback = (id) => fallbackPoint(graphNodes.findIndex((node) => node.id === id), graphNodes.length);
  const pointFor = (id) => positions.get(id) || fallback(id);
  const stocks = state.graph.companies.map((company) => {
    const point2 = pointFor(company.id);
    return {
      id: company.id,
      name: company.name,
      code: company.ticker,
      logo: company.ticker.slice(0, 1),
      kind: "stock",
      priority: 2,
      reason: null,
      source: null,
      asOf: null,
      evidence: [],
      x: point2.x,
      y: point2.y
    };
  });
  const documents = state.graph.documents.map((document2) => {
    const point2 = pointFor(document2.id);
    return {
      id: document2.id,
      name: document2.title,
      code: document2.source,
      kind: "event",
      layer: documentLayer(document2),
      priority: 2,
      reason: document2.reason,
      source: document2.source,
      asOf: document2.asOf || null,
      evidence: document2.evidence.map(projectEvidence),
      x: point2.x,
      y: point2.y
    };
  });
  return { nodes: [...stocks, ...documents], edges: state.graph.links.map(projectLink), layout };
}
function copyMarks(marks) {
  return Object.fromEntries(Object.entries(marks).map(([id, mark]) => [id, { ...mark }]));
}
function fallbackPoint(index, count) {
  const safeIndex = Math.max(index, 0);
  const columns = Math.max(1, Math.ceil(Math.sqrt(Math.max(count, 1))));
  const rows2 = Math.ceil(Math.max(count, 1) / columns);
  return { x: 0.5 + (safeIndex % columns + 0.5) / columns, y: 0.5 + (Math.floor(safeIndex / columns) + 0.5) / rows2 };
}
function documentLayer(document2) {
  const kind = document2.evidence[0]?.kind;
  if (kind === "disclosure") return "filing";
  if (kind === "news") return "news";
  if (kind === "business") return "business";
  return "other";
}
function projectEvidence(evidence) {
  return {
    ticker: evidence.ticker,
    source: evidence.source,
    asOf: evidence.asOf || null,
    url: evidence.url || null,
    reason: evidence.reason,
    explanation: evidence.explanation,
    confirmation: evidence.confirmation
  };
}
function projectLink(link) {
  return {
    id: link.id,
    from: link.documentId,
    to: link.companyId,
    reason: link.reason,
    source: link.source,
    asOf: link.asOf || null,
    evidence: link.evidence.map(projectEvidence),
    influence: "unknown"
  };
}

// framer-components/public-probe/PortfolioReviewedFacts.tsx
var LIMITS = {
  holdings: 200,
  sources: 200,
  relationships: 200,
  events: 100,
  sourceIds: 20,
  participants: 50,
  id: 128,
  factId: 90,
  label: 160,
  prose: 2e3,
  url: 2048
};
var SOURCE_KEYS = ["id", "url", "publisher", "publishedAt", "statement"];
var RELATIONSHIP_KEYS = ["id", "from", "to", "label", "asOf", "status", "sourceIds", "limitations", "review", "impact"];
var EVENT_KEYS = ["id", "title", "date", "status", "participants", "sourceIds", "mergeBasis", "review", "impact"];
var ENTITY_KEYS = ["ticker", "market"];
var PARTICIPANT_KEYS = ["ticker", "market", "role", "sourceIds"];
var failure = (reason) => ({ ok: false, reason });
var record7 = (value) => value !== null && typeof value === "object" && !Array.isArray(value) ? value : null;
function exactRecord(value, keys2) {
  const item = record7(value);
  if (!item) return null;
  const actual = Object.keys(item);
  return actual.length === keys2.length && actual.every((key) => keys2.includes(key)) ? item : null;
}
var text12 = (value, max) => {
  if (typeof value !== "string" || /[\u0000-\u0008\u000b\u000c\u000e-\u001f\u007f]/.test(value)) return null;
  const clean = value.trim();
  return clean && clean.length <= max ? clean : null;
};
var stableId = (value, max = LIMITS.id) => {
  const clean = text12(value, max);
  return clean && /^[A-Za-z0-9][A-Za-z0-9:._-]*$/.test(clean) ? clean : null;
};
function dateOnly2(value) {
  const raw = text12(value, 10), match = raw && /^(\d{4})-(\d{2})-(\d{2})$/.exec(raw);
  if (!match || Number(match[1]) < 1900) return null;
  const time = Date.parse(raw + "T00:00:00Z");
  return Number.isFinite(time) && new Date(time).toISOString().slice(0, 10) === raw ? raw : null;
}
function secureUrl(value) {
  const raw = text12(value, LIMITS.url);
  if (!raw) return null;
  try {
    const parsed = new URL(raw);
    return parsed.protocol === "https:" && !!parsed.hostname && !parsed.username && !parsed.password ? parsed.href : null;
  } catch {
    return null;
  }
}
function normalizeMarket(value) {
  if (typeof value !== "string") return null;
  const normalized = value.trim().toUpperCase();
  return normalized === "KR" || normalized === "US" ? normalized : null;
}
function normalizeTicker(value, market2) {
  if (typeof value !== "string") return null;
  const normalized = value.trim().toUpperCase();
  if (market2 === "KR") return /^\d{6}$/.test(normalized) ? normalized : null;
  return normalized.length <= 15 && /^[A-Z][A-Z0-9]*(?:[.-][A-Z0-9]+)*$/.test(normalized) ? normalized : null;
}
var entityKey = (entity3) => `${entity3.market}:${entity3.ticker}`;
function parseEntity(value, exactKeys2 = ENTITY_KEYS) {
  const item = exactRecord(value, exactKeys2), market2 = item && normalizeMarket(item.market);
  if (!item || !market2 || item.market !== market2) return null;
  const ticker = normalizeTicker(item.ticker, market2);
  return ticker && item.ticker === ticker ? { ticker, market: market2 } : null;
}
function parseIdList(value, sourceIds, path, minimum = 1) {
  if (!Array.isArray(value) || value.length < minimum || value.length > LIMITS.sourceIds) return failure(path);
  const result = [], seen = /* @__PURE__ */ new Set();
  for (const candidate of value) {
    const id = stableId(candidate);
    if (!id || seen.has(id) || !sourceIds.has(id)) return failure(path);
    seen.add(id);
    result.push(id);
  }
  return { ok: true, value: result };
}
function parseHoldings(value) {
  if (!Array.isArray(value) || value.length > LIMITS.holdings) return failure("holdings.shape");
  const result = [], seen = /* @__PURE__ */ new Set();
  for (let index = 0; index < value.length; index++) {
    const item = exactRecord(value[index], ENTITY_KEYS), market2 = item && normalizeMarket(item.market);
    const ticker = market2 && item ? normalizeTicker(item.ticker, market2) : null;
    if (!item || !market2 || !ticker) return failure(`holdings[${index}]`);
    const entity3 = { ticker, market: market2 }, key = entityKey(entity3);
    if (seen.has(key)) return failure(`holdings[${index}].duplicate`);
    seen.add(key);
    result.push(entity3);
  }
  return { ok: true, value: result };
}
function parseRegistry(value) {
  const registry = exactRecord(value, ["schemaVersion", "reviewedAt", "sources", "relationships", "events"]);
  if (!registry || registry.schemaVersion !== 1) return failure("registry.schemaVersion");
  const reviewedAt = dateOnly2(registry.reviewedAt);
  if (!reviewedAt) return failure("registry.reviewedAt");
  if (!Array.isArray(registry.sources) || registry.sources.length > LIMITS.sources) return failure("registry.sources");
  if (!Array.isArray(registry.relationships) || registry.relationships.length > LIMITS.relationships) return failure("registry.relationships");
  if (!Array.isArray(registry.events) || registry.events.length > LIMITS.events) return failure("registry.events");
  const sources = [], sourceIds = /* @__PURE__ */ new Set(), allIds = /* @__PURE__ */ new Set();
  for (let index = 0; index < registry.sources.length; index++) {
    const item = exactRecord(registry.sources[index], SOURCE_KEYS);
    const id = item && stableId(item.id), url = item && secureUrl(item.url);
    const publisher = item && text12(item.publisher, LIMITS.label), publishedAt = item && dateOnly2(item.publishedAt);
    const statement = item && text12(item.statement, LIMITS.prose);
    if (!item || !id || !url || !publisher || !publishedAt || publishedAt > reviewedAt || !statement || allIds.has(id))
      return failure(`registry.sources[${index}]`);
    sourceIds.add(id);
    allIds.add(id);
    sources.push({ id, url, publisher, publishedAt, statement });
  }
  const relationships = [];
  for (let index = 0; index < registry.relationships.length; index++) {
    const item = exactRecord(registry.relationships[index], RELATIONSHIP_KEYS);
    const id = item && stableId(item.id, LIMITS.factId), from = item && parseEntity(item.from), to = item && parseEntity(item.to);
    const label2 = item && text12(item.label, LIMITS.label), asOf = item && dateOnly2(item.asOf);
    const limitations = item && text12(item.limitations, LIMITS.prose);
    const refs = item ? parseIdList(item.sourceIds, sourceIds, `registry.relationships[${index}].sourceIds`, 2) : failure("relationship");
    if (!item || !id || !from || !to || entityKey(from) === entityKey(to) || !label2 || !asOf || asOf > reviewedAt || !limitations || !refs.ok || !["historical-announcement", "dated-fact"].includes(item.status) || item.review !== "manual-primary-source-comparison" || item.impact !== "unknown" || allIds.has(id))
      return failure(`registry.relationships[${index}]`);
    allIds.add(id);
    relationships.push({
      id,
      from,
      to,
      label: label2,
      asOf,
      status: item.status,
      sourceIds: refs.value,
      limitations,
      review: "manual-primary-source-comparison",
      impact: "unknown"
    });
  }
  const events = [];
  for (let index = 0; index < registry.events.length; index++) {
    const item = exactRecord(registry.events[index], EVENT_KEYS);
    const id = item && stableId(item.id, LIMITS.factId), title = item && text12(item.title, LIMITS.label);
    const date2 = item && dateOnly2(item.date), mergeBasis = item && text12(item.mergeBasis, LIMITS.prose);
    const refs = item ? parseIdList(item.sourceIds, sourceIds, `registry.events[${index}].sourceIds`, 2) : failure("event");
    if (!item || !id || !title || !date2 || date2 > reviewedAt || !mergeBasis || !refs.ok || item.status !== "historical-announcement" || item.review !== "manual-primary-source-comparison" || item.impact !== "unknown" || allIds.has(id) || !Array.isArray(item.participants) || item.participants.length < 2 || item.participants.length > LIMITS.participants)
      return failure(`registry.events[${index}]`);
    const allowedRefs = new Set(refs.value), participants2 = [], participantIds = /* @__PURE__ */ new Set();
    for (let participantIndex = 0; participantIndex < item.participants.length; participantIndex++) {
      const participant = exactRecord(item.participants[participantIndex], PARTICIPANT_KEYS);
      const entity3 = participant && parseEntity({ ticker: participant.ticker, market: participant.market });
      const role = participant && text12(participant.role, LIMITS.label);
      const participantRefs = participant ? parseIdList(
        participant.sourceIds,
        allowedRefs,
        `registry.events[${index}].participants[${participantIndex}].sourceIds`
      ) : failure("participant");
      if (!participant || !entity3 || !role || !participantRefs.ok || participantIds.has(entityKey(entity3)))
        return failure(`registry.events[${index}].participants[${participantIndex}]`);
      participantIds.add(entityKey(entity3));
      participants2.push({ ...entity3, role, sourceIds: participantRefs.value });
    }
    allIds.add(id);
    events.push({
      id,
      title,
      date: date2,
      status: "historical-announcement",
      participants: participants2,
      sourceIds: refs.value,
      mergeBasis,
      review: "manual-primary-source-comparison",
      impact: "unknown"
    });
  }
  return { ok: true, value: { schemaVersion: 1, reviewedAt, sources, relationships, events } };
}
function unavailable(status, reason, provided, eligible = 0) {
  return { relationships: [], events: [], coverage: {
    status,
    reason,
    reviewedAt: null,
    holdings: { provided, eligible, matched: 0 },
    sources: { reviewed: 0 },
    relationships: { reviewed: 0, included: 0 },
    events: { reviewed: 0, included: 0 }
  } };
}
function buildReviewedPortfolioFacts(holdings, registry) {
  const parsedHoldings = parseHoldings(holdings);
  const provided = Array.isArray(holdings) ? holdings.length : 0;
  if (!parsedHoldings.ok) return unavailable("invalid-holdings", parsedHoldings.reason, provided);
  const parsedRegistry = parseRegistry(registry);
  if (!parsedRegistry.ok) return unavailable("invalid-registry", parsedRegistry.reason, provided, parsedHoldings.value.length);
  const valid = parsedRegistry.value, holdingKeys = new Set(parsedHoldings.value.map(entityKey));
  const sourcesById = new Map(valid.sources.map((source) => [source.id, source]));
  const matchedKeys = /* @__PURE__ */ new Set();
  const relationships = [];
  for (const relationship of valid.relationships) {
    if (!holdingKeys.has(entityKey(relationship.from)) || !holdingKeys.has(entityKey(relationship.to))) continue;
    matchedKeys.add(entityKey(relationship.from));
    matchedKeys.add(entityKey(relationship.to));
    relationships.push({
      ...relationship,
      from: { ...relationship.from },
      to: { ...relationship.to },
      sourceIds: [...relationship.sourceIds],
      sources: relationship.sourceIds.map((id) => ({ ...sourcesById.get(id) }))
    });
  }
  const events = [];
  for (const event of valid.events) {
    const matchedHoldings = event.participants.filter((participant) => holdingKeys.has(entityKey(participant))).map(({ ticker, market: market2 }) => ({ ticker, market: market2 }));
    if (matchedHoldings.length < 2) continue;
    matchedHoldings.forEach((entity3) => matchedKeys.add(entityKey(entity3)));
    events.push({
      ...event,
      participants: event.participants.map((participant) => ({ ...participant, sourceIds: [...participant.sourceIds] })),
      matchedHoldings,
      sourceIds: [...event.sourceIds],
      sources: event.sourceIds.map((id) => ({ ...sourcesById.get(id) }))
    });
  }
  const status = relationships.length || events.length ? "available" : "empty";
  return { relationships, events, coverage: {
    status,
    reason: status === "empty" ? "no-held-reviewed-facts" : null,
    reviewedAt: valid.reviewedAt,
    holdings: { provided, eligible: parsedHoldings.value.length, matched: matchedKeys.size },
    sources: { reviewed: valid.sources.length },
    relationships: { reviewed: valid.relationships.length, included: relationships.length },
    events: { reviewed: valid.events.length, included: events.length }
  } };
}

// framer-components/public-probe/PortfolioReviewedRegistry.tsx
var portfolioReviewedRegistry = {
  schemaVersion: 1,
  reviewedAt: "2026-10-01",
  sources: [
    {
      id: "nvda-intc-nvidia",
      publisher: "NVIDIA",
      publishedAt: "2025-09-18",
      url: "https://nvidianews.nvidia.com/news/nvidia-and-intel-to-develop-ai-infrastructure-and-personal-computing-products",
      statement: "NVIDIA와 Intel이 데이터센터·PC 제품 공동개발 계획을 발표했다. Intel은 맞춤형 x86 CPU와 RTX GPU 칩렛 통합 제품을 개발할 예정이라고 밝혔다."
    },
    {
      id: "nvda-intc-intel",
      publisher: "Intel",
      publishedAt: "2025-09-18",
      url: "https://www.intel.com/content/www/us/en/newsroom/news/artificial-intelligence/intel-and-nvidia-to-jointly-develop-ai-infrastructure-and-personal-computing-products.html",
      statement: "Intel도 같은 날짜에 같은 참여 기업과 데이터센터·PC 공동개발 계획을 발표했다. 당시 투자 계획은 별도 종결 조건이 있는 미래 계획이었다."
    },
    {
      id: "nvda-tsmc-production",
      publisher: "NVIDIA",
      publishedAt: "2025-04-14",
      url: "https://blogs.nvidia.com/blog/nvidia-manufacture-american-made-ai-supercomputers-us/",
      statement: "NVIDIA는 TSMC의 미국 피닉스 공장에서 Blackwell 칩 생산이 시작됐다고 발표했다."
    },
    {
      id: "tsmc-customer",
      publisher: "TSMC",
      publishedAt: "2025-03-04",
      url: "https://pr.tsmc.com/english/news/3210",
      statement: "TSMC는 미국 투자 확대 발표에서 NVIDIA를 자사의 주요 고객 중 하나로 명시했다. 4월의 생산 발표와는 별도 사건이다."
    },
    {
      id: "skh-tsmc-hbm4-ko",
      publisher: "SK하이닉스 · 한국어",
      publishedAt: "2024-04-19",
      url: "https://news.skhynix.co.kr/skhynix-tsmc-hbm4-mou/",
      statement: "SK하이닉스는 TSMC와 기술 협력 양해각서(MOU)를 체결했다고 발표했다. HBM4 개발과 HBM·CoWoS 패키징(칩 결합) 최적화 협력 계획이며, 현재 양산 실적을 확인하는 자료는 아니다."
    },
    {
      id: "skh-tsmc-hbm4-en",
      publisher: "SK하이닉스 · 영어",
      publishedAt: "2024-04-19",
      url: "https://news.skhynix.com/en/sk-hynix-partners-with-tsmc-to-strengthen-hbm-technological-leadership/",
      statement: "같은 발표의 영문본도 HBM4의 하단 제어 칩에 TSMC 공정을 활용하고 HBM·CoWoS 결합을 최적화할 계획을 설명한다. 한국어본과 같은 발행사의 자료로 독립 확인은 아니다."
    },
    {
      id: "tsmc-skh-memory-partner",
      publisher: "TSMC",
      publishedAt: "2023-09-28",
      url: "https://pr.tsmc.com/english/news/3070",
      statement: "TSMC는 SK하이닉스를 HBM3·HBM3e 협력 메모리 파트너로 명시했다. 본문 행사일은 미국 현지 2023-09-27, 사이트 발행일은 09-28이다. 2024년 HBM4 양해각서와는 별도 발표다."
    },
    {
      id: "amd-orcl-mi355x-oracle",
      publisher: "Oracle",
      publishedAt: "2025-06-12",
      url: "https://www.oracle.com/news/announcement/oracle-and-amd-collaborate-to-help-customers-deliver-breakthrough-performance-for-large-scale-ai-and-agentic-workloads-2025-06-12/",
      statement: "Oracle은 AMD와 함께 MI355X GPU를 OCI 클라우드에서 제공할 계획을 발표했다. 당시 제공 계획이며, 현재 설치 수량이나 실제 구매 금액을 확인하는 자료는 아니다."
    },
    {
      id: "amd-orcl-mi355x-amd",
      publisher: "AMD",
      publishedAt: "2025-06-12",
      url: "https://ir.amd.com/news-events/press-releases/detail/1255/amd-unveils-vision-for-an-open-ai-ecosystem-detailing-new-silicon-software-and-systems-at-advancing-ai-2025",
      statement: "AMD의 같은 날 행사 발표 중 Oracle 항목에서도 OCI가 MI355X GPU 기반 클라우드를 제공할 계획이라고 설명한다. 다른 참여사의 발표는 이 사건에 합치지 않았다."
    }
  ],
  relationships: [
    {
      id: "relation:nvda-intc-collaboration-20250918",
      from: { ticker: "NVDA", market: "US" },
      to: { ticker: "INTC", market: "US" },
      label: "제품 공동개발 발표",
      asOf: "2025-09-18",
      status: "historical-announcement",
      sourceIds: ["nvda-intc-nvidia", "nvda-intc-intel"],
      review: "manual-primary-source-comparison",
      impact: "unknown",
      limitations: "두 회사의 당시 공동개발 발표를 확인했다. 현재 제품 출시·매출 효과·지분 보유 상태는 이 자료만으로 확인하지 않았다."
    },
    {
      id: "relation:tsmc-nvda-manufacturing-20250414",
      from: { ticker: "TSM", market: "US" },
      to: { ticker: "NVDA", market: "US" },
      label: "칩 생산·고객 관계",
      asOf: "2025-04-14",
      status: "dated-fact",
      sourceIds: ["nvda-tsmc-production", "tsmc-customer"],
      review: "manual-primary-source-comparison",
      impact: "unknown",
      limitations: "당시 생산 발표와 고객 관계를 확인했다. 두 발표는 서로 다른 사건이며, 현재 공급량·매출 비중·주가 영향은 확인하지 않았다."
    },
    {
      id: "relation:skh-tsmc-hbm-collaboration-20240419",
      from: { ticker: "000660", market: "KR" },
      to: { ticker: "TSM", market: "US" },
      label: "HBM 기술 협력",
      asOf: "2024-04-19",
      status: "historical-announcement",
      sourceIds: ["skh-tsmc-hbm4-ko", "tsmc-skh-memory-partner"],
      review: "manual-primary-source-comparison",
      impact: "unknown",
      limitations: "양사의 서로 다른 시점 원문으로 HBM 협력 관계를 확인했다. 2023년 파트너 발표와 2024년 HBM4 협력 계획은 별도 사건이다. 현재 양산·공급량·매출·주가 영향은 확인하지 않았다."
    },
    {
      id: "relation:amd-orcl-mi355x-cloud-20250612",
      from: { ticker: "AMD", market: "US" },
      to: { ticker: "ORCL", market: "US" },
      label: "GPU 기반 클라우드 제공 계획",
      asOf: "2025-06-12",
      status: "historical-announcement",
      sourceIds: ["amd-orcl-mi355x-oracle", "amd-orcl-mi355x-amd"],
      review: "manual-primary-source-comparison",
      impact: "unknown",
      limitations: "AMD 제품을 Oracle 클라우드에서 제공한다는 당시 계획을 양사 원문으로 확인했다. 현재 공급량·구매 금액·매출 비중·주가 영향은 확인하지 않았다."
    }
  ],
  events: [
    {
      id: "event:nvda-intc-collaboration-20250918",
      title: "NVIDIA·Intel 제품 공동개발 발표",
      date: "2025-09-18",
      status: "historical-announcement",
      sourceIds: ["nvda-intc-nvidia", "nvda-intc-intel"],
      participants: [
        { ticker: "NVDA", market: "US", role: "공동개발 참여 · AI 기반 시스템·GPU 기술", sourceIds: ["nvda-intc-nvidia", "nvda-intc-intel"] },
        { ticker: "INTC", market: "US", role: "공동개발 참여 · 맞춤형 x86 CPU 개발 계획", sourceIds: ["nvda-intc-nvidia", "nvda-intc-intel"] }
      ],
      mergeBasis: "양사의 2025-09-18 원문에서 참여 기업·발표일·공동개발 대상이 일치한다. 같은 공동 발표의 두 게재본이며 독립적인 성과 검증은 아니다. TSMC 관련 발표는 합치지 않았다.",
      review: "manual-primary-source-comparison",
      impact: "unknown"
    },
    {
      id: "event:skh-tsmc-hbm4-mou-20240419",
      title: "SK하이닉스·TSMC HBM4 협력 발표",
      date: "2024-04-19",
      status: "historical-announcement",
      sourceIds: ["skh-tsmc-hbm4-ko", "skh-tsmc-hbm4-en"],
      participants: [
        { ticker: "000660", market: "KR", role: "HBM4 메모리 개발 · TSMC 공정 활용 계획", sourceIds: ["skh-tsmc-hbm4-ko", "skh-tsmc-hbm4-en"] },
        { ticker: "TSM", market: "US", role: "제어 칩 공정·칩 결합 기술 협력 계획", sourceIds: ["skh-tsmc-hbm4-ko", "skh-tsmc-hbm4-en"] }
      ],
      mergeBasis: "같은 SK하이닉스 발표의 한국어·영어본에서 참여 기업·발표일·협력 대상이 일치해 사건 하나로 묶었다. 독립된 두 기관의 확인은 아니다. 2023년 TSMC 파트너 발표는 합치지 않았다. 당시 계획이며 현재 양산 성과는 확인하지 않았다.",
      review: "manual-primary-source-comparison",
      impact: "unknown"
    },
    {
      id: "event:amd-orcl-mi355x-cloud-20250612",
      title: "AMD·Oracle MI355X 클라우드 제공 계획 발표",
      date: "2025-06-12",
      status: "historical-announcement",
      sourceIds: ["amd-orcl-mi355x-oracle", "amd-orcl-mi355x-amd"],
      participants: [
        { ticker: "AMD", market: "US", role: "클라우드에 사용할 MI355X GPU 개발사", sourceIds: ["amd-orcl-mi355x-oracle", "amd-orcl-mi355x-amd"] },
        { ticker: "ORCL", market: "US", role: "MI355X 기반 OCI 클라우드 제공 계획", sourceIds: ["amd-orcl-mi355x-oracle", "amd-orcl-mi355x-amd"] }
      ],
      mergeBasis: "2025-06-12 양사 발표의 기업·GPU 제품·클라우드 제공 계획이 일치해 이 발표만 하나로 묶었다. AMD 행사 발표의 다른 기업·제품 계획은 제외했다. 두 당사자의 발표이며 독립적인 이행 검증은 아니다.",
      review: "manual-primary-source-comparison",
      impact: "unknown"
    }
  ]
};

// framer-components/public-probe/PortfolioReviewedState.tsx
var MAX_REVISION2 = Number.MAX_SAFE_INTEGER;
var FNV_OFFSET = 1469598103934665603n;
var FNV_PRIME = 1099511628211n;
var UINT64_MASK = (1n << 64n) - 1n;
var compareCanonical = (left, right) => {
  const a = JSON.stringify(left), b = JSON.stringify(right);
  return a < b ? -1 : a > b ? 1 : 0;
};
var sortedIds = (ids) => [...ids].sort();
var sourceValue = (source) => [
  source.id,
  source.url,
  source.publisher,
  source.publishedAt,
  source.statement
];
var sortedSources = (sources) => sources.map(sourceValue).sort(compareCanonical);
function relationshipValue(fact) {
  return [
    "relationships",
    [fact.from.market, fact.from.ticker],
    [fact.to.market, fact.to.ticker],
    fact.label,
    fact.asOf,
    fact.status,
    fact.limitations,
    fact.review,
    fact.impact,
    sortedIds(fact.sourceIds),
    sortedSources(fact.sources)
  ];
}
function eventValue(fact) {
  const participants2 = fact.participants.map((participant) => [
    participant.market,
    participant.ticker,
    participant.role,
    sortedIds(participant.sourceIds)
  ]).sort(compareCanonical);
  return [
    "events",
    fact.title,
    fact.date,
    fact.status,
    participants2,
    fact.mergeBasis,
    fact.review,
    fact.impact,
    sortedIds(fact.sourceIds),
    sortedSources(fact.sources)
  ];
}
function revision(value) {
  const canonical = JSON.stringify(value);
  let hash = FNV_OFFSET;
  for (let index = 0; index < canonical.length; index++) {
    hash ^= BigInt(canonical.charCodeAt(index));
    hash = hash * FNV_PRIME & UINT64_MASK;
  }
  return Number(hash % BigInt(MAX_REVISION2 - 1) + 1n);
}
function reviewedRecord(mode, fact) {
  const relationship = "from" in fact;
  if (mode === "relationships" !== relationship) throw new Error("reviewed-mode-mismatch");
  return {
    id: `reviewed:${mode}:${fact.id}`,
    read_revision: revision(relationship ? relationshipValue(fact) : eventValue(fact))
  };
}

// framer-components/public-probe/PortfolioPrototypeReviewed.ts
var entityKey2 = (entity3) => `${entity3.market}:${entity3.ticker}`;
var sourceEvidence = (sources) => sources.map((source) => ({
  id: source.id,
  sourceURL: source.url,
  publisher: source.publisher,
  publishedAt: source.publishedAt,
  statement: source.statement
}));
var firstSource = (sources) => sources[0] || null;
function reviewedPrototypeTopic(fact) {
  const claim = "label" in fact ? fact.label : fact.title;
  const statements = fact.sources.map((source) => source.statement).join("\n");
  const patterns = {
    supply: /공급|고객|공동\s*개발|기술\s*협력|협력\s*(?:발표|계획)|클라우드(?:에서|를)?\s*제공/,
    contract: /계약|수주|해지|정정/,
    policy: /정책|규제|관세|수출\s*통제/,
    commodity: /원자재|원유|천연가스|구리\s*가격/
  };
  const topics = Object.keys(patterns).filter((topic) => patterns[topic].test(claim) && patterns[topic].test(statements));
  return topics.length === 1 ? topics[0] : "holding";
}
var position = (index, count) => ({
  x: 0.75 + (index % 3 + 0.5) / 6,
  y: 0.5 + (Math.floor(index / 3) + 0.5) / Math.max(1, Math.ceil(count / 3))
});
function projectReviewedPrototype(state) {
  if (state.phase !== "ready" || !state.graph) return emptyReviewedPrototype();
  const holdingsByTicker = new Map(workspaceStocks(state).map((holding) => [holding.ticker, holding]));
  const companiesByEntity = /* @__PURE__ */ new Map();
  const holdings = state.graph.companies.flatMap((company) => {
    const holding = holdingsByTicker.get(company.ticker);
    if (!holding || holding.market !== "KR" && holding.market !== "US") return [];
    companiesByEntity.set(entityKey2({ ticker: company.ticker, market: holding.market }), company.id);
    return [{ ticker: company.ticker, market: holding.market }];
  });
  const facts = buildReviewedPortfolioFacts(holdings, portfolioReviewedRegistry);
  const nodes = [], edges = [];
  const recordsMap = {};
  const total = facts.relationships.length + facts.events.length;
  facts.relationships.forEach((fact, index) => {
    const mode = "relationships", record8 = reviewedRecord(mode, fact);
    const nodeId = record8.id, evidence = sourceEvidence(fact.sources), source = firstSource(fact.sources);
    recordsMap[record8.id] = recordFor(mode, fact, record8);
    nodes.push({
      id: nodeId,
      kind: "reviewed-relationship",
      name: fact.label,
      code: "검토 완료 관계",
      logo: "",
      priority: 2,
      topic: reviewedPrototypeTopic(fact),
      reason: fact.limitations,
      source: source?.publisher || null,
      sourceURL: source?.url || null,
      asOf: fact.asOf,
      evidence,
      relationshipKind: fact.label,
      recordId: record8.id,
      read_revision: record8.read_revision,
      ...position(index, total)
    });
    for (const endpoint of [fact.from, fact.to]) {
      const companyId = companiesByEntity.get(entityKey2(endpoint));
      if (companyId) edges.push(edgeFor("relationships", fact, record8, nodeId, companyId, endpoint, fact.label, evidence, source));
    }
  });
  facts.events.forEach((fact, index) => {
    const mode = "events", record8 = reviewedRecord(mode, fact);
    const nodeId = record8.id, evidence = sourceEvidence(fact.sources), source = firstSource(fact.sources);
    recordsMap[record8.id] = recordFor(mode, fact, record8);
    nodes.push({
      id: nodeId,
      kind: "reviewed-event",
      name: fact.title,
      code: "검토 완료 공통 사건",
      logo: "",
      priority: 2,
      topic: reviewedPrototypeTopic(fact),
      reason: fact.mergeBasis,
      source: source?.publisher || null,
      sourceURL: source?.url || null,
      asOf: fact.date,
      evidence,
      relationshipKind: null,
      recordId: record8.id,
      read_revision: record8.read_revision,
      ...position(facts.relationships.length + index, total)
    });
    const participants2 = new Map(fact.participants.map((participant) => [entityKey2(participant), participant]));
    for (const holding of fact.matchedHoldings) {
      const companyId = companiesByEntity.get(entityKey2(holding)), participant = participants2.get(entityKey2(holding));
      if (companyId && participant) edges.push(edgeFor("events", fact, record8, nodeId, companyId, holding, participant.role, evidence, source));
    }
  });
  return { nodes, edges, recordsMap, facts };
}
function edgeFor(mode, fact, record8, nodeId, companyId, endpoint, reason, evidence, source) {
  const isRelationship = mode === "relationships";
  return {
    id: `reviewed-link:${fact.id}:${entityKey2(endpoint)}`,
    from: nodeId,
    to: companyId,
    reason,
    source: source?.publisher || null,
    sourceURL: source?.url || null,
    asOf: isRelationship ? fact.asOf : fact.date,
    evidence,
    relationshipKind: isRelationship ? fact.label : null,
    recordId: record8.id,
    read_revision: record8.read_revision,
    influence: "unknown"
  };
}
function recordFor(mode, fact, record8) {
  const isRelationship = mode === "relationships";
  return {
    ...record8,
    mode,
    factId: fact.id,
    asOf: isRelationship ? fact.asOf : fact.date,
    sourceURLs: fact.sources.map((source) => source.url),
    relationshipKind: isRelationship ? fact.label : null
  };
}
function emptyReviewedPrototype() {
  return {
    nodes: [],
    edges: [],
    recordsMap: {},
    facts: { relationships: [], events: [], coverage: {
      status: "empty",
      reason: "workspace-not-ready",
      reviewedAt: null,
      holdings: { provided: 0, eligible: 0, matched: 0 },
      sources: { reviewed: 0 },
      relationships: { reviewed: 0, included: 0 },
      events: { reviewed: 0, included: 0 }
    } }
  };
}

// framer-components/public-probe/PortfolioPrototypeAutomatic.ts
function projectAutomaticPrototype(graph) {
  const companies = new Map(graph?.companies.map((c) => [`${c.market}:${c.ticker}`, c]));
  const relations = graph?.automaticRelations || [];
  const nodes = relations.map((r, index) => {
    const names = r.participants.map((p) => companies.get(p.id)?.name || p.name || p.id);
    return {
      id: r.id,
      kind: "event",
      recordKind: "relationship",
      proofLabel: r.reportedBasis === "business-period" ? "사업보고서상 확인 · 보고기간 기준" : r.reportedBasis === "filing-period" ? "보고서상 확인 · 보고기간 기준" : r.reported ? "공시상 확인 · 결산기준" : "자동 추출 · 관계 후보",
      layer: r.reported ? "relationships" : "candidates",
      topic: r.reported && r.reportedBasis === "business-period" ? "supply" : "holding",
      name: r.title,
      code: r.reported ? "현재 유효 여부 미확인" : "원문 확인 필요",
      logo: "",
      priority: 1,
      reason: r.reported && r.reportedBasis !== "filing-period" ? r.reason : `${names.join(" ↔ ")}
${r.reason}`,
      source: r.source,
      asOf: r.asOf,
      read_revision: r.read_revision,
      ...r.reported && r.measure ? { measure: r.measure } : {},
      evidence: r.url ? [{ url: r.url, source: r.source, asOf: r.asOf, explanation: r.reason }] : [],
      x: 1.05 + index % 3 * 0.2,
      y: 0.6 + Math.floor(index / 3) * 0.18
    };
  });
  const edges = relations.flatMap((r) => r.participants.flatMap((p) => {
    const company = companies.get(p.id);
    return company ? [{
      id: `automatic-link:${r.id}:${p.id}`,
      from: r.id,
      to: company.id,
      confirmation: r.reported ? "confirmed" : "candidate",
      type: r.reported ? "direct" : "unknown",
      strength: 0,
      impact: "미확인",
      impactReason: r.reportedBasis === "business-period" ? "사업보고서에 직접 기재된 거래 상대방이에요. 현재 유효 여부·거래 규모·주가 영향은 미확인이에요." : r.reportedBasis === "filing-period" ? `${p.role === "from" ? "보고기간의 공시상 지배기업" : "지배기업 현황을 공시한 회사"}예요. 현재 관계·지분율·주가 영향은 미확인이에요.` : r.reported ? "결산기준일의 공시상 지분 관계예요. 현재 관계와 주가 영향은 미확인이에요." : "자동 추출한 관계 후보이며 현재 관계와 주가 영향은 미확인이에요.",
      ...r.reported && r.measure ? { measure: r.measure } : {},
      reason: r.reason,
      verb: r.reportedBasis === "filing-period" ? p.role === "from" ? "보고서상 지배기업" : "공시 작성 회사" : p.roleLabel || r.title,
      source: r.source,
      asOf: r.asOf,
      evidence: nodes.find((n) => n.id === r.id).evidence
    }] : [];
  }));
  const recordsMap = Object.fromEntries(relations.map((r) => [r.id, { id: r.id, read_revision: r.read_revision, sourceURLs: r.url ? [r.url] : [] }]));
  return { nodes, edges, recordsMap };
}

// framer-components/public-probe/PortfolioStockSearch.ts
var MAX_RESULTS = 12;
var MAX_BODY_BYTES = 64 * 1024;
var KR_MARKETS2 = /* @__PURE__ */ new Set(["KR", "KOSPI", "KOSDAQ", "KONEX"]);
var US_MARKETS2 = /* @__PURE__ */ new Set(["US", "NASDAQ", "NYSE", "AMEX", "NYSE AMERICAN", "NYSE ARCA", "BATS"]);
function boundedString(value, max, allowEmpty = false) {
  if (typeof value !== "string" || value.length > max || /[\u0000-\u001f\u007f]/.test(value)) {
    throw new Error("Invalid search metadata");
  }
  const result = value.trim();
  if (!allowEmpty && !result) throw new Error("Invalid search metadata");
  return result;
}
function normalizeSearchResults(payload) {
  if (!Array.isArray(payload) || payload.length > MAX_RESULTS) {
    throw new Error("Invalid search response");
  }
  const byKey = /* @__PURE__ */ new Map();
  let unsupportedCount = 0;
  for (const value of payload) {
    if (!value || typeof value !== "object" || Array.isArray(value)) {
      throw new Error("Invalid search row");
    }
    const row5 = value;
    const ticker = boundedString(row5.ticker, 16).toUpperCase();
    const name = boundedString(row5.name, 160);
    const listing = boundedString(row5.market, 32).toUpperCase();
    const koreanName = row5.name_kr === void 0 ? "" : boundedString(row5.name_kr, 160, true);
    if (row5.etf !== void 0 && typeof row5.etf !== "boolean") {
      throw new Error("Invalid ETF metadata");
    }
    const market2 = KR_MARKETS2.has(listing) ? "KR" : US_MARKETS2.has(listing) ? "US" : null;
    if (!market2) {
      unsupportedCount++;
      continue;
    }
    if (!(market2 === "KR" ? /^\d{6}$/ : /^[A-Z][A-Z0-9.-]{0,15}$/).test(ticker)) {
      throw new Error("Invalid search ticker");
    }
    const item = { ticker, name: market2 === "US" ? koreanName || name : name, market: market2 };
    if (row5.etf === true) item.etf = true;
    const key = `${market2}:${ticker}`;
    const previous = byKey.get(key);
    if (previous && (previous.name !== item.name || previous.etf !== item.etf)) {
      throw new Error("Ambiguous duplicate search ticker");
    }
    if (!previous) byKey.set(key, item);
  }
  return { stocks: [...byKey.values()], unsupportedCount };
}
async function readSearchPayload(response, signal) {
  if (!response.ok || response.redirected) throw new Error("Search request failed");
  const declaredLength = response.headers.get("content-length");
  if (declaredLength !== null && (!/^\d+$/.test(declaredLength) || Number(declaredLength) > MAX_BODY_BYTES)) {
    throw new Error("Search response exceeds size limit");
  }
  const reader = response.body?.getReader();
  if (!reader) throw new Error("Missing search response body");
  const cancel = () => {
    void reader.cancel().catch(() => {
    });
  };
  signal.addEventListener("abort", cancel, { once: true });
  const chunks = [];
  let size = 0;
  let complete = false;
  try {
    signal.throwIfAborted();
    while (true) {
      const { done, value } = await reader.read();
      signal.throwIfAborted();
      if (done) break;
      size += value.byteLength;
      if (size > MAX_BODY_BYTES) throw new Error("Search response exceeds size limit");
      chunks.push(value);
    }
    complete = true;
    const bytes = new Uint8Array(size);
    let offset = 0;
    for (const chunk of chunks) {
      bytes.set(chunk, offset);
      offset += chunk.byteLength;
    }
    return JSON.parse(new TextDecoder("utf-8", { fatal: true }).decode(bytes));
  } finally {
    signal.removeEventListener("abort", cancel);
    if (!complete) cancel();
    reader.releaseLock();
  }
}
async function fetchPortfolioStockSearch(query, options = {}) {
  if (typeof query !== "string") throw new Error("Invalid search query");
  const q = query.trim().slice(0, 60);
  if (!q) return { stocks: [], unsupportedCount: 0 };
  const { fetcher = globalThis.fetch, signal, api = "/api/search" } = options;
  if (!/^\/[A-Za-z0-9/_-]+$/.test(api) || api.startsWith("//")) throw new Error("Invalid search endpoint");
  signal?.throwIfAborted();
  const controller = new AbortController();
  const abortFromCaller = () => controller.abort(signal?.reason);
  signal?.addEventListener("abort", abortFromCaller, { once: true });
  let onAbort = () => {
  };
  const aborted2 = new Promise((_, reject) => {
    onAbort = () => reject(controller.signal.reason);
    controller.signal.addEventListener("abort", onAbort, { once: true });
  });
  const timer = setTimeout(() => controller.abort(new DOMException("Search timed out", "TimeoutError")), 5e3);
  const request = async () => {
    const params = new URLSearchParams({ q, market: "all", limit: String(MAX_RESULTS) });
    const response = await fetcher(`${api}?${params}`, {
      method: "GET",
      credentials: "omit",
      redirect: "error",
      signal: controller.signal
    });
    controller.signal.throwIfAborted();
    const payload = await readSearchPayload(response, controller.signal);
    controller.signal.throwIfAborted();
    return normalizeSearchResults(payload);
  };
  try {
    return await Promise.race([request(), aborted2]);
  } finally {
    clearTimeout(timer);
    signal?.removeEventListener("abort", abortFromCaller);
    controller.signal.removeEventListener("abort", onAbort);
  }
}

// framer-components/public-probe/PortfolioCompanyDisplayNames.ts
var SHORT_NAMES = {
  "US:TSM": "TSMC"
};
function portfolioCompanyDisplayName(market2, ticker, formalName) {
  return SHORT_NAMES[`${market2}:${ticker.toUpperCase()}`] || formalName;
}

// framer-components/public-probe/PortfolioPrototypeHost.ts
var plain = (v) => !!v && typeof v === "object" && !Array.isArray(v);
var point = (v) => plain(v) && Number.isFinite(v.x) && Number.isFinite(v.y);
var pixel = (value, scale, prior) => prior !== void 0 && value === 0.5 + prior / scale ? prior : (value - 0.5) * scale;
function marketLayout(layout, market2) {
  const aliases = /* @__PURE__ */ new Map(), positions = new Map(layout.positions.map((p) => [p.node_id, p])), marks = { ...layout.marks };
  for (const node of market2.nodes) {
    const ids = node.legacyIds || [];
    for (const id of ids) {
      aliases.set(id, node.id);
      for (const edge of market2.edges.filter((e) => e.from === node.id)) {
        if (edge.id.startsWith("market-link:")) aliases.set(`market-link:${id}:${edge.id.split(":").slice(-2).join(":")}`, edge.id);
        for (const old of edge.legacyIds || []) aliases.set(old, edge.id);
      }
    }
    if (!positions.has(node.id)) {
      const old = ids.map((id) => positions.get(id)).find(Boolean);
      if (old) positions.set(node.id, { ...old, node_id: node.id });
    }
    if (!marks[node.id]) {
      const old = ids.map((id) => layout.marks[id]).filter(Boolean);
      if (old.length) marks[node.id] = {
        read_revision: old.find((m) => m.read_revision)?.read_revision ?? null,
        important: old.some((m) => m.important),
        disposition: old.some((m) => m.disposition === "later") ? "later" : old.every((m) => m.disposition === "irrelevant") ? "irrelevant" : "inbox"
      };
    }
  }
  return {
    ...layout,
    positions: [...positions.values()],
    marks,
    notes: layout.notes.map((n) => n.anchor && aliases.has(n.anchor.id) ? { ...n, anchor: { ...n.anchor, id: aliases.get(n.anchor.id) } } : n)
  };
}
function mergePrototypeDraft(state, value) {
  if (state.phase !== "ready" || !state.graph || !["ready", "saving"].includes(state.privateState.phase) || !state.privateState.document) return null;
  if (!plain(value) || !Array.isArray(value.positions) || !Array.isArray(value.notes) || !plain(value.marks) || value.positions.length > 200 || value.notes.length > 100 || Object.keys(value.marks).length > 200) return null;
  const reviewed = projectReviewedPrototype(state), automatic = projectAutomaticPrototype(state.graph), contracts = projectContractPrototype(state.graph), markets = projectMarketPrototype(state.graph);
  const market2 = { nodes: [...markets.nodes, ...contracts.nodes], edges: [...markets.edges, ...contracts.edges], recordsMap: { ...markets.recordsMap, ...contracts.recordsMap } };
  const prior = marketLayout(state.privateState.document.layouts.find((l) => l.map_key === "main") || { map_key: "main", positions: [], notes: [], marks: {} }, market2);
  const allowed = new Set([...state.graph.companies, ...state.graph.documents, ...reviewed.nodes, ...automatic.nodes, ...market2.nodes].map((n) => n.id));
  const edgeIds = /* @__PURE__ */ new Set([...state.graph.links.map((e) => e.id), ...reviewed.edges.map((e) => e.id), ...automatic.edges.map((e) => e.id), ...market2.edges.map((e) => e.id)]), positions = new Map(prior.positions.map((p) => [p.node_id, p]));
  const seen = /* @__PURE__ */ new Set();
  for (const p of value.positions) {
    if (!point(p) || typeof p.id !== "string" || !allowed.has(p.id) || seen.has(p.id)) return null;
    seen.add(p.id);
    const previous = positions.get(p.id);
    positions.set(p.id, { node_id: p.id, x: pixel(p.x, 1e3, previous?.x), y: pixel(p.y, 680, previous?.y) });
  }
  const oldNotes = new Map(prior.notes.map((n) => [n.note_id, n]));
  const notes = [];
  for (const n of value.notes) {
    if (!point(n) || typeof n.id !== "string" || typeof n.text !== "string" || typeof n.done !== "boolean" || typeof n.target !== "string") return null;
    const old = oldNotes.get(n.id);
    if (!old && !/^note-[0-9]+$/.test(n.id)) return null;
    const anchor = n.target ? allowed.has(n.target) ? { kind: "node", id: n.target } : edgeIds.has(n.target) ? { kind: "edge", id: n.target } : old && old.anchor?.id === n.target ? old.anchor : void 0 : null;
    if (anchor === void 0) return null;
    notes.push({ note_id: n.id, anchor, x: pixel(n.x, 1e3, old?.x), y: pixel(n.y, 680, old?.y), text: n.text, done: n.done });
  }
  const marks = { ...prior.marks };
  for (const [id, mark] of Object.entries(value.marks)) {
    const doc = state.graph.documents.find((d) => d.id === id) || reviewed.recordsMap[id] || automatic.recordsMap[id] || market2.recordsMap[id];
    if (!doc || !plain(mark) || ["read", "readTouched", "important", "later", "irrelevant"].some((key) => mark[key] !== void 0 && typeof mark[key] !== "boolean")) return null;
    const old = prior.marks[id];
    marks[id] = {
      read_revision: mark.read ? doc.read_revision : mark.readTouched ? null : old?.read_revision ?? null,
      important: !!mark.important,
      disposition: mark.irrelevant ? "irrelevant" : mark.later ? "later" : "inbox"
    };
  }
  const next = { map_key: "main", positions: [...positions.values()], notes, marks };
  return validMapDocument({ layouts: [next] }) ? next : null;
}
function prototypeMemberModel(state, explorationNotice = "", visitBaseline) {
  if (state.phase !== "ready" || !state.graph) return { nodes: [], edges: [], notes: {}, marks: {}, writable: false };
  const projected = projectWorkspaceToPrototype(state), graph = state.graph, reviewed = projectReviewedPrototype(state), automatic = projectAutomaticPrototype(state.graph), contracts = projectContractPrototype(state.graph), markets = projectMarketPrototype(state.graph);
  const market2 = { nodes: [...markets.nodes, ...contracts.nodes], edges: [...markets.edges, ...contracts.edges], recordsMap: { ...markets.recordsMap, ...contracts.recordsMap } };
  const base = projectWorkspaceToPrototype({ ...state, privateState: { ...state.privateState, document: { layouts: [] } } });
  const layoutBases = new Map([...base.nodes, ...reviewed.nodes, ...automatic.nodes, ...market2.nodes].map((n) => [n.id, { x: n.x, y: n.y }]));
  const stocks = new Map(workspaceStocks(state).map((stock) => [stock.ticker, stock]));
  const savedLayout = state.privateState.document?.layouts.find((l) => l.map_key === "main");
  const layout = savedLayout ? marketLayout(savedLayout, market2) : void 0;
  const positions = new Map(layout?.positions.map((p) => [p.node_id, p]));
  const evidence = (rows2) => rows2.map((s) => ({ url: s.sourceURL, source: s.publisher, asOf: s.publishedAt, explanation: s.statement }));
  const reviewedNodes = reviewed.nodes.map((n) => ({
    ...n,
    kind: "event",
    recordKind: n.kind === "reviewed-event" ? "event" : "relationship",
    layer: n.kind === "reviewed-event" ? "events" : "relationships",
    evidence: evidence(n.evidence),
    ...positions.has(n.id) ? { x: 0.5 + positions.get(n.id).x / 1e3, y: 0.5 + positions.get(n.id).y / 680 } : {}
  }));
  const records = [...graph.documents, ...Object.values(reviewed.recordsMap), ...Object.values(automatic.recordsMap), ...Object.values(market2.recordsMap)];
  const visitRevisions = Object.fromEntries(records.filter((d) => !contracts.replacedDocumentIds.has(d.id)).map((d) => [d.id, d.read_revision]));
  const changes = Object.fromEntries(records.map((d) => {
    if (visitBaseline !== void 0) return [d.id, visitBaseline === null ? "기준없음" : !Object.hasOwn(visitBaseline.revisions, d.id) ? "새로" : visitBaseline.revisions[d.id] === d.read_revision ? "기존" : "변경"];
    const m = layout?.marks[d.id];
    return [d.id, m?.read_revision ? m.read_revision === d.read_revision ? "확인" : "변경" : "미확인"];
  }));
  return {
    coverageNotice: graph.analysisNotice || "",
    ...visitBaseline !== void 0 ? { visit: { previousAt: visitBaseline?.visitedAt || null, revisions: visitRevisions } } : {},
    layoutBases: Object.fromEntries(layoutBases),
    nodes: [...projected.nodes.filter((n) => !contracts.replacedDocumentIds.has(n.id)).map((n) => {
      const company = n.kind === "stock" ? graph.companies.find((c) => c.id === n.id) : void 0;
      const stockMarket = company?.market || stocks.get(n.code)?.market;
      const formalName = company?.name || n.name;
      return {
        ...n,
        ...company ? { name: portfolioCompanyDisplayName(stockMarket || "", company.ticker, formalName), formalName } : {},
        ticker: company?.ticker,
        priority: 2,
        recordKind: n.kind === "event" ? "document" : "company",
        changeStatus: changes[n.id],
        market: stockMarket,
        held: n.kind === "stock" ? stocks.get(n.code)?.held ?? false : void 0,
        watched: n.kind === "stock" ? stocks.get(n.code)?.watched ?? false : void 0,
        explore: n.kind === "stock" ? stocks.get(n.code)?.exploring ?? false : false,
        sections: n.kind === "stock" ? graph.companies.find((c) => c.id === n.id)?.sections : void 0,
        closeQuote: n.kind === "stock" ? graph.companies.find((c) => c.id === n.id)?.closeQuote : void 0,
        reason: n.kind === "stock" ? stocks.get(n.code)?.held ? "보유종목에 연결된 자료를 확인하세요." : stocks.get(n.code)?.watched ? "관심종목이에요. 실제 보유 수량이나 평가금액에는 포함하지 않아요." : explorationNotice || "이번 화면에서 탐색 중이에요. 보유·관심목록에 등록하지 않았으며, 다시 접속하면 검색해서 추가해야 해요." : graph?.documents.find((d) => d.id === n.id)?.reason,
        source: n.kind === "event" ? graph?.documents.find((d) => d.id === n.id)?.source : "내 포트폴리오",
        asOf: n.kind === "event" ? graph?.documents.find((d) => d.id === n.id)?.asOf : void 0,
        evidence: n.kind === "event" ? graph?.documents.find((d) => d.id === n.id)?.evidence : []
      };
    }), ...reviewedNodes.map((n) => ({ ...n, changeStatus: changes[n.id] })), ...[...automatic.nodes, ...market2.nodes].map((n) => ({
      ...n,
      changeStatus: changes[n.id],
      ...positions.has(n.id) ? { x: 0.5 + positions.get(n.id).x / 1e3, y: 0.5 + positions.get(n.id).y / 680 } : {}
    }))],
    edges: [
      ...projected.edges.filter((e) => !contracts.replacedDocumentIds.has(e.from)).map((e) => ({ ...e, type: "unknown", confirmation: "candidate", strength: 0, impact: "미확인", impactReason: "자료 연결만으로 실적이나 주가 영향을 판단하지 않아요.", verb: "자료 연결" })),
      ...reviewed.edges.map((e) => ({ ...e, evidence: evidence(e.evidence), type: "documented", confirmation: "confirmed", strength: 0, impact: "미확인", impactReason: "자료에 명시된 참여 관계이며, 현재 실적이나 주가 영향을 뜻하지 않아요.", verb: e.reason })),
      ...automatic.edges,
      ...market2.edges
    ],
    notes: Object.fromEntries((layout?.notes || []).map((n) => [n.note_id, { id: n.note_id, target: n.anchor?.id || "", x: 0.5 + n.x / 1e3, y: 0.5 + n.y / 680, text: n.text, done: n.done, todo: n.done, pinned: !!n.anchor }])),
    marks: Object.fromEntries(records.map((d) => {
      const m = layout?.marks[d.id];
      return [d.id, { read: m?.read_revision === d.read_revision, important: !!m?.important, later: m?.disposition === "later", irrelevant: m?.disposition === "irrelevant" }];
    })),
    writable: state.privateState.phase === "ready" && !!state.privateState.document
  };
}
function mountMemberPrototype(frame, template, workspace, options = {}) {
  const templateURL = options.templateURL ? new URL(options.templateURL, window.location.href) : null;
  if (templateURL && (templateURL.origin !== window.location.origin || templateURL.username || templateURL.password)) throw new Error("prototype-origin-mismatch");
  const account = options.account || (() => readMapSession()?.userId || null);
  const introStore = "alphanest:map-guide:hidden:v1";
  let introHidden = false;
  try {
    introHidden = window.localStorage.getItem(introStore) === "1";
  } catch {
  }
  let owner = null, generation = 0, port = null, disposed = false, key = "", current = workspace.getState();
  let originGeneration = 0, appliedOriginGeneration = -1;
  let visitRevisions = null, rememberedVisitGeneration = -1;
  const model = (state) => {
    const projected = prototypeMemberModel(state, options.explorationNotice, options.visitBaseline);
    const visit = "visit" in projected ? projected.visit : void 0;
    visitRevisions = visit?.revisions || null;
    return {
      ...projected,
      ...visit ? { visit: { previousAt: visit.previousAt, error: options.visitError || null } } : {},
      originGeneration: ++originGeneration,
      ...options.localView ? { localView: { hiddenStockIds: options.localView.getHiddenStockIds() } } : {}
    };
  };
  const rememberVisit = () => {
    if (!options.onVisitDisplayed || !visitRevisions || rememberedVisitGeneration === originGeneration || current.privateState.phase !== "ready") return;
    const stamp2 = originGeneration, member = owner, revisions = { ...visitRevisions };
    rememberedVisitGeneration = stamp2;
    const isCurrent = () => !disposed && hydrated && stamp2 === originGeneration && appliedOriginGeneration === stamp2 && member === owner && member === account() && current.phase === "ready" && current.privateState.phase === "ready";
    if (!isCurrent()) return;
    void Promise.resolve().then(() => isCurrent() && options.onVisitDisplayed(revisions, isCurrent)).then((persisted) => {
      if (isCurrent()) port?.postMessage({ type: "visit-status", persisted: persisted === true });
    }).catch(() => {
      if (isCurrent()) port?.postMessage({ type: "visit-status", persisted: false });
    });
  };
  let waiting = false, reloadPending = false, frameNonce = "";
  let hydrated = false, focusRevision = 0;
  let displayedWindow = "", reloadingWindow = null;
  let rejectedDraft = false;
  let searchRequest = null, searchRevision = 0;
  let searchStocks = /* @__PURE__ */ new Map();
  let exploration = null;
  let logoRequest = new AbortController();
  const requestedLogos = /* @__PURE__ */ new Set();
  const sendLogos = (stocks) => {
    if (!options.logoLoader || !port || !hydrated) return;
    const version = generation, member = owner, signal = logoRequest.signal;
    for (const stock of stocks) {
      if (stock.market !== "KR" && stock.market !== "US") continue;
      const identity2 = stock.market + ":" + stock.ticker;
      if (requestedLogos.has(identity2)) continue;
      requestedLogos.add(identity2);
      void options.logoLoader({ ticker: stock.ticker, market: stock.market }, { signal }).then((dataURL) => {
        if (disposed || signal.aborted || version !== generation || member !== account() || typeof dataURL !== "string" || dataURL.length > 175e3 || !/^data:image\/png;base64,[A-Za-z0-9+/]+={0,2}$/.test(dataURL)) return;
        port?.postMessage({ type: "logo-update", identity: identity2, dataURL });
      }).catch(() => {
      });
    }
  };
  const focusWindowKey = (state) => JSON.stringify([
    state.selectedTickers,
    state.graph?.companies.map((row5) => [row5.id, row5.ticker, row5.market])
  ]);
  let pendingFocus = null;
  const clearReturnFocus = () => {
    focusRevision++;
    pendingFocus = null;
  };
  const flushReturnFocus = () => {
    if (!pendingFocus?.requested) return;
    const pending = pendingFocus, state = workspace.getState();
    if (disposed || pending.owner !== account() || pending.owner !== owner || state.phase !== "ready" || focusWindowKey(state) !== pending.windowKey || !state.selectedTickers.includes(pending.ticker)) {
      clearReturnFocus();
      return;
    }
    const company = state.graph?.companies.find((row5) => row5.ticker === pending.ticker);
    if (!company) {
      clearReturnFocus();
      return;
    }
    if (!port || !hydrated) return;
    pendingFocus = null;
    port.postMessage({ type: "focus-stock", id: company.id });
  };
  const prepareReturnFocus = () => {
    clearReturnFocus();
    const member = account(), revision2 = focusRevision;
    return (ticker) => {
      const state = workspace.getState();
      if (disposed || revision2 !== focusRevision || !member || member !== account() || member !== owner || state.phase !== "ready" || !state.selectedTickers.includes(ticker) || !state.graph?.companies.some((row5) => row5.ticker === ticker)) return;
      focusRevision++;
      pendingFocus = { owner: member, windowKey: focusWindowKey(state), ticker, requested: false };
    };
  };
  const returnToMap = () => {
    if (pendingFocus) pendingFocus.requested = true;
    flushReturnFocus();
  };
  const close = () => {
    generation++;
    searchRevision++;
    searchRequest?.abort();
    searchStocks.clear();
    logoRequest.abort();
    logoRequest = new AbortController();
    requestedLogos.clear();
    exploration = null;
    port?.close();
    port = null;
    waiting = false;
    hydrated = false;
    rejectedDraft = false;
    appliedOriginGeneration = -1;
    displayedWindow = "";
    reloadingWindow = null;
  };
  const status = () => {
    const p = current.privateState;
    const originPending = appliedOriginGeneration !== originGeneration;
    port?.postMessage({
      type: "status",
      writable: p.phase === "ready" || p.phase === "saving",
      saving: p.phase === "saving" || originPending,
      dataRefresh: options.enableDataRefresh ? { phase: current.dataRefresh?.phase || "idle", checked: !!current.dataRefresh?.checkedAt } : null,
      message: originPending ? "새 자료의 배치를 적용 중이에요…" : rejectedDraft ? "배치·메모가 저장 범위를 벗어나 저장하지 않았어요. 현재 화면은 유지했어요." : p.phase === "loading" ? "저장된 종목과 기록을 불러오는 중이에요…" : p.phase === "conflict" ? "다른 화면에서 기록이 바뀌었어요. 덮어쓰지 않았어요." : p.phase === "error" ? options.localSession && p.error ? p.error : "저장하지 못했어요. 변경 내용을 유지하고 있어요." : p.phase === "saving" ? "저장 중…" : p.dirty ? "아직 저장하지 않은 변경이 있어요" : "저장된 기록을 불러왔어요"
    });
  };
  const ready = (event) => {
    if (disposed || !waiting || !owner || owner !== account() || current.phase !== "ready" || event.source !== frame.contentWindow || event.origin !== "null" || event.data?.type !== "alphanest-member-ready" || event.data.nonce !== frameNonce) return;
    waiting = false;
    const channel = new MessageChannel(), version = generation, member = owner;
    port = channel.port1;
    port.onmessage = async (event2) => {
      if (disposed || version !== generation || !member || member !== account()) return;
      const state = workspace.getState(), command = event2.data;
      if (!plain(command)) return;
      if (command.type === "intro-preference" && typeof command.hidden === "boolean") {
        introHidden = command.hidden;
        let persisted = true;
        try {
          if (introHidden) window.localStorage.setItem(introStore, "1");
          else window.localStorage.removeItem(introStore);
        } catch {
          persisted = false;
        }
        port?.postMessage({ type: "intro-preference", hidden: introHidden, persisted });
        return;
      }
      if (command.type === "hydrated") {
        if (command.originGeneration !== originGeneration) return;
        appliedOriginGeneration = originGeneration;
        hydrated = true;
        sendLogos(state.graph?.companies || []);
        flushReturnFocus();
        status();
        rememberVisit();
        return;
      }
      if (command.type === "graph-applied") {
        if (hydrated && command.originGeneration === originGeneration) {
          appliedOriginGeneration = originGeneration;
          status();
          rememberVisit();
        }
        return;
      }
      if (state.phase !== "ready") return;
      if ((command.type === "edit" || command.type === "save") && (!hydrated || appliedOriginGeneration !== originGeneration || command.originGeneration !== originGeneration)) {
        status();
        return;
      }
      if (command.type === "search" && typeof command.query === "string" && command.query.length <= 60 && Number.isSafeInteger(command.request)) {
        searchRequest?.abort();
        searchRequest = new AbortController();
        searchStocks.clear();
        const request = ++searchRevision, signal = searchRequest.signal;
        try {
          const result = await (options.searchLoader || fetchPortfolioStockSearch)(command.query, { signal });
          if (disposed || version !== generation || request !== searchRevision || member !== account() || signal.aborted) return;
          searchStocks = new Map(result.stocks.map((stock) => [stock.ticker, stock]));
          port?.postMessage({
            type: "search-results",
            request: command.request,
            ...result,
            stocks: result.stocks.map((stock) => ({ ...stock, name: portfolioCompanyDisplayName(stock.market, stock.ticker, stock.name) }))
          });
          sendLogos(result.stocks);
        } catch {
          if (!disposed && version === generation && request === searchRevision && member === account() && !signal.aborted)
            port?.postMessage({ type: "search-results", request: command.request, error: "검색 자료를 불러오지 못했어요. 다시 입력해 주세요." });
        }
      } else if (command.type === "explore" && typeof command.ticker === "string" && !exploration) {
        const stock = searchStocks.get(command.ticker);
        if (!stock) {
          port?.postMessage({ type: "explore-result", error: "검색 결과가 바뀌었어요. 다시 검색해 주세요." });
          return;
        }
        exploration = { ticker: stock.ticker, version };
        try {
          const success = await workspace.exploreStock(stock);
          if (!disposed && version === generation && member === account())
            port?.postMessage({ type: "explore-result", ...success ? {} : { error: "추가하지 못했어요. 기존 지도는 유지했어요." } });
        } catch (error) {
          if (!disposed && version === generation && member === account()) port?.postMessage({ type: "explore-result", error: error instanceof Error && error.message.includes("30") ? "한 화면에는 30종목까지 표시할 수 있어요." : "추가하지 못했어요. 기존 지도는 유지했어요." });
        } finally {
          if (exploration?.version === version) exploration = null;
        }
      } else if (command.type === "edit") {
        const next = mergePrototypeDraft(state, command.draft);
        const hidden = command.draft?.hiddenStockIds;
        const allowed = new Set(state.graph?.companies.map((row5) => "company:" + row5.ticker));
        const validView = !options.localView || Array.isArray(hidden) && hidden.length <= 30 && new Set(hidden).size === hidden.length && hidden.every((id) => typeof id === "string" && allowed.has(id));
        rejectedDraft = !next || !validView;
        if (next && validView) {
          rejectedDraft = workspace.editLayout("main", () => next) === false;
          if (!rejectedDraft) options.localView?.setHiddenStockIds([...hidden]);
        }
        if (rejectedDraft) status();
      } else if (command.type === "save") {
        if (rejectedDraft) status();
        else await workspace.save();
      } else if (command.type === "refresh-data" && options.enableDataRefresh && !exploration) {
        await workspace.refreshData();
      } else if (command.type === "apply-data" && options.enableDataRefresh && !exploration && !rejectedDraft) {
        workspace.applyDataUpdate();
      } else if (command.type === "holdings") {
        if (options.showStockList) port?.postMessage({ type: "stock-list" });
        else options.openHoldings?.();
      } else if (command.type === "source" && typeof command.url === "string") {
        const reviewed = projectReviewedPrototype(state);
        const urls = /* @__PURE__ */ new Set([
          ...state.graph?.documents.flatMap((d) => [d.url, ...d.evidence.flatMap((e) => [e.url, ...e.sources.map((s) => s.url)])]) || [],
          ...state.graph?.companies.flatMap((c) => (c.sections || []).flatMap((s) => s.items.flatMap((i) => [i.url, ...(i.sources || []).map((source) => source.url)]))) || [],
          ...Object.values(reviewed.recordsMap).flatMap((record8) => record8.sourceURLs),
          ...Object.values(projectAutomaticPrototype(state.graph).recordsMap).flatMap((record8) => record8.sourceURLs),
          ...Object.values(projectMarketPrototype(state.graph).recordsMap).flatMap((record8) => record8.sourceURLs),
          ...Object.values(projectContractPrototype(state.graph).recordsMap).flatMap((record8) => record8.sourceURLs)
        ]);
        try {
          const url = new URL(command.url);
          if (url.protocol === "https:" && !url.username && !url.password && urls.has(url.href)) options.openSource?.(url.href);
        } catch {
        }
      }
    };
    frame.contentWindow.postMessage({ type: "alphanest-member-connect", nonce: frameNonce }, "*", [channel.port2]);
    port.postMessage({ type: "init", model: { ...model(current), introHidden } });
    status();
    frame.style.opacity = "1";
    frame.removeAttribute("aria-hidden");
    frame.removeAttribute("inert");
  };
  window.addEventListener("message", ready);
  const loaded = () => {
    if (!disposed && waiting) frame.contentWindow?.postMessage({ type: "alphanest-member-start", nonce: frameNonce }, "*");
  };
  frame.addEventListener("load", loaded);
  frame.setAttribute("sandbox", "allow-scripts");
  frame.setAttribute("referrerpolicy", "no-referrer");
  const unsubscribe = workspace.subscribe((state) => {
    const previous = current;
    current = state;
    const nextOwner = account();
    if (owner !== nextOwner || state.phase === "signed-out") clearReturnFocus();
    else if (pendingFocus && (state.phase !== "ready" || focusWindowKey(state) !== pendingFocus.windowKey)) pendingFocus = null;
    if (state.phase === "loading" && nextOwner && owner === nextOwner && key) {
      if (hydrated && reloadingWindow === null) reloadingWindow = displayedWindow;
      port?.postMessage({ type: "status", writable: false, saving: false, message: "보유종목과 자료를 갱신 중이에요" });
      return;
    }
    if (state.phase !== "ready" || !state.graph || !nextOwner) {
      frame.style.opacity = "0";
      frame.setAttribute("aria-hidden", "true");
      frame.setAttribute("inert", "");
      port?.postMessage({ type: "reset" });
      close();
      key = "";
      reloadPending = false;
      owner = nextOwner;
      return;
    }
    if (state.privateState.phase === "loading") reloadPending = true;
    if (reloadPending && state.privateState.phase === "ready" && !state.privateState.dirty) {
      key = "";
      reloadPending = false;
    }
    const nextKey = JSON.stringify([nextOwner, state.graph, workspaceStocks(state), !!state.privateState.document]);
    const sameWindowReload = reloadingWindow !== null && reloadingWindow === focusWindowKey(state);
    reloadingWindow = null;
    if (nextKey !== key) {
      if (sameWindowReload && owner === nextOwner && port && hydrated && key) {
        key = nextKey;
        displayedWindow = focusWindowKey(state);
        port.postMessage({ type: "graph-update", model: model(state) });
        sendLogos(state.graph.companies);
        status();
        return;
      }
      if (previous.dataRefresh?.phase === "available" && state.dataRefresh?.phase === "idle" && owner === nextOwner && port && hydrated && focusWindowKey(previous) === focusWindowKey(state)) {
        key = nextKey;
        displayedWindow = focusWindowKey(state);
        port.postMessage({ type: "graph-update", model: model(state) });
        sendLogos(state.graph.companies);
        status();
        return;
      }
      if (exploration?.version === generation && owner === nextOwner && port && hydrated && state.selectedTickers.includes(exploration.ticker)) {
        key = nextKey;
        displayedWindow = focusWindowKey(state);
        port.postMessage({ type: "graph-update", model: model(state), ticker: exploration.ticker });
        sendLogos(state.graph.companies);
        status();
        return;
      }
      close();
      owner = nextOwner;
      key = nextKey;
      waiting = true;
      displayedWindow = focusWindowKey(state);
      frameNonce = "an-member-" + crypto.randomUUID();
      if (templateURL) {
        const url = new URL(templateURL);
        url.searchParams.set("__an_frame", frameNonce);
        url.hash = frameNonce;
        frame.src = url.href;
      } else frame.srcdoc = template.replace("'__ALPHANEST_FRAME_NONCE__'", JSON.stringify(frameNonce));
    } else {
      status();
      if (waiting) loaded();
    }
  });
  const cleanup = () => {
    const retiredSource = templateURL ? frame.src : frame.srcdoc;
    frame.style.opacity = "0";
    frame.setAttribute("aria-hidden", "true");
    frame.setAttribute("inert", "");
    disposed = true;
    clearReturnFocus();
    close();
    unsubscribe();
    window.removeEventListener("message", ready);
    frame.removeEventListener("load", loaded);
    Promise.resolve().then(() => {
      if ((templateURL ? frame.src : frame.srcdoc) !== retiredSource) return;
      if (templateURL) frame.src = "about:blank";
      else frame.srcdoc = "";
    });
  };
  return Object.assign(cleanup, { prepareReturnFocus, clearReturnFocus, returnToMap });
}

// framer-components/public-probe/PortfolioPublicLogoLoader.ts
var BF_MAP_URL = "https://rte5guenhonw9fzn.public.blob.vercel-storage.com/logo_map.json";
var PNG_PREFIX = "https://static.toss.im/png-icons/securities/icn-sec-fill-";
var MANIFEST_MAX_BYTES = 2 * 1024 * 1024;
var LOGO_MAX_BYTES = 128 * 1024;
var DEFAULT_TIMEOUT_MS = 8e3;
var MAX_CACHE_ENTRIES = 256;
function validIdentity(stock) {
  if (!stock || typeof stock.ticker !== "string" || typeof stock.market !== "string") return false;
  if (stock.market === "KR") return /^[0-9]{6}$/.test(stock.ticker);
  if (stock.market === "US") return /^[A-Z][A-Z0-9]{0,9}(?:[.-][A-Z0-9]{1,2})?$/.test(stock.ticker);
  return false;
}
function hasDuplicateKeys(source) {
  const objects = [];
  for (let i = 0; i < source.length; i++) {
    const char = source[i];
    if (char === '"') {
      const start = i;
      i++;
      while (i < source.length) {
        if (source[i] === "\\") {
          i += 2;
          continue;
        }
        if (source[i] === '"') break;
        i++;
      }
      if (i >= source.length) return false;
      let next = i + 1;
      while (next < source.length && /\s/.test(source[next])) next++;
      if (source[next] === ":") {
        const owner = objects[objects.length - 1];
        if (!owner) return true;
        const key = JSON.parse(source.slice(start, i + 1));
        if (owner.has(key)) return true;
        owner.add(key);
      }
    } else if (char === "{") objects.push(/* @__PURE__ */ new Set());
    else if (char === "}") {
      if (!objects.length) return true;
      objects.pop();
    }
  }
  return objects.length !== 0;
}
function parseManifest(bytes) {
  try {
    const text13 = new TextDecoder("utf-8", { fatal: true }).decode(bytes);
    if (hasDuplicateKeys(text13)) return null;
    const value = JSON.parse(text13);
    if (!value || typeof value !== "object" || Array.isArray(value)) return null;
    const logos = value.logos;
    if (!logos || typeof logos !== "object" || Array.isArray(logos)) return null;
    return logos;
  } catch {
    return null;
  }
}
function publicGetInit(signal) {
  return {
    method: "GET",
    credentials: "omit",
    referrerPolicy: "no-referrer",
    redirect: "error",
    cache: "no-store",
    signal
  };
}
async function fetchManifest(fetcher, timeoutMs) {
  const controller = new AbortController();
  let stop;
  const stopped = new Promise((resolve) => {
    stop = () => resolve(null);
  });
  const timer = setTimeout(() => {
    controller.abort();
    stop();
  }, timeoutMs);
  const work = async () => {
    try {
      const response = await fetcher(BF_MAP_URL, publicGetInit(controller.signal));
      const bytes = await readBounded(response, MANIFEST_MAX_BYTES, "application/json", BF_MAP_URL);
      return bytes ? parseManifest(bytes) : null;
    } catch {
      return null;
    }
  };
  try {
    return await Promise.race([work(), stopped]);
  } finally {
    clearTimeout(timer);
  }
}
function validPng(bytes) {
  return bytes.length >= 45 && bytes[0] === 137 && bytes[1] === 80 && bytes[2] === 78 && bytes[3] === 71 && bytes[4] === 13 && bytes[5] === 10 && bytes[6] === 26 && bytes[7] === 10 && bytes[8] === 0 && bytes[9] === 0 && bytes[10] === 0 && bytes[11] === 13 && bytes[12] === 73 && bytes[13] === 72 && bytes[14] === 68 && bytes[15] === 82 && new DataView(bytes.buffer, bytes.byteOffset, bytes.byteLength).getUint32(16) > 0 && new DataView(bytes.buffer, bytes.byteOffset, bytes.byteLength).getUint32(16) <= 1024 && new DataView(bytes.buffer, bytes.byteOffset, bytes.byteLength).getUint32(20) > 0 && new DataView(bytes.buffer, bytes.byteOffset, bytes.byteLength).getUint32(20) <= 1024 && bytes[bytes.length - 12] === 0 && bytes[bytes.length - 11] === 0 && bytes[bytes.length - 10] === 0 && bytes[bytes.length - 9] === 0 && bytes[bytes.length - 8] === 73 && bytes[bytes.length - 7] === 69 && bytes[bytes.length - 6] === 78 && bytes[bytes.length - 5] === 68;
}
function toDataUrl(bytes) {
  if (typeof globalThis.btoa !== "function") return null;
  let binary = "";
  for (let offset = 0; offset < bytes.length; offset += 8192) {
    binary += String.fromCharCode(...bytes.subarray(offset, offset + 8192));
  }
  return `data:image/png;base64,${globalThis.btoa(binary)}`;
}
function contentLengthAllowed(response, limit) {
  const value = response.headers.get("Content-Length");
  return value === null || /^[0-9]+$/.test(value) && Number(value) <= limit;
}
async function readBounded(response, limit, contentType, expectedUrl) {
  if (!response.ok || response.status !== 200 || response.url && response.url !== expectedUrl || response.headers.get("Content-Type")?.split(";", 1)[0].trim().toLowerCase() !== contentType || !contentLengthAllowed(response, limit) || !response.body) return null;
  const reader = response.body.getReader();
  const chunks = [];
  let size = 0;
  try {
    while (true) {
      const { done, value } = await reader.read();
      if (done) break;
      size += value.byteLength;
      if (size > limit) {
        await reader.cancel().catch(() => {
        });
        return null;
      }
      chunks.push(value);
    }
  } finally {
    try {
      reader.releaseLock();
    } catch {
    }
  }
  const output = new Uint8Array(size);
  let offset = 0;
  for (const chunk of chunks) {
    output.set(chunk, offset);
    offset += chunk.byteLength;
  }
  return output;
}
function createPortfolioPublicLogoLoader(options = {}) {
  const fetcher = options.fetcher || globalThis.fetch.bind(globalThis);
  const timeoutMs = Number.isFinite(options.timeoutMs) && options.timeoutMs > 0 ? Math.min(options.timeoutMs, 3e4) : DEFAULT_TIMEOUT_MS;
  const cache = /* @__PURE__ */ new Map();
  let manifest = null;
  let manifestRequest = null;
  const getManifest = () => {
    if (manifest) return Promise.resolve(manifest);
    if (manifestRequest) return manifestRequest;
    let pending;
    pending = fetchManifest(fetcher, timeoutMs).then((value) => {
      if (value) manifest = value;
      return value;
    }).finally(() => {
      if (manifestRequest === pending) manifestRequest = null;
    });
    manifestRequest = pending;
    return pending;
  };
  return async (stock, { signal }) => {
    if (!validIdentity(stock) || !signal || signal.aborted) return null;
    const identity2 = `${stock.market}:${stock.ticker}`;
    const cached = cache.get(identity2);
    if (cached) {
      cache.delete(identity2);
      cache.set(identity2, cached);
      return cached;
    }
    const controller = new AbortController();
    let stop;
    const stopped = new Promise((resolve) => {
      stop = () => resolve(null);
    });
    const abort = () => {
      controller.abort();
      stop();
    };
    const timer = setTimeout(abort, timeoutMs);
    signal.addEventListener("abort", abort, { once: true });
    if (signal.aborted) abort();
    const request = (url) => fetcher(url, publicGetInit(controller.signal));
    const work = async () => {
      try {
        const logos = await getManifest();
        if (!logos || controller.signal.aborted) return null;
        const expectedUrl = `${PNG_PREFIX}${stock.ticker}.png`;
        if (Object.prototype.hasOwnProperty.call(logos, stock.ticker) && logos[stock.ticker] !== expectedUrl) return null;
        const response = await request(expectedUrl);
        const bytes = await readBounded(response, LOGO_MAX_BYTES, "image/png", expectedUrl);
        if (controller.signal.aborted) return null;
        return bytes && validPng(bytes) ? toDataUrl(bytes) : null;
      } catch {
        return null;
      }
    };
    try {
      const value = await Promise.race([work(), stopped]);
      if (value) {
        cache.set(identity2, value);
        if (cache.size > MAX_CACHE_ENTRIES) cache.delete(cache.keys().next().value);
      }
      return value;
    } finally {
      clearTimeout(timer);
      signal.removeEventListener("abort", abort);
    }
  };
}

// framer-components/public-probe/PortfolioHoldingsPanel.tsx
import * as React4 from "react";

// framer-components/public-probe/PortfolioHoldingsDraft.ts
var tickerFor = (value, market2) => {
  if (typeof value !== "string") throw new Error("invalid-ticker");
  const ticker = value.trim().toUpperCase();
  const pattern = market2 === "kr" ? /^[0-9A-Z]{6}$/ : /^[A-Z][A-Z0-9.-]{0,14}$/;
  if (!pattern.test(ticker) || ticker.startsWith("CMD_")) throw new Error("invalid-ticker");
  return ticker;
};
var apiMarketFor = (value) => {
  if (typeof value !== "string") throw new Error("invalid-market");
  const market2 = value.trim().toLowerCase();
  if (market2 !== "kr" && market2 !== "us") throw new Error("invalid-market");
  return market2;
};
var holdingMarketFor = (market2) => market2 === "kr" ? "KR" : "US";
var identifierFor = (value) => {
  if (typeof value !== "string" || !value.trim()) throw new Error("missing-holding-id");
  return value.trim();
};
var positiveNumber = (value, field3) => {
  if (typeof value === "boolean") throw new Error(`invalid-${field3}`);
  if (typeof value === "string") {
    const text13 = value.replace(/[,\s₩$원]/g, "");
    if (!/^[+-]?(?:\d+(?:\.\d*)?|\.\d+)(?:[eE][+-]?\d+)?$/.test(text13)) throw new Error(`invalid-${field3}`);
    value = Number(text13);
  }
  if (typeof value !== "number" || !Number.isFinite(value) || value <= 0) throw new Error(`invalid-${field3}`);
  return value;
};
var textField = (value, field3) => {
  if (typeof value !== "string") throw new Error(`invalid-${field3}`);
  return value;
};
var copy2 = (record8) => ({ ...record8 });
function targetById(records, id) {
  const matches = records.filter((record8) => record8.id === id);
  if (!matches.length) throw new Error("holding-not-found");
  if (matches.length !== 1) throw new Error("duplicate-holding-id");
  if (matches[0].duplicate === true) throw new Error("duplicate-holding-record");
  return matches[0];
}
function previewHoldingChange(records, change) {
  if (change.kind === "add") return previewAdd(records, change);
  if (change.kind !== "edit" && change.kind !== "remove") throw new Error("invalid-holding-change");
  const id = identifierFor(change.id), before = targetById(records, id);
  if (change.kind === "remove") return {
    kind: "remove",
    id,
    before: copy2(before),
    after: null,
    changedFields: [],
    request: { method: "DELETE", body: { id } }
  };
  const after = { ...copy2(before), id };
  const changedFields = [];
  const body = { id };
  if (change.shares !== void 0) {
    after.shares = positiveNumber(change.shares, "shares");
    body.shares = after.shares;
    changedFields.push("shares");
  }
  if (change.avg_cost !== void 0) {
    after.avg_cost = positiveNumber(change.avg_cost, "avg_cost");
    body.avg_cost = after.avg_cost;
    changedFields.push("avg_cost");
  }
  if (change.name !== void 0) {
    after.name = textField(change.name, "name");
    body.name = after.name;
    changedFields.push("name");
  }
  if (change.memo !== void 0) {
    after.memo = textField(change.memo, "memo");
    body.memo = after.memo;
    changedFields.push("memo");
  }
  if (!changedFields.length) throw new Error("no-holding-changes");
  return { kind: "edit", id, before: copy2(before), after, changedFields, request: { method: "PATCH", body } };
}
function previewAdd(records, change) {
  const apiMarket = apiMarketFor(change.market), market2 = holdingMarketFor(apiMarket), ticker = tickerFor(change.ticker, apiMarket);
  const sameTicker = records.filter((record8) => record8.ticker.trim().toUpperCase() === ticker);
  if (sameTicker.some((record8) => record8.duplicate === true)) throw new Error("duplicate-holding-record");
  if (sameTicker.length) {
    throw new Error("holding-ticker-requires-edit");
  }
  const shares = positiveNumber(change.shares, "shares"), avg_cost = positiveNumber(change.avg_cost, "avg_cost");
  const name = change.name === void 0 ? "" : textField(change.name, "name");
  const memo = change.memo === void 0 ? "" : textField(change.memo, "memo");
  const after = { id: null, ticker, market: market2, shares, avg_cost, name, memo };
  return {
    kind: "add",
    id: null,
    before: null,
    after,
    changedFields: ["ticker", "name", "market", "shares", "avg_cost", "memo"],
    request: { method: "POST", body: { ticker, market: apiMarket, shares, avg_cost, name, memo } }
  };
}

// framer-components/public-probe/PortfolioHoldingsList.tsx
import * as React from "react";
var quantity = new Intl.NumberFormat("ko-KR", { maximumFractionDigits: 8 });
var won = new Intl.NumberFormat("ko-KR", { style: "currency", currency: "KRW", maximumFractionDigits: 0 });
var dollar = new Intl.NumberFormat("en-US", { style: "currency", currency: "USD", minimumFractionDigits: 2, maximumFractionDigits: 4 });
function formatHoldingQuantity(value) {
  if (value === null) return "확인 필요";
  return value < 1e-8 ? "0.00000001 미만" : quantity.format(value);
}
function formatHoldingAverageCost(holding) {
  if (holding.duplicate) return "중복 행 확인 필요";
  if (holding.avg_cost === null) return "확인 필요";
  if (holding.market === "KR" && holding.avg_cost < 1) return "1 KRW 미만";
  if (holding.market === "US" && holding.avg_cost < 1e-4) return "0.0001 USD 미만";
  return holding.market === "KR" ? `${won.format(holding.avg_cost)} KRW` : `${dollar.format(holding.avg_cost)} USD`;
}

// framer-components/public-probe/PortfolioHoldingsCsvPanel.tsx
import * as React2 from "react";

// framer-components/public-probe/PortfolioHoldingsCsv.ts
var HOLDINGS_CSV_LIMITS = Object.freeze({ maxCharacters: 262144, maxRows: 200 });
var ALIASES = {
  ticker: ["ticker", "code", "symbol", "stockcode", "종목코드", "티커"],
  market: ["market", "시장"],
  shares: ["shares", "quantity", "qty", "수량", "보유수량"],
  avg_cost: ["avgcost", "averagecost", "평단", "평단가", "평균매수가", "평균매입가"],
  name: ["name", "stockname", "종목명", "이름"],
  memo: ["memo", "note", "메모"],
  currency: ["currency", "통화"]
};
var columnFor = (value) => {
  const normalized = value.trim().toLowerCase().replace(/[\s_-]/g, "");
  return Object.keys(ALIASES).find((key) => ALIASES[key].includes(normalized));
};
function parse(text13) {
  if (text13.length > HOLDINGS_CSV_LIMITS.maxCharacters) return { rows: [], errors: [{ rowNumber: 1, code: "csv-input-too-large" }] };
  text13 = text13.replace(/^\uFEFF/, "");
  const rows2 = [];
  let line = 1, startLine = 1, cells = [], field3 = "", errors = [];
  let quoted = false, closed = false, touched = false;
  const issue2 = (code) => {
    if (!errors.includes(code)) errors.push(code);
  };
  const endField = () => {
    cells.push(field3);
    field3 = "";
    closed = false;
  };
  const endRow = () => {
    endField();
    rows2.push({ line: startLine, cells, errors });
    cells = [];
    errors = [];
    touched = false;
  };
  for (let i = 0; i < text13.length; i++) {
    const char = text13[i];
    if (char === "\0" || char === "�") issue2("csv-invalid-text");
    if (quoted) {
      if (char === '"') {
        if (text13[i + 1] === '"') {
          field3 += '"';
          i++;
        } else {
          quoted = false;
          closed = true;
        }
      } else {
        field3 += char;
        if (char === "\n" || char === "\r" && text13[i + 1] !== "\n") line++;
      }
      continue;
    }
    if (char === "\r" || char === "\n") {
      endRow();
      if (rows2.length > HOLDINGS_CSV_LIMITS.maxRows + 1) return { rows: [], errors: [{ rowNumber: startLine, code: "csv-too-many-rows" }] };
      if (char === "\r" && text13[i + 1] === "\n") i++;
      startLine = ++line;
      continue;
    }
    touched = true;
    if (char === ",") {
      endField();
      continue;
    }
    if (char === '"' && !field3 && !closed) {
      quoted = true;
      continue;
    }
    if (closed || char === '"') issue2("csv-invalid-quote");
    field3 += char;
  }
  if (quoted) issue2("csv-unclosed-quote");
  if (touched || cells.length || field3.length) endRow();
  if (rows2.length > HOLDINGS_CSV_LIMITS.maxRows + 1) return { rows: [], errors: [{ rowNumber: startLine, code: "csv-too-many-rows" }] };
  return { rows: rows2, errors: [] };
}
function buildHoldingCsvPreview(text13, memberHoldings) {
  const parsed = parse(text13), errors = parsed.errors.slice();
  const header = parsed.rows[0];
  const columns = header?.cells.map(columnFor) || [];
  if (!header && !errors.length) errors.push({ rowNumber: 1, code: "csv-missing-header" });
  else if (header) {
    errors.push(...header.errors.map((code) => ({ rowNumber: header.line, code })));
    if (columns.some((column) => !column)) errors.push({ rowNumber: header.line, code: "csv-unknown-header" });
    if (new Set(columns).size !== columns.length) errors.push({ rowNumber: header.line, code: "csv-duplicate-header" });
    for (const required of ["ticker", "market", "shares", "avg_cost"]) {
      if (!columns.includes(required)) errors.push({ rowNumber: header.line, code: `csv-missing-${required}-header` });
    }
  }
  const existingTickers = new Set(memberHoldings.map((record8) => record8.ticker.trim().toUpperCase()));
  const rows2 = parsed.rows.slice(1).map((row5) => ({ rowNumber: row5.line, cells: row5.cells, errors: row5.errors.slice(), ticker: null, kind: "error", preview: null }));
  if (header && !rows2.length && !errors.length) errors.push({ rowNumber: header.line + 1, code: "csv-no-data" });
  const tickerIndex = columns.indexOf("ticker");
  const occurrences = /* @__PURE__ */ new Map();
  for (const row5 of rows2) {
    row5.ticker = tickerIndex >= 0 ? row5.cells[tickerIndex]?.trim().toUpperCase() || null : null;
    if (row5.ticker) occurrences.set(row5.ticker, (occurrences.get(row5.ticker) || 0) + 1);
  }
  for (const row5 of rows2) {
    if (errors.length) row5.errors.push("csv-invalid-file");
    if (row5.cells.length !== columns.length) row5.errors.push("csv-column-count");
    if (row5.ticker && (occurrences.get(row5.ticker) || 0) > 1) row5.errors.push("csv-duplicate-ticker");
    if (row5.errors.length) continue;
    const input = {};
    columns.forEach((column, index) => {
      if (column) input[column] = row5.cells[index];
    });
    try {
      const candidate = previewHoldingChange([], {
        kind: "add",
        ticker: input.ticker,
        market: input.market,
        shares: input.shares,
        avg_cost: input.avg_cost,
        name: input.name,
        memo: input.memo
      });
      const after = candidate.after;
      if (input.currency !== void 0 && input.currency.trim().toUpperCase() !== (after.market === "KR" ? "KRW" : "USD")) {
        throw new Error("csv-currency-mismatch");
      }
      const matches = memberHoldings.filter((record8) => record8.ticker.trim().toUpperCase() === after.ticker);
      if (!matches.length) {
        row5.kind = "add";
        row5.preview = candidate;
        continue;
      }
      const before = matches[0];
      if (matches.length !== 1 || before.duplicate || !before.id?.trim() || before.id !== before.id.trim() || memberHoldings.filter((record8) => record8.id === before.id).length !== 1) throw new Error("csv-ambiguous-existing-identity");
      if (before.market !== after.market) throw new Error("csv-existing-market-conflict");
      const change = { kind: "edit", id: before.id };
      if (before.shares !== after.shares) change.shares = after.shares;
      if (before.avg_cost !== after.avg_cost) change.avg_cost = after.avg_cost;
      if (input.name !== void 0 && before.name !== after.name) change.name = after.name;
      if (input.memo !== void 0 && (before.memo ?? "") !== after.memo) change.memo = after.memo;
      if (Object.keys(change).length === 2) {
        row5.kind = "unchanged";
        continue;
      }
      row5.preview = previewHoldingChange(memberHoldings, change);
      row5.kind = "edit";
    } catch (error) {
      row5.errors.push(error instanceof Error ? error.message : "csv-invalid-row");
    }
  }
  const additions = rows2.filter((row5) => row5.kind === "add");
  const projectedUnique = existingTickers.size + additions.length;
  const counts = { add: 0, edit: 0, unchanged: 0, error: 0, existingUnique: existingTickers.size, projectedUnique };
  for (const row5 of rows2) counts[row5.kind]++;
  if (errors.length || counts.error) for (const row5 of rows2) row5.preview = null;
  return {
    rows: rows2,
    fatalErrors: errors,
    counts,
    requiresConfirmation: true,
    readyForConfirmation: !errors.length && !counts.error && counts.add + counts.edit > 0
  };
}

// framer-components/public-probe/PortfolioHoldingsCsvPanel.tsx
var fields2 = { ticker: "종목코드", market: "시장", name: "이름", shares: "수량", avg_cost: "평균 매수가", memo: "메모" };
function issue(code) {
  if (/duplicate-ticker/.test(code)) return "파일 안에 같은 종목이 두 번 있어요. 한 행으로 정리해주세요.";
  if (/ambiguous|duplicate-holding/.test(code)) return "기존 보유 기록을 하나로 구분할 수 없어요. 목록을 먼저 확인해주세요.";
  if (/member-limit/.test(code)) return "기존 보유와 합쳐 30종목을 넘어요. 추가할 종목을 줄여주세요.";
  if (/currency|market/.test(code)) return "시장은 KR 또는 US, 통화는 각각 KRW 또는 USD인지 확인해주세요.";
  if (/shares|avg_cost/.test(code) && !/header/.test(code)) return "수량·평균 매수가를 0보다 큰 숫자로 입력해주세요.";
  if (/ticker/.test(code) && !/header/.test(code)) return "종목코드를 확인해주세요. 국내 코드는 앞자리 0까지 6자리로 적어주세요.";
  if (/header/.test(code)) return "첫 줄의 항목 이름을 아래 예시와 맞춰주세요. 시장·종목코드·수량·평균 매수가는 필수예요.";
  if (/too-large|too-many/.test(code)) return "파일이 너무 커요. 200행 이하의 필요한 보유 기록만 넣어주세요.";
  if (/no-data/.test(code)) return "항목 이름 아래에 보유 기록을 넣어주세요.";
  if (/quote|column-count/.test(code)) return "쉼표·따옴표와 각 행의 항목 수를 확인해주세요.";
  return "파일 내용을 읽을 수 없어요. UTF-8 CSV로 저장해 다시 선택해주세요.";
}
function PortfolioHoldingsCsvPanel({ holdings, unsupportedCount, busy, onBusy, onClose, onConfirm }) {
  const [text13, setText] = React2.useState(null);
  const [error, setError] = React2.useState("");
  const [result, setResult] = React2.useState(null);
  const [submitted, setSubmitted] = React2.useState(null);
  const generation = React2.useRef(0);
  React2.useEffect(() => () => {
    generation.current++;
  }, []);
  const computed = React2.useMemo(() => text13 === null ? null : buildHoldingCsvPreview(text13, holdings), [text13, holdings]);
  const report = submitted || computed;
  const load = async (file) => {
    const current = ++generation.current;
    setText(null);
    setError("");
    setResult(null);
    setSubmitted(null);
    if (!file) return;
    onBusy(true);
    try {
      if (file.size > HOLDINGS_CSV_LIMITS.maxCharacters * 3) throw Error("csv-input-too-large");
      const content = new TextDecoder("utf-8", { fatal: true }).decode(await file.arrayBuffer());
      if (generation.current === current) setText(content);
    } catch (failure2) {
      if (generation.current === current) setError(issue(failure2 instanceof Error ? failure2.message : "csv-invalid-text"));
    } finally {
      if (generation.current === current) onBusy(false);
    }
  };
  const confirm = async () => {
    if (!report?.readyForConfirmation || busy || submitted || unsupportedCount) return;
    const current = generation.current;
    const previews = report.rows.flatMap((row5) => row5.preview ? [row5.preview] : []);
    setSubmitted(report);
    setError("");
    onBusy(true);
    try {
      const value = await onConfirm(previews);
      if (generation.current === current) setResult(value);
    } catch {
      if (generation.current === current) setError("저장 결과를 확정하지 못했어요. 다시 저장하지 말고 목록을 다시 불러와 확인해주세요.");
    } finally {
      if (generation.current === current) onBusy(false);
    }
  };
  return /* @__PURE__ */ React2.createElement("section", { className: "an-nest-preview", "aria-label": "CSV 보유 기록 가져오기", style: { marginTop: 16 } }, /* @__PURE__ */ React2.createElement("h3", null, "파일로 한 번에 넣기"), /* @__PURE__ */ React2.createElement("p", null, "엑셀에서 UTF-8 CSV로 저장해주세요. 파일은 이 브라우저에서만 읽으며 원본을 서버에 보내지 않아요."), /* @__PURE__ */ React2.createElement("p", null, "현재 보유 수량으로 바꿔요. 기존 수량에 더하거나 거래 기록으로 등록하지 않아요. 파일에 없는 종목은 그대로 유지해요."), /* @__PURE__ */ React2.createElement("details", null, /* @__PURE__ */ React2.createElement("summary", null, "파일 형식과 예시"), /* @__PURE__ */ React2.createElement("pre", { style: { whiteSpace: "pre-wrap", overflowWrap: "anywhere", font: "inherit" } }, "시장,종목코드,수량,평균 매수가,이름,메모", "\n", "KR,005930,2,70000,삼성전자,장기 보유", "\n", "US,AAPL,1,180,Apple,"), /* @__PURE__ */ React2.createElement("p", null, "이름·메모·통화 열은 선택이에요. 기존 기록에서 빠진 선택 열은 유지하고, 빈칸으로 넣은 이름·메모는 비워요. 종목코드로 찾으며 이름으로 추측하지 않아요.")), /* @__PURE__ */ React2.createElement("label", { style: { marginTop: 12 } }, "CSV 파일", /* @__PURE__ */ React2.createElement("input", { type: "file", accept: ".csv,text/csv", disabled: busy, onChange: (e) => {
    void load(e.target.files?.[0]);
    e.target.value = "";
  } })), unsupportedCount ? /* @__PURE__ */ React2.createElement("p", { role: "alert" }, "지원하지 않는 기존 보유 항목 ", unsupportedCount, "개가 있어 전체 중복·한도를 확인할 수 없어요. 파일 저장은 보류하고 목록에서 항목별로 확인해주세요.") : null, error ? /* @__PURE__ */ React2.createElement("p", { role: "alert" }, error) : null, report ? /* @__PURE__ */ React2.createElement(React2.Fragment, null, /* @__PURE__ */ React2.createElement("p", { role: "status" }, "추가 ", report.counts.add, " · 수정 ", report.counts.edit, " · 변경 없음 ", report.counts.unchanged, " · 오류 ", report.counts.error), report.fatalErrors.map((entry, i) => /* @__PURE__ */ React2.createElement("p", { role: "alert", key: i }, entry.rowNumber, "행: ", issue(entry.code))), /* @__PURE__ */ React2.createElement("ul", { className: "an-nest-rows" }, report.rows.map((row5) => /* @__PURE__ */ React2.createElement("li", { key: row5.rowNumber }, /* @__PURE__ */ React2.createElement("div", { style: { minWidth: 0 } }, /* @__PURE__ */ React2.createElement("strong", null, row5.rowNumber, "행 · ", row5.ticker || "종목 확인 필요", " · ", { add: "추가", edit: "수정", unchanged: "변경 없음", error: "오류" }[row5.kind]), row5.errors.map((code, i) => /* @__PURE__ */ React2.createElement("p", { key: i }, issue(code))), row5.preview ? /* @__PURE__ */ React2.createElement("dl", null, row5.preview.changedFields.map((key) => /* @__PURE__ */ React2.createElement(React2.Fragment, { key }, /* @__PURE__ */ React2.createElement("dt", null, fields2[key]), /* @__PURE__ */ React2.createElement("dd", null, String(row5.preview.before?.[key] ?? "없음"), " → ", String(row5.preview.after?.[key] ?? "없음"))))) : null)))), !submitted ? /* @__PURE__ */ React2.createElement("p", null, "오류가 있으면 저장하지 않아요. 확인 후 한 항목씩 저장하며, 도중에 실패하면 그 지점에서 멈춰요.") : null, result ? /* @__PURE__ */ React2.createElement("div", { role: result.error || !result.refreshed ? "alert" : "status", "aria-live": "polite" }, /* @__PURE__ */ React2.createElement("p", null, result.total, "개 변경 중 ", result.saved, "개 저장을 확인했어요."), result.error ? /* @__PURE__ */ React2.createElement("p", null, result.saved + 1, "번째 항목에서 멈췄어요. 이 항목은 저장됐을 수도 있으니 목록에서 확인해주세요. 뒤의 ", Math.max(0, result.total - result.saved - 1), "개 항목은 요청하지 않았어요.") : null, !result.refreshed ? /* @__PURE__ */ React2.createElement("p", null, "새 목록 조회에 실패했어요. 다시 저장하지 말고 파일을 닫은 뒤 목록 다시 불러오기를 눌러주세요.") : null, /* @__PURE__ */ React2.createElement("p", null, "같은 파일을 다시 저장하지 말고, 새 목록을 기준으로 변경 내용을 다시 확인해주세요.")) : null) : null, /* @__PURE__ */ React2.createElement("div", { className: "an-nest-actions" }, /* @__PURE__ */ React2.createElement("button", { type: "button", disabled: busy || !!submitted || !!unsupportedCount || !report?.readyForConfirmation, onClick: confirm }, busy ? "확인 중…" : "변경 확인 후 파일 내용 저장"), /* @__PURE__ */ React2.createElement("button", { type: "button", disabled: busy, onClick: onClose }, "파일 닫기")));
}

// framer-components/public-probe/PortfolioHoldingValuation.ts
var positive2 = (value) => typeof value === "number" && Number.isFinite(value) && value > 0;
var market = (value) => /^(KR|KOSPI|KOSDAQ)$/i.test(value.trim()) ? "KR" : /^(US|NASDAQ|NYSE|AMEX)$/i.test(value.trim()) ? "US" : null;
function holdingValuation(holding, companies) {
  const unavailable2 = (reason) => ({ quote: null, value: null, gain: null, gainPct: null, reason });
  const matches = companies.filter((company) => company.ticker === holding.ticker && market(company.market) === holding.market);
  if (!matches.length) return unavailable2("종가 미연결 · 평가금액·손익 계산 보류");
  if (matches.length !== 1) return unavailable2("종가 자료 중복 · 평가금액·손익 계산 보류");
  const quote3 = matches[0].closeQuote;
  if (!quote3 || quote3.state !== "available") return unavailable2("종가 미제공 · 평가금액·손익 계산 보류");
  if (!positive2(quote3.price)) return unavailable2("종가 확인 필요 · 평가금액·손익 계산 보류");
  const result = { quote: quote3, value: null, gain: null, gainPct: null, reason: null };
  if (quote3.currency !== (holding.market === "KR" ? "KRW" : "USD")) return { ...result, reason: "종가와 매수가의 통화 확인 필요 · 계산 보류" };
  if (holding.duplicate) return { ...result, reason: "보유 기록 중복 확인 필요 · 계산 보류" };
  if (!positive2(holding.shares)) return { ...result, reason: "보유 수량 확인 필요 · 계산 보류" };
  const value = holding.shares * quote3.price;
  if (!positive2(value)) return { ...result, reason: "평가금액 계산 범위 초과" };
  if (!positive2(holding.avg_cost)) return { ...result, value, reason: "평균 매수가 확인 필요 · 손익 계산 보류" };
  const cost = holding.shares * holding.avg_cost, gain = value - cost, gainPct = (quote3.price / holding.avg_cost - 1) * 100;
  if (!positive2(cost) || !Number.isFinite(gain) || !Number.isFinite(gainPct)) return { ...result, value, reason: "손익 계산 범위 초과" };
  return { ...result, value, gain, gainPct };
}

// framer-components/public-probe/PortfolioCloseDetails.tsx
import * as React3 from "react";
function closePriceLabel(price, currency) {
  if (currency === "KRW" || currency === "USD") {
    return new Intl.NumberFormat("ko-KR", {
      style: "currency",
      currency,
      currencyDisplay: "code",
      maximumFractionDigits: currency === "KRW" ? 0 : 2
    }).format(price);
  }
  return `${new Intl.NumberFormat("ko-KR", { maximumFractionDigits: 2 }).format(price)}${currency ? ` ${currency}` : " · 단위 미제공"}`;
}
function changeLabel(changePct) {
  if (changePct === null) return "전 거래일 대비 미제공";
  if (changePct === 0) return "전 거래일 대비 0.00% · 보합";
  return `전 거래일 대비 ${changePct > 0 ? "+" : ""}${changePct.toFixed(2)}%`;
}
function freshnessLabel(freshness) {
  return freshness === "older" ? "이전 기준일 자료" : freshness === "unknown" ? "최신 거래일 여부 미확인" : "확인된 거래일 기준";
}

// framer-components/public-probe/PortfolioHoldingsPanel.tsx
var blank = () => ({ ticker: "", market: "KR", name: "", shares: "", avg_cost: "", memo: "" });
var CSS = `
.an-nest{color-scheme:light dark;--panel:light-dark(#fff,#171c23);--ink:light-dark(#191f28,#e3e7ec);--muted:light-dark(#6b7684,#9aa4b1);--soft:light-dark(#f8f9fb,#1d242c);--hover:light-dark(#f1f3f5,#252c35);--focus:light-dark(#e9edf2,#303945);background:var(--panel);color:var(--ink);font:600 13px/1.6 Pretendard,-apple-system,BlinkMacSystemFont,'Apple SD Gothic Neo',sans-serif;padding:20px;min-width:0}
.an-nest *{box-sizing:border-box}.an-nest h2,.an-nest h3,.an-nest p{margin:0}.an-nest h2{font-size:20px;font-weight:800}.an-nest h3{font-size:15px;font-weight:700}.an-nest p,.an-nest small{color:var(--muted);font-weight:600}.an-nest header{display:flex;justify-content:space-between;gap:12px;align-items:center;margin-bottom:16px}.an-nest button{font:inherit;font-weight:700;color:var(--ink);background:var(--soft);border:0;border-radius:8px;padding:6px 10px;min-height:32px;cursor:pointer;transition:background 160ms}.an-nest button:disabled{opacity:.5;cursor:default}.an-nest :is(button,input,select,textarea):focus-visible{outline:0;background:var(--focus)}.an-nest input,.an-nest select,.an-nest textarea{display:block;width:100%;font:inherit;color:var(--ink);background:var(--soft);border:0;border-radius:8px;padding:8px;min-height:36px}.an-nest textarea{resize:vertical;min-height:72px}.an-nest label{display:grid;gap:4px;color:var(--muted);font-weight:700}.an-nest-grid{display:grid;grid-template-columns:repeat(2,minmax(0,1fr));gap:12px}.an-nest-form,.an-nest-preview{padding:16px;border-radius:16px;background:var(--soft);margin-bottom:16px}.an-nest-summary{padding:12px 0;display:flex;gap:8px 14px;flex-wrap:wrap}.an-nest-summary strong{font-weight:800}.an-nest-form input,.an-nest-form select,.an-nest-form textarea{background:var(--panel)}.an-nest-actions{display:flex;gap:8px;flex-wrap:wrap;margin-top:12px}.an-nest-rows{display:grid;gap:8px;list-style:none;padding:0;margin:16px 0}.an-nest-rows li{display:flex;align-items:center;justify-content:space-between;gap:12px;background:var(--soft);padding:12px;border-radius:12px}.an-nest-rows strong{font-weight:700;overflow-wrap:anywhere}.an-nest-rows small{display:block}.an-nest-rows .an-nest-actions{margin:0;flex-shrink:0}.an-nest-preview dl{margin:8px 0;display:grid;grid-template-columns:100px minmax(0,1fr);gap:6px}.an-nest-preview dt{color:var(--muted)}.an-nest-preview dd{margin:0;overflow-wrap:anywhere;white-space:pre-wrap}.an-nest [role=alert]{padding:10px 0;color:var(--ink)}
@media(hover:hover){.an-nest button:not(:disabled):hover{background:var(--hover)}}@media(pointer:coarse){.an-nest button,.an-nest input,.an-nest select{min-height:44px}}@media(max-width:600px){.an-nest{padding:12px}.an-nest-grid{grid-template-columns:1fr}.an-nest-rows li{align-items:flex-start;flex-direction:column}.an-nest-preview dl{grid-template-columns:74px minmax(0,1fr)}}@media(prefers-reduced-motion:reduce){.an-nest button{transition:none}}
.an-nest-grid label{align-content:start}
.an-nest summary{display:flex;align-items:center;gap:8px;cursor:pointer;list-style:none;padding:6px 8px;border-radius:8px;min-height:32px}.an-nest summary::-webkit-details-marker{display:none}.an-nest summary::before{content:"";width:6px;height:6px;border-right:1.5px solid currentColor;border-bottom:1.5px solid currentColor;transform:rotate(-45deg);flex-shrink:0}.an-nest details[open]>summary::before{transform:rotate(45deg)}.an-nest summary:focus-visible{outline:0;background:var(--focus)}@media(hover:hover){.an-nest summary:hover{background:var(--hover)}}@media(pointer:coarse){.an-nest summary{min-height:44px}}
`;
var labels = { ticker: "종목코드", market: "시장", name: "이름", shares: "수량", avg_cost: "평균 매수가", memo: "메모" };
function errorText(error) {
  const code = error instanceof Error ? error.message : "";
  if (/invalid-shares|invalid-avg_cost/.test(code)) return "수량과 평균 매수가를 0보다 큰 숫자로 입력해주세요.";
  if (/ticker-requires-edit/.test(code)) return "이미 등록된 종목이에요. 목록에서 수정을 눌러주세요.";
  if (/invalid-ticker|invalid-market/.test(code)) return "시장과 종목코드를 확인해주세요. 국내·미국 주식과 ETF를 지원해요.";
  if (/stale|changed|conflict/.test(code)) return "다른 화면에서 보유 기록이 바뀌었어요. 다시 불러온 뒤 변경 내용을 확인해주세요.";
  if (/auth|owner|session|disposed/.test(code)) return "로그인 상태가 바뀌었어요. 다시 로그인한 뒤 확인해주세요.";
  if (/duplicate|holding-id|holding-not-found/.test(code)) return "수정할 보유 항목을 정확히 구분할 수 없어요. 목록을 다시 확인해주세요.";
  if (/no-holding-changes/.test(code)) return "변경한 내용이 없어요.";
  return "저장 여부를 확인하지 못했어요. 입력은 남겨두었어요. 다시 저장하기 전에 목록을 확인해주세요.";
}
function PortfolioHoldingsPanel({ state, visible, onBack, onConfirm, onConfirmCsv, onReload }) {
  const [form, setForm] = React4.useState(null);
  const [preview, setPreview] = React4.useState(null);
  const [busy, setBusy] = React4.useState(false);
  const [message, setMessage] = React4.useState("");
  const [error, setError] = React4.useState("");
  const [csvOpen, setCsvOpen] = React4.useState(false);
  const [lastSavedKind, setLastSavedKind] = React4.useState(null);
  const known = state.phase === "ready" || state.phase === "choose-stocks";
  const change = (key, value) => {
    setForm((old) => old ? { ...old, [key]: value } : old);
    setPreview(null);
    setError("");
  };
  const edit = (holding) => {
    setCsvOpen(false);
    setForm({ id: holding.id, ticker: holding.ticker, market: holding.market, name: holding.name, shares: holding.shares?.toString() || "", avg_cost: holding.avg_cost?.toString() || "", memo: holding.memo || "" });
    setPreview(null);
    setError("");
    setMessage("");
    setLastSavedKind(null);
  };
  const prepare = (remove) => {
    setError("");
    setMessage("");
    setLastSavedKind(null);
    try {
      if (remove) {
        setCsvOpen(false);
        setPreview(previewHoldingChange(state.holdings, { kind: "remove", id: remove.id }));
      } else if (form) {
        if (!form.id) setPreview(previewHoldingChange(state.holdings, { kind: "add", ...form }));
        else {
          const original = state.holdings.find((h) => h.id === form.id);
          if (!original) throw Error("holding-not-found");
          const fields3 = {};
          for (const key of ["name", "shares", "avg_cost", "memo"]) if (form[key] !== String(original[key] ?? "")) fields3[key] = form[key];
          setPreview(previewHoldingChange(state.holdings, { kind: "edit", id: form.id, ...fields3 }));
        }
      }
    } catch (e) {
      setError(errorText(e));
    }
  };
  const confirm = async () => {
    if (!preview || busy) return;
    setBusy(true);
    setError("");
    setMessage("");
    try {
      const kind = preview.kind, result = await onConfirm(preview);
      setPreview(null);
      setForm(null);
      setLastSavedKind(result.refreshed ? kind : null);
      setMessage(result.refreshed ? "보유 기록을 저장했어요. 거래 기록은 바뀌지 않았어요." : "저장 요청은 완료됐지만 새 목록을 불러오지 못했어요. 다시 저장하지 말고 목록을 다시 불러와 확인해주세요.");
    } catch (e) {
      setError(errorText(e));
    } finally {
      setBusy(false);
    }
  };
  return /* @__PURE__ */ React4.createElement("section", { className: "an-nest", "aria-label": "둥지 보유종목 관리", hidden: !visible, style: { position: "absolute", inset: 0, overflow: "auto", zIndex: 1 } }, /* @__PURE__ */ React4.createElement("style", null, CSS), /* @__PURE__ */ React4.createElement("header", null, /* @__PURE__ */ React4.createElement("div", null, /* @__PURE__ */ React4.createElement("h2", null, "둥지 보유목록"), /* @__PURE__ */ React4.createElement("p", null, "종목 관리와 지도 메모는 따로 저장해요.")), /* @__PURE__ */ React4.createElement("button", { type: "button", disabled: busy, onClick: onBack }, "지도로 돌아가기")), /* @__PURE__ */ React4.createElement("div", { className: "an-nest-actions" }, /* @__PURE__ */ React4.createElement("button", { type: "button", disabled: !known || busy, onClick: () => {
    setCsvOpen(false);
    setForm(blank());
    setPreview(null);
    setError("");
    setMessage("");
    setLastSavedKind(null);
  } }, "종목 추가"), /* @__PURE__ */ React4.createElement("button", { type: "button", disabled: !known || busy, onClick: () => {
    setCsvOpen(true);
    setForm(null);
    setPreview(null);
    setError("");
    setMessage("");
    setLastSavedKind(null);
  } }, "파일로 넣기"), /* @__PURE__ */ React4.createElement("button", { type: "button", disabled: busy, onClick: async () => {
    setBusy(true);
    setError("");
    try {
      if (!await onReload()) setError("목록을 불러오지 못했어요. 입력한 내용은 남겨두었어요.");
    } catch (e) {
      setError(errorText(e));
    } finally {
      setBusy(false);
    }
  } }, "목록 다시 불러오기")), known ? /* @__PURE__ */ React4.createElement("div", { className: "an-nest-summary", "aria-label": "둥지 항목 요약" }, /* @__PURE__ */ React4.createElement("span", null, /* @__PURE__ */ React4.createElement("strong", null, state.holdings.length), " 보유"), /* @__PURE__ */ React4.createElement("span", null, /* @__PURE__ */ React4.createElement("strong", null, state.watchlist?.length || 0), " 관심"), state.unsupportedCount || state.watchlistUnsupportedCount ? /* @__PURE__ */ React4.createElement("span", null, /* @__PURE__ */ React4.createElement("strong", null, state.unsupportedCount + (state.watchlistUnsupportedCount || 0)), " 지원 범위 밖") : null) : null, message ? /* @__PURE__ */ React4.createElement("p", { role: "status" }, message) : null, lastSavedKind && lastSavedKind !== "remove" ? /* @__PURE__ */ React4.createElement("p", null, "지도로 돌아가면 저장한 종목을 바로 확인할 수 있어요.") : null, error ? /* @__PURE__ */ React4.createElement("p", { role: "alert" }, error) : null, csvOpen ? /* @__PURE__ */ React4.createElement(PortfolioHoldingsCsvPanel, { holdings: state.holdings, unsupportedCount: state.unsupportedCount, busy: busy || !known, onBusy: setBusy, onClose: () => setCsvOpen(false), onConfirm: onConfirmCsv }) : null, form ? /* @__PURE__ */ React4.createElement("form", { className: "an-nest-form", onSubmit: (e) => {
    e.preventDefault();
    prepare();
  } }, /* @__PURE__ */ React4.createElement("h3", null, form.id ? "보유 기록 수정" : "보유종목 추가"), /* @__PURE__ */ React4.createElement("p", null, "입력값은 변경 내용을 확인한 뒤 저장돼요."), /* @__PURE__ */ React4.createElement("fieldset", { disabled: busy || !known, style: { border: 0, padding: 0, margin: "12px 0 0" } }, /* @__PURE__ */ React4.createElement("div", { className: "an-nest-grid" }, /* @__PURE__ */ React4.createElement("label", null, "시장", /* @__PURE__ */ React4.createElement("select", { value: form.market, disabled: !!form.id, onChange: (e) => change("market", e.target.value) }, /* @__PURE__ */ React4.createElement("option", { value: "KR" }, "국내 · KRW"), /* @__PURE__ */ React4.createElement("option", { value: "US" }, "미국 · USD"))), /* @__PURE__ */ React4.createElement("label", null, "종목코드", /* @__PURE__ */ React4.createElement("input", { value: form.ticker, disabled: !!form.id, onChange: (e) => change("ticker", e.target.value), placeholder: form.market === "KR" ? "005930" : "AAPL" })), /* @__PURE__ */ React4.createElement("label", null, "이름", /* @__PURE__ */ React4.createElement("input", { value: form.name, onChange: (e) => change("name", e.target.value) })), /* @__PURE__ */ React4.createElement("label", null, "수량", /* @__PURE__ */ React4.createElement("input", { inputMode: "decimal", value: form.shares, onChange: (e) => change("shares", e.target.value) })), /* @__PURE__ */ React4.createElement("label", null, "평균 매수가 · ", form.market === "KR" ? "KRW" : "USD", /* @__PURE__ */ React4.createElement("input", { inputMode: "decimal", value: form.avg_cost, onChange: (e) => change("avg_cost", e.target.value) })), /* @__PURE__ */ React4.createElement("label", null, "보유 메모", /* @__PURE__ */ React4.createElement("textarea", { value: form.memo, onChange: (e) => change("memo", e.target.value) }))), /* @__PURE__ */ React4.createElement("div", { className: "an-nest-actions" }, /* @__PURE__ */ React4.createElement("button", { type: "submit" }, "변경 내용 확인"), /* @__PURE__ */ React4.createElement("button", { type: "button", onClick: () => {
    setForm(null);
    setPreview(null);
  } }, "입력 취소")))) : null, preview ? /* @__PURE__ */ React4.createElement("section", { className: "an-nest-preview", "aria-label": "보유 변경 미리보기" }, /* @__PURE__ */ React4.createElement("h3", null, preview.kind === "remove" ? "이 보유 기록을 삭제할까요?" : "이 내용으로 저장할까요?"), /* @__PURE__ */ React4.createElement("p", null, preview.kind === "remove" ? "목록의 보유 기록만 삭제해요. 실제 매도나 거래 기록 추가가 아니며 지도 메모도 삭제하지 않아요." : "현재 기록과 비교해주세요. 다른 화면에서 동시에 수정하지 않는 것이 좋아요."), /* @__PURE__ */ React4.createElement("dl", null, /* @__PURE__ */ React4.createElement("dt", null, "종목"), /* @__PURE__ */ React4.createElement("dd", null, preview.after?.name || preview.before?.name, " · ", preview.after?.ticker || preview.before?.ticker), (preview.kind === "remove" ? ["shares", "avg_cost", "memo"] : preview.changedFields).map((key) => /* @__PURE__ */ React4.createElement(React4.Fragment, { key }, /* @__PURE__ */ React4.createElement("dt", null, labels[key]), /* @__PURE__ */ React4.createElement("dd", null, String(preview.before?.[key] ?? "없음"), " → ", String(preview.after?.[key] ?? "삭제"))))), /* @__PURE__ */ React4.createElement("div", { className: "an-nest-actions" }, /* @__PURE__ */ React4.createElement("button", { type: "button", disabled: busy || !known, onClick: confirm }, busy ? "확인 중…" : preview.kind === "remove" ? "확인 후 보유 기록 삭제" : "확인 후 보유 기록 저장"), /* @__PURE__ */ React4.createElement("button", { type: "button", disabled: busy, onClick: () => setPreview(null) }, "돌아가서 수정"))) : null, !known ? /* @__PURE__ */ React4.createElement("p", { role: "status" }, state.phase === "error" ? "목록을 불러오지 못했어요. 보유 기록이 없다는 뜻은 아니에요." : "보유목록을 확인하고 있어요.") : /* @__PURE__ */ React4.createElement(React4.Fragment, null, state.holdings.length ? /* @__PURE__ */ React4.createElement("p", null, "연결된 종가 기준으로 계산해요. 실시간 가격이 아니며 수수료·세금·환율 손익은 제외해요.") : null, /* @__PURE__ */ React4.createElement("ul", { className: "an-nest-rows" }, state.holdings.map((h) => {
    const valuation = holdingValuation(h, state.graph?.companies || []), quote3 = valuation.quote;
    return /* @__PURE__ */ React4.createElement("li", { key: h.market + ":" + h.ticker }, /* @__PURE__ */ React4.createElement("div", null, /* @__PURE__ */ React4.createElement("strong", null, h.name), /* @__PURE__ */ React4.createElement("small", null, h.ticker, " · ", h.market, " · ", state.selectedTickers.includes(h.ticker) ? "분석 범위에 포함" : "분석 범위 밖"), /* @__PURE__ */ React4.createElement("small", null, "수량 ", h.duplicate ? "중복 확인 필요" : formatHoldingQuantity(h.shares), " · 평균 매수가 ", formatHoldingAverageCost(h)), quote3 ? /* @__PURE__ */ React4.createElement(React4.Fragment, null, /* @__PURE__ */ React4.createElement("small", null, "종가 ", closePriceLabel(quote3.price, quote3.currency), " · ", changeLabel(quote3.changePct)), /* @__PURE__ */ React4.createElement("small", null, quote3.priceDate, " · ", quote3.source, " · ", freshnessLabel(quote3.freshness))) : null, quote3 && valuation.value !== null ? /* @__PURE__ */ React4.createElement("small", null, "평가금액 ", closePriceLabel(valuation.value, quote3.currency), valuation.gain !== null && valuation.gainPct !== null ? /* @__PURE__ */ React4.createElement(React4.Fragment, null, " · 평가손익 ", valuation.gain > 0 ? "+" : "", closePriceLabel(valuation.gain, quote3.currency), " (", valuation.gainPct > 0 ? "+" : "", valuation.gainPct.toFixed(2), "%)") : null) : null, valuation.reason ? /* @__PURE__ */ React4.createElement("small", null, valuation.reason) : null), /* @__PURE__ */ React4.createElement("div", { className: "an-nest-actions" }, /* @__PURE__ */ React4.createElement("button", { type: "button", disabled: busy || !h.id || h.duplicate, onClick: () => edit(h), "aria-label": h.name + " 수정" }, "수정"), /* @__PURE__ */ React4.createElement("button", { type: "button", disabled: busy || !h.id || h.duplicate, onClick: () => prepare(h), "aria-label": h.name + " 삭제" }, "삭제")));
  })), !state.holdings.length ? /* @__PURE__ */ React4.createElement("p", null, "등록한 보유종목이 없어요. 종목 추가로 시작하세요.") : null, state.unsupportedCount ? /* @__PURE__ */ React4.createElement("p", null, "이 지도에서 지원하지 않는 보유 항목 ", state.unsupportedCount, "개는 별도로 유지돼요.") : null, state.watchlistError ? /* @__PURE__ */ React4.createElement("p", { role: "status" }, "관심종목을 불러오지 못했어요. 목록 다시 불러오기로 재시도할 수 있어요.") : state.watchlist?.length ? /* @__PURE__ */ React4.createElement("details", null, /* @__PURE__ */ React4.createElement("summary", null, "관심종목 ", state.watchlist.length, "개"), /* @__PURE__ */ React4.createElement("p", null, "관심종목은 보유 수량·평균 매수가에 포함하지 않아요."), /* @__PURE__ */ React4.createElement("ul", { className: "an-nest-rows" }, state.watchlist.map((stock) => /* @__PURE__ */ React4.createElement("li", { key: stock.market + ":" + stock.ticker }, /* @__PURE__ */ React4.createElement("div", null, /* @__PURE__ */ React4.createElement("strong", null, stock.name), /* @__PURE__ */ React4.createElement("small", null, stock.ticker, " · ", stock.market, " · ", state.holdings.some((h) => h.ticker === stock.ticker && h.market === stock.market) ? "보유·관심" : "관심만", " · ", state.selectedTickers.includes(stock.ticker) ? "분석 범위에 포함" : "분석 범위 밖")))))) : null, state.watchlistUnsupportedCount ? /* @__PURE__ */ React4.createElement("p", null, "지원하지 않는 관심 항목 ", state.watchlistUnsupportedCount, "개는 원래 목록에 유지돼요.") : null));
}

// framer-components/public-probe/PortfolioHoldingsEditor.ts
var API2 = "https://project-yw131.vercel.app/api/holdings";
var USER_ID2 = /^[a-f0-9]{8}(?:-[a-f0-9]{4}){3}-[a-f0-9]{12}$/i;
var TICKER = { KR: /^[0-9A-Z]{6}$/, US: /^[A-Z][A-Z0-9.-]{0,14}$/ };
var EDIT_FIELDS = ["shares", "avg_cost", "name", "memo"];
var PortfolioHoldingsEditorError = class extends Error {
  constructor(code) {
    super(code);
    __publicField(this, "code", code);
    this.name = code;
  }
};
function fail2(code) {
  throw new PortfolioHoldingsEditorError(code);
}
var isRecord = (value) => !!value && typeof value === "object" && !Array.isArray(value);
var sameUser = (left, right) => !!right && left.userId === right.userId;
var sameText = (left, right) => (left || "") === (right || "");
var copy3 = (value) => JSON.parse(JSON.stringify(value));
function sessionFor(getSession) {
  try {
    const value = getSession();
    return value && USER_ID2.test(value.userId) && typeof value.token === "string" && value.token.trim() ? value : null;
  } catch {
    return null;
  }
}
function positiveStoredNumber(value) {
  if (typeof value === "boolean") return null;
  if (typeof value === "string") {
    const text13 = value.replace(/[,\s₩$원]/g, "");
    if (!/^[+-]?(?:\d+(?:\.\d*)?|\.\d+)(?:[eE][+-]?\d+)?$/.test(text13)) return null;
    value = Number(text13);
  }
  return typeof value === "number" && Number.isFinite(value) && value > 0 ? value : null;
}
function holdingRow(value) {
  if (!isRecord(value) || typeof value.id !== "string" || !value.id.trim() || typeof value.ticker !== "string" || typeof value.market !== "string" || typeof value.name !== "string") return null;
  const ticker = value.ticker.trim().toUpperCase(), rawMarket = value.market.trim().toLowerCase();
  const market2 = rawMarket === "kr" ? "KR" : rawMarket === "us" ? "US" : null;
  if (!market2 || !TICKER[market2].test(ticker)) return null;
  return {
    id: value.id.trim(),
    ticker,
    market: market2,
    name: value.name,
    shares: positiveStoredNumber(value.shares),
    avg_cost: positiveStoredNumber(value.avg_cost),
    memo: typeof value.memo === "string" ? value.memo : "",
    duplicate: false
  };
}
function holdingsRows(value) {
  const values = Array.isArray(value) ? value : isRecord(value) && Array.isArray(value.holdings) ? value.holdings : null;
  if (!values) return fail2("holdings-unavailable");
  const tickers = values.map((row5) => {
    if (!isRecord(row5) || typeof row5.ticker !== "string" || !row5.ticker.trim()) fail2("holdings-unavailable");
    return row5.ticker.trim().toUpperCase();
  });
  return { rows: values.map(holdingRow).filter((row5) => row5 !== null), tickers };
}
function sameHolding(left, right) {
  return left.id === right.id && left.ticker === right.ticker && left.market === right.market && (left.name.trim() || left.ticker) === (right.name.trim() || right.ticker) && left.shares === right.shares && left.avg_cost === right.avg_cost && sameText(left.memo, right.memo) && left.duplicate !== true && right.duplicate !== true;
}
function editFields(preview) {
  if (!Array.isArray(preview.changedFields) || !preview.changedFields.length || new Set(preview.changedFields).size !== preview.changedFields.length) fail2("invalid-preview");
  if (!preview.changedFields.every((field3) => EDIT_FIELDS.includes(field3))) fail2("invalid-preview");
  return preview.changedFields;
}
function canonicalPreview(fresh, preview) {
  if (preview.kind === "add") {
    const after2 = preview.after;
    if (preview.id !== null || preview.before !== null || !after2 || after2.id !== null || typeof after2.name !== "string" || typeof after2.memo !== "string") fail2("invalid-preview");
    if (fresh.some((row5) => row5.ticker === after2.ticker)) fail2("preflight-ticker-exists");
    return previewHoldingChange([], { kind: "add", ticker: after2.ticker, market: after2.market, shares: after2.shares, avg_cost: after2.avg_cost, name: after2.name, memo: after2.memo });
  }
  const before = preview.before;
  if (!preview.id || !before?.id || preview.id !== before.id) fail2("invalid-preview");
  const targets = fresh.filter((row5) => row5.id === before.id);
  if (targets.length !== 1 || !sameHolding(targets[0], before)) fail2("preflight-stale");
  if (preview.kind === "remove") {
    if (preview.after !== null || preview.changedFields.length) fail2("invalid-preview");
    return previewHoldingChange([targets[0]], { kind: "remove", id: before.id });
  }
  const after = preview.after, fields3 = editFields(preview);
  if (!after || after.id !== before.id || after.ticker !== before.ticker || after.market !== before.market) fail2("invalid-preview");
  const change = { kind: "edit", id: before.id };
  fields3.forEach((field3) => {
    change[field3] = after[field3];
  });
  return previewHoldingChange([targets[0]], change);
}
function acknowledged(preview, value) {
  if (preview.kind === "remove") {
    if (!isRecord(value) || value.ok !== true || !preview.id) fail2("write-unacknowledged");
    return { kind: "deleted", id: preview.id };
  }
  const row5 = holdingRow(value), after = preview.after;
  if (!row5 || !after || preview.kind === "edit" && row5.id !== preview.id || row5.ticker !== after.ticker || row5.market !== after.market || row5.name !== after.name || row5.shares !== after.shares || row5.avg_cost !== after.avg_cost || !sameText(row5.memo, after.memo)) fail2("write-unacknowledged");
  return { kind: "saved", row: row5 };
}
function createPortfolioHoldingsEditor(options = {}) {
  const getSession = options.getSession || readMapSession, fetcher = options.fetcher || fetch;
  const timeoutMs = typeof options.timeoutMs === "number" && Number.isFinite(options.timeoutMs) && options.timeoutMs > 0 ? options.timeoutMs : 15e3;
  let disposed = false, writing = false;
  const pending = /* @__PURE__ */ new Set();
  const current = (account) => {
    if (disposed) fail2("editor-disposed");
    const value = sessionFor(getSession);
    if (!value) fail2("authentication-required");
    if (!sameUser(account, value)) fail2("session-changed");
    return value;
  };
  const request = async (init, failure2) => {
    const controller = new AbortController(), timer = setTimeout(() => controller.abort(), timeoutMs);
    pending.add(controller);
    try {
      const response = await fetcher(API2, { ...init, signal: controller.signal, cache: "no-store", credentials: "omit", redirect: "error" });
      return { response, body: await response.json() };
    } catch {
      if (disposed) fail2("editor-disposed");
      if (controller.signal.aborted) fail2("request-timeout");
      fail2(failure2);
    } finally {
      clearTimeout(timer);
      pending.delete(controller);
    }
  };
  return {
    prepare(records, change) {
      return previewHoldingChange(records, change);
    },
    async confirm(preview) {
      if (writing) fail2("mutation-in-flight");
      const account = sessionFor(getSession);
      if (!account) fail2("authentication-required");
      writing = true;
      try {
        const readSession = current(account);
        const preflight = await request({ headers: { Authorization: "Bearer " + readSession.token } }, "holdings-unavailable");
        current(account);
        if (!preflight.response.ok) fail2(preflight.response.status === 401 ? "authentication-required" : "holdings-unavailable");
        const fresh = holdingsRows(preflight.body);
        current(account);
        if (preview.kind === "add" && fresh.tickers.includes(String(preview.after?.ticker || "").trim().toUpperCase())) fail2("preflight-ticker-exists");
        const canonical = canonicalPreview(fresh.rows, preview);
        const writeSession = current(account);
        const write = await request({ method: canonical.request.method, headers: { Authorization: "Bearer " + writeSession.token, "Content-Type": "application/json" }, body: JSON.stringify(canonical.request.body) }, "write-failed");
        current(account);
        if (!write.response.ok) fail2(write.response.status === 401 ? "authentication-required" : "write-failed");
        const result = acknowledged(canonical, write.body);
        current(account);
        options.onSaved?.(copy3(result));
        return result;
      } finally {
        writing = false;
      }
    },
    dispose() {
      if (!disposed) {
        disposed = true;
        pending.forEach((controller) => controller.abort());
        pending.clear();
      }
    }
  };
}

// framer-components/public-probe/PortfolioHoldingsCsvSave.ts
async function saveConfirmedHoldingCsv(previews, options) {
  if (!previews.length || previews.length > HOLDINGS_CSV_LIMITS.maxRows || previews.some((p) => !p.after || p.kind === "remove") || new Set(previews.map((p) => p.after.ticker)).size !== previews.length) throw Error("invalid-csv-preview");
  const changes = JSON.parse(JSON.stringify(previews));
  const getSession = options.getSession || readMapSession, account = getSession();
  if (!account) throw Error("authentication-required");
  const current = () => options.isCurrent() && getSession()?.userId === account.userId;
  let saved = 0, error = null;
  for (const preview of changes) {
    if (!current()) throw Error("session-changed");
    try {
      await options.editor.confirm(preview);
      saved++;
    } catch (failure2) {
      error = failure2 instanceof Error ? failure2.message : "write-failed";
      break;
    }
    if (!current()) throw Error("session-changed");
  }
  if (!current()) throw Error("session-changed");
  let refreshed = false;
  try {
    refreshed = await options.reload();
  } catch {
  }
  if (!current()) throw Error("session-changed");
  return { saved, total: changes.length, refreshed, error };
}

// framer-components/public-probe/PortfolioMapTheme.tsx
import { useEffect as useEffect2, useState as useState3 } from "react";
var THEME_KEY = "verity_theme";
var THEME_EVENT = "alphanest-theme-preference";
function readPortfolioMapTheme({
  htmlTheme,
  bodyTheme,
  storedTheme
} = {}) {
  if (htmlTheme === "dark" || htmlTheme === "light") return htmlTheme;
  if (bodyTheme === "dark" || bodyTheme === "light") return bodyTheme;
  if (storedTheme === "dark" || storedTheme === "light") return storedTheme;
  return "light";
}
function browserThemeInput() {
  if (typeof window === "undefined" || typeof document === "undefined")
    return {};
  let storedTheme = null;
  try {
    storedTheme = window.localStorage.getItem(THEME_KEY);
  } catch {
  }
  return {
    htmlTheme: document.documentElement?.dataset.anTheme,
    bodyTheme: document.body?.dataset.framerTheme,
    storedTheme
  };
}
function usePortfolioMapTheme() {
  const [theme, setTheme] = useState3(
    () => readPortfolioMapTheme(browserThemeInput())
  );
  useEffect2(() => {
    if (typeof window === "undefined" || typeof document === "undefined")
      return;
    const sync = () => setTheme(readPortfolioMapTheme(browserThemeInput()));
    const observer = typeof MutationObserver === "undefined" ? null : new MutationObserver(sync);
    const onStorage = (event) => {
      if (!event.key || event.key === THEME_KEY) sync();
    };
    sync();
    observer?.observe(document.documentElement, {
      attributes: true,
      attributeFilter: ["data-an-theme"]
    });
    if (document.body) {
      observer?.observe(document.body, {
        attributes: true,
        attributeFilter: ["data-framer-theme"]
      });
    }
    window.addEventListener("storage", onStorage);
    window.addEventListener(THEME_EVENT, sync);
    return () => {
      observer?.disconnect();
      window.removeEventListener("storage", onStorage);
      window.removeEventListener(THEME_EVENT, sync);
    };
  }, []);
  return theme;
}

// framer-components/public-probe/PublicPortfolioPrototype.tsx
function PublicPortfolioPrototype({ template = "", templateURL }) {
  const theme = usePortfolioMapTheme();
  const frame = React5.useRef(null);
  const controller = React5.useRef(null);
  const editor = React5.useRef(null);
  const bridge = React5.useRef(null);
  const [state, setState] = React5.useState(null);
  const [source, setSource] = React5.useState(null);
  const [view, setView] = React5.useState("map");
  const [memberEpoch, setMemberEpoch] = React5.useState(0);
  const needsLoginCheck = state?.error === "authentication-required" || state?.watchlistError === "authentication-required" || state?.privateState.error === "authentication-required";
  React5.useEffect(() => {
    if (!frame.current) return;
    const workspace = createPortfolioMapWorkspace({ includeWatchlist: true, usePortfolioAnalysis: true });
    let holdingsEditor = createPortfolioHoldingsEditor();
    editor.current = holdingsEditor;
    controller.current = workspace;
    const unsubscribe = workspace.subscribe((value) => {
      setState(value);
      if (value.phase !== "ready") setSource(null);
      if (value.phase === "signed-out") {
        bridge.current?.clearReturnFocus();
        holdingsEditor.dispose();
        holdingsEditor = createPortfolioHoldingsEditor();
        editor.current = holdingsEditor;
        setSelected([]);
        setView("map");
        setMemberEpoch((epoch) => epoch + 1);
      }
    });
    const logoLoader = createPortfolioPublicLogoLoader();
    const unmount = mountMemberPrototype(frame.current, template, workspace, { openSource: setSource, openHoldings: () => setView("holdings"), templateURL, logoLoader });
    bridge.current = unmount;
    const unbind = workspace.bindAuth(window);
    const stopDataRefresh = workspace.bindDataRefresh(window);
    void workspace.open();
    return () => {
      stopDataRefresh();
      unmount();
      unsubscribe();
      unbind();
      holdingsEditor.dispose();
      workspace.dispose();
      controller.current = null;
      editor.current = null;
      bridge.current = null;
    };
  }, [template, templateURL]);
  const [selected, setSelected] = React5.useState([]);
  return /* @__PURE__ */ React5.createElement("section", { "aria-label": "내 포트폴리오 관계지도", style: { position: "relative", width: "100%", minWidth: 0 } }, /* @__PURE__ */ React5.createElement("style", null, `.an-data-refresh{display:flex;flex-wrap:wrap;align-items:center;gap:8px;padding:8px 12px;background:var(--an-refresh-bg);color:var(--an-refresh-text);font:600 12px/1.6 Pretendard,-apple-system,BlinkMacSystemFont,'Apple SD Gothic Neo',sans-serif}.an-data-refresh button{border:0;border-radius:8px;padding:6px 8px;min-height:32px;background:var(--an-refresh-card);color:inherit;font-family:inherit;font-size:12px;line-height:1.6;font-weight:700;cursor:pointer;transition:background 160ms}.an-data-refresh button:focus-visible{outline:0;background:var(--an-refresh-focus)}.an-data-refresh button:disabled{cursor:wait;opacity:.65}@media(hover:hover){.an-data-refresh button:not(:disabled):hover{background:var(--an-refresh-hover)}}@media(pointer:coarse){.an-data-refresh button{min-height:44px}}@media(prefers-reduced-motion:reduce){.an-data-refresh button{transition:none}}`), !state || state.phase === "loading" || state.phase === "signed-out" ? /* @__PURE__ */ React5.createElement("p", { role: "status" }, state?.phase === "signed-out" ? "로그인 후 지도 자료를 불러옵니다." : "보유종목과 지도 자료를 불러오는 중이에요.") : null, state?.phase === "ready" ? /* @__PURE__ */ React5.createElement("div", { className: "an-data-refresh", "aria-label": "지도 자료 갱신", style: {
    "--an-refresh-bg": theme === "dark" ? "#1d242c" : "#f8f9fb",
    "--an-refresh-card": theme === "dark" ? "#171c23" : "#ffffff",
    "--an-refresh-text": theme === "dark" ? "#e3e7ec" : "#191f28",
    "--an-refresh-hover": theme === "dark" ? "#252c35" : "#f1f3f5",
    "--an-refresh-focus": theme === "dark" ? "#303945" : "#e9edf2"
  } }, /* @__PURE__ */ React5.createElement("span", { role: "status" }, state.dataRefresh?.phase === "checking" ? "자료 변경을 확인 중이에요. 지도는 계속 사용할 수 있어요." : state.dataRefresh?.phase === "available" ? "지도에 반영할 자료 변경이 있어요." : state.dataRefresh?.phase === "error" ? "자료 확인이 지연됐어요. 기존 지도와 기록은 유지했어요." : "화면을 보는 동안 5분마다 자료 변경을 확인해요."), !!state.dataRefresh?.incompleteSources ? /* @__PURE__ */ React5.createElement("span", { role: "status" }, "원문 연결 범위 ", state.dataRefresh.incompleteSources, "/", state.dataRefresh.totalSources, "개가 부분적이거나 확인이 필요해요. 이 숫자만으로 조회 실패를 뜻하지는 않아요. 누락된 기존 원문은 이전 조회 내용으로 유지해요.") : null, state.dataRefresh?.checkedAt ? /* @__PURE__ */ React5.createElement("span", null, "최근 조회 ", new Date(state.dataRefresh.checkedAt).toLocaleTimeString("ko-KR", { hour: "2-digit", minute: "2-digit" }), " · 자료 기준일은 원문별 확인") : null, state.dataRefresh?.phase === "available" ? /* @__PURE__ */ React5.createElement("button", { type: "button", onClick: () => {
    controller.current?.applyDataUpdate();
  } }, "변경 자료 반영") : /* @__PURE__ */ React5.createElement("button", { type: "button", disabled: state.dataRefresh?.phase === "checking", onClick: () => {
    void controller.current?.refreshData();
  } }, "자료 다시 확인")) : null, state?.phase === "choose-stocks" ? /* @__PURE__ */ React5.createElement("div", null, /* @__PURE__ */ React5.createElement("p", null, "지도에 함께 표시할 종목을 최대 30개 골라주세요. 둥지의 보유 목록은 바뀌지 않아요."), workspaceStocks(state).map((h) => /* @__PURE__ */ React5.createElement("label", { key: h.ticker }, /* @__PURE__ */ React5.createElement(
    "input",
    {
      type: "checkbox",
      checked: selected.includes(h.ticker),
      disabled: !selected.includes(h.ticker) && selected.length >= 30,
      onChange: (e) => setSelected((old) => e.target.checked ? [...old, h.ticker] : old.filter((t) => t !== h.ticker))
    }
  ), h.name, " · ", h.held ? h.watched ? "보유·관심" : "보유" : "관심")), /* @__PURE__ */ React5.createElement("button", { type: "button", disabled: !selected.length, onClick: () => {
    void controller.current?.showTickers(selected);
  } }, "지도에서 보기"), /* @__PURE__ */ React5.createElement("button", { type: "button", onClick: () => setView("holdings") }, "보유목록")) : null, needsLoginCheck ? /* @__PURE__ */ React5.createElement("div", { className: "an-data-refresh", role: "alert", style: {
    "--an-refresh-bg": theme === "dark" ? "#1d242c" : "#f8f9fb",
    "--an-refresh-card": theme === "dark" ? "#171c23" : "#ffffff",
    "--an-refresh-text": theme === "dark" ? "#e3e7ec" : "#191f28",
    "--an-refresh-hover": theme === "dark" ? "#252c35" : "#f1f3f5",
    "--an-refresh-focus": theme === "dark" ? "#303945" : "#e9edf2"
  } }, "로그인 상태를 다시 확인해 주세요. 저장된 기록은 그대로 유지돼요.", /* @__PURE__ */ React5.createElement("button", { type: "button", onClick: () => {
    if (!state?.privateState.dirty && view !== "holdings" || window.confirm("새로고침하면 저장되지 않은 변경이 사라질 수 있어요. 계속할까요?")) window.location.reload();
  } }, "로그인 상태 다시 확인")) : null, state?.watchlistError && state.watchlistError !== "authentication-required" && (state.phase === "ready" || state.phase === "choose-stocks") ? /* @__PURE__ */ React5.createElement("p", { role: "status" }, "관심종목을 불러오지 못했어요. 보유종목은 그대로 볼 수 있어요. 보유목록에서 다시 불러올 수 있어요.") : null, state?.phase === "error" && state.error !== "authentication-required" ? /* @__PURE__ */ React5.createElement("div", { role: "alert" }, "자료를 불러오지 못했어요. 저장한 기록은 그대로예요.", /* @__PURE__ */ React5.createElement("button", { type: "button", onClick: () => {
    void controller.current?.open();
  } }, "다시 불러오기")) : null, state?.phase === "ready" && (state.privateState.phase === "conflict" || state.privateState.phase === "error" && state.privateState.error !== "authentication-required") ? /* @__PURE__ */ React5.createElement("div", { role: "alert" }, state.privateState.phase === "conflict" ? "다른 화면에서 기록이 바뀌었어요. 내 변경은 아직 저장되지 않았어요." : "저장 기록을 확인하지 못했어요. 현재 변경은 유지하고 있어요.", state.privateState.phase === "error" && state.privateState.error !== "authentication-required" && state.privateState.dirty ? /* @__PURE__ */ React5.createElement("button", { type: "button", onClick: () => {
    void controller.current?.save();
  } }, "저장 다시 시도") : null, /* @__PURE__ */ React5.createElement("button", { type: "button", onClick: () => {
    if (!state.privateState.dirty || window.confirm("현재 미저장 변경을 버리고 저장된 기록을 다시 불러올까요?")) void controller.current?.reloadSaved(state.privateState.dirty);
  } }, "저장 기록 다시 불러오기")) : null, source ? /* @__PURE__ */ React5.createElement("div", { role: "status" }, /* @__PURE__ */ React5.createElement("a", { href: source, target: "_blank", rel: "noopener noreferrer" }, "선택한 원문 열기"), /* @__PURE__ */ React5.createElement("button", { type: "button", onClick: () => setSource(null) }, "닫기")) : null, /* @__PURE__ */ React5.createElement(
    "iframe",
    {
      ref: frame,
      title: "내 종목 작업판",
      sandbox: "allow-scripts",
      referrerPolicy: "no-referrer",
      style: { display: "block", visibility: view === "map" ? "visible" : "hidden", width: "100%", height: "max(680px, calc(100dvh - 40px))", border: 0 }
    }
  ), state && state.phase !== "signed-out" ? /* @__PURE__ */ React5.createElement(
    PortfolioHoldingsPanel,
    {
      key: memberEpoch,
      state,
      visible: view === "holdings",
      onBack: () => {
        setView("map");
        bridge.current?.returnToMap();
      },
      onReload: () => controller.current?.open() || Promise.resolve(false),
      onConfirmCsv: (previews) => {
        bridge.current?.clearReturnFocus();
        const currentEditor = editor.current, workspace = controller.current;
        if (!currentEditor || !workspace) return Promise.reject(Error("session-unavailable"));
        return saveConfirmedHoldingCsv(previews, {
          editor: currentEditor,
          isCurrent: () => editor.current === currentEditor && controller.current === workspace,
          reload: () => workspace.open()
        });
      },
      onConfirm: async (preview) => {
        const currentEditor = editor.current, workspace = controller.current;
        if (!currentEditor || !workspace) throw Error("session-unavailable");
        const completeFocus = bridge.current?.prepareReturnFocus();
        const result = await currentEditor.confirm(preview);
        if (editor.current !== currentEditor || controller.current !== workspace) throw Error("session-changed");
        const refreshed = await workspace.open();
        if (editor.current !== currentEditor || controller.current !== workspace) throw Error("session-changed");
        if (refreshed && result.kind === "saved") completeFocus?.(result.row.ticker);
        return { refreshed };
      }
    }
  ) : null);
}

// output/member-map-integration-20260927/PortfolioMapReview.entry.tsx
function PublicPortfolioMapReview({ minHeight = 820, style }) {
  const isStatic = useIsStaticRenderer();
  return /* @__PURE__ */ React6.createElement("div", { style: { ...style, position: "relative", width: "100%", minHeight, boxSizing: "border-box" } }, isStatic ? /* @__PURE__ */ React6.createElement("section", { "aria-label": "회원 지도 검수용" }, /* @__PURE__ */ React6.createElement("h2", null, "회원 지도 검수용"), /* @__PURE__ */ React6.createElement("p", null, "실제 미리보기에서 로그인 후 보유종목과 저장 기록을 불러옵니다. 공개 사이트는 바꾸지 않습니다.")) : /* @__PURE__ */ React6.createElement(PublicPortfolioPrototype, { templateURL: "/member-map-canvas" }));
}
addPropertyControls(PublicPortfolioMapReview, {
  minHeight: { type: ControlType.Number, title: "최소 높이", defaultValue: 820, min: 480, max: 1200, step: 20 }
});
export {
  PublicPortfolioMapReview as default
};
/** @preserve User-approved review-only member map. Preserve the published site and existing member data.
 * Uses the existing authenticated candidate unchanged; no embedded session or fixture holdings.
 */
/**
 * @preserve
 * @framerIntrinsicWidth 1200
 * @framerIntrinsicHeight 820
 * @framerSupportedLayoutWidth any-prefer-fixed
 * @framerSupportedLayoutHeight auto
 */
