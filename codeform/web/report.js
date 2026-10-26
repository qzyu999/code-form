"use strict";

document.addEventListener("DOMContentLoaded", () => {
  window.CodeFormMath?.render(document.querySelector(".review-report"));
  document.getElementById("report-print")?.addEventListener("click", () => {
    // Include evidence that is normally collapsed when printing.
    document.querySelectorAll("details").forEach(detail => { detail.open = true; });
    window.print();
  });
  document.getElementById("report-json")?.addEventListener("click", event => {
    event.preventDefault();
    const text = document.getElementById("report-data").textContent;
    const report = JSON.parse(text);
    const url = URL.createObjectURL(new Blob([text], { type: "application/json" }));
    const link = document.createElement("a");
    link.href = url;
    link.download = `${report.snapshot_id}-review.json`;
    link.click();
    setTimeout(() => URL.revokeObjectURL(url), 1000);
  });
});
