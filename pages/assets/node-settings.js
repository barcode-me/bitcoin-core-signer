/* The data directory choice at the top of the pages that run bitcoin-cli: the default, a remembered path, or a new one.
   The scripts read #datadir, which this keeps in step with the choice. Paths are remembered in this browser only. */
(() => {
  const storageKey = 'bitcoin-core-signer.datadirs';
  const maxPaths = 10;
  const choice = document.querySelector('#datadir-choice');
  const input = document.querySelector('#datadir');
  if (!choice || !input) return;

  // Storage can be missing or blocked, for example in a private window, so the page works without it.
  function loadPaths() {
    try {
      const paths = JSON.parse(localStorage.getItem(storageKey) ?? '[]');
      return Array.isArray(paths) ? paths.filter(path => typeof path === 'string' && path) : [];
    } catch {
      return [];
    }
  }
  function savePaths(paths) {
    try { localStorage.setItem(storageKey, JSON.stringify(paths)); } catch { /* Not remembered, but still used. */ }
  }

  function option(kind, label, value = '') {
    const item = document.createElement('option');
    item.dataset.kind = kind; item.value = value; item.textContent = label;
    return item;
  }
  // Default, the remembered paths (most recent first), then New path. Selects selectedPath when given.
  function render(selectedPath) {
    const paths = loadPaths();
    choice.replaceChildren(
      option('default', "Default (Bitcoin Core's own)"),
      ...paths.map(path => option('saved', path, path)),
      option('new', 'New path…'),
    );
    const saved = [...choice.options].find(item => item.dataset.kind === 'saved' && item.value === selectedPath);
    if (saved) saved.selected = true;
    else if (selectedPath) choice.options[choice.options.length - 1].selected = true;
    sync();
  }

  // The input is only shown for a new path. Otherwise it holds the chosen path, or nothing for the default.
  function sync() {
    const kind = choice.selectedOptions[0].dataset.kind;
    input.hidden = kind !== 'new';
    if (kind !== 'new') input.value = choice.value;
  }

  choice.addEventListener('change', () => {
    const isNew = choice.selectedOptions[0].dataset.kind === 'new';
    if (isNew) input.value = '';
    sync();
    if (isNew) input.focus();
  });

  // Called after a script ran successfully with this path, so only paths that worked are remembered.
  function remember(path) {
    path = path.trim();
    if (!path) return;
    savePaths([path, ...loadPaths().filter(saved => saved !== path)].slice(0, maxPaths));
    render(path);
  }

  // Start with the most recently used path.
  render(loadPaths()[0] ?? '');
  globalThis.NodeSettings = { remember };
})();
