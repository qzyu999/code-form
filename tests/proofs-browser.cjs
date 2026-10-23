const assert = require("node:assert/strict");
const fs = require("node:fs/promises");
const path = require("node:path");
const { chromium } = require(process.env.PLAYWRIGHT_MODULE || "playwright-core");

(async () => {
  const base = process.env.CODEFORM_URL || "http://127.0.0.1:7332";
  const artifacts = path.resolve(__dirname, "..", ".codeform", "browser-artifacts");
  await fs.mkdir(artifacts, { recursive: true });
  const browser = await chromium.launch({ headless: true });
  try {
    const page = await browser.newPage({ viewport: { width: 1440, height: 1050 } });
    const errors = [];
    page.on("pageerror", error => errors.push(error.message));
    const bootstrap = await (await page.request.get(base + "/api/bootstrap")).json();
    assert.equal(bootstrap.proof_checker.available, true);
    const transfer = bootstrap.snapshots.find(s => s.repository.name === "verified-transfer");
    const workflow = bootstrap.snapshots.find(s => s.repository.name === "verified-workflow");
    await page.goto(`${base}/#${transfer.id}/proofs`);
    await page.getByRole("heading", { name: "Proofs & mathematics", exact: true }).waitFor();
    await page.getByRole("button", { name: "Check proofs with Lean" }).click();
    await page.getByRole("button", { name: "Check proofs with Lean" }).waitFor({ state: "visible" });
    await page.waitForFunction(() => document.querySelectorAll(".proof-card .badge.proved").length === 4, null, { timeout: 60000 });
    assert.equal(await page.locator(".proof-card .badge.disproved").count(), 2);
    await page.locator(".proof-details summary").first().click();
    await page.getByText("Quot.sound", { exact: true }).first().waitFor();
    assert.equal(await page.getByText("Lean-checked counterexample", { exact: true }).count(), 2);
    await page.screenshot({ path: path.join(artifacts, "checked-mathematics.png"), fullPage: true });
    const downloadWait = page.waitForEvent("download");
    await page.getByRole("button", { name: "Export proof report" }).click();
    const download = await downloadWait;
    await download.saveAs(path.join(artifacts, "checked-proof-report.json"));
    const report = JSON.parse(await fs.readFile(path.join(artifacts, "checked-proof-report.json"), "utf8"));
    assert.equal(report.summary.proved, 4);
    await page.selectOption("#snapshot-select", workflow.id);
    await page.getByText("Induct over all finite executions", { exact: true }).waitFor();
    assert.equal(await page.locator(".proof-card .badge.proved").count(), 1);
    await page.reload();
    await page.getByText("Induct over all finite executions", { exact: true }).waitFor();
    await page.setViewportSize({ width: 390, height: 844 });
    await page.screenshot({ path: path.join(artifacts, "checked-mathematics-mobile.png"), fullPage: true });
    assert.equal(await page.evaluate(() => document.documentElement.scrollWidth <= innerWidth), true);
    assert.deepEqual(errors, []);
    console.log("Proof browser journey passed: actual Lean checking, theorem results, axiom ledger, counterexamples, exports, induction, persistence, and mobile layout.");
  } finally {
    await browser.close();
  }
})().catch(error => { console.error(error); process.exitCode = 1; });
