(function () {
  "use strict";

  const tabsEl = document.getElementById("tabs");
  const panelEl = document.getElementById("panel");
  const preloader = document.getElementById("preloader");
  const cursorGlow = document.getElementById("cursor-glow");
  const heroMetrics = document.getElementById("hero-metrics");
  const liveBanner = document.getElementById("live-banner");

  let activeIndex = 0;
  let switching = false;
  let livePayload = null;
  const reducedMotion = window.matchMedia("(prefers-reduced-motion: reduce)").matches;

  function shortTabLabel(fn) {
    const entry = fn.entry.replace(/ ·.*/, "");
    const title = fn.title.replace(/&amp;/g, "&").split(",")[0].split(" &")[0];
    return { entry, title };
  }

  function countAllMetrics() {
    return FN.reduce((n, f) => n + f.metrics.length, 0);
  }

  function countByStamp(st) {
    return FN.reduce((n, f) => n + f.metrics.filter((m) => m.st === st).length, 0);
  }

  function renderHeroStats() {
    if (!heroMetrics) return;
    heroMetrics.innerHTML = `
      <div class="stat-pill"><strong>${FN.length}</strong> constitutional functions</div>
      <div class="stat-pill"><strong>${countAllMetrics()}</strong> traced metrics</div>
      <div class="stat-pill"><strong>${countByStamp("gap")}</strong> documented gaps</div>
      <div class="stat-pill"><strong>${countByStamp("survey") + countByStamp("audit")}</strong> independent sources</div>
    `;
  }

  function buildTabs() {
    FN.forEach((fn, i) => {
      const { entry, title } = shortTabLabel(fn);
      const btn = document.createElement("button");
      btn.type = "button";
      btn.className = "tab-btn" + (i === 0 ? " active" : "");
      btn.setAttribute("role", "tab");
      btn.setAttribute("aria-selected", i === 0 ? "true" : "false");
      btn.innerHTML = `<span class="tab-entry">${entry}</span>${title}`;
      btn.addEventListener("click", () => show(i));
      tabsEl.appendChild(btn);
    });
  }

  function fnStats(f) {
    const gaps = f.metrics.filter((m) => m.st === "gap").length;
    const independent = f.metrics.filter((m) => m.st === "survey" || m.st === "audit").length;
    return { total: f.metrics.length, gaps, independent };
  }

  function resolveMetricDisplay(m) {
    if (!m.liveId || !livePayload?.sources?.[m.liveId]) {
      return { value: m.v, year: m.y, live: false, note: "" };
    }
    const src = livePayload.sources[m.liveId];
    if (src.status !== "ok") {
      return {
        value: m.v,
        year: m.y,
        live: false,
        note: src.error ? `Live fetch failed: ${src.error}` : ""
      };
    }
    const year = src.detail ? `${src.year} · ${src.detail}` : src.year;
    return { value: src.value, year, live: true, note: "" };
  }

  function renderPanel(index) {
    const f = FN[index];
    const stats = fnStats(f);
    let html = `
      <div class="fn-header">
        <div class="fn-entry">${f.entry}</div>
        <h2 class="fn-title">${f.title}</h2>
        <p class="fn-note">${f.note}</p>
      </div>
      <div class="fn-critical">${f.critical}</div>
      <div class="fn-metrics-bar">
        <div class="metric-chip"><span>${stats.total}</span> metrics</div>
        <div class="metric-chip"><span>${stats.independent}</span> survey / audit</div>
        <div class="metric-chip"><span>${stats.gaps}</span> data gaps</div>
      </div>
    `;

    STAGES.forEach((stage, si) => {
      const metrics = f.metrics.filter((m) => m.s === si);
      if (!metrics.length) return;

      const color = STAGE_COLORS[si];
      html += `
        <section class="stage" data-stage="${si}">
          <div class="stage-head">
            <div class="stage-badge" style="background:${color}18;color:${color};border:1px solid ${color}40">${STAGE_BADGES[si]}</div>
            <div class="stage-info">
              <h3>${stage[0]}</h3>
              <p>${stage[1]}</p>
            </div>
            <span class="stage-count">${metrics.length} metric${metrics.length > 1 ? "s" : ""}</span>
          </div>
          <div class="cards">
      `;

      metrics.forEach((m) => {
        const accent = {
          survey: "#14b8a6",
          audit: "#818cf8",
          self: "#94a3b8",
          statute: "#fbbf24",
          fill: "#fb7185",
          gap: "#f87171"
        }[m.st];
        const live = resolveMetricDisplay(m);
        const liveBadge = live.live
          ? `<span class="stamp live">Live</span>`
          : m.liveId
            ? `<span class="stamp live-fail">Static</span>`
            : "";

        html += `
          <details class="card${live.live ? " is-live" : ""}" style="--card-accent:${accent}"${m.liveId ? ` data-live-id="${m.liveId}"` : ""}>
            <summary>
              <div class="m-top">
                <span class="m-name">${m.name}</span>
                <span class="stamp-row">${liveBadge}<span class="stamp ${m.st}">${STAMP_LABELS[m.st]}</span></span>
              </div>
              <span class="m-value${m.st === "gap" && !live.live ? " none" : ""}${live.live ? " live-value" : ""}">${escapeHtml(live.value)}</span>
              ${live.year && live.year !== "—" ? `<span class="m-year">${escapeHtml(live.year)}</span>` : ""}
              <span class="m-source">${escapeHtml(sourceLine(m, live))}</span>
              ${live.note ? `<span class="m-live-note">${escapeHtml(live.note)}</span>` : ""}
              <span class="expand-icon" aria-hidden="true">⌄</span>
            </summary>
            <div class="meta">
              <dl>
                <dt>Source</dt><dd>${escapeHtml(m.src)}${live.live ? ` <em class="live-src">(refreshed from ${escapeHtml(livePayload.sources[m.liveId].source)})</em>` : ""}</dd>
                <dt>Pub. lag</dt><dd>${escapeHtml(m.lag)}</dd>
                <dt>Granularity</dt><dd>${escapeHtml(m.gran)}</dd>
                <dt>Denominator</dt><dd>${escapeHtml(m.den)}</dd>
              </dl>
              <div class="why">${m.why}</div>
            </div>
          </details>
        `;
      });

      html += `</div></section>`;
    });

    return html;
  }

  function sourceLine(m, live) {
    if (m.st === "gap" && !live.live) {
      return m.src && m.src !== "—" ? m.src : "No published source found";
    }
    const src = m.src && m.src !== "—" ? m.src : "Source not recorded";
    if (live.live && livePayload?.sources?.[m.liveId]?.source) {
      return `Source: ${src} · live: ${livePayload.sources[m.liveId].source}`;
    }
    return `Source: ${src}`;
  }

  function escapeHtml(str) {
    return String(str)
      .replace(/&/g, "&amp;")
      .replace(/</g, "&lt;")
      .replace(/>/g, "&gt;")
      .replace(/"/g, "&quot;");
  }

  function escapeAttr(str) {
    return escapeHtml(str);
  }

  function show(index) {
    if (switching || index === activeIndex) return;
    switching = true;

    [...tabsEl.children].forEach((btn, j) => {
      btn.classList.toggle("active", j === index);
      btn.setAttribute("aria-selected", j === index ? "true" : "false");
    });

    panelEl.classList.add("switching");

    setTimeout(() => {
      activeIndex = index;
      panelEl.innerHTML = renderPanel(index);
      panelEl.classList.remove("switching");
      observeCards();
      switching = false;
      panelEl.scrollIntoView({ behavior: reducedMotion ? "auto" : "smooth", block: "nearest" });
    }, reducedMotion ? 0 : 180);
  }

  function observeCards() {
    const cards = panelEl.querySelectorAll(".card");
    if (reducedMotion) {
      cards.forEach((c) => c.classList.add("visible"));
      return;
    }

    const observer = new IntersectionObserver(
      (entries) => {
        entries.forEach((entry) => {
          if (entry.isIntersecting) {
            entry.target.classList.add("visible");
            observer.unobserve(entry.target);
          }
        });
      },
      { threshold: 0.08, rootMargin: "0px 0px -40px 0px" }
    );

    cards.forEach((card, i) => {
      card.style.transitionDelay = `${Math.min(i * 0.04, 0.4)}s`;
      observer.observe(card);
    });
  }

  function observeChain() {
    const steps = document.querySelectorAll(".chain-step");
    if (reducedMotion) {
      steps.forEach((s) => s.classList.add("visible"));
      return;
    }

    const observer = new IntersectionObserver(
      (entries) => {
        entries.forEach((entry) => {
          if (entry.isIntersecting) {
            entry.target.classList.add("visible");
          }
        });
      },
      { threshold: 0.3 }
    );

    steps.forEach((step) => observer.observe(step));
  }

  function initCursorGlow() {
    if (!cursorGlow || reducedMotion || window.matchMedia("(max-width: 900px)").matches) return;

    let raf = null;
    let x = 0;
    let y = 0;

    document.addEventListener("mousemove", (e) => {
      x = e.clientX;
      y = e.clientY;
      if (!raf) {
        raf = requestAnimationFrame(() => {
          cursorGlow.style.left = x + "px";
          cursorGlow.style.top = y + "px";
          raf = null;
        });
      }
    });
  }

  function initCardTilt() {
    if (reducedMotion || window.matchMedia("(max-width: 900px)").matches) return;

    panelEl.addEventListener("mousemove", (e) => {
      const card = e.target.closest(".card:not([open])");
      if (!card) return;

      const rect = card.getBoundingClientRect();
      const px = (e.clientX - rect.left) / rect.width - 0.5;
      const py = (e.clientY - rect.top) / rect.height - 0.5;
      card.style.transform = `translateY(-4px) scale(1) perspective(600px) rotateX(${py * -4}deg) rotateY(${px * 4}deg)`;
    });

    panelEl.addEventListener("mouseleave", () => {
      panelEl.querySelectorAll(".card:not([open])").forEach((card) => {
        card.style.transform = "";
      });
    });
  }

  function dismissPreloader() {
    setTimeout(() => {
      preloader.classList.add("done");
      document.body.classList.remove("no-scroll");
    }, reducedMotion ? 0 : 900);
  }

  function updateLiveBanner(loading) {
    if (!liveBanner) return;
    if (loading) {
      liveBanner.className = "live-banner loading";
      liveBanner.innerHTML = `<span class="live-dot pulse"></span> Fetching live data from government dashboards…`;
      return;
    }
    if (!livePayload) {
      liveBanner.className = "live-banner offline";
      const local = ["localhost", "127.0.0.1"].includes(location.hostname);
      liveBanner.innerHTML = local
        ? `<span class="live-dot"></span> Live scraper unavailable — showing static values. Run <code>python server/app.py</code> and open via <code>http://localhost:8080</code>`
        : `<span class="live-dot"></span> Showing sourced snapshot values (live government dashboards not connected on this host).`;
      return;
    }
    const s = livePayload.summary;
    const time = new Date(livePayload.fetchedAt).toLocaleString("en-IN", {
      dateStyle: "medium",
      timeStyle: "short"
    });
    liveBanner.className = "live-banner ok";
    liveBanner.innerHTML = `
      <span class="live-dot"></span>
      <strong>${s.ok}/${s.total}</strong> live sources updated · ${time}
      <button type="button" id="live-refresh-inline" class="live-refresh-btn">↻ Refresh</button>
    `;
    document.getElementById("live-refresh-inline")?.addEventListener("click", () => {
      liveAttempts = 0;
      fetchLiveData(true);
    });
  }

  let liveAttempts = 0;

  async function fetchLiveData(forceRefresh) {
    updateLiveBanner(true);
    try {
      const url = forceRefresh ? "/api/live-data?refresh=1" : "/api/live-data";
      const resp = await fetch(url, { cache: "no-store" });
      if (!resp.ok) throw new Error(`HTTP ${resp.status}`);
      const payload = await resp.json();
      const warming = payload.status === "warming" || payload.refreshing;
      if (warming && liveAttempts < 20) {
        liveAttempts += 1;
        if (payload.sources && Object.keys(payload.sources).length) {
          livePayload = payload;
          panelEl.innerHTML = renderPanel(activeIndex);
          observeCards();
        }
        setTimeout(() => fetchLiveData(false), 2000);
        return;
      }
      liveAttempts = 0;
      livePayload = payload.status === "warming" ? null : payload;
      updateLiveBanner(false);
      panelEl.innerHTML = renderPanel(activeIndex);
      observeCards();
    } catch (err) {
      livePayload = null;
      liveAttempts = 0;
      updateLiveBanner(false);
      console.warn("Live data fetch failed:", err);
    }
  }

  function init() {
    renderHeroStats();
    buildTabs();
    panelEl.innerHTML = renderPanel(0);
    observeCards();
    observeChain();
    initCursorGlow();
    initCardTilt();
    dismissPreloader();
    fetchLiveData();
  }

  if (document.readyState === "loading") {
    document.addEventListener("DOMContentLoaded", init);
  } else {
    init();
  }
})();
