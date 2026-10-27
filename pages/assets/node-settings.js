/* The data directory choice at the top of the pages that run bitcoin-cli: the default, a remembered path, or a new one.
   The scripts read #datadir, which this keeps in step with the choice. Paths are remembered in this browser only, as soon as they are typed. */
(() => {
  const storageKey = 'bitcoin-core-signer.datadirs';
  // The path chosen last, or '' for the default, so a reload shows the same choice.
  const selectedKey = 'bitcoin-core-signer.datadir';
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
  function loadSelected() {
    try { return localStorage.getItem(selectedKey); } catch { return null; }
  }
  function saveSelected(path) {
    try { localStorage.setItem(selectedKey, path); } catch { /* Not remembered, but still used. */ }
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

  // The new path being typed. Each keystroke replaces it in the list, so only the whole path is kept.
  let typing = null;

  choice.addEventListener('change', () => {
    const isNew = choice.selectedOptions[0].dataset.kind === 'new';
    typing = null;
    if (isNew) input.value = '';
    sync();
    if (isNew) input.focus();
    else saveSelected(choice.value);
  });

  // Saved as soon as it is typed, so a reload keeps it. The list is not redrawn, which would move the focus.
  input.addEventListener('input', () => {
    const path = input.value.trim();
    const others = loadPaths().filter(saved => saved !== typing && saved !== path);
    savePaths(path ? [path, ...others].slice(0, maxPaths) : others);
    saveSelected(path);
    typing = path || null;
  });

  // Called after a script ran successfully with this path, which moves it to the top of the list.
  function remember(path) {
    path = path.trim();
    if (!path) return;
    typing = null;
    savePaths([path, ...loadPaths().filter(saved => saved !== path)].slice(0, maxPaths));
    saveSelected(path);
    render(path);
  }

  // Start with the last choice, or the most recently used path.
  render(loadSelected() ?? loadPaths()[0] ?? '');
  globalThis.NodeSettings = { remember };
})();
