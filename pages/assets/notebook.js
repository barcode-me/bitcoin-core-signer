/* Shared by the guide pages that run Python through the local server in python/server.py. Requests only go to localhost. */
(() => {
  const root = document.querySelector('[data-server]');
  const server = root.dataset.server;
  // The token printed by the server, pasted at the top of the page. Every request sends it.
  const tokenInput = document.querySelector('#server-token');
  const headers = (extra = {}) => ({ ...extra, 'X-Signer-Token': tokenInput?.value.trim() ?? '' });
  document.querySelector('#show-server-token')?.addEventListener('change', event => {
    tokenInput.type = event.target.checked ? 'text' : 'password';
  });
  // A page may show the server status in more than one place, such as two parts that each need the server.
  const setServerStatus = text => document.querySelectorAll('.server-status').forEach(status => { status.textContent = text; });

  // Opened from a file: offer the same page on localhost:8000, served from the project folder.
  // data-home is the site's index.html, so its folder (build) and everything after it is the path.
  if (location.protocol === 'file:' && root.dataset.home) {
    const siteRoot = new URL('.', new URL(root.dataset.home, location.href)).href;
    if (location.href.startsWith(siteRoot)) {
      const banner = document.createElement('div');
      banner.className = 'file-banner';
      banner.setAttribute('role', 'note');
      const text = document.createElement('p');
      const command = document.createElement('code');
      command.textContent = 'python3 -m http.server 8000';
      text.append('This page is open from a file, so it cannot talk to the local server. In a terminal, from the project folder, run ', command, ', then open it on localhost.');
      const link = document.createElement('a');
      link.className = 'open-localhost';
      const buildFolder = siteRoot.split('/').at(-2);
      link.href = new URL(`${buildFolder}/${location.href.slice(siteRoot.length)}`, 'http://localhost:8000/').href;
      link.textContent = 'Open this page on localhost:8000';
      banner.append(text, link);
      root.prepend(banner);
    }
  }
  // A page opened from a file can never reach the server, because the server only answers http://localhost:8000.
  const notRunning = location.protocol === 'file:'
    ? 'Cannot reach the local server: this page was opened from a file (file://). From the project folder, serve it with python3 -m http.server 8000 and open http://localhost:8000/build/ instead, or copy the code and run it yourself.'
    : 'Cannot reach the local server. Start it with python3 python/server.py, and make sure this page is open at http://localhost:8000 (not file://), or copy the code and run it yourself.';

  async function checkServer() {
    try {
      const response = await fetch(`${server}/health`, { headers: headers(), cache: 'no-store' });
      if (!response.ok) {
        const body = await response.json().catch(() => ({}));
        setServerStatus(`The local server refused this page: ${body.error ?? response.status}`);
        return;
      }
      setServerStatus('Local server is running.');
    } catch {
      setServerStatus(notRunning);
    }
  }
  checkServer();
  tokenInput?.addEventListener('input', checkServer);

  async function copyText(text, status, label = 'Copied.') {
    try {
      await navigator.clipboard.writeText(text);
    } catch {
      // Clipboard API needs a secure context; fall back to selecting a temporary field.
      const field = document.createElement('textarea');
      field.value = text; field.setAttribute('readonly', '');
      field.style.position = 'fixed'; field.style.opacity = '0';
      document.body.append(field); field.select();
      const copied = document.execCommand('copy');
      field.remove();
      if (!copied) { status.textContent = 'Copy failed. Select the text and copy it manually.'; return; }
    }
    status.textContent = label;
    setTimeout(() => { if (status.textContent === label) status.textContent = ''; }, 2000);
  }

  // Runs a script listed in python/server.py and returns its result, or throws with the message to show.
  async function runScript(script, inputs) {
    let response;
    try {
      response = await fetch(`${server}/run`, {
        method: 'POST',
        headers: headers({ 'Content-Type': 'application/json' }),
        cache: 'no-store',
        body: JSON.stringify({ script, inputs }),
      });
    } catch {
      setServerStatus(notRunning);
      throw new Error(notRunning);
    }
    setServerStatus('Local server is running.');
    const body = await response.json().catch(() => ({}));
    if (!response.ok) throw new Error(body.error ?? `Server returned ${response.status}`);
    // A data directory that worked is offered again next time.
    if (inputs.datadir) globalThis.NodeSettings?.remember(inputs.datadir);
    return body.result;
  }

  let codeBlocks = 0;
  // A cell is a code block with Run and Copy buttons and an output area, like a notebook.
  // collect() returns the script's inputs, show(value) renders its result as text.
  function setupCell(cell, { collect, show, clear = () => {} }) {
    const runButton = cell.querySelector('[data-action=run]');
    const status = cell.querySelector('.run-status');
    const output = cell.querySelector('.notebook-output');
    const result = cell.querySelector('.result');
    const source = cell.querySelector('.code-block code').textContent;

    // Show 3 lines of the code until expanded. Copy code still copies all of it.
    const codeBlock = cell.querySelector('.code-block');
    const codeBox = codeBlock.querySelector('pre');
    const lineCount = source.split('\n').length;
    const toggle = document.createElement('button');
    toggle.type = 'button'; toggle.dataset.action = 'toggle-code';
    codeBox.id ||= `code-${++codeBlocks}`;
    toggle.setAttribute('aria-controls', codeBox.id);
    function setCollapsed(collapsed) {
      codeBlock.classList.toggle('is-collapsed', collapsed);
      toggle.setAttribute('aria-expanded', String(!collapsed));
      toggle.textContent = collapsed ? `Show all ${lineCount} lines` : 'Show less';
      if (collapsed) codeBox.scrollTop = 0;
    }
    toggle.addEventListener('click', () => setCollapsed(!codeBlock.classList.contains('is-collapsed')));
    cell.querySelector('[data-action=copy-code]').before(toggle);
    setCollapsed(true);

    function clearResult() { output.hidden = true; result.textContent = ''; result.classList.remove('is-error'); clear(); }
    function showResult(text, isError) {
      result.textContent = text; result.classList.toggle('is-error', isError); output.hidden = false;
    }

    runButton.addEventListener('click', async () => {
      clearResult();
      runButton.disabled = true;
      status.textContent = 'Running…';
      try {
        let inputs;
        try { inputs = collect(); } catch (error) { return showResult(error.message, true); }
        let result;
        try { result = await runScript(cell.dataset.script, inputs); } catch (error) { return showResult(error.message, true); }
        showResult(show(result), false);
      } finally {
        status.textContent = '';
        runButton.disabled = false;
      }
    });
    cell.querySelector('[data-action=copy-code]').addEventListener('click', () => copyText(source, status));
    cell.querySelector('[data-action=copy-result]')?.addEventListener('click', () => copyText(result.textContent, status, 'Copied.'));
    return clearResult;
  }

  // Any edit makes the previous output stale, and the output holds secrets.
  function clearOnEdit(form, clearResult) {
    form.addEventListener('input', clearResult);
    form.addEventListener('change', clearResult);
  }

  globalThis.Notebook = { setupCell, clearOnEdit, copyText, runScript };
})();
