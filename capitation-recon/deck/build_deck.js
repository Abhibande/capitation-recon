// Builds the solution deck. Run: node deck/build_deck.js
const pptxgen = require("pptxgenjs");
const React = require("react");
const ReactDOMServer = require("react-dom/server");
const sharp = require("sharp");
const fa = require("react-icons/fa");
const fs = require("fs");
const path = require("path");
const { applyTheme } = require(process.env.PPTX_SKILL + "/scripts/apply_theme.js");

const D = JSON.parse(fs.readFileSync(path.join(__dirname, "data.json")));
const S = D.summary;

// ---------------------------------------------------------------- theme
const HEX = { navy: "0B2E3C", teal: "0E7C7B", teal2: "5FB3B0", mint: "DCEFEE", amber: "E59A2F", amberLt: "FBEBD2",
  ink: "1C2B33", mute: "5E6E76", line: "D5DEE1", paper: "FFFFFF", soft: "F2F6F7", red: "B4432F" };
const THEME = {
  name: "Capitation Close", headFontFace: "Cambria", bodyFontFace: "Calibri",
  colors: { dk1: HEX.ink, lt1: HEX.paper, dk2: HEX.navy, lt2: HEX.soft, accent1: HEX.teal, accent2: HEX.amber,
    accent3: HEX.teal2, accent4: HEX.red, accent5: HEX.mint, accent6: HEX.mute, hlink: HEX.teal, folHlink: HEX.mute },
};
const pres = new pptxgen();
pres.layout = "LAYOUT_WIDE"; // 13.33 x 7.5
pres.theme = { headFontFace: THEME.headFontFace, bodyFontFace: THEME.bodyFontFace };
pres.title = "AI-assisted capitation revenue close";
const C = pres.SchemeColor;
// semantic aliases
const NAVY = C.text2, TEAL = C.accent1, AMBER = C.accent2, TEAL2 = C.accent3, RED = C.accent4, MINT = C.accent5,
  MUTE = C.accent6, INK = C.text1, WHITE = C.background1, SOFT = C.background2;

// ---------------------------------------------------------------- layouts
pres.defineSlideMaster({
  title: "TITLE", background: { color: NAVY },
  objects: [
    { placeholder: { options: { name: "title", type: "title", x: 0.8, y: 2.2, w: 11.5, h: 1.6, fontFace: "Cambria", fontSize: 44, bold: true, color: WHITE, valign: "bottom", align: "left" }, text: "" } },
    { placeholder: { options: { name: "body", type: "body", x: 0.8, y: 3.95, w: 11.0, h: 1.2, fontSize: 20, color: TEAL2, valign: "top" }, text: "" } },
  ],
});
pres.defineSlideMaster({
  title: "SECTION", background: { color: NAVY },
  objects: [
    { placeholder: { options: { name: "title", type: "title", x: 0.8, y: 2.7, w: 11.5, h: 1.2, fontFace: "Cambria", fontSize: 40, bold: true, color: WHITE, valign: "middle", align: "left" }, text: "" } },
    { placeholder: { options: { name: "body", type: "body", x: 0.8, y: 3.9, w: 11.5, h: 0.8, fontSize: 18, color: TEAL2, valign: "top" }, text: "" } },
  ],
  slideNumber: { x: 12.3, y: 7.0, w: 0.6, h: 0.3, fontSize: 10, color: TEAL2, align: "right" },
});
pres.defineSlideMaster({
  title: "CONTENT", background: { color: WHITE },
  objects: [
    { placeholder: { options: { name: "title", type: "title", x: 0.6, y: 0.35, w: 12.1, h: 0.85, fontFace: "Cambria", fontSize: 32, bold: true, color: NAVY, valign: "middle", align: "left", margin: 0 }, text: "" } },
    { text: { text: "Capitation revenue close  |  AI-assisted reconciliation prototype", options: { x: 0.6, y: 7.0, w: 8, h: 0.3, fontSize: 10, color: MUTE, margin: 0 } } },
  ],
  slideNumber: { x: 12.3, y: 7.0, w: 0.45, h: 0.3, fontSize: 10, color: MUTE, align: "right" },
});

// ---------------------------------------------------------------- helpers
const iconCache = {};
async function icon(name, color = "#FFFFFF") {
  const key = name + color;
  if (!iconCache[key]) {
    const svg = ReactDOMServer.renderToStaticMarkup(React.createElement(fa[name], { color, size: 256 }));
    const buf = await sharp(Buffer.from(svg)).resize(256, 256).png().toBuffer();
    iconCache[key] = "image/png;base64," + buf.toString("base64");
  }
  return iconCache[key];
}
let objN = 0;
const nm = (p) => `${p}-${++objN}`;
const money = (x, d = 0) => (x < 0 ? "-" : "") + "$" + Math.abs(x).toLocaleString("en-US", { minimumFractionDigits: d, maximumFractionDigits: d });
const n0 = (x) => x.toLocaleString("en-US");

async function circleIcon(s, name, x, y, d = 0.6, fill = TEAL, ic = "#FFFFFF") {
  s.addShape(pres.shapes.OVAL, { x, y, w: d, h: d, fill: { color: fill }, line: { color: fill }, objectName: nm("icon-bg") });
  s.addImage({ data: await icon(name, ic), x: x + d * 0.24, y: y + d * 0.24, w: d * 0.52, h: d * 0.52, objectName: nm("icon") });
}
function card(s, x, y, w, h, fill = SOFT, line = null) {
  s.addShape(pres.shapes.ROUNDED_RECTANGLE, { x, y, w, h, rectRadius: 0.08, fill: { color: fill }, line: line ? { color: line, width: 1 } : { color: fill }, objectName: nm("card") });
}
function txt(s, text, o) {
  s.addText(text, Object.assign({ isTextBox: true, margin: 0, fontSize: 14, color: INK, valign: "top", objectName: nm("text") }, o));
}
function arrow(s, x1, y1, x2, y2, color = MUTE, dash = "solid") {
  const flipH = x2 < x1, flipV = y2 < y1;
  s.addShape(pres.shapes.LINE, { x: Math.min(x1, x2), y: Math.min(y1, y2), w: Math.max(Math.abs(x2 - x1), 0.001), h: Math.max(Math.abs(y2 - y1), 0.001),
    flipH, flipV, line: { color, width: 1.5, endArrowType: "triangle", dashType: dash }, objectName: nm("arrow") });
}
function box(s, x, y, w, h, title, sub, kind = "core") {
  const st = { core: { fill: MINT, line: TEAL, t: NAVY }, ai: { fill: C.background1, line: AMBER, t: NAVY }, src: { fill: SOFT, line: MUTE, t: INK }, human: { fill: NAVY, line: NAVY, t: WHITE } }[kind];
  s.addShape(pres.shapes.ROUNDED_RECTANGLE, { x, y, w, h, rectRadius: 0.06, fill: { color: kind === "ai" ? C.background1 : st.fill }, line: { color: st.line, width: kind === "ai" ? 2 : 1 }, objectName: nm("box") });
  if (kind === "ai") s.addShape(pres.shapes.ROUNDED_RECTANGLE, { x, y, w, h, rectRadius: 0.06, fill: { color: AMBER, transparency: 85 }, line: { color: AMBER, width: 2 }, objectName: nm("box-tint") });
  const runs = [{ text: title, options: { bold: true, fontSize: 12, color: st.t, breakLine: !!sub } }];
  if (sub) runs.push({ text: sub, options: { fontSize: 10.5, color: kind === "human" ? TEAL2 : MUTE } });
  s.addText(runs, { isTextBox: true, x: x + 0.08, y, w: w - 0.16, h, margin: 0, valign: "middle", align: "center", objectName: nm("box-text") });
}
function content(title, section) {
  const s = pres.addSlide({ masterName: "CONTENT", sectionTitle: section });
  s.addText(title, { placeholder: "title" });
  return s;
}
function bullets(s, items, o) {
  const arr = items.map((t, i) => {
    const isArr = Array.isArray(t);
    return { text: isArr ? t[0] : t, options: { bullet: { indent: 16 }, breakLine: i < items.length - 1, paraSpaceAfter: 6, ...(isArr ? t[1] : {}) } };
  });
  s.addText(arr, Object.assign({ isTextBox: true, margin: 0, fontSize: 14, color: INK, valign: "top", objectName: nm("bullets") }, o));
}

(async () => {
  // ============================================================== 1 Title
  pres.addSection({ title: "Opening" });
  let s = pres.addSlide({ masterName: "TITLE", sectionTitle: "Opening" });
  s.addText("Closing capitation revenue in hours, not days", { placeholder: "title" });
  s.addText("An AI-assisted design and working prototype for reconciling Medicaid capitation: expected revenue, state remittances, bank deposits and retroactive rate changes", { placeholder: "body" });
  s.addImage({ data: await icon("FaBalanceScale", "#5FB3B0"), x: 11.2, y: 0.8, w: 1.2, h: 1.2, objectName: "title-icon" });
  s.addNotes("Purpose: show how I understood the problem, the solution I designed, the decisions and tradeoffs behind it, and evidence from a working prototype run end-to-end on synthetic data.");

  // ============================================================== 2 Exec summary
  s = content("The short version", "Opening");
  const stats = [
    [`${S.auto_matched_pct.toFixed(1)}%`, "of 41,407 member-months reconciled with no human touch"],
    [`${n0(S.raw_variance_items)} → ${S.clusters}`, "raw variances collapsed into root causes, each with an owner"],
    ["$0.00", `residual after re-performing the state's ${money(S.lump_sums_ytd, 2)} retro lump sum`],
    ["100%", "of injected discrepancies found, 0 false positives (synthetic data)"],
  ];
  stats.forEach(([v, l], i) => {
    const x = 0.6 + i * 3.08;
    card(s, x, 1.5, 2.88, 2.1);
    txt(s, v, { x: x + 0.25, y: 1.7, w: 2.4, h: 0.85, fontSize: 36, bold: true, color: TEAL, fontFace: "Cambria", valign: "middle" });
    txt(s, l, { x: x + 0.25, y: 2.6, w: 2.4, h: 0.9, fontSize: 13, color: MUTE });
  });
  const rows = [
    ["Problem", "Every month finance rebuilds expected revenue by hand, ties it to state 820 remittances and bank deposits, and chases variances, while rates change mid-year and retroactively in inconsistent formats. It takes days and depends on a few people."],
    ["Approach", "Deterministic engine for every dollar (versioned, bitemporal rates; member-month matching; rules-based root causes). AI only where inputs or outputs are language: reading rate notices, explaining clusters, drafting the memo. Humans approve rates and accounting treatments."],
    ["Outcome", "Reviewers work 8 explained clusters instead of thousands of lines; retro changes flow automatically into prior-period adjustments; every number traces to a source and a rule."],
  ];
  rows.forEach(([h, b], i) => {
    const y = 3.95 + i * 0.98;
    txt(s, h, { x: 0.6, y, w: 1.6, h: 0.8, fontSize: 16, bold: true, color: NAVY, fontFace: "Cambria" });
    txt(s, b, { x: 2.3, y, w: 10.4, h: 0.85, fontSize: 14 });
  });

  // ============================================================== Section: problem
  pres.addSection({ title: "Understanding the problem" });
  s = pres.addSlide({ masterName: "SECTION", sectionTitle: "Understanding the problem" });
  s.addText("Understanding the problem", { placeholder: "title" });
  s.addText("Three streams of data that are supposed to agree, but rarely do", { placeholder: "body" });

  // ============================================================== 3 money flow
  s = content("Three streams have to agree: rates, members and money", "Understanding the problem");
  const lanes = [
    ["FaFileInvoiceDollar", "Rates", "State publishes rate per rate cell (region × category). Excel schedule, PDF amendments, emails. Can change mid-year or retroactively.", "Approved, versioned rate table"],
    ["FaUsers", "Members", "State eligibility system sends enrollment (834). Plan loads it into its own roster; the two drift (missed terms, retro adds, address and age changes).", "Plan roster by member-month"],
    ["FaUniversity", "Money", "State pays monthly via 820 remittance (member lines, retro adjustments, header-level withholds and lump sums) and an EFT to the bank.", "820 detail + bank deposit"],
  ];
  for (let i = 0; i < lanes.length; i++) {
    const [ic, h, d, out] = lanes[i];
    const y = 1.5 + i * 1.65;
    await circleIcon(s, ic, 0.6, y + 0.2, 0.75);
    txt(s, h, { x: 1.55, y: y + 0.05, w: 1.6, h: 0.45, fontSize: 18, bold: true, color: NAVY, fontFace: "Cambria" });
    txt(s, d, { x: 1.55, y: y + 0.5, w: 5.6, h: 0.95, fontSize: 13, color: INK });
    arrow(s, 7.35, y + 0.6, 8.0, y + 0.6, TEAL);
    box(s, 8.1, y + 0.2, 2.2, 0.8, out, null, "core");
  }
  s.addShape(pres.shapes.ROUNDED_RECTANGLE, { x: 10.65, y: 1.7, w: 2.1, h: 4.4, rectRadius: 0.08, fill: { color: NAVY }, line: { color: NAVY }, objectName: "recon-box" });
  txt(s, [{ text: "Reconcile", options: { bold: true, fontSize: 16, color: WHITE, breakLine: true, fontFace: "Cambria" } },
    { text: "Expected = roster × rate", options: { fontSize: 12, color: TEAL2, breakLine: true } },
    { text: "vs. paid on 820", options: { fontSize: 12, color: TEAL2, breakLine: true } },
    { text: "vs. cash in bank", options: { fontSize: 12, color: TEAL2, breakLine: true } },
    { text: " ", options: { fontSize: 8, breakLine: true } },
    { text: "…and re-state prior months when rates change", options: { fontSize: 12, color: WHITE, italic: true } }],
    { x: 10.8, y: 1.9, w: 1.8, h: 4.0, valign: "middle" });
  for (let i = 0; i < 3; i++) arrow(s, 10.3, 2.1 + i * 1.65, 10.65, 2.1 + i * 1.65, TEAL);

  // ============================================================== 4 why it's hard
  s = content("Why the close takes days today", "Understanding the problem");
  const hard = [
    ["FaHistory", "Rates move under you", "Mid-year amendments and retroactive changes mean months already closed must be re-stated, and the right rate depends on when you ask."],
    ["FaFileAlt", "Formats are inconsistent", "The same kind of change arrives as a spreadsheet, a PDF table or a sentence in an email: \"+2.1% on rates in effect\"."],
    ["FaExchangeAlt", "Payments don't line up", "Retro adds, corrections and recoupments land in later 820s; some retro is paid as one lump sum with no member detail."],
    ["FaUsers", "Eligibility drifts", "Missed terms, members the state never loaded, age-band and region changes: each looks like a rate problem until you dig."],
    ["FaUniversity", "Cash differs from the 820", "Withholds, offsets taken outside the remittance, deposits after cut-off, deposits with no remittance at all."],
    ["FaUserTie", "Knowledge sits in people", "Thousands of line variances are triaged with judgment that lives in two or three heads and personal spreadsheets."],
  ];
  for (let i = 0; i < hard.length; i++) {
    const [ic, h, d] = hard[i];
    const col = i % 3, row = Math.floor(i / 3);
    const x = 0.6 + col * 4.1, y = 1.5 + row * 2.6;
    card(s, x, y, 3.9, 2.35);
    await circleIcon(s, ic, x + 0.25, y + 0.25, 0.6, i === 5 ? AMBER : TEAL);
    txt(s, h, { x: x + 1.0, y: y + 0.3, w: 2.75, h: 0.55, fontSize: 16, bold: true, color: NAVY, fontFace: "Cambria", valign: "middle" });
    txt(s, d, { x: x + 0.25, y: y + 1.0, w: 3.45, h: 1.25, fontSize: 13 });
  }

  // ============================================================== 5 the questions
  s = content("Four questions the close must answer, every month", "Understanding the problem");
  const qs = [
    ["1", "What should we have earned?", "Plan roster × rate that applies to each member-month, using only approved rates, as known at close."],
    ["2", "What did the state pay, and why is it different?", "Match at member × coverage month across all 820s; classify each difference by root cause; size it and assign an owner."],
    ["3", "What actually reached the bank?", "820 remittance totals vs EFT deposits; withholds, offsets, timing, unidentified receipts."],
    ["4", "What changed for prior periods?", "When a rate or eligibility fact changes for a closed month, quantify and book the prior-period adjustment; follow it until the state settles it."],
  ];
  qs.forEach(([n, q, a], i) => {
    const y = 1.5 + i * 1.3;
    s.addShape(pres.shapes.OVAL, { x: 0.6, y: y + 0.1, w: 0.8, h: 0.8, fill: { color: i === 3 ? AMBER : TEAL }, line: { color: i === 3 ? AMBER : TEAL }, objectName: nm("num") });
    txt(s, n, { x: 0.6, y: y + 0.1, w: 0.8, h: 0.8, fontSize: 24, bold: true, color: WHITE, align: "center", valign: "middle", fontFace: "Cambria" });
    txt(s, q, { x: 1.7, y: y + 0.05, w: 10.9, h: 0.45, fontSize: 18, bold: true, color: NAVY, fontFace: "Cambria" });
    txt(s, a, { x: 1.7, y: y + 0.52, w: 10.9, h: 0.6, fontSize: 14, color: MUTE });
  });

  // ============================================================== Section: approach
  pres.addSection({ title: "Approach & architecture" });
  s = pres.addSlide({ masterName: "SECTION", sectionTitle: "Approach & architecture" });
  s.addText("Approach & architecture", { placeholder: "title" });
  s.addText("Deterministic money, AI at the edges, humans at the gates", { placeholder: "body" });

  // ============================================================== 6 principle
  s = content("Deterministic money, AI at the edges, humans at the gates", "Approach & architecture");
  const cols = [
    ["FaCogs", TEAL, "Code computes", ["Rate lookups and amendments, rounded to the cent", "Expected revenue for every member-month", "Matching across all 820 cycles", "Root-cause rules and clustering", "Lump-sum re-performance and allocation", "Cash, withhold, retro triangle, JEs"], "Repeatable, testable, auditable. Same inputs, same answer."],
    ["FaRobot", AMBER, "AI reads & writes", ["Turns free-text rate notices into a strict schema, with quotes", "Explains each exception cluster from engine facts", "Drafts the close memo and state disputes", "Investigates the residue the rules can't explain"], "Never computes a dollar. Every number it writes is checked against engine output."],
    ["FaUserCheck", NAVY, "People decide", ["Approve each rate version before it touches revenue", "Accept or override accounting treatment per cluster", "Post journal entries", "Feed resolutions back as new rules"], "Judgment stays with finance; the system captures it."],
  ];
  for (let i = 0; i < cols.length; i++) {
    const [ic, col, h, items, foot] = cols[i];
    const x = 0.6 + i * 4.1;
    card(s, x, 1.45, 3.9, 5.3);
    await circleIcon(s, ic, x + 0.25, 1.7, 0.7, col);
    txt(s, h, { x: x + 1.1, y: 1.75, w: 2.7, h: 0.6, fontSize: 20, bold: true, color: NAVY, fontFace: "Cambria", valign: "middle" });
    bullets(s, items, { x: x + 0.3, y: 2.65, w: 3.4, h: 2.9, fontSize: 13 });
    txt(s, foot, { x: x + 0.3, y: 5.75, w: 3.4, h: 0.8, fontSize: 12.5, italic: true, color: MUTE });
  }

  // ============================================================== 7 architecture
  s = content("Solution architecture", "Approach & architecture");
  const colX = [0.5, 2.85, 5.45, 8.25, 10.75], colW = [2.0, 2.2, 2.4, 2.1, 2.1];
  ["Sources", "Ingest", "Deterministic core", "AI layer", "Outputs & gates"].forEach((h, i) =>
    txt(s, h, { x: colX[i], y: 1.3, w: colW[i], h: 0.35, fontSize: 12, bold: true, color: MUTE, align: "center" }));
  const src = [["Rate notices", "xlsx · pdf · email"], ["Plan roster", "834-fed, member-month"], ["820 remittances", "X12, monthly + retro"], ["Bank statement", "BAI/CSV"]];
  src.forEach(([a, b], i) => box(s, colX[0], 1.8 + i * 1.25, colW[0], 0.85, a, b, "src"));
  box(s, colX[1], 1.8, colW[1], 0.85, "Rate Intake Agent", "extract · validate · impact", "ai");
  box(s, colX[1], 3.05, colW[1], 0.85, "Roster loader", "rate cell per member-month", "core");
  box(s, colX[1], 4.3, colW[1], 0.85, "820 parser", "SE / BPR integrity checks", "core");
  box(s, colX[1], 5.55, colW[1], 0.85, "Bank loader", "credits, refs, dates", "core");
  const core = [["Bitemporal rate store", "approved versions only"], ["Expected revenue", "roster × rate as of close"], ["Member-month matcher", "+ root-cause rules"], ["Retro re-performance", "lump sums, triangle"], ["Cash & withhold recon", "820 ↔ bank"]];
  core.forEach(([a, b], i) => box(s, colX[2], 1.8 + i * 0.98, colW[2], 0.78, a, b, "core"));
  box(s, colX[3], 1.8, colW[3], 1.1, "Variance Investigator", "explains clusters from facts", "ai");
  box(s, colX[3], 3.2, colW[3], 1.1, "Close Narrator", "memo, disputes", "ai");
  box(s, colX[3], 4.6, colW[3], 1.1, "Grounding check", "every number must trace to engine", "core");
  box(s, colX[4], 1.8, colW[4], 0.85, "Rate approval", "human gate #1", "human");
  box(s, colX[4], 2.95, colW[4], 0.85, "Review console", "clusters, evidence, actions", "core");
  box(s, colX[4], 4.1, colW[4], 0.85, "Treatment & JE approval", "human gate #2", "human");
  box(s, colX[4], 5.25, colW[4], 0.85, "Close workpaper", "xlsx with live formulas", "core");
  // arrows
  for (let i = 0; i < 4; i++) arrow(s, colX[0] + colW[0], 2.22 + i * 1.25, colX[1], 2.22 + i * 1.25);
  arrow(s, colX[1] + colW[1], 2.22, colX[2], 2.19, AMBER);
  arrow(s, colX[1] + colW[1], 3.47, colX[2], 3.17);
  arrow(s, colX[1] + colW[1], 4.72, colX[2], 4.15);
  arrow(s, colX[1] + colW[1], 5.97, colX[2], 5.71);
  arrow(s, colX[2] + colW[2], 4.15, colX[3], 2.35);
  arrow(s, colX[2] + colW[2], 5.13, colX[3], 3.75);
  arrow(s, colX[3] + colW[3], 2.35, colX[4], 3.37);
  arrow(s, colX[3] + colW[3], 3.75, colX[4], 4.52);
  // legend
  [["Deterministic", MINT, TEAL], ["AI (Claude)", WHITE, AMBER], ["Human gate", NAVY, NAVY]].forEach(([l, f, ln], i) => {
    s.addShape(pres.shapes.ROUNDED_RECTANGLE, { x: 0.5 + i * 2.1, y: 6.6, w: 0.3, h: 0.22, rectRadius: 0.04, fill: { color: f }, line: { color: ln, width: 1.5 }, objectName: nm("legend") });
    txt(s, l, { x: 0.9 + i * 2.1, y: 6.57, w: 1.6, h: 0.28, fontSize: 11, color: MUTE, valign: "middle" });
  });
  txt(s, "Rates enter the store only after gate #1; JEs post only after gate #2.", { x: 6.9, y: 6.57, w: 5.9, h: 0.28, fontSize: 11, italic: true, color: MUTE, valign: "middle", align: "right" });
  s.addNotes("Dashed arrow: approved rate versions are committed to the store only after the human gate. AI components are amber; they sit on the edges: unstructured input and narrative output.");

  // ============================================================== 8 workflow
  s = content("How a month-end close runs", "Approach & architecture");
  const steps = [
    ["Continuous", "Rate notices ingested as they arrive; approval packet to reviewer; approved version committed"],
    ["~26th", "820 and EFT arrive; parser checks integrity; cash matched to remittance"],
    ["Close day 1", "Automated run, minutes: expected revenue, matching, root causes, retro re-performance, roll-forward"],
    ["Day 1–2", "Reviewers work clusters, not lines: accept treatment, assign owner, send disputes"],
    ["Day 2", "Approve draft JEs; controller signs off on memo and workpaper"],
  ];
  steps.forEach(([w, d], i) => {
    const x = 0.6 + i * 2.48;
    s.addShape(pres.shapes.CHEVRON, { x, y: 1.6, w: 2.4, h: 0.8, fill: { color: i === 2 ? AMBER : TEAL }, line: { color: i === 2 ? AMBER : TEAL }, objectName: nm("chev") });
    txt(s, w, { x: x + 0.35, y: 1.6, w: 1.75, h: 0.8, fontSize: 15, bold: true, color: WHITE, align: "center", valign: "middle" });
    txt(s, d, { x: x + 0.1, y: 2.6, w: 2.25, h: 1.5, fontSize: 12.5 });
  });
  card(s, 0.6, 4.35, 5.95, 2.4, SOFT);
  card(s, 6.75, 4.35, 5.95, 2.4, MINT);
  txt(s, "Today", { x: 0.85, y: 4.5, w: 5.5, h: 0.45, fontSize: 18, bold: true, color: NAVY, fontFace: "Cambria" });
  bullets(s, ["Several days, spreadsheet-driven", "Expected revenue rebuilt by hand", "Line-by-line variance chasing", "Retro tracked in side files; key-person risk"], { x: 0.85, y: 5.0, w: 5.5, h: 1.6 });
  txt(s, "Target state", { x: 7.0, y: 4.5, w: 5.5, h: 0.45, fontSize: 18, bold: true, color: NAVY, fontFace: "Cambria" });
  bullets(s, ["About one day, most of it review and approval", "Expected revenue computed and versioned", "Clusters with evidence, owner and treatment", "Retro tracked automatically through to settlement"], { x: 7.0, y: 5.0, w: 5.5, h: 1.6 });

  // ============================================================== Section: decisions
  pres.addSection({ title: "Key design decisions" });
  s = pres.addSlide({ masterName: "SECTION", sectionTitle: "Key design decisions" });
  s.addText("Key design decisions", { placeholder: "title" });
  s.addText("Where the hard parts are, and how the design handles them", { placeholder: "body" });

  // ============================================================== 9 bitemporal
  s = content("Rates are stored on two time axes", "Key design decisions");
  txt(s, "Every rate has an effective period (which coverage months it applies to) and a knowledge time (when finance approved it). The engine can always answer both \"what is right for August?\" and \"what did we believe about August when we closed?\". The difference between those two answers is the prior-period adjustment.", { x: 0.6, y: 1.4, w: 5.6, h: 2.0, fontSize: 14 });
  txt(s, "Example: Region 3 SSI rate for August 2026 coverage", { x: 0.6, y: 3.55, w: 5.6, h: 0.4, fontSize: 14, bold: true, color: NAVY });
  const ex = D.rate_example;
  const exRows = [[{ text: "As known at", options: { bold: true, color: WHITE, fill: { color: NAVY } } }, { text: "Rate (PMPM)", options: { bold: true, color: WHITE, fill: { color: NAVY }, align: "right" } }, { text: "Version", options: { bold: true, color: WHITE, fill: { color: NAVY } } }]]
    .concat(ex.map((e) => [e.label, { text: money(e.rate, 2), options: { align: "right" } }, e.version]));
  s.addTable(exRows, { x: 0.6, y: 4.0, w: 5.6, colW: [2.5, 1.5, 1.6], fontSize: 12.5, color: INK, border: { type: "solid", pt: 0.5, color: "D5DEE1" }, rowH: 0.42, objectName: "rate-table" });
  // PPA chart
  const tri = D.triangle;
  s.addChart(pres.charts.BAR, [{ name: "Recognised at Sep close", labels: tri.slice(0, 8).map((r) => r.coverage_month.slice(5)), values: tri.slice(0, 8).map((r) => r["2026-09"] || 0) }], {
    x: 6.6, y: 1.4, w: 6.1, h: 4.1, barDir: "col", chartColors: [HEX.amber], showTitle: true, title: "Prior-period adjustment booked at the Sep close, by coverage month",
    titleFontSize: 13, titleColor: HEX.navy, titleFontFace: "+mn-lt", showValue: true, dataLabelPosition: "outEnd", dataLabelFormatCode: "$#,##0", dataLabelFontSize: 10, dataLabelColor: HEX.ink, dataLabelFontFace: "+mn-lt",
    valAxisHidden: true, valGridLine: { style: "none" }, catGridLine: { style: "none" }, catAxisLabelColor: HEX.mute, catAxisLabelFontSize: 11, catAxisLabelFontFace: "+mn-lt", showLegend: false, objectName: "ppa-chart" });
  card(s, 6.6, 5.7, 6.1, 1.05, MINT);
  txt(s, `The Region 3 retro amendment was approved on Sep 22. At the September close the engine booked ${money(D.ppa.find((p) => p.close === "2026-09").prior_period_adjustment, 2)} for Jan–Aug automatically and attributed it to RV-2026-003.`, { x: 6.8, y: 5.8, w: 5.7, h: 0.9, fontSize: 13, valign: "middle" });

  // ============================================================== 10 rate intake
  s = content("Rate Intake Agent: any format in, a reviewable proposal out", "Key design decisions");
  const pipe = [["FaFileImport", "Extract", "Tables (xlsx, pdf) parsed in code. Free text (email, letters) read by Claude through a forced tool call against a strict schema."],
    ["FaClipboardCheck", "Validate", "Cells recognised, schedule complete, stated prior rates equal the store, moves within ±15%, basis stated, retro flagged."],
    ["FaChartLine", "Impact", "$ effect by coverage month against the current rate table; which closed months it re-states."],
    ["FaUserCheck", "Approve", "Packet shows citations, checks and open questions. Nothing affects revenue until a person signs."],
    ["FaDatabase", "Commit", "Immutable version; % rules materialised to the cent at commit, so they never change afterwards."]];
  for (let i = 0; i < pipe.length; i++) {
    const [ic, h, d] = pipe[i];
    const x = 0.6 + i * 2.48;
    await circleIcon(s, ic, x + 0.8, 1.45, 0.7, i === 0 ? AMBER : i === 3 ? NAVY : TEAL);
    if (i < 4) arrow(s, x + 1.6, 1.8, x + 3.18, 1.8, MUTE);
    txt(s, h, { x, y: 2.25, w: 2.3, h: 0.4, fontSize: 16, bold: true, color: NAVY, align: "center", fontFace: "Cambria" });
    txt(s, d, { x: x + 0.05, y: 2.7, w: 2.2, h: 1.55, fontSize: 12 });
  }
  card(s, 0.6, 4.45, 12.1, 2.3, SOFT);
  const p3 = D.proposals.find((p) => p.change_type === "percent_adjustment");
  txt(s, "Example from the run: the retroactive email", { x: 0.85, y: 4.6, w: 6, h: 0.4, fontSize: 15, bold: true, color: NAVY });
  txt(s, [{ text: "Source says: ", options: { bold: true } }, { text: "Region 3 rates rise 2.1% retroactive to January 1, applied on top of whatever rate was in effect each month, with Jan–Sep paid as one lump sum in October.", options: { italic: true } }],
    { x: 0.85, y: 5.05, w: 5.6, h: 1.5, fontSize: 13 });
  txt(s, [{ text: "Agent produced: ", options: { bold: true, breakLine: true } },
    { text: `+${(p3.adjustment.pct * 100).toFixed(1)}% · regions ${p3.adjustment.regions.join(",")} · all categories · basis: rates in effect each month`, options: { breakLine: true } },
    { text: `Effective ${p3.effective_from} → ${p3.effective_to} · RETRO · ${p3.checks.filter((c) => c.result === "pass").length}/${p3.checks.length} checks pass, 1 warning (re-states closed months)`, options: { breakLine: true } },
    { text: `Impact ≈ ${money(Object.values(p3.impact).reduce((a, b) => a + b, 0))} Jan–Oct · approved by Controller after phone confirmation`, options: {} }],
    { x: 6.7, y: 4.6, w: 5.8, h: 2.0, fontSize: 13, valign: "middle" });

  // ============================================================== 11 matching & clustering
  s = content("Match per member-month, explain by root cause", "Key design decisions");
  bullets(s, [
    ["Match at the grain where revenue is earned: member × coverage month, netting every 820 line from any cycle (retro adds, corrections, recoupments).", {}],
    ["Ordered, explainable rules turn each difference into a root cause, using evidence: date of birth for age-band, payment history for missed terms, rate history for superseded rates.", {}],
    ["Exceptions are grouped by signature so a reviewer decides once per cause, with an owner, an action and an accounting treatment.", {}],
    ["Anything no rule explains is labelled UNEXPLAINED and goes to the AI investigator with the member's full timeline. It is never forced into a bucket.", {}],
  ], { x: 0.6, y: 1.45, w: 5.4, h: 4.2, fontSize: 14 });
  // funnel
  const fun = [[n0(S.member_months), "member-months"], [n0(S.raw_variance_items), "raw variances"], [n0(S.open_items), "open after auto-resolution"], [String(S.clusters), "root-cause clusters"]];
  fun.forEach(([v, l], i) => {
    const w = 5.8 - i * 1.1, x = 6.6 + (5.8 - w) / 2, y = 1.5 + i * 1.3;
    s.addShape(pres.shapes.ROUNDED_RECTANGLE, { x, y, w, h: 1.1, rectRadius: 0.08, fill: { color: i === 3 ? AMBER : i === 0 ? NAVY : TEAL }, line: { color: i === 3 ? AMBER : i === 0 ? NAVY : TEAL }, objectName: nm("funnel") });
    txt(s, [{ text: v + "  ", options: { fontSize: 24, bold: true, fontFace: "Cambria" } }, { text: l, options: { fontSize: 13 } }], { x, y, w, h: 1.1, color: WHITE, align: "center", valign: "middle" });
  });
  txt(s, "Auto-resolved along the way: corrections paid in later cycles, recoupments netting to zero, and the Region 3 retro settled by lump sum.", { x: 0.6, y: 5.9, w: 5.4, h: 0.8, fontSize: 12.5, italic: true, color: MUTE });

  // ============================================================== 12 lump sum
  s = content("Re-performing the state's retro lump sum to the cent", "Key design decisions");
  const L = D.lumps[0];
  const lumpStats = [[money(L.amount, 2), "paid by the state as one header-level line on the October 820 (no member detail)"],
    [money(L.state_basis_estimate, 2), "re-performed by the engine on the state's own eligibility basis"],
    [money(L.residual, 2), `residual; allocated back to ${n0(L.member_months)} member-months, Jan–Sep`]];
  lumpStats.forEach(([v, l], i) => {
    const y = 1.45 + i * 1.6;
    card(s, 0.6, y, 5.6, 1.4, i === 2 ? MINT : SOFT);
    txt(s, v, { x: 0.85, y: y + 0.15, w: 5.1, h: 0.6, fontSize: 28, bold: true, color: i === 2 ? TEAL : NAVY, fontFace: "Cambria" });
    txt(s, l, { x: 0.85, y: y + 0.75, w: 5.1, h: 0.55, fontSize: 13, color: MUTE });
  });
  txt(s, "How it works", { x: 6.7, y: 1.45, w: 6, h: 0.45, fontSize: 18, bold: true, color: NAVY, fontFace: "Cambria" });
  bullets(s, [
    "Link the lump sum to the retro rate version it pays, by testing which version's re-performed total explains the amount",
    "Re-compute it the state's way: every member-month the state paid at the old rate, times the rate change for that cell and month",
    "Zero residual proves the state's calculation and lets the lump sum be allocated back to member-months, so 8,820 rate variances resolve automatically",
    "Where the state's basis and the plan's differ (members the state paid but the plan didn't expect, and vice versa), the difference shows up in the eligibility clusters, not as a mystery variance",
  ], { x: 6.7, y: 2.0, w: 6.0, h: 4.6, fontSize: 14 });

  // ============================================================== 13 AI guardrails
  s = content("Guardrails that make the AI safe to use in a close", "Key design decisions");
  const g = [["FaListAlt", "Schema-forced extraction", "Tool-use with an enum-constrained JSON schema; no free-form parsing of model text."],
    ["FaQuoteRight", "Citations on every field", "Each extracted value carries the verbatim sentence it came from, shown to the approver."],
    ["FaCalculator", "Numeric grounding check", "Any number in an AI explanation or memo that isn't in the engine's facts → draft rejected, template used."],
    ["FaQuestionCircle", "Open questions, not guesses", "Ambiguity (basis of a %, rounding, payment timing) becomes a question for the reviewer."],
    ["FaUserShield", "Human approval gates", "Rate versions and accounting treatments need a named approver; time-stamped in the store."],
    ["FaPlug", "Works offline", "Without an API key every step falls back to rules and templates, each labelled with the method that produced it."]];
  for (let i = 0; i < g.length; i++) {
    const [ic, h, d] = g[i];
    const col = i % 2, row = Math.floor(i / 2);
    const x = 0.6 + col * 6.15, y = 1.45 + row * 1.75;
    await circleIcon(s, ic, x, y + 0.1, 0.7, col === 0 ? TEAL : AMBER);
    txt(s, h, { x: x + 0.95, y: y + 0.05, w: 4.9, h: 0.45, fontSize: 16, bold: true, color: NAVY, fontFace: "Cambria" });
    txt(s, d, { x: x + 0.95, y: y + 0.5, w: 4.9, h: 0.9, fontSize: 13 });
  }

  // ============================================================== 14 tradeoffs
  s = content("Tradeoffs I made deliberately", "Key design decisions");
  const H = (t) => ({ text: t, options: { bold: true, color: WHITE, fill: { color: NAVY } } });
  const trows = [[H("Decision"), H("Chose"), H("Over"), H("Why")],
    ["Who computes dollars", "Deterministic code", "LLM end-to-end", "Revenue must be exact, repeatable and auditable; LLMs add risk without benefit on arithmetic"],
    ["Parsing structured rate files", "Table parsers", "LLM for every format", "Cheaper, exact and testable; the LLM is kept for language that code can't read"],
    ["Root-cause logic", "Explicit ordered rules + AI for the remainder", "ML classifier", "No labelled history at the start; rules are explainable to auditors and encode team knowledge; ML is an option later"],
    ["Rate history", "Bitemporal, immutable versions", "Overwrite current table", "Retro changes and \"as known at close\" questions are routine; overwriting loses the audit trail"],
    ["Matching grain", "Member × coverage month", "Per 820 / per payment", "Retro and corrections arrive in later cycles; only coverage-month matching lets them net out"],
    ["Automation level", "Human gates on rates and JEs", "Fully autonomous close", "Accounting judgment and SOX accountability stay with people; the system prepares, people approve"],
  ];
  s.addTable(trows, { x: 0.6, y: 1.45, w: 12.1, colW: [2.2, 2.6, 2.1, 5.2], fontSize: 12.5, color: INK, valign: "middle", border: { type: "solid", pt: 0.5, color: "D5DEE1" }, rowH: [0.42, 0.75, 0.75, 0.75, 0.75, 0.75, 0.75], objectName: "tradeoffs" });

  // ============================================================== Section: prototype
  pres.addSection({ title: "Prototype & results" });
  s = pres.addSlide({ masterName: "SECTION", sectionTitle: "Prototype & results" });
  s.addText("Prototype & results", { placeholder: "title" });
  s.addText("Run end-to-end on a synthetic plan: ~5,000 members, 10 months, 3 rate changes, 14 injected problems", { placeholder: "body" });

  // ============================================================== 15 what was built
  s = content("What the prototype does today", "Prototype & results");
  const built = [["Synthetic scenario", "Seeded generator: Excel, PDF and email rate notices; 10 X12-style 820s; bank CSV; roster; ground truth of 14 injected issue types"],
    ["Rate intake", "Parsers for xlsx/pdf; Claude tool-call for free text (rules fallback offline); 6 validation checks; impact; approval packet"],
    ["Engine", "Bitemporal store, expected revenue, matcher + 17 root-cause codes, lump-sum re-performance, cash/withhold recon, retro triangle, roll-forward"],
    ["AI layer", "Cluster explanations, cash explanations, close memo, all with the numeric grounding check"],
    ["Outputs", "HTML review console; Excel workpaper with live tie-out formulas; draft JEs; memo; member-month CSV"],
    ["Quality", "Unit tests (bitemporal lookups, 820 integrity, grounding check); scoring against ground truth on every run"]];
  built.forEach(([h, d], i) => {
    const y = 1.45 + i * 0.88;
    s.addShape(pres.shapes.OVAL, { x: 0.6, y: y + 0.12, w: 0.42, h: 0.42, fill: { color: TEAL }, line: { color: TEAL }, objectName: nm("dot") });
    txt(s, String(i + 1), { x: 0.6, y: y + 0.12, w: 0.42, h: 0.42, fontSize: 13, bold: true, color: WHITE, align: "center", valign: "middle" });
    txt(s, h, { x: 1.2, y: y + 0.08, w: 2.2, h: 0.5, fontSize: 15, bold: true, color: NAVY, valign: "middle" });
    txt(s, d, { x: 3.4, y: y + 0.08, w: 9.3, h: 0.7, fontSize: 13, valign: "middle" });
  });

  // ============================================================== 16 results: clusters chart
  s = content("October close: 342 open items, 8 causes, every one owned", "Prototype & results");
  const cl = D.clusters;
  s.addChart(pres.charts.BAR, [{ name: "Open variance", labels: cl.map((c) => (c.variance_usd < 0 ? "Under: " : "Over: ") + c.label.replace("Rate cell mismatch: ", "cell mismatch, ").replace("Unpaid: ", "").replace(/^./, (m) => m.toLowerCase())), values: cl.map((c) => Math.abs(Math.round(c.variance_usd))) }], {
    x: 0.5, y: 1.4, w: 7.4, h: 5.3, barDir: "bar", chartColors: [HEX.teal], showTitle: true, title: "Open variance by root cause (absolute $; under = state underpaid)", titleFontSize: 13, titleColor: HEX.navy, titleFontFace: "+mn-lt",
    showValue: true, dataLabelFormatCode: "$#,##0", dataLabelFontSize: 10, dataLabelColor: HEX.ink, dataLabelFontFace: "+mn-lt", dataLabelPosition: "outEnd",
    catAxisLabelColor: HEX.ink, catAxisLabelFontSize: 10.5, catAxisLabelFontFace: "+mn-lt", catAxisOrientation: "maxMin", valAxisHidden: true, valGridLine: { style: "none" }, catGridLine: { style: "none" }, showLegend: false, objectName: "cluster-chart" });
  const own = {};
  cl.forEach((c) => { own[c.owner] = (own[c.owner] || 0) + c.member_months; });
  txt(s, "Owner and treatment", { x: 8.2, y: 1.45, w: 4.5, h: 0.4, fontSize: 16, bold: true, color: NAVY, fontFace: "Cambria" });
  bullets(s, [
    [`Enrollment Ops: missed terms, members not on roster, newborn timing (${own["Enrollment Ops"]} member-months)`, {}],
    [`State Liaison: never-paid members and age-band cell corrections, disputes drafted (${own["State Liaison"]})`, {}],
    [`Revenue Accounting: duplicates and paid-after-term → overpayment liability (${own["Revenue Accounting"]})`, {}],
    ["Each cluster carries a proposed entry: revenue reversal, reserve, liability or no entry", {}],
  ], { x: 8.2, y: 1.95, w: 4.5, h: 3.4, fontSize: 13 });
  card(s, 8.2, 5.5, 4.5, 1.2, MINT);
  txt(s, `Largest item: ${cl[0].member_months} member-months the state stopped paying, most likely terms the plan never processed. Revenue of ${money(-cl[0].variance_usd)} is reversed, not carried.`, { x: 8.4, y: 5.6, w: 4.1, h: 1.0, fontSize: 12.5, valign: "middle" });

  // ============================================================== 17 roll-forward + cash
  s = content("Open items clear on their own as the state catches up", "Prototype & results");
  const rf = D.rollforward;
  s.addChart(pres.charts.BAR, [{ name: "Open items at close", labels: rf.map((r) => r.close.slice(5)), values: rf.map((r) => r.closing_items) }], {
    x: 0.5, y: 1.4, w: 6.6, h: 4.0, barDir: "col", chartColors: [HEX.teal], showTitle: true, title: "Open member-month items at each close (log scale)", titleFontSize: 13, titleColor: HEX.navy, titleFontFace: "+mn-lt",
    valAxisLogScaleBase: 10, valAxisMinVal: 1, valAxisHidden: true, showValue: true, dataLabelFormatCode: "#,##0", dataLabelFontSize: 10, dataLabelColor: HEX.ink, dataLabelFontFace: "+mn-lt", dataLabelPosition: "outEnd",
    catAxisLabelColor: HEX.mute, catAxisLabelFontSize: 11, catAxisLabelFontFace: "+mn-lt", valGridLine: { style: "none" }, catGridLine: { style: "none" }, showLegend: false, objectName: "rf-chart" });
  txt(s, "July: the state paid SSI/Expansion at superseded rates (1,397 items), cleared by the September catch-up. September: Region 3 retro booked as receivable, cleared by the October lump sum.", { x: 0.6, y: 5.55, w: 6.4, h: 1.1, fontSize: 12.5, italic: true, color: MUTE });
  txt(s, "Cash: 820 vs bank", { x: 7.6, y: 1.45, w: 5.1, h: 0.4, fontSize: 16, bold: true, color: NAVY, fontFace: "Cambria" });
  const ci = D.cash_items;
  const cashRows = [
    ["Net remitted on 820s (YTD)", money(S.net_remitted_ytd, 2)],
    ["Deposits matched to 820s", money(S.deposited_ytd, 2)],
    ["Difference", money(S.deposited_ytd - S.net_remitted_ytd, 2)],
  ];
  s.addTable(cashRows.map((r, i) => [{ text: r[0], options: { bold: i === 2 } }, { text: r[1], options: { align: "right", bold: i === 2 } }]), { x: 7.6, y: 1.95, w: 5.1, colW: [3.2, 1.9], fontSize: 12.5, color: INK, border: { type: "solid", pt: 0.5, color: "D5DEE1" }, rowH: 0.38, objectName: "cash-table" });
  bullets(s, [
    "Aug EFT $18,432.17 short of a balanced 820: an offset taken outside the remittance → due-from-state, request notice",
    "Oct 820 (Oct 29) posted Nov 2: deposit in transit at cut-off",
    "$46,250 state deposit with no 820 (ref MKP…): likely maternity kick payment → unapplied cash until identified",
    "Quality withhold of 1% verified on all 10 remittances; receivable tracked YTD",
  ], { x: 7.6, y: 3.3, w: 5.1, h: 3.4, fontSize: 12.5 });

  // ============================================================== 18 console screenshot
  s = content("What the reviewer works in", "Prototype & results");
  s.addImage({ path: path.join(__dirname, "console_exceptions.png"), x: 0.6, y: 1.4, w: 7.6, h: 7.6 * 860 / 1400, objectName: "console-shot" });
  s.addShape(pres.shapes.RECTANGLE, { x: 0.6, y: 1.4, w: 7.6, h: 7.6 * 860 / 1400, fill: { type: "none" }, line: { color: "D5DEE1", width: 1 }, objectName: "shot-frame" });
  bullets(s, [
    "One card per root cause: amount, plain-English explanation, owner, treatment and evidence sample",
    "Accept, assign or draft a state dispute from the card",
    "Tabs for rate intake packets (citations, checks, impact), retro triangle, cash and the close memo",
    "Excel workpaper alongside it ties out with live formulas: open variance = paid + lump sums − expected",
  ], { x: 8.6, y: 1.5, w: 4.1, h: 4.6, fontSize: 13.5 });

  // ============================================================== Section: path forward
  pres.addSection({ title: "Path forward" });
  s = pres.addSlide({ masterName: "SECTION", sectionTitle: "Path forward" });
  s.addText("Path forward", { placeholder: "title" });
  s.addText("What changes with real data, and how to roll it out safely", { placeholder: "body" });

  // ============================================================== 19 limits
  s = content("Honest limits of the prototype", "Path forward");
  const lim = [["Synthetic data", "100% detection is on problems I injected. Real data will have causes no rule covers yet; the UNEXPLAINED bucket and AI investigator exist for that."],
    ["Scope of rate types", "Full-month capitation only. Real contracts add proration, kick/delivery payments, risk adjustment, directed payments, MLR rebates."],
    ["Enrollment as of now", "Rates are bitemporal; the roster is not yet. Retro eligibility changes need the same 'as known at close' treatment."],
    ["Simplified 820 & GL", "820 layout is simplified; journal entries are proposed ending balances rather than changes against a live GL."],
    ["AI ran offline here", "No API key in the build environment, so offline fallbacks produced the outputs; the Claude path is implemented and labelled."]];
  lim.forEach(([h, d], i) => {
    const y = 1.45 + i * 1.05;
    card(s, 0.6, y, 12.1, 0.9, i % 2 ? WHITE : SOFT);
    txt(s, h, { x: 0.85, y, w: 2.8, h: 0.9, fontSize: 15, bold: true, color: NAVY, valign: "middle" });
    txt(s, d, { x: 3.7, y, w: 8.8, h: 0.9, fontSize: 13, valign: "middle" });
  });

  // ============================================================== 20 roadmap
  s = content("Rollout: earn trust before taking over the close", "Path forward");
  const ph = [["Phase 1", "Shadow (2–3 closes)", ["Run alongside the manual close on real 820s and rosters", "Compare results line by line; tune rules", "Measure match rate, unexplained %, hours saved"]],
    ["Phase 2", "Assist", ["Reviewers work from the console; manual process as backup", "Rate intake becomes the system of record", "Add kick payments, proration, retro eligibility"]],
    ["Phase 3", "Operate", ["Engine output is the close workpaper; JEs into the GL", "Auto-drafted state disputes and aging", "Resolutions feed back as new rules"]]];
  ph.forEach(([p, h, items], i) => {
    const x = 0.6 + i * 4.1;
    card(s, x, 1.45, 3.9, 2.95, i === 0 ? MINT : SOFT);
    txt(s, p, { x: x + 0.3, y: 1.6, w: 3.3, h: 0.35, fontSize: 13, bold: true, color: i === 0 ? TEAL : MUTE });
    txt(s, h, { x: x + 0.3, y: 1.95, w: 3.3, h: 0.5, fontSize: 20, bold: true, color: NAVY, fontFace: "Cambria" });
    bullets(s, items, { x: x + 0.3, y: 2.6, w: 3.35, h: 2.6, fontSize: 13 });
    if (i < 2) arrow(s, x + 3.92, 2.9, x + 4.08, 2.9, TEAL);
  });
  txt(s, "Success measures", { x: 0.6, y: 4.65, w: 3, h: 0.4, fontSize: 16, bold: true, color: NAVY, fontFace: "Cambria" });
  const kp = [["~1 day", "close duration, down from several"], ["> 95%", "member-months auto-reconciled"], ["< 1%", "of variance dollars unexplained"], ["Same close", "retro booked in the close it is approved"]];
  kp.forEach(([a, b], i) => {
    const x = 0.6 + i * 3.08;
    s.addShape(pres.shapes.ROUNDED_RECTANGLE, { x, y: 5.15, w: 2.88, h: 1.55, rectRadius: 0.08, fill: { color: C.background1 }, line: { color: TEAL, width: 1 }, objectName: nm("kpi") });
    txt(s, a, { x: x + 0.25, y: 5.3, w: 2.4, h: 0.65, fontSize: 26, bold: true, color: TEAL, fontFace: "Cambria", valign: "middle" });
    txt(s, b, { x: x + 0.25, y: 5.95, w: 2.4, h: 0.65, fontSize: 13, color: MUTE });
  });

  // ============================================================== 21 close
  s = pres.addSlide({ masterName: "TITLE", sectionTitle: "Path forward" });
  s.addText("Exact numbers from code. Explanations from AI. Decisions by people.", { placeholder: "title" });
  s.addText("The prototype, data generator, workpaper and review console are in the accompanying code package (README has quick-start)", { placeholder: "body" });

  const out = path.join(__dirname, "..", "out", "Capitation_Close_AI_Solution.pptx");
  await pres.writeFile({ fileName: out });
  await applyTheme(out, THEME);
  console.log("wrote", out);
})();
