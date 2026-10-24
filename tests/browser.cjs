/* Optional browser acceptance test. No npm install is needed to run the app.
   Provide an existing playwright-core module path through PLAYWRIGHT_MODULE. */
const assert = require("node:assert/strict");
const fs = require("node:fs/promises");
const path = require("node:path");
const { chromium } = require(process.env.PLAYWRIGHT_MODULE || "playwright-core");

async function main() {
  const root = path.resolve(__dirname, "..");
  const artifacts = path.join(root, ".codeform", "browser-artifacts");
  const fixture = path.join(root, ".codeform", "browser-fixture");
  await fs.mkdir(artifacts, { recursive: true });
  await fs.mkdir(fixture, { recursive: true });
  const original = await fs.readFile(path.join(root, "examples", "order-workflow", "workflow.py"), "utf8");
  await fs.writeFile(path.join(fixture, "workflow.py"), original);
  const browser = await chromium.launch({ headless: true });
  let page, passed = false;
  try {
    page = await browser.newPage({ viewport: { width: 1440, height: 1050 } });
    const errors = [];
    page.on("pageerror", error => errors.push(error.message));
    page.on("console", message => { if (message.type() === "error") errors.push(message.text()); });
    const base = process.env.CODEFORM_URL || "http://127.0.0.1:7331";
    const initial = await (await page.request.get(base + "/api/bootstrap")).json();
    const latest = name => initial.snapshots.find(s => s.repository.name === name);
    await page.goto(`${base}/#${latest("payment-service").id}/overview`);
    await page.getByRole("heading", { name: "System overview" }).waitFor();
    await page.locator(".metrics").waitFor();
    await page.screenshot({ path: path.join(artifacts, "overview-desktop.png"), fullPage: true });
    await page.locator("[data-view=claims]").first().click();
    await page.locator("tbody [data-claim]").first().click();
    await page.locator(".source-code .highlight").first().waitFor();
    assert.match(await page.locator(".source-header").innerText(), /Captured/);
    await page.getByRole("button", { name: "Close inspector" }).click();
    await page.locator("[data-view=architecture]").first().click();
    await page.locator(".graph-node").first().click();
    await page.getByRole("button", { name: "View captured source" }).waitFor();
    await page.getByRole("button", { name: "View captured source" }).click();
    await page.locator(".source-code").waitFor();
    await page.keyboard.press("Escape");

    await page.selectOption("#snapshot-select", latest("order-workflow").id);
    await page.locator("[data-view=findings]").first().click();
    await page.locator(".finding-card").first().click();
    await page.selectOption("#review-status", "accepted");
    await page.locator("#review-note").fill("Browser acceptance test: confirm the terminal-state requirement.");
    await page.getByRole("button", { name: "Save review" }).click();
    await page.getByRole("button", { name: "Export task specification" }).waitFor({ state: "visible" });
    const taskDownload = page.waitForEvent("download");
    await page.getByRole("button", { name: "Export task specification" }).click();
    await (await taskDownload).saveAs(path.join(artifacts, "task.json"));
    const task = JSON.parse(await fs.readFile(path.join(artifacts, "task.json"), "utf8"));
    assert.equal(task.execution.target_code_executed, false);
    assert.equal(task.execution.merge, "human_review");
    await page.screenshot({ path: path.join(artifacts, "finding-evidence.png"), fullPage: true });
    await page.keyboard.press("Escape");
    await page.locator("[data-view=behavior]").first().click();
    await page.getByText("Counterexample", { exact: true }).waitFor();
    const leanDownload = page.waitForEvent("download");
    await page.getByRole("button", { name: "Download Lean candidate" }).click();
    await (await leanDownload).saveAs(path.join(artifacts, "candidate.lean"));
    assert.match(await fs.readFile(path.join(artifacts, "candidate.lean"), "utf8"), /sorry/);

    await page.getByRole("main").getByRole("button", { name: "Analyze repository", exact: true }).click();
    await page.locator("#repository-path").fill(".codeform/browser-fixture");
    await page.getByRole("button", { name: "Build system model" }).click();
    await page.getByRole("heading", { name: "System walkthrough" }).waitFor();
    await page.locator("[data-view=overview]").first().click();
    await page.getByText("Terminal state can change in workflow", { exact: true }).waitFor();
    const before = await page.locator("#snapshot-select").inputValue();
    await fs.writeFile(path.join(fixture, "workflow.py"), original.replace('    ("cancelled", "reopen"): "pending",\n', ""));
    await page.getByRole("button", { name: "Re-analyze", exact: true }).click();
    await page.waitForFunction(id => {
      const select = document.getElementById("snapshot-select");
      return select && select.value !== id;
    }, before);
    assert.equal(await page.getByText("Terminal state can change in workflow", { exact: true }).count(), 0);
    const after = await page.locator("#snapshot-select").inputValue();
    assert.notEqual(before, after);
    await page.locator("[data-view=compare]").first().click();
    await page.selectOption("#compare-before", before);
    await page.selectOption("#compare-after", after);
    await page.getByRole("button", { name: "Compare snapshots", exact: true }).click();
    await page.getByRole("heading", { name: "Source changes" }).waitFor();
    await page.getByText("Terminal state can change in workflow", { exact: false }).waitFor();
    await page.screenshot({ path: path.join(artifacts, "snapshot-comparison.png"), fullPage: true });

    await page.getByRole("button", { name: "Export", exact: false }).first().click();
    const bundleDownload = page.waitForEvent("download");
    await page.getByRole("link", { name: "Analysis bundle · JSON" }).click();
    await (await bundleDownload).saveAs(path.join(artifacts, "bundle.json"));
    const importResponse = page.waitForResponse(response => response.url().endsWith("/api/import"));
    await page.locator("#import-file").setInputFiles(path.join(artifacts, "bundle.json"));
    const imported = await importResponse;
    assert.equal(imported.status(), 201, await imported.text());
    await page.waitForFunction(id => document.querySelector("#snapshot-select")?.value === id, after);
    await page.waitForTimeout(200);
    await page.reload();
    await page.getByRole("heading", { name: "Snapshot comparison" }).waitFor();
    await page.selectOption("#snapshot-select", latest("payment-service").id);
    await page.locator("[data-view=overview]").first().click();
    await page.setViewportSize({ width: 390, height: 844 });
    await page.screenshot({ path: path.join(artifacts, "overview-mobile.png"), fullPage: true });
    assert.equal(await page.evaluate(() => document.documentElement.scrollWidth <= innerWidth), true);
    await page.locator("[data-view=findings]").first().click();
    await page.locator("#search").fill("refunds");
    assert.equal(await page.locator(".finding-card").count(), 1);
    await page.locator("#severity-filter").selectOption("high");
    await page.getByText("No matches. Adjust your search or filters.").waitFor();
    assert.deepEqual(errors, [], "No browser errors should occur.");
    console.log("Browser acceptance passed: evidence, architecture, review, exports, invariants, analysis, comparison, import, reload, filters, and mobile layout.");
    console.log(`Artifacts: ${artifacts}`);
    passed = true;
  } finally {
    if (page && !passed) {
      await page.screenshot({ path: path.join(artifacts, "failure.png"), fullPage: true });
      console.error("Last UI message:", await page.locator("#toast").innerText());
    }
    await browser.close();
  }
}

main().catch(error => { console.error(error); process.exitCode = 1; });
