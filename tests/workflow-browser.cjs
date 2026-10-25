const assert = require("node:assert/strict");
const fs = require("node:fs/promises");
const path = require("node:path");
const { chromium } = require(process.env.PLAYWRIGHT_MODULE || "playwright-core");

(async () => {
  const base = process.env.CODEFORM_URL || "http://127.0.0.1:7334";
  const artifacts = path.resolve(__dirname, "..", ".codeform", "browser-artifacts");
  await fs.mkdir(artifacts, { recursive: true });
  const browser = await chromium.launch({ headless: true });
  let page, passed = false;
  try {
    page = await browser.newPage({ viewport: { width: 1440, height: 1000 } });
    const errors = [];
    page.on("pageerror", error => errors.push(error.message));
    const bootstrap = await (await page.request.get(base + "/api/bootstrap")).json();
    const snapshot = bootstrap.snapshots.find(s => s.repository.name === (process.env.WORKFLOW_REVIEW_REPO || "inference-exchange"));
    assert.ok(snapshot, "Prepare the requested real review snapshot before this test.");
    const initial = await (await page.request.get(`${base}/api/v1/snapshots/${snapshot.id}/workflows`)).json();
    const run = initial.at(-1);
    assert.equal(run.state, "awaiting_review");
    assert.equal(run.nodes.find(n => n.id === "model_review").status, "awaiting_review");
    await page.goto(`${base}/#${snapshot.id}/workflow`);
    await page.getByRole("heading", { name: "Analysis workflow", exact: true }).waitFor();
    await page.getByRole("heading", { name: "Human model review", exact: true }).waitFor();
    await page.locator(".flow-claim .katex").first().waitFor();
    assert.equal(await page.locator(".math-fallback").count(), 0);
    await page.locator(".flow-model-diagram svg").waitFor();
    await page.locator(".flow-claim [data-walk-captured-source]").first().click();
    await page.locator(".drawer .source-code").waitFor();
    await page.getByRole("button", { name: "Close inspector", exact: true }).click();
    await page.screenshot({ path: path.join(artifacts, "inference-exchange-dag-review.png"), fullPage: true });
    await page.setViewportSize({ width: 390, height: 844 });
    assert.equal(await page.evaluate(() => document.documentElement.scrollWidth <= innerWidth), true);
    await page.screenshot({ path: path.join(artifacts, "inference-exchange-dag-mobile.png"), fullPage: true });
    const unchanged = await (await page.request.get(`${base}/api/v1/snapshots/${snapshot.id}/workflows/${run.id}`)).json();
    assert.equal(unchanged.state, "awaiting_review");
    assert.equal(unchanged.events.length, run.events.length, "The real human gate must not be approved by this test.");
    const staleFormMarkup = await page.locator("#flow-review").evaluate(form => form.outerHTML);

    // Test gate release on an authored example only, never the real review run.
    const fixture = bootstrap.snapshots.find(s => s.repository.name === "verified-transfer");
    const headers = { "X-Codeform-Token": bootstrap.token };
    const created = await (await page.request.post(`${base}/api/v1/snapshots/${fixture.id}/workflows`,
      { headers, data: { objective: `Browser fixture gate test ${Date.now()}; not the inference-exchange review.` } })).json();
    const job = await (await page.request.post(`${base}/api/v1/snapshots/${fixture.id}/workflows/${created.id}/advance`,
      { headers, data: {} })).json();
    for (let i = 0; i < 60; i++) {
      const status = await (await page.request.get(`${base}/api/v1/jobs/${job.id}`)).json();
      if (status.status === "complete") break;
      await page.waitForTimeout(100);
    }
    const context = await (await page.request.get(`${base}/api/v1/snapshots/${fixture.id}/workflows/${created.id}/nodes/model/context`)).json();
    const outputResponse = await page.request.post(`${base}/api/v1/snapshots/${fixture.id}/workflows/${created.id}/nodes/model/outputs`, {
      headers, data: {
        snapshot_id: fixture.id, spec_sha256: context.spec_sha256, input_sha256: context.input_sha256,
        actor: "browser fixture agent", summary: "Fixture model for gate-control verification.",
        claims: [{ statement: "The transfer source updates two balance values.", status: "observed",
          evidence: [{ path: "transfer.py", line_start: 4, line_end: 8 }] }],
      },
    });
    assert.equal(outputResponse.status(), 201);
    await page.setViewportSize({ width: 1440, height: 1000 });
    await page.goto(`${base}/#${fixture.id}/workflow`);
    await page.waitForFunction(id => document.querySelector("#snapshot-select")?.value === id, fixture.id);
    await page.locator(`#flow-review[data-workflow="${created.id}"][data-snapshot="${fixture.id}"]`).waitFor();
    // A queued/detached form from another snapshot must never submit against
    // whichever run happens to be selected now.
    await page.evaluate(markup => {
      const holder = document.createElement("div");
      holder.innerHTML = markup;
      document.body.appendChild(holder);
      const form = holder.querySelector("form");
      form.elements.note.value = "Stale fixture submission must be rejected.";
      form.dispatchEvent(new Event("submit", { bubbles: true, cancelable: true }));
      holder.remove();
    }, staleFormMarkup);
    await page.getByRole("status").filter({ hasText: "different snapshot or run" }).waitFor();
    await page.locator("#flow-note").fill("Fixture-only review: release parallel analysis tasks, not source execution.");
    const reviewResponse = page.waitForResponse(r => r.url().endsWith("/reviews"), { timeout: 10000 });
    await page.getByRole("button", { name: "Record human review", exact: true }).click();
    const reviewed = await reviewResponse;
    assert.equal(reviewed.status(), 201, await reviewed.text());
    await page.locator(".flow-node.awaiting_agent").first().waitFor();
    const released = await (await page.request.get(`${base}/api/v1/snapshots/${fixture.id}/workflows/${created.id}`)).json();
    assert.ok(released.parallel_ready.includes("architecture"));
    assert.ok(released.parallel_ready.includes("formalization"));
    const realAfter = await (await page.request.get(`${base}/api/v1/snapshots/${snapshot.id}/workflows/${run.id}`)).json();
    assert.equal(realAfter.state, "awaiting_review");
    assert.equal(realAfter.events.length, run.events.length);
    assert.deepEqual(errors, []);
    passed = true;
    console.log("Workflow UI passed: real inference-exchange draft, math/source/DAG inspection, preserved human gate, mobile, and fixture parallel release.");
  } finally {
    if (page && !passed) {
      console.error("Last UI message:", await page.locator("#toast").innerText());
      await page.screenshot({ path: path.join(artifacts, "workflow-failure.png"), fullPage: true });
    }
    await browser.close();
  }
})().catch(error => { console.error(error); process.exitCode = 1; });
