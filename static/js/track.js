/* Live order tracking: countdown, status polling, progress map. */
(function () {
  "use strict";

  var root = document.querySelector("[data-track]");
  if (!root) return;

  var statusUrl = root.getAttribute("data-status-url");
  var initialStatus = root.getAttribute("data-initial-status");
  var eta = parseInt(root.getAttribute("data-eta-seconds") || "0", 10);

  var badge = root.querySelector("[data-status-badge]");
  var progress = root.querySelector("[data-progress]");
  var countdown = root.querySelector("[data-countdown]");
  var etaBlock = root.querySelector("[data-eta-block]");
  var stepsEls = root.querySelectorAll("[data-step]");

  var STATUS_CLASSES = [
    "amber", "blue", "indigo", "teal", "purple", "green", "red", "gray"
  ];
  var TERMINAL = ["completed", "cancelled", "refunded"];

  /* ---- Countdown ------------------------------------------------------- */
  function formatEta(seconds) {
    if (seconds <= 0) return null;
    var h = Math.floor(seconds / 3600);
    var m = Math.floor((seconds % 3600) / 60);
    var s = seconds % 60;
    function pad(n) { return (n < 10 ? "0" : "") + n; }
    return (h > 0 ? h + ":" : "") + pad(m) + ":" + pad(s);
  }

  var ticker = null;
  function startCountdown() {
    if (!countdown) return;
    stopCountdown();
    function render() {
      if (eta <= 0) {
        countdown.textContent = "Any moment now";
        stopCountdown();
        return;
      }
      countdown.textContent = formatEta(eta);
      eta -= 1;
    }
    render();
    ticker = setInterval(render, 1000);
  }
  function stopCountdown() {
    if (ticker) { clearInterval(ticker); ticker = null; }
  }

  var ETA_TEXT = {
    ready: "Ready ✓",
    out_for_delivery: "On its way 🛵",
    completed: "Done ✓"
  };

  if (countdown && ETA_TEXT[initialStatus] !== undefined) {
    countdown.textContent = ETA_TEXT[initialStatus];
  } else {
    startCountdown();
  }

  /* ---- Route map ------------------------------------------------------- */
  var track = document.getElementById("route-track");
  var draw = document.getElementById("route-progress-draw");
  var marker = root.querySelector("[data-courier-marker]");
  var trackLength = track ? track.getTotalLength() : 0;

  function setMapProgress(percent) {
    if (!track || !marker) return;
    var frac = Math.max(0, Math.min(100, percent)) / 100;
    var point = track.getPointAtLength(trackLength * frac);
    marker.setAttribute("transform", "translate(" + point.x + "," + point.y + ")");
    if (draw) {
      draw.setAttribute("stroke-dasharray", (trackLength * frac) + " 99999");
    }
  }
  setMapProgress(parseInt((progress && progress.style.width) || "0", 10));

  /* ---- Status rendering ------------------------------------------------ */
  function renderTimeline(steps) {
    if (!steps || !steps.length) return;
    steps.forEach(function (step) {
      var el = root.querySelector('[data-step="' + step.key + '"]');
      if (!el) return;
      el.classList.toggle("done", !!step.done);
      el.classList.toggle("current", !!step.current);
      var note = el.querySelector("[data-step-note]");
      if (note) note.textContent = step.current ? "In progress" : (step.done ? "Done" : "Waiting");
    });
  }

  function applyStatus(data, firstLoad) {
    if (badge) {
      badge.textContent = data.status_display;
      STATUS_CLASSES.forEach(function (c) { badge.classList.remove(c); });
      badge.classList.add(data.status_color || "gray");
    }
    if (progress) progress.style.width = data.progress + "%";
    setMapProgress(data.progress);
    renderTimeline(data.steps);

    if (countdown && ETA_TEXT[data.status] !== undefined) {
      stopCountdown();
      countdown.textContent = ETA_TEXT[data.status];
    } else if (etaBlock && data.eta_seconds !== null && data.eta_seconds !== undefined) {
      eta = data.eta_seconds;
      startCountdown();
    }

    var readyEl = root.querySelector("[data-ready-time]");
    if (readyEl && data.estimated_ready_at) {
      var d = new Date(data.estimated_ready_at);
      var hr = d.getHours(), min = d.getMinutes();
      var ampm = hr >= 12 ? "PM" : "AM";
      hr = hr % 12 || 12;
      readyEl.textContent = hr + ":" + (min < 10 ? "0" : "") + min + " " + ampm;
    }

    var changed = data.status !== initialStatus;
    if (!firstLoad && changed && (TERMINAL.indexOf(data.status) !== -1 ||
        TERMINAL.indexOf(initialStatus) !== -1)) {
      // Terminal transitions (reveal rating form, hide cancel) need fresh HTML.
      window.location.reload();
    }
  }

  async function poll() {
    if (document.hidden) return;
    try {
      var res = await fetch(statusUrl, { headers: { Accept: "application/json" }, cache: "no-store" });
      if (!res.ok) return;
      applyStatus(await res.json(), false);
    } catch (err) { /* offline; try again next tick */ }
  }

  if (initialStatus && TERMINAL.indexOf(initialStatus) === -1) {
    setTimeout(poll, 3000);
    setInterval(poll, 12000);
    document.addEventListener("visibilitychange", function () {
      if (!document.hidden) poll();
    });
  }

  /* ---- Tip chips ------------------------------------------------------- */
  var tipInput = document.getElementById("tip");
  root.querySelectorAll("[data-tip]").forEach(function (chip) {
    chip.addEventListener("click", function () {
      if (!tipInput) return;
      var current = parseFloat(tipInput.value) || 0;
      var add = parseFloat(chip.getAttribute("data-tip")) || 0;
      tipInput.value = (current + add).toFixed(2);
      root.querySelectorAll(".tip-chip").forEach(function (c) { c.classList.remove("active"); });
      chip.classList.add("active");
    });
  });
})();
