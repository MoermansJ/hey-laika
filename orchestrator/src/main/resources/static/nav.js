/**
 * Shared collapsible sidebar for the sub-pages (Behavior Lab, Control
 * Panel, Sequence Builder). Injects its own markup and styles so each
 * page only needs <script src="nav.js" defer></script>. The console
 * (index.html) keeps its richer sidebar and shares the collapse state
 * via the same localStorage key.
 */
(function () {
  // Mirrors the console sidebar. Robots are injected dynamically from the
  // fleet API; hash destinations resolve via the console's router on load.
  // (Control Panel lives as a tab on the robot page; the Sequence Builder
  // is unlisted pending its rebirth as a behavior builder.)
  // Restructured 2026-09-01: system pages became per-robot tabs on the
  // Robot Detail page; the sidebar is Dashboard + robots only, no emojis.
  const PAGES = [
    { href: "index.html#dashboard", label: "Dashboard" },
    { sep: "Robots" },
    { robots: true },
  ];
  const KEY = "heyLaikaNavCollapsed";
  const current = (location.pathname.split("/").pop() || "index.html");
  if (current === "index.html" || current === "") return;
  // Embedded mode (iframe inside the robot page's Control tab): no sidebar.
  if (new URLSearchParams(location.search).has("embedded")) return;

  const css = `
    :root { --hlnav-w: 188px; --hlnav-w-collapsed: 52px; }
    body { padding-left: var(--hlnav-w); transition: padding-left 0.18s ease; }
    body.hl-nav-collapsed { padding-left: var(--hlnav-w-collapsed); }
    .hl-nav { position: fixed; top: 0; left: 0; bottom: 0; z-index: 50;
      width: var(--hlnav-w); box-sizing: border-box; overflow: hidden;
      display: flex; flex-direction: column; gap: 0.15rem; padding: 0.6rem 0.5rem;
      background: #2c3e50; border-right: 1px solid rgba(255,255,255,0.12);
      transition: width 0.18s ease; }
    body.hl-nav-collapsed .hl-nav { width: var(--hlnav-w-collapsed); }
    .hl-nav a, .hl-nav button { display: flex; align-items: center; gap: 0.55rem;
      padding: 0.45rem 0.55rem; border-radius: 8px; border: none; width: 100%;
      background: none; color: #cfd5e1; text-decoration: none; font: inherit;
      font-size: 0.85rem; cursor: pointer; white-space: nowrap; text-align: left; }
    .hl-nav a:hover, .hl-nav button:hover { background: rgba(127,127,127,0.15); }
    .hl-nav a.current { background: rgba(127,127,127,0.22); color: #fff; }
    .hl-nav .hl-icon { font-size: 1.05rem; line-height: 1; flex: 0 0 auto; }
    .hl-nav .hl-label { overflow: hidden; text-overflow: ellipsis;
      opacity: 1; transition: opacity 0.12s ease; }
    body.hl-nav-collapsed .hl-nav .hl-label { opacity: 0; }
    .hl-nav .hl-toggle { margin-bottom: 0.4rem; color: #8b93a5; }
    .hl-nav .hl-sep { font-size: 0.62rem; text-transform: uppercase;
      letter-spacing: 0.06em; color: rgba(255,255,255,0.4);
      padding: 0.55rem 0.55rem 0.15rem; white-space: nowrap; }
    body.hl-nav-collapsed .hl-nav .hl-sep { visibility: hidden; height: 0.4rem;
      padding: 0.2rem 0; }
  `;
  const style = document.createElement("style");
  style.textContent = css;
  document.head.appendChild(style);

  const linkHtml = (p) =>
    `<a href="${p.href}" title="${p.label}"` +
    `${p.href === current ? ' class="current"' : ""}>` +
    `<span class="hl-label">${p.label}</span></a>`;

  const nav = document.createElement("nav");
  nav.className = "hl-nav";
  nav.innerHTML =
    `<button class="hl-toggle" title="Collapse navigation">` +
    `<span class="hl-label">Collapse</span></button>` +
    PAGES.map((p) => {
      if (p.sep) return `<div class="hl-sep">${p.sep}</div>`;
      if (p.robots) return `<div class="hl-robots"></div>`;
      return linkHtml(p);
    }).join("");
  document.body.prepend(nav);

  fetch("/api/fleet/robots")
    .then((res) => res.json())
    .then((robots) => {
      nav.querySelector(".hl-robots").innerHTML = robots.map((r) =>
        linkHtml({
          href: `index.html#robot/${encodeURIComponent(r.robotId)}`,
          label: r.name,
        })).join("");
    })
    .catch(() => { /* fleet API unreachable; static links still work */ });

  function apply(collapsed) {
    document.body.classList.toggle("hl-nav-collapsed", collapsed);
  }
  apply(localStorage.getItem(KEY) === "1");
  nav.querySelector(".hl-toggle").addEventListener("click", () => {
    const collapsed = !document.body.classList.contains("hl-nav-collapsed");
    localStorage.setItem(KEY, collapsed ? "1" : "0");
    apply(collapsed);
  });
})();
