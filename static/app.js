/* Ground Level News: progressive enhancements. Everything works without this file. */
(function () {
  "use strict";
  var d = document, body = d.body;

  /* relative times from <time data-ts datetime> */
  function rel(ts) {
    var s = Math.floor(Date.now() / 1000) - ts;
    if (s < 3600) return Math.max(1, s / 60 | 0) + "m ago";
    if (s < 86400) return (s / 3600 | 0) + "h ago";
    return new Date(ts * 1000).toLocaleDateString(undefined, { month: "short", day: "numeric" });
  }
  d.querySelectorAll("time[data-ts]").forEach(function (e) {
    var ts = +e.dataset.ts; if (ts > 0) e.textContent = rel(ts);
  });

  /* "Show N more" buttons: reveal `step` hidden items per click, keep focus sensible */
  d.querySelectorAll(".loadmore").forEach(function (b) {
    var g = d.getElementById(b.getAttribute("aria-controls")) || b.parentNode.previousElementSibling;
    if (!g) return;
    var st = +g.dataset.step || 9, noun = g.dataset.noun || "more";
    function lbl() {
      var n = g.querySelectorAll(".more-item").length;
      if (!n) b.parentNode.remove(); else b.textContent = "Show " + Math.min(st, n) + " more" + (noun && noun !== "more" ? " " + noun : "");
    }
    lbl();
    b.addEventListener("click", function () {
      var h = [].slice.call(g.querySelectorAll(".more-item"), 0, st);
      h.forEach(function (e) { e.classList.remove("more-item"); });
      var f = h[0] && h[0].querySelector("a"); if (f) f.focus({ preventScroll: true });
      lbl();
    });
  });

  /* header: hamburger sheet with inert page, Escape, outside click; dropdown panels close each other */
  var btn = d.querySelector(".menu"), nav = d.getElementById("site-nav"), top = d.getElementById("top");
  var mq = matchMedia("(min-width:1025px)");
  function setOpen(o) {
    body.classList.toggle("open", o);
    if (btn) { btn.setAttribute("aria-expanded", o); btn.setAttribute("aria-label", o ? "Close menu" : "Open menu"); }
    ["main", "footer", ".justin"].forEach(function (s) { var el = d.querySelector(s); if (el) { if (o) el.setAttribute("inert", ""); else el.removeAttribute("inert"); } });
  }
  if (btn && nav) {
    btn.addEventListener("click", function () {
      var o = btn.getAttribute("aria-expanded") !== "true"; setOpen(o);
      if (o) { var a = nav.querySelector("a,summary"); if (a) a.focus(); }
    });
    nav.addEventListener("click", function (e) { if (e.target.closest("a") && !mq.matches) setOpen(false); });
    mq.addEventListener("change", function (m) { if (m.matches) setOpen(false); });
  }
  var dds = [].slice.call(d.querySelectorAll(".nav details.dd"));
  dds.forEach(function (dd) {
    dd.addEventListener("toggle", function () { if (dd.open && mq.matches) dds.forEach(function (o) { if (o !== dd) o.open = false; }); });
  });
  function closeAll() { dds.forEach(function (o) { o.open = false; }); }
  d.addEventListener("keydown", function (e) {
    if (e.key !== "Escape") return;
    if (btn && btn.getAttribute("aria-expanded") === "true") { setOpen(false); btn.focus(); return; }
    var open = dds.filter(function (o) { return o.open; })[0];
    if (open) { open.open = false; open.querySelector("summary").focus(); }
  });
  d.addEventListener("click", function (e) { if (mq.matches && !e.target.closest(".nav details.dd")) closeAll(); });
  d.addEventListener("focusin", function (e) { if (mq.matches && !e.target.closest(".nav details.dd")) closeAll(); });
  if (top) {
    var c = false;
    addEventListener("scroll", function () { var n = scrollY > 40; if (n !== c) { c = n; top.classList.toggle("compact", n); } }, { passive: true });
  }

  /* share: Web Share API, else copy the link */
  d.querySelectorAll(".share").forEach(function (s) {
    var url = s.dataset.url || location.href, title = s.dataset.title || d.title, orig = s.textContent;
    function done(t) { s.setAttribute("data-done", "1"); s.textContent = t; setTimeout(function () { s.removeAttribute("data-done"); s.textContent = orig; }, 2200); }
    s.addEventListener("click", function () {
      if (navigator.share) { navigator.share({ title: title, url: url }).catch(function () {}); return; }
      if (navigator.clipboard) navigator.clipboard.writeText(url).then(function () { done("Link copied"); }, function () { prompt("Copy this link", url); });
      else prompt("Copy this link", url);
    });
  });

  /* back to top */
  d.querySelectorAll(".totop").forEach(function (a) {
    a.addEventListener("click", function (e) { e.preventDefault(); scrollTo({ top: 0, behavior: matchMedia("(prefers-reduced-motion:reduce)").matches ? "auto" : "smooth" }); var l = d.querySelector(".logo"); if (l) l.focus({ preventScroll: true }); });
  });
})();
