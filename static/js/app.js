(function () {
  // mobile sidebar
  var burger = document.querySelector(".burger"), sb = document.getElementById("sidebar");
  if (burger && sb) burger.addEventListener("click", function () { sb.classList.toggle("open"); });

  // confirm before destructive / sensitive actions
  document.addEventListener("submit", function (e) {
    var msg = e.target.getAttribute("data-confirm");
    if (msg && !window.confirm(msg)) e.preventDefault();
  });

  // live percentage in marks-entry grid
  document.querySelectorAll("input[data-max]").forEach(function (inp) {
    var out = document.getElementById("pct-" + inp.dataset.id), max = parseFloat(inp.dataset.max);
    function show() {
      var v = parseFloat(inp.value);
      out.textContent = isNaN(v) || !max ? "" : (v / max * 100).toFixed(1) + "%";
    }
    inp.addEventListener("input", show); show();
  });

  // charts: <canvas data-chart="id"> + <script type="application/json" id="id"> built server-side
  var canvases = document.querySelectorAll("canvas[data-chart]");
  if (!canvases.length) return;
  if (typeof Chart === "undefined") {
    canvases.forEach(function (c) {
      var p = document.createElement("p"); p.className = "empty muted";
      p.textContent = "Charts could not load (Chart.js needs an internet connection the first time).";
      c.replaceWith(p);
    });
    return;
  }
  Chart.defaults.font.family = 'system-ui,-apple-system,"Segoe UI",Roboto,sans-serif';
  Chart.defaults.color = "#6b7190";
  canvases.forEach(function (canvas) {
    var cfg = JSON.parse(document.getElementById(canvas.dataset.chart).textContent);
    var pct = cfg.options && cfg.options.plugins && cfg.options.plugins.testflow && cfg.options.plugins.testflow.percent;
    if (pct) {
      var axis = cfg.options.indexAxis === "y" ? "x" : "y";
      cfg.options.scales[axis].ticks = { callback: function (v) { return v + "%"; } };
      cfg.options.plugins.tooltip = { callbacks: { label: function (c) {
        var v = c.parsed[axis]; return c.dataset.label + ": " + (v === null ? "no data" : v + "%"); } } };
    }
    new Chart(canvas, cfg);
  });
})();
