const assert = require("node:assert/strict");
const fs = require("node:fs/promises");
const path = require("node:path");
const { chromium } = require(process.env.PLAYWRIGHT_MODULE || "playwright-core");

(async () => {
  const base = process.env.CODEFORM_URL || "http://127.0.0.1:7334";
  const artifacts = path.resolve(__dirname, "..", ".codeform", "browser-artifacts");
  await fs.mkdir(artifacts, { recursive: true });
  const browser = await chromium.launch({ headless: true });
  try {
    const page = await browser.newPage({ viewport: { width: 1440, height: 1000 } });
    const errors = [];
    page.on("pageerror", error => errors.push(error.message));
    const bootstrap = await (await page.request.get(base + "/api/bootstrap")).json();
    const snapshot = bootstrap.snapshots.find(s => s.repository.name === "inference-exchange");
    const runs = await (await page.request.get(`${base}/api/v1/snapshots/${snapshot.id}/workflows`)).json();
    const live = runs.filter(r => r.mode !== "preview" && r.state !== "superseded").at(-1);
    const preview = runs.filter(r => r.mode === "preview" && r.state === "preview_complete").at(-1);
    assert.ok(preview);
    assert.equal(live.state, "awaiting_review");
    const liveEvents = live.events.length;
    await page.goto(`${base}/#${snapshot.id}/workflow/${preview.id}`);
    await page.getByText("Read-only E2E preview — not owner-approved", { exact: true }).waitFor();
    await page.getByRole("heading", { name: "Evidence synthesis", exact: true }).waitFor();
    await page.getByText("Verification coverage", { exact: true }).waitFor();
    assert.equal(await page.getByRole("button", { name: "Record human review", exact: true }).count(), 0);
    assert.equal(await page.locator(".flow-node.complete").count(), 12);
    assert.ok((await page.locator(".flow-artifact").innerText()).includes("0 checked proof/counterexample references"));
    await page.reload();
    await page.getByText("Read-only E2E preview — not owner-approved", { exact: true }).waitFor();
    assert.ok(page.url().endsWith("/" + preview.id));
    await page.locator(".flow-map [data-flow-node=architecture]").click();
    await page.getByRole("heading", { name: "Architecture reviewer", exact: true }).waitFor();
    await page.locator(".flow-claim .katex").first().waitFor();
    await page.screenshot({ path: path.join(artifacts, "inference-e2e-preview.png"), fullPage: true });
    await page.locator(".flow-map [data-flow-node=tests]").click();
    await page.getByText("Proposed tests · not executed", { exact: true }).waitFor();
    await page.setViewportSize({ width: 390, height: 844 });
    assert.equal(await page.evaluate(() => document.documentElement.scrollWidth <= innerWidth), true);
    await page.screenshot({ path: path.join(artifacts, "inference-e2e-preview-mobile.png"), fullPage: true });
    await page.goto(`${base}/#${snapshot.id}/workflow`);
    await page.getByRole("heading", { name: "Human model review", exact: true }).waitFor();
    assert.equal(await page.getByText("Read-only E2E preview — not owner-approved", { exact: true }).count(), 0);
    const unchanged = await (await page.request.get(`${base}/api/v1/snapshots/${snapshot.id}/workflows/${live.id}`)).json();
    assert.equal(unchanged.state, "awaiting_review");
    assert.equal(unchanged.events.length, liveEvents);
    assert.deepEqual(errors, []);
    console.log("E2E preview UI passed: complete pipeline, clear preview checkpoints, synthesis, verification gaps, deep links, reload, source analysis, tests, mobile, and unchanged live gate.");
  } finally {
    await browser.close();
  }
})().catch(error => { console.error(error); process.exitCode = 1; });
