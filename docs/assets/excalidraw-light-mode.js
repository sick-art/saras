(() => {
  const patch = (el) => {
    if (!el || el.__saras_light_forced) return;
    if (!el.theme || typeof el.theme.applyTheme !== "function") {
      requestAnimationFrame(() => patch(el));
      return;
    }
    el.__saras_light_forced = true;
    el.theme.applyTheme = function (t) {
      t.appState = t.appState || {};
      t.appState.exportWithDarkMode = false;
      t.appState.viewBackgroundColor = "#ffffff";
      t.exportPadding = 20;
      t.appState.exportEmbedScene = true;
      return t;
    };
    if (el.theme.handler) {
      try {
        Object.defineProperty(el.theme.handler, "mode", {
          configurable: true,
          get: () => "light",
          set: () => {},
        });
      } catch (_) {}
    }
    if (typeof el.connectedCallback === "function" && el.isConnected) {
      el.connectedCallback();
    }
  };

  const scan = (root) => {
    (root || document).querySelectorAll("excalidraw-renderer").forEach(patch);
  };

  const start = () => {
    scan(document);
    new MutationObserver((muts) => {
      for (const m of muts) {
        for (const node of m.addedNodes) {
          if (!(node instanceof Element)) continue;
          if (node.tagName === "EXCALIDRAW-RENDERER") patch(node);
          else scan(node);
        }
      }
    }).observe(document.documentElement, { childList: true, subtree: true });
  };

  if (document.readyState === "loading") {
    document.addEventListener("DOMContentLoaded", start);
  } else {
    start();
  }
})();
