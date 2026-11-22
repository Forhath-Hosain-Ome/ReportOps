// Local Vite browser regressions; Playwright is supplied externally through NODE_PATH.
import { after, before, test } from "node:test";
import assert from "node:assert/strict";
import { Buffer } from "node:buffer";
import { createRequire } from "node:module";
import { env } from "node:process";
import { readFileSync } from "node:fs";
const { chromium } = createRequire(import.meta.url)("playwright");
const baseURL = env.INSPECTION_SUMMARY_TEST_URL || "http://127.0.0.1:5187";
assert.ok(["127.0.0.1", "localhost"].includes(new URL(baseURL).hostname));
let browser;
before(async () => { browser = await chromium.launch({ channel: env.PLAYWRIGHT_BROWSER_CHANNEL || "msedge", headless: true }); });
after(async () => { await browser?.close(); });

async function setup(authenticated = true) {
  const page = await browser.newPage();
  if (authenticated) await page.addInitScript(() => {
    // Unsigned UI fixture; every feature request is intercepted below.
    const payload = btoa(JSON.stringify({ user_id: 1, exp: 4102444800 }));
    localStorage.setItem("qc-auth", JSON.stringify({ state: { access: `test.${payload}.test`, refresh: null }, version: 0 }));
  });
  return page;
}
async function upload(page) {
  await page.goto(`${baseURL}/inspection-summary`);
  const file = { name: `${"long-source-name-".repeat(10)}.xlsx`, mimeType: "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet", buffer: Buffer.from("UI fixture") };
  await page.getByLabel("Inspection Summary", { exact: true }).setInputFiles(file);
  await page.getByLabel("100% Inspection Data", { exact: true }).setInputFiles(file);
  await page.getByRole("button", { name: "Generate Report", exact: true }).click();
}

test("page requires authentication", async () => {
  const page = await setup(false);
  try { await page.goto(`${baseURL}/inspection-summary`); await page.waitForURL("**/login"); }
  finally { await page.close(); }
});

test("two inputs, terminal polling stop, one Result.xlsx download", async () => {
  const page = await setup();
  let posts = 0, polls = 0, downloads = 0;
  try {
    await page.route("**/inspection-summary/jobs/**", async (route) => {
      const request = route.request();
      if (request.method() === "POST") {
        posts += 1;
        for (const field of ["inspection_summary", "hundred_percent"]) assert.ok(request.postDataBuffer().includes(Buffer.from(`name="${field}"`)));
        return route.fulfill({ status: 202, json: { job_id: "one" } });
      }
      if (request.url().endsWith("download/")) {
        downloads += 1;
        return route.fulfill({ contentType: "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet", body: Buffer.from("PK-test") });
      }
      if (request.url().endsWith("preview/")) return route.fulfill({ json: previewFixture() });
      polls += 1;
      return route.fulfill({ json: { status: polls === 1 ? "PROCESSING" : "COMPLETED", stage: "PARSING_SHEETS", download_ready: polls > 1,
        expires_at: "2100-01-01T00:00:00Z", sheet_manifest: [{ name: "Final" }, { name: "100%" }] } });
    });
    await page.setViewportSize({ width: 390, height: 844 });
    await upload(page);
    await page.evaluate(() => document.fonts.ready);
    assert.ok(await page.evaluate(() => document.documentElement.scrollWidth <= window.innerWidth));
    const button = page.getByRole("button", { name: "Download Result.xlsx", exact: true });
    await button.waitFor({ timeout: 10000 });
    assert.ok(await page.evaluate(() => document.documentElement.scrollWidth <= window.innerWidth));
    const before = polls;
    await page.waitForTimeout(2400); assert.equal(polls, before);
    const received = page.waitForEvent("download"); await button.click();
    assert.equal((await received).suggestedFilename(), "Result.xlsx");
    assert.equal(posts, 1); assert.equal(downloads, 1);
    assert.ok(await page.evaluate(() => document.documentElement.scrollWidth <= window.innerWidth));
  } finally { await page.close(); }
});

test("structured failure displays source cell and stops polling", async () => {
  const page = await setup(); let polls = 0;
  try {
    await page.route("**/inspection-summary/jobs/**", async (route) => {
      if (route.request().method() === "POST") return route.fulfill({ status: 202, json: { job_id: "failed" } });
      polls += 1;
      return route.fulfill({ json: { status: "FAILED", stage: "FAILED", error: { code: "INVALID_QUANTITY", input: "raw", sheet: "Raw", cell: "M6", detail: "Quantity missing." } } });
    });
    await upload(page);
    await page.getByRole("alert").getByText("M6", { exact: true }).waitFor();
    const before = polls; await page.waitForTimeout(2400); assert.equal(polls, before);
    assert.equal(await page.getByRole("button", { name: "Download Result.xlsx", exact: true }).count(), 0);
  } finally { await page.close(); }
});

test("download expiry error is decoded from the blob response", async () => {
  const page = await setup();
  try {
    await page.route("**/inspection-summary/jobs/**", async (route) => {
      if (route.request().method() === "POST") return route.fulfill({ status: 202, json: { job_id: "expired" } });
      if (route.request().url().endsWith("download/")) return route.fulfill({ status: 410, json: { code: "ARTIFACT_EXPIRED", detail: "This generated report has expired." } });
      if (route.request().url().endsWith("preview/")) return route.fulfill({ json: previewFixture() });
      return route.fulfill({ json: { status: "COMPLETED", stage: "COMPLETED", download_ready: true, expires_at: "2100-01-01T00:00:00Z" } });
    });
    await upload(page);
    await page.getByRole("button", { name: "Download Result.xlsx", exact: true }).click();
    await page.getByRole("alert").getByText("detail: This generated report has expired.", { exact: true }).waitFor();
  } finally { await page.close(); }
});


// These are server-response fixtures. The UI only formats provided ratios.
function previewFixture(matched = false) {
  const group = (quantity, ratio) => [{ rank: 1, quantity, ratio, defects: [{ category: "A: Sewing", label: "Open seam" }] }];
  const final = { id: "block-0", title: "Final", report_type: "Final", kind: "ordinary", empty: false,
    factory_names: ["Factory"], date_start: "2026-10-01", date_end: "2026-10-05", inspection_days: 2,
    count: 6, count_kind: "audit", shipment_qty: 5000, inspected_qty: 2120, pass_qty: null,
    defect_qty: 36, defect_ratio: 0.0169811320754717, items: ["Shirt"], team_leader: null,
    top_defects: group(7, 0.00330188679245283) };
  const raw = { ...final, id: "block-1", title: "100%", report_type: "100%", kind: "raw",
    count: 12, count_kind: "style", inspection_days: 13, inspected_qty: 156132, pass_qty: 139557,
    defect_qty: 16575, defect_ratio: 0.106160172162, shipment_qty: null,
    top_defects: group(5020, 0.032152281402915484), manpower: { days: 13, aggregate_persons: null,
      entries: [{ date: "2026-10-05", values: ["52", "20"] }, { date: "2026-10-06", values: [null] }] } };
  const { manpower: _manpower, ...rawSummary } = raw;
  const columns = [{ key: "date", label: "Inspection Date", group: "Inspection", number: null },
    ...Array.from({ length: 18 }, (_, i) => ({ key: `metadata-${i}`, label: `Source field ${i}`, group: "Inspection", number: null })),
    ...Array.from({ length: 35 }, (_, i) => ({ key: `defect-${i}`, label: i === 0 ? "Open seam" : `Defect ${i + 1}`, group: "A: Sewing", number: i + 1 }))];
  const team = { duration_days: matched ? 2 : 0, inspected_qty: matched ? 2120 : 0, defect_qty: matched ? 36 : 0,
    defect_ratio: matched ? 0.0169811320754717 : null, top_defects: matched ? group(7,0.00330188679245283) : [] };
  return { available_sections: { qc_dashboard: true, analysis: true, summary: true, detail_100: true },
    sources: { inspection_summary: true, hundred_percent: true, hundred_percent_format: "raw" },
    job: { job_id: "preview", status: "COMPLETED", stage: "COMPLETED", expires_at: "2100-01-01T00:00:00Z", download_ready: true },
    overview: { generation_status: "COMPLETED", reconciliation_status: "passed", sections: ["QC Dashboard", "Analysis", "Summary", "100%"],
      blocks: [{ id: "block-0", name: "Final", position: 0, empty: false }, { id: "block-1", name: "100%", position: 1, empty: false }] },
    analysis: [final,raw], summary: [{ ...final, top_defects: group(7,0.1944444444444444) }, { ...rawSummary, top_defects: group(5020,0.3028657616892911) }],
    dashboard: { matched_styles: matched ? ["STYLE-EXACT"] : [], matched_style_count: matched ? 1 : 0, final_available: true,
      team_100: { ...team, style_count: matched ? 1 : 0, passed_qty: matched ? 2084 : 0 }, final: { ...team, audit_count: matched ? 6 : 0, shipment_qty: matched ? 5000 : 0 },
      comparison: { ratio_reduction: null, inspection_factor: matched ? 1 : null,
        equivalent_findings: matched ? "36 defect-equivalent pcs" : null, equivalent_calculation: null } },
    detail: { columns, record_count: 83, rows: [{ kind: "detail", values: { date: "2026-10-05", "defect-0": 4 } },
      { kind: "subtotal", values: { date: "Weekly Subtotal to 09 Oct 2026", "defect-0": 4 } },
      { kind: "total", values: { date: "Grand Total", "defect-0": 5020 } }] },
    reconciliation: { status: "passed", inspection_qty: 156132, pass_qty: 139557, defect_qty: 16575, defect_category_total: 16575,
      record_count: 83, inspection_day_count: 13, style_count: 12, defect_field_count: 35, defect_category_count: 1, hundred_percent_format: "raw", inspection_matches_detail: true, pass_matches_detail: true,
      defect_matches_categories: true, record_count_valid: true } };
}

async function completedRoutes(page, { matched = false, previewStatus = 200, expires = "2100-01-01T00:00:00Z" } = {}) {
  const calls = { posts: 0, polls: 0, previews: 0, downloads: 0 };
  await page.route("**/inspection-summary/jobs/**", async (route) => {
    const req = route.request();
    if (req.method() === "POST") { calls.posts++; return route.fulfill({ status: 202, json: { job_id: `job-${calls.posts}` } }); }
    if (req.url().endsWith("preview/")) { calls.previews++; return route.fulfill({ status: previewStatus,
      json: previewStatus === 200 ? previewFixture(matched) : { code: "PREVIEW_UNAVAILABLE", detail: "The report preview is unavailable." } }); }
    if (req.url().endsWith("download/")) { calls.downloads++; return route.fulfill({ contentType: "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet", body: Buffer.from("PK-test") }); }
    calls.polls++;
    return route.fulfill({ json: { status: "COMPLETED", stage: "COMPLETED", download_ready: true, expires_at: expires } });
  });
  return calls;
}
async function noOverflow(page) {
  await page.evaluate(() => document.fonts.ready);
  assert.ok(await page.evaluate(() => document.documentElement.scrollWidth <= window.innerWidth));
  assert.equal(/â€|Â·/.test(await page.locator("body").textContent()), false);
}
async function section(page, name) { await page.getByRole("navigation", { name: "Report sections" }).getByRole("button", { name, exact: true }).click(); }

test("shared shell once, completed preview once, keyboard sections, and mobile report parity", async () => {
  const page = await setup();
  const errors = []; page.on("pageerror", (e) => errors.push(e.message));
  try {
    const calls = await completedRoutes(page);
    await page.setViewportSize({ width: 390, height: 844 });
    await page.goto(`${baseURL}/inspection-summary`); await noOverflow(page);
    await upload(page);
    await page.getByRole("heading", { name: "Overview", exact: true }).waitFor();
    assert.equal(await page.getByRole("banner").count(), 1);
    assert.equal(await page.getByRole("main").count(), 1);
    assert.equal(await page.getByRole("button", { name: "INSPECTION SUMMARY", exact: true }).count(), 1);
    assert.equal(calls.posts,1); assert.equal(calls.previews,1);
    await noOverflow(page);
    for (const value of ["156,132", "139,557", "16,575"]) assert.ok(await page.getByText(value, { exact: true }).count() > 0);
    await section(page,"QC Dashboard");
    await page.getByRole("heading", { name: "No exact style matches were found between Final and 100%." }).waitFor();
    assert.equal(await page.getByText("NaN",{exact:true}).count(),0); await noOverflow(page);
    await section(page,"Analysis");
    await page.getByText("Top defect ratio based on inspected quantity",{exact:true}).waitFor();
    await page.getByText("0.33%",{exact:true}).waitFor(); await page.getByText("3.22%",{exact:true}).waitFor();
    await page.getByRole("region",{name:"MANPOWER"}).getByText("2026-10-05",{exact:true}).waitFor();
    await page.getByText("52 / 20",{exact:true}).waitFor(); await page.getByText("Not provided",{exact:true}).waitFor(); await noOverflow(page);
    await section(page,"Summary");
    await page.getByText("Top defect ratio based on total defect quantity",{exact:true}).waitFor();
    await page.getByText("19.44%",{exact:true}).waitFor(); await page.getByText("30.29%",{exact:true}).waitFor();
    assert.equal(await page.getByRole("region",{name:"MANPOWER"}).count(),0); await noOverflow(page);
    await section(page,"100% Detail");
    const wrapper = page.getByRole("region",{name:"Scrollable 100% detail"});
    assert.equal(await wrapper.getByRole("columnheader").count(),54);
    await wrapper.getByRole("rowheader",{name:"Grand Total",exact:true}).waitFor();
    assert.equal(await wrapper.locator('tr[data-kind="subtotal"]').count(),1);
    assert.equal(await wrapper.locator('tr[data-kind="total"]').count(),1);
    assert.ok(await wrapper.evaluate((el)=>el.scrollWidth>el.clientWidth));
    await wrapper.focus(); await page.keyboard.press("ArrowRight");
    await page.waitForFunction(() => document.querySelector(".inspection-detail").scrollLeft > 0); await noOverflow(page);
    const overview = page.getByRole("navigation",{name:"Report sections"}).getByRole("button",{name:"Overview",exact:true});
    await overview.focus(); await page.keyboard.press("Enter");
    await page.getByRole("heading",{name:"Overview",exact:true}).waitFor();
    assert.equal(await overview.getAttribute("aria-current"),"page");
    const count = calls.polls; await page.waitForTimeout(2300); assert.equal(calls.polls,count); assert.equal(calls.previews,1);
    const received = page.waitForEvent("download"); await page.getByRole("button",{name:"Download Result.xlsx",exact:true}).click();
    assert.equal((await received).suggestedFilename(),"Result.xlsx"); assert.equal(calls.downloads,1);
    await page.setViewportSize({width:1440,height:1000});
    for (const name of ["Overview","QC Dashboard","Analysis","Summary","100% Detail"]) { await section(page,name); await noOverflow(page); }
    assert.deepEqual(errors,[]);
  } finally { await page.close(); }
});

test("exact matched style and source-backed comparison render", async () => {
  const page = await setup();
  try { await completedRoutes(page,{matched:true}); await upload(page); await section(page,"QC Dashboard");
    await page.getByText("STYLE-EXACT",{exact:true}).waitFor();
    await page.getByText("Equivalent findings: 36 defect-equivalent pcs",{exact:true}).waitFor();
    assert.equal(await page.getByText("No exact style matches were found between Final and 100%.",{exact:true}).count(),0);
  } finally { await page.close(); }
});

test("preview failure is separate from valid download and remains responsive", async () => {
  const page = await setup();
  try { const calls=await completedRoutes(page,{previewStatus:404}); await page.setViewportSize({width:390,height:844}); await upload(page);
    await page.getByRole("heading",{name:"Preview unavailable",exact:true}).waitFor();
    assert.ok(await page.getByRole("button",{name:"Download Result.xlsx",exact:true}).isEnabled());
    const received=page.waitForEvent("download"); await page.getByRole("button",{name:"Download Result.xlsx",exact:true}).click(); await received;
    await page.getByRole("button",{name:"Retry preview",exact:true}).click();
    await page.waitForTimeout(300); assert.equal(calls.previews,2); await noOverflow(page);
  } finally { await page.close(); }
});

test("expired completion never requests preview or enables download", async () => {
  const page = await setup();
  try { const calls=await completedRoutes(page,{expires:"2020-01-01T00:00:00Z"}); await upload(page);
    await page.getByRole("button",{name:"Report expired",exact:true}).waitFor();
    assert.ok(await page.getByRole("button",{name:"Report expired",exact:true}).isDisabled());
    assert.equal(calls.previews,0); assert.equal(await page.getByRole("navigation",{name:"Report sections"}).count(),0);
  } finally { await page.close(); }
});

test("a new upload hides the old preview and resets section selection", async () => {
  const page = await setup();
  try { const calls=await completedRoutes(page); await upload(page); await section(page,"Analysis");
    let release; const gate = new Promise((resolve) => { release = resolve; });
    await page.route("**/inspection-summary/jobs/", async (route) => { await gate; await route.fallback(); });
    await page.getByRole("button",{name:"Generate Report",exact:true}).click();
    await page.getByRole("button",{name:"Uploading…",exact:true}).waitFor();
    assert.equal(await page.getByRole("navigation",{name:"Report sections"}).count(),0);
    release();
    await page.getByRole("heading",{name:"Overview",exact:true}).waitFor();
    assert.equal(calls.posts,2); assert.equal(calls.previews,2);
    assert.equal(await page.getByRole("region",{name:"MANPOWER"}).count(),0);
  } finally { await page.close(); }
});

test("shared shell sibling routes keep their API workspace", async () => {
  const page=await setup();
  try { await page.goto(`${baseURL}/inspection-summary`);
    for (const label of ["PUMA SUMMARY","Defect Image","AUDIT SUMMARY"]) { await page.getByRole("button",{name:label,exact:true}).click();
      assert.equal(await page.getByRole("banner").count(),1);
      assert.equal(await page.locator(".api_menu").count(),1);
      assert.equal(await page.getByRole("button",{name:"INSPECTION SUMMARY",exact:true}).count(),1);
    }
  } finally { await page.close(); }
});


test("a displayed preview expires without another user action", async () => {
  const page = await setup();
  try {
    const calls = await completedRoutes(page,{expires:new Date(Date.now()+3500).toISOString()});
    await upload(page);
    await page.getByRole("heading",{name:"Overview",exact:true}).waitFor();
    await page.getByRole("button",{name:"Report expired",exact:true}).waitFor({timeout:10000});
    assert.equal(await page.getByRole("navigation",{name:"Report sections"}).count(),0);
    assert.equal(calls.previews,1);
  } finally { await page.close(); }
});


test("backend-generated reference preview renders all 83 records and 54 fields", { skip: !env.INSPECTION_SUMMARY_PREVIEW_FIXTURE }, async () => {
  const page = await setup();
  try {
    const fixture = JSON.parse(readFileSync(env.INSPECTION_SUMMARY_PREVIEW_FIXTURE, "utf8"));
    await completedRoutes(page);
    await page.route("**/inspection-summary/jobs/*/preview/", (route) => route.fulfill({json:fixture}));
    await page.setViewportSize({width:390,height:844});
    await upload(page);
    await page.getByRole("heading",{name:"Overview",exact:true}).waitFor();
    await noOverflow(page);
    await section(page,"QC Dashboard");
    await page.getByRole("heading",{name:"No exact style matches were found between Final and 100%."}).waitFor();
    await section(page,"Analysis");
    await page.getByText("0.33%",{exact:true}).first().waitFor();
    await page.getByText("3.22%",{exact:true}).first().waitFor();
    await page.getByText("52 / 20",{exact:true}).waitFor();
    await noOverflow(page);
    await section(page,"Summary");
    await page.getByText("19.44%",{exact:true}).first().waitFor();
    await page.getByText("30.29%",{exact:true}).first().waitFor();
    assert.equal(await page.getByRole("region",{name:"MANPOWER"}).count(),0);
    await noOverflow(page);
    await section(page,"100% Detail");
    const detail=page.getByRole("region",{name:"Scrollable 100% detail"});
    assert.equal(await detail.getByRole("columnheader").count(),54);
    assert.equal(await detail.locator('tr[data-kind="detail"]').count(),83);
    assert.ok(await detail.locator('tr[data-kind="subtotal"]').count()>0);
    assert.equal(await detail.locator('tr[data-kind="total"]').count(),1);
    assert.ok(await detail.evaluate((el)=>el.scrollWidth>el.clientWidth));
    await noOverflow(page);
  } finally { await page.close(); }
});


test("neither source is rejected before posting", async () => {
  const page=await setup(); let posts=0;
  try {
    await page.route("**/inspection-summary/jobs/",route=>{posts++;return route.fulfill({status:500});});
    await page.goto(`${baseURL}/inspection-summary`);
    await page.getByRole("button",{name:"Generate Report",exact:true}).click();
    await page.getByRole("alert").getByText("At least one Inspection Summary or 100% workbook is required.",{exact:true}).waitFor();
    assert.equal(posts,0);
  } finally { await page.close(); }
});

for (const mode of ["summary-only","raw-only","structured-only","monthly-only","both-no-final"]) {
  test(`${mode}: explicit capabilities, optional upload, mobile navigation and dynamic labels`,async()=>{
    const page=await setup(); let posts=0;
    try {
      const summary=mode==="summary-only"||mode==="both-no-final";
      const hundred=mode!=="summary-only";
      const fixture=previewFixture();
      fixture.available_sections={qc_dashboard:false,analysis:true,summary:true,detail_100:hundred};
      fixture.sources={inspection_summary:summary,hundred_percent:hundred,hundred_percent_format:hundred?(mode==="raw-only"?"raw":mode==="monthly-only"?"structured_monthly_100":"structured"):null};
      fixture.dashboard=null;
      fixture.analysis=fixture.analysis.filter(b=>b.kind==="raw"?hundred:summary);
      fixture.summary=fixture.summary.filter(b=>b.kind==="raw"?hundred:summary);
      if(mode==="both-no-final") for(const b of [...fixture.analysis,...fixture.summary]) if(b.kind!=="raw") b.title=b.report_type="Random";
      if(!hundred) {fixture.detail=null;fixture.reconciliation=null;}
      else {
        fixture.detail.columns=[{key:"date",label:"Inspection Date",group:"Inspection"},...Array.from({length:60},(_,i)=>({
          key:`d-${i}`,kind:"defect",ordinal:i+1,number:i+1,category:i<30?"Material Defects":"Sewing Defects",
          group:i<30?"Material Defects":"Sewing Defects",label:i<2||i===59?"Other":`Field ${i+1}`}))];
        fixture.detail.rows=[{kind:"detail",values:{date:"2026-10-01","d-0":1,"d-1":2,"d-59":3}},{kind:"total",values:{date:"Grand Total","d-0":1,"d-1":2,"d-59":3}}];
        fixture.reconciliation={...fixture.reconciliation,defect_field_count:60,defect_category_count:2,hundred_percent_format:fixture.sources.hundred_percent_format};
      }
      await page.route("**/inspection-summary/jobs/**",async route=>{
        const req=route.request();
        if(req.method()==="POST") {
          posts++;
          const body=req.postDataBuffer();
          assert.equal(body.includes(Buffer.from('name="inspection_summary"')),summary);
          assert.equal(body.includes(Buffer.from('name="hundred_percent"')),hundred);
          assert.equal(body.includes(Buffer.from('name="raw"')),false);
          return route.fulfill({status:202,json:{job_id:"optional"}});
        }
        return route.fulfill({json:req.url().endsWith("preview/")?fixture:{status:"COMPLETED",stage:"COMPLETED",download_ready:true,expires_at:"2100-01-01T00:00:00Z"}});
      });
      await page.setViewportSize({width:390,height:844});
      await page.goto(`${baseURL}/inspection-summary`);
      const file={name:"source.xlsx",mimeType:"application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",buffer:Buffer.from("Fixture")};
      if(summary) await page.getByLabel("Inspection Summary",{exact:true}).setInputFiles(file);
      if(hundred) await page.getByLabel("100% Inspection Data",{exact:true}).setInputFiles(file);
      await page.getByRole("button",{name:"Generate Report",exact:true}).click();
      await page.getByRole("heading",{name:"Overview",exact:true}).waitFor();
      if(mode==="monthly-only") await page.getByText("100% Format: Structured Monthly",{exact:true}).waitFor();
      const nav=page.getByRole("navigation",{name:"Report sections"});
      assert.equal(await nav.getByRole("button",{name:"QC Dashboard",exact:true}).count(),0);
      assert.equal(await nav.getByRole("button",{name:"100% Detail",exact:true}).count(),hundred?1:0);
      for(const name of ["Overview","Analysis","Summary",...(hundred?["100% Detail"]:[])]) {await section(page,name);await noOverflow(page);}
      if(hundred) {
        const table=page.getByRole("region",{name:"Scrollable 100% detail"});
        assert.equal(await table.getByRole("columnheader").count(),61);
        assert.equal(await table.getByRole("columnheader").filter({hasText:"Other"}).count(),3);
        assert.ok(await table.getByRole("columnheader").filter({hasText:"Sewing Defects"}).count()>0);
      }
      assert.equal(posts,1);
    } finally {await page.close();}
  });
}


test("backend monthly preview retains 34 records, 35 defect fields and source totals at 390px", {skip:!env.INSPECTION_SUMMARY_MONTHLY_PREVIEW_FIXTURE}, async()=>{
  const page=await setup();
  try {
    const fixture=JSON.parse(readFileSync(env.INSPECTION_SUMMARY_MONTHLY_PREVIEW_FIXTURE,"utf8"));
    await completedRoutes(page);
    await page.route("**/inspection-summary/jobs/*/preview/",route=>route.fulfill({json:fixture}));
    await page.setViewportSize({width:390,height:844});
    await page.goto(`${baseURL}/inspection-summary`);
    await page.getByLabel("100% Inspection Data",{exact:true}).setInputFiles({name:"monthly.xlsx",mimeType:"application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",buffer:Buffer.from("UI fixture")});
    await page.getByRole("button",{name:"Generate Report",exact:true}).click();
    await page.getByRole("heading",{name:"Overview",exact:true}).waitFor();
    await page.getByText("100% Format: Structured Monthly",{exact:true}).waitFor();
    for(const value of ["37,874","28,249","9,625"]) assert.ok(await page.getByText(value,{exact:true}).count()>0);
    assert.equal(await page.getByRole("navigation",{name:"Report sections"}).getByRole("button",{name:"QC Dashboard",exact:true}).count(),0);
    await noOverflow(page);
    await section(page,"Analysis");await page.getByRole("region",{name:"MANPOWER"}).waitFor();await noOverflow(page);
    await section(page,"Summary");assert.equal(await page.getByRole("region",{name:"MANPOWER"}).count(),0);await noOverflow(page);
    await section(page,"100% Detail");
    const detail=page.getByRole("region",{name:"Scrollable 100% detail"});
    assert.equal(await detail.getByRole("columnheader").count(),fixture.detail.columns.length);
    assert.equal(fixture.detail.columns.filter(c=>c.kind==="defect").length,35);
    assert.equal(await detail.locator('tr[data-kind="detail"]').count(),34);
    assert.equal(await detail.locator('tr[data-kind="total"]').count(),1);
    assert.ok(await detail.evaluate(el=>el.scrollWidth>el.clientWidth));await noOverflow(page);
  } finally {await page.close();}
});
