"use strict";

window.CodeFormMath = {
  render(root = document) {
    for (const element of root.querySelectorAll("[data-latex]")) {
      const formula = element.dataset.latex;
      if (!window.katex) {
        element.textContent = formula;
        continue;
      }
      try {
        window.katex.render(formula, element, {
          displayMode: element.dataset.display === "true",
          throwOnError: true, trust: false, strict: "error",
          output: "htmlAndMathml", maxExpand: 1000, maxSize: 10,
        });
      } catch {
        element.textContent = formula;
        element.classList.add("math-fallback");
        element.title = "Formula shown as source because it could not be rendered.";
      }
    }
  },
};
