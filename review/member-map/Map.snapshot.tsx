var __defProp = Object.defineProperty;
var __defNormalProp = (obj, key, value) => key in obj ? __defProp(obj, key, { enumerable: true, configurable: true, writable: true, value }) : obj[key] = value;
var __publicField = (obj, key, value) => __defNormalProp(obj, typeof key !== "symbol" ? key + "" : key, value);

// output/member-map-integration-20260927/PortfolioMapReview.entry.tsx
import * as React5 from "react";
import { addPropertyControls, ControlType, useIsStaticRenderer } from "framer";

// framer-components/public-probe/PublicPortfolioPrototype.tsx
import * as React4 from "react";

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
var periodOrder = (row) => `${text(row.end) || "0000-00-00"}\0${text(row.year).padStart(8, "0")}`;
function uniqueAnnual(rows2) {
  const unique3 = /* @__PURE__ */ new Map();
  for (const row of rows2.slice().sort((a, b) => periodOrder(a).localeCompare(periodOrder(b)))) unique3.set(`${text(row.start)}\0${text(row.end)}\0${text(row.year)}`, row);
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
  list(chain.snippets).forEach((row, index) => {
    const snippet = text(row.snippet);
    if (!snippet || seen.has(snippet)) return;
    seen.add(snippet);
    items.push({ id: `customer-${index}`, title: `${text(row.anchor) || "고객·공급망"} · 발췌 ${index + 1}`, topic: "누구와 거래하나", explanation: snippet, source: [text(chain.report_nm), text(chain.note) || "사업보고서 발췌"].filter(Boolean).join(" · "), asOf: text(chain.rcept_dt) || void 0, url: safeHttpLink(chain.source_url), relationship: "direct" });
  });
  return readySection("business", items, items.length ? "사업 설명·거래처 발췌입니다. 경쟁 우위가 입증됐다는 뜻은 아닙니다." : "사업 원문이 제공되지 않았습니다.");
}
function financeSection(slice, failed) {
  if (failed) return errorSection("finance", "종목 정보 요청에 실패했습니다.");
  const report = record(slice.report);
  const periods = list(record(report.financial_evidence).periods);
  const annual = periods.filter((row) => text(row.period_kind) === "annual" && text(row.currency) && text(row.fs_div) && (Number.isFinite(row.revenue) || Number.isFinite(row.op) || Number.isFinite(row.net)));
  const evidenceGroups = annual.reduce((groups2, row) => {
    const key = `${text(row.currency)}\0${text(row.fs_div)}`;
    groups2[key] = [...groups2[key] || [], row];
    return groups2;
  }, {});
  const evidenceSeries = Object.values(evidenceGroups).map(uniqueAnnual).sort((a, b) => b.length - a.length || periodOrder(b[b.length - 1] || {}).localeCompare(periodOrder(a[a.length - 1] || {})))[0] || [];
  const latestEvidence = evidenceSeries[evidenceSeries.length - 1];
  const legacyUSAnnual = /^(US|NASDAQ|NYSE|AMEX)$/.test(text(slice.market).toUpperCase());
  const fallbackGroups = list(report.fin_series).filter((row) => (text(row.period_kind) === "annual" || legacyUSAnnual && !text(row.period_kind) && Number.isInteger(row.year)) && text(row.currency) && (Number.isFinite(row.revenue) || Number.isFinite(row.op) || Number.isFinite(row.net))).reduce((groups2, row) => {
    const currency = text(row.currency);
    groups2[currency] = [...groups2[currency] || [], row];
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
    chart: verifiedSeries.slice(-6).filter((row) => Number.isFinite(row.revenue)).map((row) => ({ label: text(row.year), value: row.revenue })),
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
    rows: list(group.rows).filter((row) => text(row.k) && hasValue(row.v)).map((row) => ({ label: text(row.k), value: text(row.v) }))
  })).filter((item) => item.rows.length > 0);
  const items = [...income, ...factItems(report, "finance"), ...groups];
  return readySection("finance", items, items.length ? void 0 : "재무 지표가 제공되지 않았습니다.");
}
function valuationSection(slice, failed) {
  if (failed) return errorSection("valuation", "종목 정보 요청에 실패했습니다.");
  const report = record(slice.report), peer = record(report.peer);
  const items = factItems(report, "valuation");
  const rows2 = list(peer.rows).filter((row) => text(row.key) && hasValue(row.value) && hasValue(row.median));
  if (rows2.length) items.push({
    id: "peer-comparison",
    title: "같은 분류 기업의 중앙값",
    topic: "무엇과 비교하나",
    explanation: [text(peer.sector), hasValue(peer.n) ? `지표별 비교 표본 최대 ${text(peer.n)}개 기업 (각 지표의 표본 수는 미제공)` : "비교 기업 수 미제공", text(peer.note), "중앙값은 크기순 가운데 값입니다. 개별 지표의 동일 기준일·기간은 확인되지 않았으며, 낮거나 높다는 이유만으로 저평가·고평가로 판단하지 않습니다."].filter(Boolean).join("\n"),
    rows: rows2.map((row) => ({ label: factTitle(text(row.key)), value: `기업 ${text(row.value)} / 중앙값 ${text(row.median)}` })),
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
  const keys = ["family_pct", "latest_pct", "n_13d", "n_13g", "total", "window_total"].filter((key) => hasValue(ownership[key]));
  const summaryRows = keys.map((key) => ({ label: key === "family_pct" ? "총수일가 지분" : key === "latest_pct" ? "최신 지분율" : key === "n_13d" ? "13D 건수" : key === "n_13g" ? "13G 건수" : key === "total" ? "공시 건수" : "조회 창 공시 건수", value: key.endsWith("pct") ? `${text(ownership[key])}%` : text(ownership[key]) }));
  const holderRows = shareholders.map((holder) => ({ label: [text(holder.name), text(holder.type)].filter(Boolean).join(" · "), value: `${text(holder.pct)}%` }));
  const items = keys.length || shareholders.length ? [{
    id: "ownership-summary",
    title: "보유·지분 요약",
    topic: "누가 보유하나",
    explanation: [text(ownership.note), hasValue(ownership.fiscal_year) ? `기준 회계연도: ${text(ownership.fiscal_year)}` : "", text(ownership.collected_at) && `자료 수집일: ${text(ownership.collected_at)} (보유 기준일과 다를 수 있음)`].filter(Boolean).join(" · ") || "발행 종목 리포트에 제공된 보유·지분 정보입니다.",
    source: text(ownership.kind) || "발행 종목 리포트",
    asOf: text(ownership.collected_at) || void 0,
    relationship: "unknown",
    rows: holderRows.length ? holderRows : summaryRows
  }] : [];
  const dividendRows = list(dividends.recent).filter((row) => hasValue(row.dps) && text(row.record_date));
  if (dividendRows.length) items.push({
    id: "dividend-history",
    title: "배당 이력",
    topic: "주주에게 어떻게 돌려주나",
    explanation: [text(dividends.note), "배당기준일과 지급일을 구별합니다. 배당기준일은 배당락일이 아닙니다."].filter(Boolean).join("\n"),
    rows: dividendRows.map((row) => ({ label: `기준 ${text(row.record_date)} · 지급 ${text(row.pay_date) || "미제공"}`, value: `${text(row.dps)}원/주` })),
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
  const market = text(report.market) || text(sliceData.market);
  const marketUpper = market.toUpperCase();
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
    market,
    country,
    sections,
    coverage: { ok: sections.length - missing2.length, total: sections.length, missing: missing2 }
  };
}

// framer-components/public-probe/PortfolioMapSources.tsx
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
  const date = /* @__PURE__ */ new Date(`${value.slice(0, 10)}T00:00:00Z`);
  if (!Number.isFinite(date.getTime()) || date.toISOString().slice(0, 10) !== value.slice(0, 10)) return void 0;
  return value;
}
function acceptedPayload(value, ticker, family) {
  const raw = record2(value), report = record2(raw.report);
  const mismatch = (value2) => !!text2(value2) && text2(value2).toUpperCase() !== ticker;
  if (raw.__infoMapError || text2(raw.status) && text2(raw.status) !== "ok" || family === "news" && raw.error || mismatch(raw.ticker) || mismatch(family === "slice" ? report.ticker : raw.code)) return {};
  return raw;
}
function normalizePortfolioSources(ticker, slice, news) {
  const code = text2(ticker).toUpperCase(), map = normalizeInfoMap(code, slice, news);
  const report = record2(acceptedPayload(slice, code, "slice").report);
  const articles = acceptedPayload(news, code, "news");
  const eventSources = [];
  for (const row of rows(report.disclosures)) {
    const url = sourceUrl(row.source_url);
    if (!url) continue;
    const parsed = new URL(url), receipts = parsed.searchParams.getAll("rcpNo");
    const dartMain = parsed.hostname === "dart.fss.or.kr" && !parsed.port && parsed.pathname === "/dsaf001/main.do";
    const dartReceipt = dartMain && receipts.length === 1 && /^\d{14}$/.test(receipts[0]) ? receipts[0] : void 0;
    const receipt = typeof row.rcept_no === "string" && /^\d{14}$/.test(row.rcept_no) ? row.rcept_no : void 0;
    const receiptConflict = dartMain && !dartReceipt || row.rcept_no != null && row.rcept_no !== "" && (!receipt || receipt !== dartReceipt);
    eventSources.push({
      kind: "disclosure",
      title: text2(row.title) || "공시",
      source: "공시 원문",
      url,
      publishedAt: receiptConflict ? void 0 : label(row.date),
      observedAt: receiptConflict ? void 0 : observation(row.detected_at),
      receiptNumber: receiptConflict ? void 0 : receipt,
      ...receiptConflict ? { receiptConflict: true } : {},
      isCorrection: receiptConflict ? null : flag(row.is_correction),
      isBackfill: receiptConflict ? null : flag(row.is_backfill)
    });
  }
  for (const row of rows(articles.items)) {
    const url = sourceUrl(row.url);
    if (url) eventSources.push({
      kind: "news",
      title: text2(row.title) || "뉴스",
      source: text2(row.source) || "뉴스 원문",
      url,
      publishedAt: label(row.datetime),
      isCorrection: null,
      isBackfill: null
    });
  }
  return { ...map, eventSources };
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
async function fetchPortfolioSources(ticker, apiBase, signal) {
  const code = text2(ticker).toUpperCase(), base = text2(apiBase).replace(/\/+$/, "");
  const overview = /^\d{6}$/.test(code) ? "&overview=1" : "";
  const results = await Promise.allSettled([
    boundedJson(`${base}/api/stock_slice?ticker=${encodeURIComponent(code)}${overview}`, signal),
    boundedJson(`${base}/api/stock_news?code=${encodeURIComponent(code)}`, signal)
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
function normalizePortfolioCloseQuote(ticker, market, input) {
  if (!input) return missing("연결된 종가 자료가 없습니다.");
  if (!/^(KR|KOSPI|KOSDAQ)$/i.test(market.trim()) || !/^\d{6}$/.test(ticker))
    return missing("이 시장의 종가 자료는 아직 연결하지 않았습니다.");
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
  if (!priceDate || !source || !basis.includes("종가")) return missing("종가·기준일·출처를 확인할 수 없습니다.");
  const price = record3(payload.prices)?.[ticker];
  if (!positive(price)) return missing("이 종목의 종가가 제공되지 않았습니다.");
  const expectedDate = dateOnly(input.latestCompletedTradingDate);
  if (expectedDate && priceDate > expectedDate) return missing("종가 기준일이 확인된 마지막 거래일보다 뒤에 있습니다.");
  const priorDate = dateOnly(meta.prev_as_of), prior = record3(payload.prev)?.[ticker];
  const previousDate = priorDate && priorDate < priceDate && positive(prior) ? priorDate : null;
  const previousPrice = previousDate ? prior : null;
  const reported = record3(payload.chg)?.[ticker];
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
    expectedDate
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
  const sourceRecords = sectionId === "events" ? unique(records.filter((row) => row.url === item.url)) : [];
  const conflict = sourceRecords.some((row) => row.receiptConflict);
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
  const dates = evidence.flatMap((row) => [
    row.asOf,
    ...row.sources.map((source) => source.asOf),
    ...(row.sourceRecords || []).map((source) => source.publishedAt)
  ]);
  return {
    source: unique(evidence.flatMap((row) => [row.source, ...row.sources.map((source) => source.source)])).join(" · "),
    // Conflicting or absent dates remain in evidence; do not invent a single representative date.
    asOf: dates.every((date) => date === dates[0]) ? dates[0] : void 0,
    reason: unique(evidence.map((row) => row.reason)).join(" · "),
    confirmation: evidence.every((row) => row.confirmation === "confirmed") ? "confirmed" : "unknown",
    isCorrection: evidence.some((row) => row.isCorrection) ? true : null
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
    const labels2 = unique(rows2.map((row) => ({ name: row.name, market: row.market })));
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
      const sections = rows2.flatMap((row) => row.sections.filter((section) => section.id === sectionId));
      const upstreamStates = unique(sections.map((section) => section.state));
      const messages = unique(sections.flatMap((section) => section.message ? [section.message] : []));
      const items = unique(rows2.flatMap((row) => row.sections.filter((section) => section.id === sectionId).flatMap((section) => section.items.filter((item) => item.kind !== "question").map((item) => evidenceFor(ticker, sectionId, item, row.eventSources || [])))));
      let linkedItems = 0;
      for (const evidence of items) {
        const raw = evidence.url || "";
        if (!identities.has(raw)) identities.set(raw, portfolioDocumentIdentity(raw));
        const identity2 = await identities.get(raw);
        if (!identity2) continue;
        linkedItems++;
        const document = documentsById.get(identity2.id) || { ...identity2, evidence: [] };
        document.evidence.push(evidence);
        documentsById.set(identity2.id, document);
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
  for (const document of [...documentsById.values()].sort((a, b) => order(a.id, b.id))) {
    const evidence = unique(document.evidence);
    const tickers = unique(evidence.map((row) => row.ticker));
    const content = unique(evidence.map(({ ticker: _ticker, sectionId: _section, reason: _reason, sourceRecords, ...row }) => ({
      ...row,
      // Collection/backfill bookkeeping alone is not a change to source content.
      ...sourceRecords?.length ? { sourceRecords: unique(sourceRecords.map(({ observedAt: _observed, isBackfill: _backfill, ...source }) => source)) } : {}
    })));
    const contentHash = await sha256(JSON.stringify(content));
    const read_revision = Number.parseInt(contentHash.slice(0, 13), 16) + 1;
    documents.push({
      id: document.id,
      kind: "source-document",
      title: evidence[0].title,
      url: document.url,
      ...summarize(evidence),
      evidence,
      tickers,
      contentHash,
      read_revision
    });
    for (const ticker of tickers) {
      const associated = evidence.filter((row) => row.ticker === ticker);
      links.push({
        id: `link:${ticker}:${document.id}`,
        companyId: `company:${ticker}`,
        documentId: document.id,
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
    commonItems: documents.filter((document) => document.tickers.length >= 2),
    coverage: {
      total: sources.length,
      available: sources.filter((row) => row.state === "available").length,
      empty: sources.filter((row) => row.state === "empty").length,
      partial: sources.filter((row) => row.state === "partial").length,
      unavailable: sources.filter((row) => row.state === "unavailable").length,
      unknown: sources.filter((row) => row.state === "unknown").length,
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
  if (!Array.isArray(layouts) || layouts.length > 3 || !unique2(layouts.map((row) => row?.map_key))) return false;
  for (const layout of layouts) {
    if (!fields(layout, ["map_key", "positions", "notes", "marks"]) || typeof layout.map_key !== "string" || !MAP_KEY.test(layout.map_key)) return false;
    if (!Array.isArray(layout.positions) || layout.positions.length > 200 || !unique2(layout.positions.map((row) => row?.node_id))) return false;
    for (const row of layout.positions) {
      if (!fields(row, ["node_id", "x", "y"]) || !identifier(row.node_id) || !coordinate(row.x) || !coordinate(row.y)) return false;
    }
    if (!Array.isArray(layout.notes) || layout.notes.length > 100 || !unique2(layout.notes.map((row) => row?.note_id))) return false;
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
      const document = change(copy(state.document));
      if (!validMapDocument(document)) throw new Error("invalid-document");
      if (stable(document) === stable(state.document)) return true;
      state = { ...state, document: copy(document), dirty: true };
      editVersion += 1;
      emit();
      return true;
    },
    async save() {
      const account = session();
      if (!current(account, generation) || !account || !state.document || state.revision === null || !state.dirty || ["saving", "loading", "conflict"].includes(state.phase)) return false;
      const version = generation, edits = editVersion, expected = state.revision, document = copy(state.document);
      state = { ...state, phase: "saving", error: null };
      emit();
      try {
        const result = await request(account, { expected_revision: expected, document });
        if (!current(account, version)) return false;
        if (result.revision !== expected + 1 || stable(result.document) !== stable(document)) throw new Error("invalid-save-response");
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
function editMapLayout(document, mapKey, change) {
  const layouts = copy(document.layouts), index = layouts.findIndex((row) => row.map_key === mapKey);
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
      const ticker = item.ticker.trim().toUpperCase(), market = item.market.trim().toUpperCase();
      if (ticker && (market === "KR" || market === "US")) {
        const prior = markets.get(ticker);
        if (prior && prior !== market) throw new Error("ambiguous-watchlist-market");
        markets.set(ticker, market);
      }
      const supported = market === "KR" ? /^\d{6}$/.test(ticker) : market === "US" && /^[A-Z][A-Z0-9.-]{0,15}$/.test(ticker);
      if (!supported || item.type === "commodity") {
        unsupportedCount++;
        continue;
      }
      const key = `${market}:${ticker}`;
      if (!stocks.has(key)) stocks.set(key, {
        ticker,
        market,
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

// framer-components/public-probe/PortfolioMapWorkspace.tsx
var API = "https://project-yw131.vercel.app";
var clone = (value) => JSON.parse(JSON.stringify(value));
var sameAccount = (a, b) => a?.userId === b?.userId;
var empty = (privateState) => ({ phase: "signed-out", holdings: [], watchlist: [], watchlistError: null, watchlistUnsupportedCount: 0, exploratory: [], unsupportedCount: 0, selectedTickers: [], graph: null, privateState, error: null });
function workspaceStocks(state) {
  const watched = new Set((state.watchlist || []).map((row) => `${row.market}:${row.ticker}`));
  const stocks = new Map(state.holdings.map((row) => [row.ticker, { ticker: row.ticker, name: row.name, market: row.market, held: true, watched: watched.has(`${row.market}:${row.ticker}`), exploring: false }]));
  for (const row of state.watchlist || []) if (!stocks.has(row.ticker)) stocks.set(row.ticker, { ...row, held: false, watched: true, exploring: false });
  for (const row of state.exploratory || []) if (!stocks.has(row.ticker)) stocks.set(row.ticker, { ...row, held: false, watched: false, exploring: true });
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
  for (const row of rows2) {
    if (!row || typeof row !== "object" || typeof row.ticker !== "string") throw new Error("invalid-holdings-response");
    const ticker = row.ticker.trim().toUpperCase(), market = String(row.market || "").toUpperCase();
    const supported = market === "KR" ? /^\d{6}$/.test(ticker) : market === "US" && /^[A-Z][A-Z0-9.-]{0,15}$/.test(ticker);
    if (!supported || row.type === "commodity") {
      unsupportedCount += 1;
      continue;
    }
    const prior = holdings.get(ticker);
    if (prior && prior.market !== market) throw new Error("ambiguous-holding-market");
    if (prior) {
      const { id: _ambiguousId, ...display } = prior;
      holdings.set(ticker, { ...display, shares: null, avg_cost: null, duplicate: true });
      continue;
    }
    holdings.set(ticker, {
      ticker,
      name: typeof row.name === "string" && row.name.trim() ? row.name.trim() : ticker,
      market,
      shares: finitePositive(row.shares),
      avg_cost: finitePositive(row.avg_cost),
      duplicate: false,
      ...typeof row.id === "string" && row.id.trim() ? { id: row.id.trim() } : {},
      ...typeof row.memo === "string" ? { memo: row.memo } : {}
    });
  }
  return { holdings: [...holdings.values()], unsupportedCount };
}
function createPortfolioMapWorkspace(options = {}) {
  const getSession = options.getSession || readMapSession, fetcher = options.fetcher || fetch;
  const graphLoader = options.graphLoader || fetchPortfolioMapGraph;
  let disposed = false;
  const store = createMemberMapStore({ getSession, fetcher: (input, init) => disposed ? Promise.reject(new Error("workspace-disposed")) : fetcher(input, init) });
  let state = empty(store.getState()), account = null, generation = 0;
  let automaticSelection = true;
  let pending = null;
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
  const showTickers = async (tickers, fromOpen = false) => {
    if (!account || !valid(generation)) return false;
    const codes = [...new Set(tickers.map((ticker) => ticker.trim().toUpperCase()))];
    if (codes.length > 30 || codes.some((code) => !workspaceStocks(state).some((row) => row.ticker === code))) throw new Error("choose-up-to-30-holdings");
    if (!fromOpen) automaticSelection = false;
    pending?.abort();
    pending = new AbortController();
    const signal = pending.signal, version = ++generation;
    state = { ...state, phase: "loading", selectedTickers: codes, graph: null, error: null };
    emit();
    try {
      if (!valid(version) || signal.aborted) return false;
      const graph = await graphLoader(codes, API, signal);
      if (!valid(version) || signal.aborted) return false;
      if (graph.companies.length !== codes.length || new Set(graph.companies.map((row) => row.ticker)).size !== codes.length || graph.companies.some((row) => !codes.includes(row.ticker))) throw new Error("graph-holdings-mismatch");
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
    const known = workspaceStocks(state).find((row) => row.ticker === stock.ticker);
    if (known && known.market !== stock.market) throw new Error("ambiguous-exploratory-market");
    const codes = [.../* @__PURE__ */ new Set([...state.selectedTickers, stock.ticker])];
    if (codes.length > 30) throw new Error("choose-up-to-30-holdings");
    if (state.selectedTickers.includes(stock.ticker)) return true;
    pending?.abort();
    const controller = new AbortController();
    pending = controller;
    const version = ++generation, signal = controller.signal;
    try {
      const graph = await graphLoader([...codes], API, signal);
      if (!valid(version) || signal.aborted) return false;
      if (graph.companies.length !== codes.length || new Set(graph.companies.map((row) => row.ticker)).size !== codes.length || graph.companies.some((row) => !codes.includes(row.ticker) || typeof row.id !== "string" || !row.id.trim()) || new Set(graph.companies.map((row) => row.id)).size !== codes.length) throw new Error("graph-exploration-mismatch");
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
      if (pending === controller) pending = null;
    }
  };
  const open = async () => {
    if (disposed) return false;
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
      const previous = state.selectedTickers.filter((code) => stocks.some((row) => row.ticker === code));
      if (stocks.length > 30 && (automaticSelection || !previous.length)) {
        state = { ...state, phase: "choose-stocks", graph: null, selectedTickers: [] };
        emit();
        await restore;
        return valid(version);
      }
      const success = await showTickers(!automaticSelection && previous.length ? previous : stocks.map((row) => row.ticker), true);
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
    editLayout(mapKey, change) {
      if (!valid(generation)) return false;
      return store.update((document) => editMapLayout(document, mapKey, change));
    },
    markDocument(mapKey, id, change) {
      if (!valid(generation)) return false;
      const document = state.graph?.documents.find((row) => row.id === id);
      if (!document) return false;
      return store.update((value) => editMapLayout(value, mapKey, (layout) => {
        const prior = layout.marks[id] || { read_revision: null, important: false, disposition: "inbox" };
        const mark = {
          read_revision: change.read === void 0 ? prior.read_revision : change.read ? document.read_revision : null,
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
      const marks = state.privateState.document?.layouts.find((row) => row.map_key === mapKey)?.marks || {};
      return (state.graph?.documents || []).filter((row) => marks[row.id]?.disposition !== "irrelevant" && mapReadState(marks[row.id], row.read_revision) !== "read");
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
  const documents = state.graph.documents.map((document) => {
    const point2 = pointFor(document.id);
    return {
      id: document.id,
      name: document.title,
      code: document.source,
      kind: "event",
      layer: documentLayer(document),
      priority: 2,
      reason: document.reason,
      source: document.source,
      asOf: document.asOf || null,
      evidence: document.evidence.map(projectEvidence),
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
function documentLayer(document) {
  const kind = document.evidence[0]?.kind;
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
var record6 = (value) => value !== null && typeof value === "object" && !Array.isArray(value) ? value : null;
function exactRecord(value, keys) {
  const item = record6(value);
  if (!item) return null;
  const actual = Object.keys(item);
  return actual.length === keys.length && actual.every((key) => keys.includes(key)) ? item : null;
}
var text4 = (value, max) => {
  if (typeof value !== "string" || /[\u0000-\u0008\u000b\u000c\u000e-\u001f\u007f]/.test(value)) return null;
  const clean = value.trim();
  return clean && clean.length <= max ? clean : null;
};
var stableId = (value, max = LIMITS.id) => {
  const clean = text4(value, max);
  return clean && /^[A-Za-z0-9][A-Za-z0-9:._-]*$/.test(clean) ? clean : null;
};
function dateOnly2(value) {
  const raw = text4(value, 10), match = raw && /^(\d{4})-(\d{2})-(\d{2})$/.exec(raw);
  if (!match || Number(match[1]) < 1900) return null;
  const time = Date.parse(raw + "T00:00:00Z");
  return Number.isFinite(time) && new Date(time).toISOString().slice(0, 10) === raw ? raw : null;
}
function secureUrl(value) {
  const raw = text4(value, LIMITS.url);
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
function normalizeTicker(value, market) {
  if (typeof value !== "string") return null;
  const normalized = value.trim().toUpperCase();
  if (market === "KR") return /^\d{6}$/.test(normalized) ? normalized : null;
  return normalized.length <= 15 && /^[A-Z][A-Z0-9]*(?:[.-][A-Z0-9]+)*$/.test(normalized) ? normalized : null;
}
var entityKey = (entity) => `${entity.market}:${entity.ticker}`;
function parseEntity(value, exactKeys = ENTITY_KEYS) {
  const item = exactRecord(value, exactKeys), market = item && normalizeMarket(item.market);
  if (!item || !market || item.market !== market) return null;
  const ticker = normalizeTicker(item.ticker, market);
  return ticker && item.ticker === ticker ? { ticker, market } : null;
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
    const item = exactRecord(value[index], ENTITY_KEYS), market = item && normalizeMarket(item.market);
    const ticker = market && item ? normalizeTicker(item.ticker, market) : null;
    if (!item || !market || !ticker) return failure(`holdings[${index}]`);
    const entity = { ticker, market }, key = entityKey(entity);
    if (seen.has(key)) return failure(`holdings[${index}].duplicate`);
    seen.add(key);
    result.push(entity);
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
    const publisher = item && text4(item.publisher, LIMITS.label), publishedAt = item && dateOnly2(item.publishedAt);
    const statement = item && text4(item.statement, LIMITS.prose);
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
    const label2 = item && text4(item.label, LIMITS.label), asOf = item && dateOnly2(item.asOf);
    const limitations = item && text4(item.limitations, LIMITS.prose);
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
    const id = item && stableId(item.id, LIMITS.factId), title = item && text4(item.title, LIMITS.label);
    const date = item && dateOnly2(item.date), mergeBasis = item && text4(item.mergeBasis, LIMITS.prose);
    const refs = item ? parseIdList(item.sourceIds, sourceIds, `registry.events[${index}].sourceIds`, 2) : failure("event");
    if (!item || !id || !title || !date || date > reviewedAt || !mergeBasis || !refs.ok || item.status !== "historical-announcement" || item.review !== "manual-primary-source-comparison" || item.impact !== "unknown" || allIds.has(id) || !Array.isArray(item.participants) || item.participants.length < 2 || item.participants.length > LIMITS.participants)
      return failure(`registry.events[${index}]`);
    const allowedRefs = new Set(refs.value), participants = [], participantIds = /* @__PURE__ */ new Set();
    for (let participantIndex = 0; participantIndex < item.participants.length; participantIndex++) {
      const participant = exactRecord(item.participants[participantIndex], PARTICIPANT_KEYS);
      const entity = participant && parseEntity({ ticker: participant.ticker, market: participant.market });
      const role = participant && text4(participant.role, LIMITS.label);
      const participantRefs = participant ? parseIdList(
        participant.sourceIds,
        allowedRefs,
        `registry.events[${index}].participants[${participantIndex}].sourceIds`
      ) : failure("participant");
      if (!participant || !entity || !role || !participantRefs.ok || participantIds.has(entityKey(entity)))
        return failure(`registry.events[${index}].participants[${participantIndex}]`);
      participantIds.add(entityKey(entity));
      participants.push({ ...entity, role, sourceIds: participantRefs.value });
    }
    allIds.add(id);
    events.push({
      id,
      title,
      date,
      status: "historical-announcement",
      participants,
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
    const matchedHoldings = event.participants.filter((participant) => holdingKeys.has(entityKey(participant))).map(({ ticker, market }) => ({ ticker, market }));
    if (matchedHoldings.length < 2) continue;
    matchedHoldings.forEach((entity) => matchedKeys.add(entityKey(entity)));
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
  reviewedAt: "2026-09-29",
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
  const participants = fact.participants.map((participant) => [
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
    participants,
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
var entityKey2 = (entity) => `${entity.market}:${entity.ticker}`;
var sourceEvidence = (sources) => sources.map((source) => ({
  id: source.id,
  sourceURL: source.url,
  publisher: source.publisher,
  publishedAt: source.publishedAt,
  statement: source.statement
}));
var firstSource = (sources) => sources[0] || null;
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
    const mode = "relationships", record7 = reviewedRecord(mode, fact);
    const nodeId = record7.id, evidence = sourceEvidence(fact.sources), source = firstSource(fact.sources);
    recordsMap[record7.id] = recordFor(mode, fact, record7);
    nodes.push({
      id: nodeId,
      kind: "reviewed-relationship",
      name: fact.label,
      code: "검토 완료 관계",
      logo: "",
      priority: 2,
      reason: fact.limitations,
      source: source?.publisher || null,
      sourceURL: source?.url || null,
      asOf: fact.asOf,
      evidence,
      relationshipKind: fact.label,
      recordId: record7.id,
      read_revision: record7.read_revision,
      ...position(index, total)
    });
    for (const endpoint of [fact.from, fact.to]) {
      const companyId = companiesByEntity.get(entityKey2(endpoint));
      if (companyId) edges.push(edgeFor("relationships", fact, record7, nodeId, companyId, endpoint, fact.label, evidence, source));
    }
  });
  facts.events.forEach((fact, index) => {
    const mode = "events", record7 = reviewedRecord(mode, fact);
    const nodeId = record7.id, evidence = sourceEvidence(fact.sources), source = firstSource(fact.sources);
    recordsMap[record7.id] = recordFor(mode, fact, record7);
    nodes.push({
      id: nodeId,
      kind: "reviewed-event",
      name: fact.title,
      code: "검토 완료 공통 사건",
      logo: "",
      priority: 2,
      reason: fact.mergeBasis,
      source: source?.publisher || null,
      sourceURL: source?.url || null,
      asOf: fact.date,
      evidence,
      relationshipKind: null,
      recordId: record7.id,
      read_revision: record7.read_revision,
      ...position(facts.relationships.length + index, total)
    });
    const participants = new Map(fact.participants.map((participant) => [entityKey2(participant), participant]));
    for (const holding of fact.matchedHoldings) {
      const companyId = companiesByEntity.get(entityKey2(holding)), participant = participants.get(entityKey2(holding));
      if (companyId && participant) edges.push(edgeFor("events", fact, record7, nodeId, companyId, holding, participant.role, evidence, source));
    }
  });
  return { nodes, edges, recordsMap, facts };
}
function edgeFor(mode, fact, record7, nodeId, companyId, endpoint, reason, evidence, source) {
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
    recordId: record7.id,
    read_revision: record7.read_revision,
    influence: "unknown"
  };
}
function recordFor(mode, fact, record7) {
  const isRelationship = mode === "relationships";
  return {
    ...record7,
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

// framer-components/public-probe/PortfolioStockSearch.ts
var MAX_RESULTS = 12;
var MAX_BODY_BYTES = 64 * 1024;
var KR_MARKETS = /* @__PURE__ */ new Set(["KR", "KOSPI", "KOSDAQ", "KONEX"]);
var US_MARKETS = /* @__PURE__ */ new Set(["US", "NASDAQ", "NYSE", "AMEX", "NYSE AMERICAN", "NYSE ARCA", "BATS"]);
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
    const row = value;
    const ticker = boundedString(row.ticker, 16).toUpperCase();
    const name = boundedString(row.name, 160);
    const listing = boundedString(row.market, 32).toUpperCase();
    const koreanName = row.name_kr === void 0 ? "" : boundedString(row.name_kr, 160, true);
    if (row.etf !== void 0 && typeof row.etf !== "boolean") {
      throw new Error("Invalid ETF metadata");
    }
    const market = KR_MARKETS.has(listing) ? "KR" : US_MARKETS.has(listing) ? "US" : null;
    if (!market) {
      unsupportedCount++;
      continue;
    }
    if (!(market === "KR" ? /^\d{6}$/ : /^[A-Z][A-Z0-9.-]{0,15}$/).test(ticker)) {
      throw new Error("Invalid search ticker");
    }
    const item = { ticker, name: market === "US" ? koreanName || name : name, market };
    if (row.etf === true) item.etf = true;
    const key = `${market}:${ticker}`;
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

// framer-components/public-probe/PortfolioPrototypeHost.ts
var plain = (v) => !!v && typeof v === "object" && !Array.isArray(v);
var point = (v) => plain(v) && Number.isFinite(v.x) && Number.isFinite(v.y);
var pixel = (value, scale, prior) => prior !== void 0 && value === 0.5 + prior / scale ? prior : (value - 0.5) * scale;
function mergePrototypeDraft(state, value) {
  if (state.phase !== "ready" || !state.graph || !["ready", "saving"].includes(state.privateState.phase) || !state.privateState.document) return null;
  if (!plain(value) || !Array.isArray(value.positions) || !Array.isArray(value.notes) || !plain(value.marks) || value.positions.length > 200 || value.notes.length > 100 || Object.keys(value.marks).length > 200) return null;
  const prior = state.privateState.document.layouts.find((l) => l.map_key === "main") || { map_key: "main", positions: [], notes: [], marks: {} };
  const reviewed = projectReviewedPrototype(state);
  const allowed = new Set([...state.graph.companies, ...state.graph.documents, ...reviewed.nodes].map((n) => n.id));
  const edgeIds = /* @__PURE__ */ new Set([...state.graph.links.map((e) => e.id), ...reviewed.edges.map((e) => e.id)]), positions = new Map(prior.positions.map((p) => [p.node_id, p]));
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
    const doc = state.graph.documents.find((d) => d.id === id) || reviewed.recordsMap[id];
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
function prototypeMemberModel(state) {
  if (state.phase !== "ready" || !state.graph) return { nodes: [], edges: [], notes: {}, marks: {}, writable: false };
  const projected = projectWorkspaceToPrototype(state), graph = state.graph, reviewed = projectReviewedPrototype(state);
  const stocks = new Map(workspaceStocks(state).map((stock) => [stock.ticker, stock]));
  const layout = state.privateState.document?.layouts.find((l) => l.map_key === "main");
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
  const records = [...graph.documents, ...Object.values(reviewed.recordsMap)];
  const changes = Object.fromEntries(records.map((d) => {
    const m = layout?.marks[d.id];
    return [d.id, m?.read_revision ? m.read_revision === d.read_revision ? "확인" : "변경" : "미확인"];
  }));
  return {
    nodes: [...projected.nodes.map((n) => ({
      ...n,
      ticker: n.kind === "stock" ? graph.companies.find((c) => c.id === n.id)?.ticker : void 0,
      priority: 2,
      recordKind: n.kind === "event" ? "document" : "company",
      changeStatus: changes[n.id],
      market: n.kind === "stock" ? stocks.get(n.code)?.market : void 0,
      held: n.kind === "stock" ? stocks.get(n.code)?.held ?? false : void 0,
      watched: n.kind === "stock" ? stocks.get(n.code)?.watched ?? false : void 0,
      explore: n.kind === "stock" ? stocks.get(n.code)?.exploring ?? false : false,
      reason: n.kind === "stock" ? stocks.get(n.code)?.held ? "보유종목에 연결된 자료를 확인하세요." : stocks.get(n.code)?.watched ? "관심종목이에요. 실제 보유 수량이나 평가금액에는 포함하지 않아요." : "이번 화면에서 탐색 중이에요. 보유·관심목록에 등록하지 않았으며, 다시 접속하면 검색해서 추가해야 해요." : graph?.documents.find((d) => d.id === n.id)?.reason,
      source: n.kind === "event" ? graph?.documents.find((d) => d.id === n.id)?.source : "내 포트폴리오",
      asOf: n.kind === "event" ? graph?.documents.find((d) => d.id === n.id)?.asOf : void 0,
      evidence: n.kind === "event" ? graph?.documents.find((d) => d.id === n.id)?.evidence : []
    })), ...reviewedNodes.map((n) => ({ ...n, changeStatus: changes[n.id] }))],
    edges: [
      ...projected.edges.map((e) => ({ ...e, type: "unknown", strength: 0, impact: "미확인", impactReason: "자료 연결만으로 실적이나 주가 영향을 판단하지 않아요.", verb: "자료 연결" })),
      ...reviewed.edges.map((e) => ({ ...e, evidence: evidence(e.evidence), type: "documented", strength: 0, impact: "미확인", impactReason: "자료에 명시된 참여 관계이며, 현재 실적이나 주가 영향을 뜻하지 않아요.", verb: e.reason }))
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
  let owner = null, generation = 0, port = null, disposed = false, key = "", current = workspace.getState();
  let waiting = false, reloadPending = false, frameNonce = "";
  let hydrated = false, focusRevision = 0;
  let searchRequest = null, searchRevision = 0;
  let searchStocks = /* @__PURE__ */ new Map();
  let exploration = null;
  const focusWindowKey = (state) => JSON.stringify([
    state.selectedTickers,
    state.graph?.companies.map((row) => [row.id, row.ticker, row.market])
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
    const company = state.graph?.companies.find((row) => row.ticker === pending.ticker);
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
      if (disposed || revision2 !== focusRevision || !member || member !== account() || member !== owner || state.phase !== "ready" || !state.selectedTickers.includes(ticker) || !state.graph?.companies.some((row) => row.ticker === ticker)) return;
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
    exploration = null;
    port?.close();
    port = null;
    waiting = false;
    hydrated = false;
  };
  const status = () => {
    const p = current.privateState;
    port?.postMessage({
      type: "status",
      writable: p.phase === "ready" || p.phase === "saving",
      saving: p.phase === "saving",
      message: p.phase === "conflict" ? "다른 화면에서 기록이 바뀌었어요. 덮어쓰지 않았어요." : p.phase === "error" ? "저장하지 못했어요. 변경 내용을 유지하고 있어요." : p.phase === "saving" ? "저장 중…" : p.dirty ? "아직 저장하지 않은 변경이 있어요" : "저장된 기록을 불러왔어요"
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
      if (command.type === "hydrated") {
        hydrated = true;
        flushReturnFocus();
        return;
      }
      if (state.phase !== "ready") return;
      if (command.type === "search" && typeof command.query === "string" && command.query.length <= 60 && Number.isSafeInteger(command.request)) {
        searchRequest?.abort();
        searchRequest = new AbortController();
        searchStocks.clear();
        const request = ++searchRevision, signal = searchRequest.signal;
        try {
          const result = await (options.searchLoader || fetchPortfolioStockSearch)(command.query, { signal });
          if (disposed || version !== generation || request !== searchRevision || member !== account() || signal.aborted) return;
          searchStocks = new Map(result.stocks.map((stock) => [stock.ticker, stock]));
          port?.postMessage({ type: "search-results", request: command.request, ...result });
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
        if (next) workspace.editLayout("main", () => next);
      } else if (command.type === "save") await workspace.save();
      else if (command.type === "holdings") options.openHoldings?.();
      else if (command.type === "source" && typeof command.url === "string") {
        const reviewed = projectReviewedPrototype(state);
        const urls = /* @__PURE__ */ new Set([
          ...state.graph?.documents.flatMap((d) => [d.url, ...d.evidence.flatMap((e) => [e.url, ...e.sources.map((s) => s.url)])]) || [],
          ...Object.values(reviewed.recordsMap).flatMap((record7) => record7.sourceURLs)
        ]);
        try {
          const url = new URL(command.url);
          if (url.protocol === "https:" && !url.username && !url.password && urls.has(url.href)) options.openSource?.(url.href);
        } catch {
        }
      }
    };
    frame.contentWindow.postMessage({ type: "alphanest-member-connect", nonce: frameNonce }, "*", [channel.port2]);
    port.postMessage({ type: "init", model: prototypeMemberModel(current) });
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
    current = state;
    const nextOwner = account();
    if (owner !== nextOwner || state.phase === "signed-out") clearReturnFocus();
    else if (pendingFocus && (state.phase !== "ready" || focusWindowKey(state) !== pendingFocus.windowKey)) pendingFocus = null;
    if (state.phase === "loading" && nextOwner && owner === nextOwner && key) {
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
    if (nextKey !== key) {
      if (exploration?.version === generation && owner === nextOwner && port && hydrated && state.selectedTickers.includes(exploration.ticker)) {
        key = nextKey;
        port.postMessage({ type: "graph-update", model: prototypeMemberModel(state), ticker: exploration.ticker });
        status();
        return;
      }
      close();
      owner = nextOwner;
      key = nextKey;
      waiting = true;
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
    disposed = true;
    clearReturnFocus();
    close();
    unsubscribe();
    window.removeEventListener("message", ready);
    frame.removeEventListener("load", loaded);
    if (templateURL) frame.src = "about:blank";
    else frame.srcdoc = "";
  };
  return Object.assign(cleanup, { prepareReturnFocus, clearReturnFocus, returnToMap });
}

// framer-components/public-probe/PortfolioHoldingsPanel.tsx
import * as React3 from "react";

// framer-components/public-probe/PortfolioHoldingsDraft.ts
var tickerFor = (value, market) => {
  if (typeof value !== "string") throw new Error("invalid-ticker");
  const ticker = value.trim().toUpperCase();
  const pattern = market === "kr" ? /^[0-9A-Z]{6}$/ : /^[A-Z][A-Z0-9.-]{0,14}$/;
  if (!pattern.test(ticker) || ticker.startsWith("CMD_")) throw new Error("invalid-ticker");
  return ticker;
};
var apiMarketFor = (value) => {
  if (typeof value !== "string") throw new Error("invalid-market");
  const market = value.trim().toLowerCase();
  if (market !== "kr" && market !== "us") throw new Error("invalid-market");
  return market;
};
var holdingMarketFor = (market) => market === "kr" ? "KR" : "US";
var identifierFor = (value) => {
  if (typeof value !== "string" || !value.trim()) throw new Error("missing-holding-id");
  return value.trim();
};
var positiveNumber = (value, field) => {
  if (typeof value === "boolean") throw new Error(`invalid-${field}`);
  if (typeof value === "string") {
    const text5 = value.replace(/[,\s₩$원]/g, "");
    if (!/^[+-]?(?:\d+(?:\.\d*)?|\.\d+)(?:[eE][+-]?\d+)?$/.test(text5)) throw new Error(`invalid-${field}`);
    value = Number(text5);
  }
  if (typeof value !== "number" || !Number.isFinite(value) || value <= 0) throw new Error(`invalid-${field}`);
  return value;
};
var textField = (value, field) => {
  if (typeof value !== "string") throw new Error(`invalid-${field}`);
  return value;
};
var copy2 = (record7) => ({ ...record7 });
function targetById(records, id) {
  const matches = records.filter((record7) => record7.id === id);
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
  const apiMarket = apiMarketFor(change.market), market = holdingMarketFor(apiMarket), ticker = tickerFor(change.ticker, apiMarket);
  const sameTicker = records.filter((record7) => record7.ticker.trim().toUpperCase() === ticker);
  if (sameTicker.some((record7) => record7.duplicate === true)) throw new Error("duplicate-holding-record");
  if (sameTicker.length) {
    throw new Error("holding-ticker-requires-edit");
  }
  const shares = positiveNumber(change.shares, "shares"), avg_cost = positiveNumber(change.avg_cost, "avg_cost");
  const name = change.name === void 0 ? "" : textField(change.name, "name");
  const memo = change.memo === void 0 ? "" : textField(change.memo, "memo");
  const after = { id: null, ticker, market, shares, avg_cost, name, memo };
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
var HOLDINGS_CSV_LIMITS = Object.freeze({ maxCharacters: 262144, maxRows: 200, memberUnique: 30 });
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
function parse(text5) {
  if (text5.length > HOLDINGS_CSV_LIMITS.maxCharacters) return { rows: [], errors: [{ rowNumber: 1, code: "csv-input-too-large" }] };
  text5 = text5.replace(/^\uFEFF/, "");
  const rows2 = [];
  let line = 1, startLine = 1, cells = [], field = "", errors = [];
  let quoted = false, closed = false, touched = false;
  const issue2 = (code) => {
    if (!errors.includes(code)) errors.push(code);
  };
  const endField = () => {
    cells.push(field);
    field = "";
    closed = false;
  };
  const endRow = () => {
    endField();
    rows2.push({ line: startLine, cells, errors });
    cells = [];
    errors = [];
    touched = false;
  };
  for (let i = 0; i < text5.length; i++) {
    const char = text5[i];
    if (char === "\0" || char === "�") issue2("csv-invalid-text");
    if (quoted) {
      if (char === '"') {
        if (text5[i + 1] === '"') {
          field += '"';
          i++;
        } else {
          quoted = false;
          closed = true;
        }
      } else {
        field += char;
        if (char === "\n" || char === "\r" && text5[i + 1] !== "\n") line++;
      }
      continue;
    }
    if (char === "\r" || char === "\n") {
      endRow();
      if (rows2.length > HOLDINGS_CSV_LIMITS.maxRows + 1) return { rows: [], errors: [{ rowNumber: startLine, code: "csv-too-many-rows" }] };
      if (char === "\r" && text5[i + 1] === "\n") i++;
      startLine = ++line;
      continue;
    }
    touched = true;
    if (char === ",") {
      endField();
      continue;
    }
    if (char === '"' && !field && !closed) {
      quoted = true;
      continue;
    }
    if (closed || char === '"') issue2("csv-invalid-quote");
    field += char;
  }
  if (quoted) issue2("csv-unclosed-quote");
  if (touched || cells.length || field.length) endRow();
  if (rows2.length > HOLDINGS_CSV_LIMITS.maxRows + 1) return { rows: [], errors: [{ rowNumber: startLine, code: "csv-too-many-rows" }] };
  return { rows: rows2, errors: [] };
}
function buildHoldingCsvPreview(text5, memberHoldings) {
  const parsed = parse(text5), errors = parsed.errors.slice();
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
  const existingTickers = new Set(memberHoldings.map((record7) => record7.ticker.trim().toUpperCase()));
  const rows2 = parsed.rows.slice(1).map((row) => ({ rowNumber: row.line, cells: row.cells, errors: row.errors.slice(), ticker: null, kind: "error", preview: null }));
  if (header && !rows2.length && !errors.length) errors.push({ rowNumber: header.line + 1, code: "csv-no-data" });
  const tickerIndex = columns.indexOf("ticker");
  const occurrences = /* @__PURE__ */ new Map();
  for (const row of rows2) {
    row.ticker = tickerIndex >= 0 ? row.cells[tickerIndex]?.trim().toUpperCase() || null : null;
    if (row.ticker) occurrences.set(row.ticker, (occurrences.get(row.ticker) || 0) + 1);
  }
  for (const row of rows2) {
    if (errors.length) row.errors.push("csv-invalid-file");
    if (row.cells.length !== columns.length) row.errors.push("csv-column-count");
    if (row.ticker && (occurrences.get(row.ticker) || 0) > 1) row.errors.push("csv-duplicate-ticker");
    if (row.errors.length) continue;
    const input = {};
    columns.forEach((column, index) => {
      if (column) input[column] = row.cells[index];
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
      const matches = memberHoldings.filter((record7) => record7.ticker.trim().toUpperCase() === after.ticker);
      if (!matches.length) {
        row.kind = "add";
        row.preview = candidate;
        continue;
      }
      const before = matches[0];
      if (matches.length !== 1 || before.duplicate || !before.id?.trim() || before.id !== before.id.trim() || memberHoldings.filter((record7) => record7.id === before.id).length !== 1) throw new Error("csv-ambiguous-existing-identity");
      if (before.market !== after.market) throw new Error("csv-existing-market-conflict");
      const change = { kind: "edit", id: before.id };
      if (before.shares !== after.shares) change.shares = after.shares;
      if (before.avg_cost !== after.avg_cost) change.avg_cost = after.avg_cost;
      if (input.name !== void 0 && before.name !== after.name) change.name = after.name;
      if (input.memo !== void 0 && (before.memo ?? "") !== after.memo) change.memo = after.memo;
      if (Object.keys(change).length === 2) {
        row.kind = "unchanged";
        continue;
      }
      row.preview = previewHoldingChange(memberHoldings, change);
      row.kind = "edit";
    } catch (error) {
      row.errors.push(error instanceof Error ? error.message : "csv-invalid-row");
    }
  }
  const additions = rows2.filter((row) => row.kind === "add");
  const projectedUnique = existingTickers.size + additions.length;
  if (projectedUnique > HOLDINGS_CSV_LIMITS.memberUnique) for (const row of additions) {
    row.kind = "error";
    row.preview = null;
    row.errors.push("csv-member-limit");
  }
  const counts = { add: 0, edit: 0, unchanged: 0, error: 0, existingUnique: existingTickers.size, projectedUnique };
  for (const row of rows2) counts[row.kind]++;
  if (errors.length || counts.error) for (const row of rows2) row.preview = null;
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
  const [text5, setText] = React2.useState(null);
  const [error, setError] = React2.useState("");
  const [result, setResult] = React2.useState(null);
  const [submitted, setSubmitted] = React2.useState(null);
  const generation = React2.useRef(0);
  React2.useEffect(() => () => {
    generation.current++;
  }, []);
  const computed = React2.useMemo(() => text5 === null ? null : buildHoldingCsvPreview(text5, holdings), [text5, holdings]);
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
    const previews = report.rows.flatMap((row) => row.preview ? [row.preview] : []);
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
  } })), unsupportedCount ? /* @__PURE__ */ React2.createElement("p", { role: "alert" }, "지원하지 않는 기존 보유 항목 ", unsupportedCount, "개가 있어 전체 중복·한도를 확인할 수 없어요. 파일 저장은 보류하고 목록에서 항목별로 확인해주세요.") : null, error ? /* @__PURE__ */ React2.createElement("p", { role: "alert" }, error) : null, report ? /* @__PURE__ */ React2.createElement(React2.Fragment, null, /* @__PURE__ */ React2.createElement("p", { role: "status" }, "추가 ", report.counts.add, " · 수정 ", report.counts.edit, " · 변경 없음 ", report.counts.unchanged, " · 오류 ", report.counts.error), report.fatalErrors.map((entry, i) => /* @__PURE__ */ React2.createElement("p", { role: "alert", key: i }, entry.rowNumber, "행: ", issue(entry.code))), /* @__PURE__ */ React2.createElement("ul", { className: "an-nest-rows" }, report.rows.map((row) => /* @__PURE__ */ React2.createElement("li", { key: row.rowNumber }, /* @__PURE__ */ React2.createElement("div", { style: { minWidth: 0 } }, /* @__PURE__ */ React2.createElement("strong", null, row.rowNumber, "행 · ", row.ticker || "종목 확인 필요", " · ", { add: "추가", edit: "수정", unchanged: "변경 없음", error: "오류" }[row.kind]), row.errors.map((code, i) => /* @__PURE__ */ React2.createElement("p", { key: i }, issue(code))), row.preview ? /* @__PURE__ */ React2.createElement("dl", null, row.preview.changedFields.map((key) => /* @__PURE__ */ React2.createElement(React2.Fragment, { key }, /* @__PURE__ */ React2.createElement("dt", null, fields2[key]), /* @__PURE__ */ React2.createElement("dd", null, String(row.preview.before?.[key] ?? "없음"), " → ", String(row.preview.after?.[key] ?? "없음"))))) : null)))), !submitted ? /* @__PURE__ */ React2.createElement("p", null, "오류가 있으면 저장하지 않아요. 확인 후 한 항목씩 저장하며, 도중에 실패하면 그 지점에서 멈춰요.") : null, result ? /* @__PURE__ */ React2.createElement("p", { role: "status" }, result.total, "개 변경 중 ", result.saved, "개 저장을 확인했어요.", result.error ? ` ${result.saved + 1}번째 항목에서 멈췄어요. 이 항목은 저장됐을 수도 있으니 목록에서 확인해주세요. 뒤의 항목은 요청하지 않았어요.` : "", !result.refreshed ? " 새 목록 조회에 실패했어요. 목록 다시 불러오기를 눌러주세요." : "", " 다시 가져올 때는 새 목록을 기준으로 변경 내용을 다시 확인해요.") : null) : null, /* @__PURE__ */ React2.createElement("div", { className: "an-nest-actions" }, /* @__PURE__ */ React2.createElement("button", { type: "button", disabled: busy || !!submitted || !!unsupportedCount || !report?.readyForConfirmation, onClick: confirm }, busy ? "확인 중…" : "변경 확인 후 파일 내용 저장"), /* @__PURE__ */ React2.createElement("button", { type: "button", disabled: busy, onClick: onClose }, "파일 닫기")));
}

// framer-components/public-probe/PortfolioHoldingsPanel.tsx
var blank = () => ({ ticker: "", market: "KR", name: "", shares: "", avg_cost: "", memo: "" });
var CSS = `
.an-nest{color-scheme:light dark;--panel:light-dark(#fff,#171c23);--ink:light-dark(#191f28,#e3e7ec);--muted:light-dark(#6b7684,#9aa4b1);--soft:light-dark(#f8f9fb,#1d242c);--hover:light-dark(#f1f3f5,#252c35);--focus:light-dark(#e9edf2,#303945);background:var(--panel);color:var(--ink);font:400 13px/1.6 Pretendard,-apple-system,BlinkMacSystemFont,'Apple SD Gothic Neo',sans-serif;padding:20px;min-width:0}
.an-nest *{box-sizing:border-box}.an-nest h2,.an-nest h3,.an-nest p{margin:0}.an-nest h2{font-size:20px;font-weight:800}.an-nest h3{font-size:15px;font-weight:700}.an-nest p,.an-nest small{color:var(--muted)}.an-nest header{display:flex;justify-content:space-between;gap:12px;align-items:center;margin-bottom:16px}.an-nest button{font:inherit;color:var(--ink);background:var(--soft);border:0;border-radius:8px;padding:6px 10px;min-height:32px;cursor:pointer;transition:background 160ms}.an-nest button:disabled{opacity:.5;cursor:default}.an-nest :is(button,input,select,textarea):focus-visible{outline:0;background:var(--focus)}.an-nest input,.an-nest select,.an-nest textarea{display:block;width:100%;font:inherit;color:var(--ink);background:var(--soft);border:0;border-radius:8px;padding:8px;min-height:36px}.an-nest textarea{resize:vertical;min-height:72px}.an-nest label{display:grid;gap:4px;color:var(--muted)}.an-nest-grid{display:grid;grid-template-columns:repeat(2,minmax(0,1fr));gap:12px}.an-nest-form,.an-nest-preview{padding:16px;border-radius:16px;background:var(--soft);margin-bottom:16px}.an-nest-form input,.an-nest-form select,.an-nest-form textarea{background:var(--panel)}.an-nest-actions{display:flex;gap:8px;flex-wrap:wrap;margin-top:12px}.an-nest-rows{display:grid;gap:8px;list-style:none;padding:0;margin:16px 0}.an-nest-rows li{display:flex;align-items:center;justify-content:space-between;gap:12px;background:var(--soft);padding:12px;border-radius:12px}.an-nest-rows strong{font-weight:600;overflow-wrap:anywhere}.an-nest-rows small{display:block}.an-nest-rows .an-nest-actions{margin:0;flex-shrink:0}.an-nest-preview dl{margin:8px 0;display:grid;grid-template-columns:100px minmax(0,1fr);gap:6px}.an-nest-preview dt{color:var(--muted)}.an-nest-preview dd{margin:0;overflow-wrap:anywhere;white-space:pre-wrap}.an-nest [role=alert]{padding:10px 0;color:var(--ink)}
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
  const [form, setForm] = React3.useState(null);
  const [preview, setPreview] = React3.useState(null);
  const [busy, setBusy] = React3.useState(false);
  const [message, setMessage] = React3.useState("");
  const [error, setError] = React3.useState("");
  const [csvOpen, setCsvOpen] = React3.useState(false);
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
  };
  const prepare = (remove) => {
    setError("");
    setMessage("");
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
      const result = await onConfirm(preview);
      setPreview(null);
      setForm(null);
      setMessage(result.refreshed ? "보유 기록을 저장했어요. 거래 기록은 바뀌지 않았어요." : "저장 요청은 완료됐지만 새 목록을 불러오지 못했어요. 목록을 다시 불러와주세요.");
    } catch (e) {
      setError(errorText(e));
    } finally {
      setBusy(false);
    }
  };
  return /* @__PURE__ */ React3.createElement("section", { className: "an-nest", "aria-label": "둥지 보유종목 관리", hidden: !visible, style: { position: "absolute", inset: 0, overflow: "auto", zIndex: 1 } }, /* @__PURE__ */ React3.createElement("style", null, CSS), /* @__PURE__ */ React3.createElement("header", null, /* @__PURE__ */ React3.createElement("div", null, /* @__PURE__ */ React3.createElement("h2", null, "둥지 보유목록"), /* @__PURE__ */ React3.createElement("p", null, "종목 관리와 지도 메모는 따로 저장해요.")), /* @__PURE__ */ React3.createElement("button", { type: "button", disabled: busy, onClick: onBack }, "지도로 돌아가기")), /* @__PURE__ */ React3.createElement("div", { className: "an-nest-actions" }, /* @__PURE__ */ React3.createElement("button", { type: "button", disabled: !known || busy, onClick: () => {
    setCsvOpen(false);
    setForm(blank());
    setPreview(null);
    setError("");
    setMessage("");
  } }, "종목 추가"), /* @__PURE__ */ React3.createElement("button", { type: "button", disabled: !known || busy, onClick: () => {
    setCsvOpen(true);
    setForm(null);
    setPreview(null);
    setError("");
    setMessage("");
  } }, "파일로 넣기"), /* @__PURE__ */ React3.createElement("button", { type: "button", disabled: busy, onClick: async () => {
    setBusy(true);
    setError("");
    try {
      if (!await onReload()) setError("목록을 불러오지 못했어요. 입력한 내용은 남겨두었어요.");
    } catch (e) {
      setError(errorText(e));
    } finally {
      setBusy(false);
    }
  } }, "목록 다시 불러오기")), message ? /* @__PURE__ */ React3.createElement("p", { role: "status" }, message) : null, error ? /* @__PURE__ */ React3.createElement("p", { role: "alert" }, error) : null, csvOpen ? /* @__PURE__ */ React3.createElement(PortfolioHoldingsCsvPanel, { holdings: state.holdings, unsupportedCount: state.unsupportedCount, busy: busy || !known, onBusy: setBusy, onClose: () => setCsvOpen(false), onConfirm: onConfirmCsv }) : null, form ? /* @__PURE__ */ React3.createElement("form", { className: "an-nest-form", onSubmit: (e) => {
    e.preventDefault();
    prepare();
  } }, /* @__PURE__ */ React3.createElement("h3", null, form.id ? "보유 기록 수정" : "보유종목 추가"), /* @__PURE__ */ React3.createElement("p", null, "입력값은 변경 내용을 확인한 뒤 저장돼요."), /* @__PURE__ */ React3.createElement("fieldset", { disabled: busy || !known, style: { border: 0, padding: 0, margin: "12px 0 0" } }, /* @__PURE__ */ React3.createElement("div", { className: "an-nest-grid" }, /* @__PURE__ */ React3.createElement("label", null, "시장", /* @__PURE__ */ React3.createElement("select", { value: form.market, disabled: !!form.id, onChange: (e) => change("market", e.target.value) }, /* @__PURE__ */ React3.createElement("option", { value: "KR" }, "국내 · KRW"), /* @__PURE__ */ React3.createElement("option", { value: "US" }, "미국 · USD"))), /* @__PURE__ */ React3.createElement("label", null, "종목코드", /* @__PURE__ */ React3.createElement("input", { value: form.ticker, disabled: !!form.id, onChange: (e) => change("ticker", e.target.value), placeholder: form.market === "KR" ? "005930" : "AAPL" })), /* @__PURE__ */ React3.createElement("label", null, "이름", /* @__PURE__ */ React3.createElement("input", { value: form.name, onChange: (e) => change("name", e.target.value) })), /* @__PURE__ */ React3.createElement("label", null, "수량", /* @__PURE__ */ React3.createElement("input", { inputMode: "decimal", value: form.shares, onChange: (e) => change("shares", e.target.value) })), /* @__PURE__ */ React3.createElement("label", null, "평균 매수가 · ", form.market === "KR" ? "KRW" : "USD", /* @__PURE__ */ React3.createElement("input", { inputMode: "decimal", value: form.avg_cost, onChange: (e) => change("avg_cost", e.target.value) })), /* @__PURE__ */ React3.createElement("label", null, "보유 메모", /* @__PURE__ */ React3.createElement("textarea", { value: form.memo, onChange: (e) => change("memo", e.target.value) }))), /* @__PURE__ */ React3.createElement("div", { className: "an-nest-actions" }, /* @__PURE__ */ React3.createElement("button", { type: "submit" }, "변경 내용 확인"), /* @__PURE__ */ React3.createElement("button", { type: "button", onClick: () => {
    setForm(null);
    setPreview(null);
  } }, "입력 취소")))) : null, preview ? /* @__PURE__ */ React3.createElement("section", { className: "an-nest-preview", "aria-label": "보유 변경 미리보기" }, /* @__PURE__ */ React3.createElement("h3", null, preview.kind === "remove" ? "이 보유 기록을 삭제할까요?" : "이 내용으로 저장할까요?"), /* @__PURE__ */ React3.createElement("p", null, preview.kind === "remove" ? "목록의 보유 기록만 삭제해요. 실제 매도나 거래 기록 추가가 아니며 지도 메모도 삭제하지 않아요." : "현재 기록과 비교해주세요. 다른 화면에서 동시에 수정하지 않는 것이 좋아요."), /* @__PURE__ */ React3.createElement("dl", null, /* @__PURE__ */ React3.createElement("dt", null, "종목"), /* @__PURE__ */ React3.createElement("dd", null, preview.after?.name || preview.before?.name, " · ", preview.after?.ticker || preview.before?.ticker), (preview.kind === "remove" ? ["shares", "avg_cost", "memo"] : preview.changedFields).map((key) => /* @__PURE__ */ React3.createElement(React3.Fragment, { key }, /* @__PURE__ */ React3.createElement("dt", null, labels[key]), /* @__PURE__ */ React3.createElement("dd", null, String(preview.before?.[key] ?? "없음"), " → ", String(preview.after?.[key] ?? "삭제"))))), /* @__PURE__ */ React3.createElement("div", { className: "an-nest-actions" }, /* @__PURE__ */ React3.createElement("button", { type: "button", disabled: busy || !known, onClick: confirm }, busy ? "확인 중…" : preview.kind === "remove" ? "확인 후 보유 기록 삭제" : "확인 후 보유 기록 저장"), /* @__PURE__ */ React3.createElement("button", { type: "button", disabled: busy, onClick: () => setPreview(null) }, "돌아가서 수정"))) : null, !known ? /* @__PURE__ */ React3.createElement("p", { role: "status" }, state.phase === "error" ? "목록을 불러오지 못했어요. 보유 기록이 없다는 뜻은 아니에요." : "보유목록을 확인하고 있어요.") : /* @__PURE__ */ React3.createElement(React3.Fragment, null, state.holdings.length ? /* @__PURE__ */ React3.createElement("p", null, "현재 가격 미연결 · 평가금액·손익 계산 보류. 입력한 평균 매수가는 현재 시세가 아니에요.") : null, /* @__PURE__ */ React3.createElement("ul", { className: "an-nest-rows" }, state.holdings.map((h) => /* @__PURE__ */ React3.createElement("li", { key: h.ticker }, /* @__PURE__ */ React3.createElement("div", null, /* @__PURE__ */ React3.createElement("strong", null, h.name), /* @__PURE__ */ React3.createElement("small", null, h.ticker, " · ", h.market, " · ", state.selectedTickers.includes(h.ticker) ? "현재 지도에 표시" : "지도 표시 범위 밖"), /* @__PURE__ */ React3.createElement("small", null, "수량 ", h.duplicate ? "중복 확인 필요" : formatHoldingQuantity(h.shares), " · 평균 매수가 ", formatHoldingAverageCost(h))), /* @__PURE__ */ React3.createElement("div", { className: "an-nest-actions" }, /* @__PURE__ */ React3.createElement("button", { type: "button", disabled: busy || !h.id || h.duplicate, onClick: () => edit(h), "aria-label": h.name + " 수정" }, "수정"), /* @__PURE__ */ React3.createElement("button", { type: "button", disabled: busy || !h.id || h.duplicate, onClick: () => prepare(h), "aria-label": h.name + " 삭제" }, "삭제"))))), !state.holdings.length ? /* @__PURE__ */ React3.createElement("p", null, "등록한 보유종목이 없어요. 종목 추가로 시작하세요.") : null, state.unsupportedCount ? /* @__PURE__ */ React3.createElement("p", null, "이 지도에서 지원하지 않는 보유 항목 ", state.unsupportedCount, "개는 별도로 유지돼요.") : null, state.watchlistError ? /* @__PURE__ */ React3.createElement("p", { role: "status" }, "관심종목을 불러오지 못했어요. 목록 다시 불러오기로 재시도할 수 있어요.") : state.watchlist?.length ? /* @__PURE__ */ React3.createElement("details", null, /* @__PURE__ */ React3.createElement("summary", null, "관심종목 ", state.watchlist.length, "개"), /* @__PURE__ */ React3.createElement("p", null, "관심종목은 보유 수량·평균 매수가에 포함하지 않아요."), /* @__PURE__ */ React3.createElement("ul", { className: "an-nest-rows" }, state.watchlist.map((stock) => /* @__PURE__ */ React3.createElement("li", { key: stock.market + ":" + stock.ticker }, /* @__PURE__ */ React3.createElement("div", null, /* @__PURE__ */ React3.createElement("strong", null, stock.name), /* @__PURE__ */ React3.createElement("small", null, stock.ticker, " · ", stock.market, " · ", state.holdings.some((h) => h.ticker === stock.ticker && h.market === stock.market) ? "보유·관심" : "관심만", " · ", state.selectedTickers.includes(stock.ticker) ? "현재 지도에 표시" : "지도 표시 범위 밖")))))) : null, state.watchlistUnsupportedCount ? /* @__PURE__ */ React3.createElement("p", null, "지원하지 않는 관심 항목 ", state.watchlistUnsupportedCount, "개는 원래 목록에 유지돼요.") : null));
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
function fail(code) {
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
    const text5 = value.replace(/[,\s₩$원]/g, "");
    if (!/^[+-]?(?:\d+(?:\.\d*)?|\.\d+)(?:[eE][+-]?\d+)?$/.test(text5)) return null;
    value = Number(text5);
  }
  return typeof value === "number" && Number.isFinite(value) && value > 0 ? value : null;
}
function holdingRow(value) {
  if (!isRecord(value) || typeof value.id !== "string" || !value.id.trim() || typeof value.ticker !== "string" || typeof value.market !== "string" || typeof value.name !== "string") return null;
  const ticker = value.ticker.trim().toUpperCase(), rawMarket = value.market.trim().toLowerCase();
  const market = rawMarket === "kr" ? "KR" : rawMarket === "us" ? "US" : null;
  if (!market || !TICKER[market].test(ticker)) return null;
  return {
    id: value.id.trim(),
    ticker,
    market,
    name: value.name,
    shares: positiveStoredNumber(value.shares),
    avg_cost: positiveStoredNumber(value.avg_cost),
    memo: typeof value.memo === "string" ? value.memo : "",
    duplicate: false
  };
}
function holdingsRows(value) {
  const values = Array.isArray(value) ? value : isRecord(value) && Array.isArray(value.holdings) ? value.holdings : null;
  if (!values) return fail("holdings-unavailable");
  const tickers = values.map((row) => {
    if (!isRecord(row) || typeof row.ticker !== "string" || !row.ticker.trim()) fail("holdings-unavailable");
    return row.ticker.trim().toUpperCase();
  });
  return { rows: values.map(holdingRow).filter((row) => row !== null), tickers };
}
function sameHolding(left, right) {
  return left.id === right.id && left.ticker === right.ticker && left.market === right.market && (left.name.trim() || left.ticker) === (right.name.trim() || right.ticker) && left.shares === right.shares && left.avg_cost === right.avg_cost && sameText(left.memo, right.memo) && left.duplicate !== true && right.duplicate !== true;
}
function editFields(preview) {
  if (!Array.isArray(preview.changedFields) || !preview.changedFields.length || new Set(preview.changedFields).size !== preview.changedFields.length) fail("invalid-preview");
  if (!preview.changedFields.every((field) => EDIT_FIELDS.includes(field))) fail("invalid-preview");
  return preview.changedFields;
}
function canonicalPreview(fresh, preview) {
  if (preview.kind === "add") {
    const after2 = preview.after;
    if (preview.id !== null || preview.before !== null || !after2 || after2.id !== null || typeof after2.name !== "string" || typeof after2.memo !== "string") fail("invalid-preview");
    if (fresh.some((row) => row.ticker === after2.ticker)) fail("preflight-ticker-exists");
    return previewHoldingChange([], { kind: "add", ticker: after2.ticker, market: after2.market, shares: after2.shares, avg_cost: after2.avg_cost, name: after2.name, memo: after2.memo });
  }
  const before = preview.before;
  if (!preview.id || !before?.id || preview.id !== before.id) fail("invalid-preview");
  const targets = fresh.filter((row) => row.id === before.id);
  if (targets.length !== 1 || !sameHolding(targets[0], before)) fail("preflight-stale");
  if (preview.kind === "remove") {
    if (preview.after !== null || preview.changedFields.length) fail("invalid-preview");
    return previewHoldingChange([targets[0]], { kind: "remove", id: before.id });
  }
  const after = preview.after, fields3 = editFields(preview);
  if (!after || after.id !== before.id || after.ticker !== before.ticker || after.market !== before.market) fail("invalid-preview");
  const change = { kind: "edit", id: before.id };
  fields3.forEach((field) => {
    change[field] = after[field];
  });
  return previewHoldingChange([targets[0]], change);
}
function acknowledged(preview, value) {
  if (preview.kind === "remove") {
    if (!isRecord(value) || value.ok !== true || !preview.id) fail("write-unacknowledged");
    return { kind: "deleted", id: preview.id };
  }
  const row = holdingRow(value), after = preview.after;
  if (!row || !after || preview.kind === "edit" && row.id !== preview.id || row.ticker !== after.ticker || row.market !== after.market || row.name !== after.name || row.shares !== after.shares || row.avg_cost !== after.avg_cost || !sameText(row.memo, after.memo)) fail("write-unacknowledged");
  return { kind: "saved", row };
}
function createPortfolioHoldingsEditor(options = {}) {
  const getSession = options.getSession || readMapSession, fetcher = options.fetcher || fetch;
  const timeoutMs = typeof options.timeoutMs === "number" && Number.isFinite(options.timeoutMs) && options.timeoutMs > 0 ? options.timeoutMs : 15e3;
  let disposed = false, writing = false;
  const pending = /* @__PURE__ */ new Set();
  const current = (account) => {
    if (disposed) fail("editor-disposed");
    const value = sessionFor(getSession);
    if (!value) fail("authentication-required");
    if (!sameUser(account, value)) fail("session-changed");
    return value;
  };
  const request = async (init, failure2) => {
    const controller = new AbortController(), timer = setTimeout(() => controller.abort(), timeoutMs);
    pending.add(controller);
    try {
      const response = await fetcher(API2, { ...init, signal: controller.signal, cache: "no-store", credentials: "omit", redirect: "error" });
      return { response, body: await response.json() };
    } catch {
      if (disposed) fail("editor-disposed");
      if (controller.signal.aborted) fail("request-timeout");
      fail(failure2);
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
      if (writing) fail("mutation-in-flight");
      const account = sessionFor(getSession);
      if (!account) fail("authentication-required");
      writing = true;
      try {
        const readSession = current(account);
        const preflight = await request({ headers: { Authorization: "Bearer " + readSession.token } }, "holdings-unavailable");
        current(account);
        if (!preflight.response.ok) fail(preflight.response.status === 401 ? "authentication-required" : "holdings-unavailable");
        const fresh = holdingsRows(preflight.body);
        current(account);
        if (preview.kind === "add" && fresh.tickers.includes(String(preview.after?.ticker || "").trim().toUpperCase())) fail("preflight-ticker-exists");
        const canonical = canonicalPreview(fresh.rows, preview);
        const writeSession = current(account);
        const write = await request({ method: canonical.request.method, headers: { Authorization: "Bearer " + writeSession.token, "Content-Type": "application/json" }, body: JSON.stringify(canonical.request.body) }, "write-failed");
        current(account);
        if (!write.response.ok) fail(write.response.status === 401 ? "authentication-required" : "write-failed");
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

// framer-components/public-probe/PublicPortfolioPrototype.tsx
function PublicPortfolioPrototype({ template = "", templateURL }) {
  const frame = React4.useRef(null);
  const controller = React4.useRef(null);
  const editor = React4.useRef(null);
  const bridge = React4.useRef(null);
  const [state, setState] = React4.useState(null);
  const [source, setSource] = React4.useState(null);
  const [view, setView] = React4.useState("map");
  const [memberEpoch, setMemberEpoch] = React4.useState(0);
  React4.useEffect(() => {
    if (!frame.current) return;
    const workspace = createPortfolioMapWorkspace({ includeWatchlist: true });
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
    const unmount = mountMemberPrototype(frame.current, template, workspace, { openSource: setSource, openHoldings: () => setView("holdings"), templateURL });
    bridge.current = unmount;
    const unbind = workspace.bindAuth(window);
    void workspace.open();
    return () => {
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
  const [selected, setSelected] = React4.useState([]);
  return /* @__PURE__ */ React4.createElement("section", { "aria-label": "내 포트폴리오 관계지도", style: { position: "relative", width: "100%", minWidth: 0 } }, !state || state.phase === "loading" || state.phase === "signed-out" ? /* @__PURE__ */ React4.createElement("p", { role: "status" }, state?.phase === "signed-out" ? "로그인 후 지도 자료를 불러옵니다." : "보유종목과 지도 자료를 불러오는 중이에요.") : null, state?.phase === "choose-stocks" ? /* @__PURE__ */ React4.createElement("div", null, /* @__PURE__ */ React4.createElement("p", null, "지도에 함께 표시할 종목을 최대 30개 골라주세요. 둥지의 보유 목록은 바뀌지 않아요."), workspaceStocks(state).map((h) => /* @__PURE__ */ React4.createElement("label", { key: h.ticker }, /* @__PURE__ */ React4.createElement(
    "input",
    {
      type: "checkbox",
      checked: selected.includes(h.ticker),
      disabled: !selected.includes(h.ticker) && selected.length >= 30,
      onChange: (e) => setSelected((old) => e.target.checked ? [...old, h.ticker] : old.filter((t) => t !== h.ticker))
    }
  ), h.name, " · ", h.held ? h.watched ? "보유·관심" : "보유" : "관심")), /* @__PURE__ */ React4.createElement("button", { type: "button", disabled: !selected.length, onClick: () => {
    void controller.current?.showTickers(selected);
  } }, "지도에서 보기"), /* @__PURE__ */ React4.createElement("button", { type: "button", onClick: () => setView("holdings") }, "보유목록")) : null, state?.watchlistError && (state.phase === "ready" || state.phase === "choose-stocks") ? /* @__PURE__ */ React4.createElement("p", { role: "status" }, "관심종목을 불러오지 못했어요. 보유종목은 그대로 볼 수 있어요. 보유목록에서 다시 불러올 수 있어요.") : null, state?.phase === "error" ? /* @__PURE__ */ React4.createElement("div", { role: "alert" }, "자료를 불러오지 못했어요. 저장한 기록은 그대로예요.", /* @__PURE__ */ React4.createElement("button", { type: "button", onClick: () => {
    void controller.current?.open();
  } }, "다시 불러오기")) : null, state?.phase === "ready" && ["error", "conflict"].includes(state.privateState.phase) ? /* @__PURE__ */ React4.createElement("div", { role: "alert" }, state.privateState.phase === "conflict" ? "다른 화면에서 기록이 바뀌었어요. 내 변경은 아직 저장되지 않았어요." : "저장 기록을 확인하지 못했어요. 현재 변경은 유지하고 있어요.", state.privateState.phase === "error" && state.privateState.dirty ? /* @__PURE__ */ React4.createElement("button", { type: "button", onClick: () => {
    void controller.current?.save();
  } }, "저장 다시 시도") : null, /* @__PURE__ */ React4.createElement("button", { type: "button", onClick: () => {
    if (!state.privateState.dirty || window.confirm("현재 미저장 변경을 버리고 저장된 기록을 다시 불러올까요?")) void controller.current?.reloadSaved(state.privateState.dirty);
  } }, "저장 기록 다시 불러오기")) : null, source ? /* @__PURE__ */ React4.createElement("div", { role: "status" }, /* @__PURE__ */ React4.createElement("a", { href: source, target: "_blank", rel: "noopener noreferrer" }, "선택한 원문 열기"), /* @__PURE__ */ React4.createElement("button", { type: "button", onClick: () => setSource(null) }, "닫기")) : null, /* @__PURE__ */ React4.createElement(
    "iframe",
    {
      ref: frame,
      title: "내 종목 작업판",
      sandbox: "allow-scripts",
      referrerPolicy: "no-referrer",
      style: { display: "block", visibility: view === "map" ? "visible" : "hidden", width: "100%", height: "max(680px, calc(100dvh - 40px))", border: 0 }
    }
  ), state && state.phase !== "signed-out" ? /* @__PURE__ */ React4.createElement(
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
  return /* @__PURE__ */ React5.createElement("div", { style: { ...style, position: "relative", width: "100%", minHeight, boxSizing: "border-box" } }, isStatic ? /* @__PURE__ */ React5.createElement("section", { "aria-label": "회원 지도 검수용" }, /* @__PURE__ */ React5.createElement("h2", null, "회원 지도 검수용"), /* @__PURE__ */ React5.createElement("p", null, "실제 미리보기에서 로그인 후 보유종목과 저장 기록을 불러옵니다. 공개 사이트는 바꾸지 않습니다.")) : /* @__PURE__ */ React5.createElement(PublicPortfolioPrototype, { templateURL: "/member-map-canvas" }));
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
