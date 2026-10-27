/* Runs the Python shown on the page through the local server in python/server.py. Requests only go to localhost. */
(() => {
  const form = document.querySelector('#decrypt-form');
  const backup = document.querySelector('#backup');
  const otp = document.querySelector('#otp');
  const sameAsPassphrase = document.querySelector('#same-as-passphrase');
  const passphrase = document.querySelector('#passphrase');
  const showSecrets = document.querySelector('#show-secrets');
  const runButton = document.querySelector('#run-script');
  const copyButton = document.querySelector('#copy-script');
  const status = document.querySelector('#run-status');
  const output = document.querySelector('#run-output');
  const result = document.querySelector('#run-result');
  const source = document.querySelector('.notebook-cell code').textContent;
  const choice = name => form.querySelector(`input[name=${name}]:checked`).value;

  function clearResult() { output.hidden = true; result.textContent = ''; result.classList.remove('is-error'); }
  function showResult(text, isError) {
    result.textContent = text; result.classList.toggle('is-error', isError); output.hidden = false;
  }
  const serverStatus = document.querySelector('#server-status');
  const notRunning = 'Cannot reach the local server. Start it with python3 python/server.py, or copy the code and run it yourself.';
  async function checkServer() {
    try {
      const response = await fetch(`${form.dataset.server}/health`, { cache: 'no-store' });
      if (!response.ok) {
        const body = await response.json().catch(() => ({}));
        serverStatus.textContent = `The local server refused this page: ${body.error ?? response.status}`;
        return false;
      }
      serverStatus.textContent = 'Local server is running.';
      return true;
    } catch {
      serverStatus.textContent = notRunning;
      return false;
    }
  }
  checkServer();

  sameAsPassphrase.addEventListener('change', () => {
    otp.disabled = sameAsPassphrase.checked;
    if (otp.disabled) otp.value = ''; else otp.focus();
  });
  showSecrets.addEventListener('change', () => {
    otp.type = passphrase.type = showSecrets.checked ? 'text' : 'password';
  });
  // Any edit makes the previous output stale, and it holds a seed phrase.
  form.addEventListener('input', clearResult);
  form.addEventListener('change', clearResult);

  runButton.addEventListener('click', async () => {
    clearResult();
    runButton.disabled = true;
    status.textContent = 'Running…';
    try {
      let response;
      try {
        response = await fetch(`${form.dataset.server}/run`, {
          method: 'POST',
          headers: { 'Content-Type': 'application/json' },
          cache: 'no-store',
          body: JSON.stringify({
            script: form.dataset.script,
            inputs: {
              backup: backup.value, encoding: choice('encoding'), words: Number(choice('words')),
              passphrase: passphrase.value, ...(sameAsPassphrase.checked ? {} : { otp: otp.value }),
            },
          }),
        });
      } catch {
        serverStatus.textContent = notRunning;
        return showResult(notRunning, true);
      }
      serverStatus.textContent = 'Local server is running.';
      const body = await response.json().catch(() => ({}));
      if (response.ok) showResult(`Mnemonic: ${body.result}`, false);
      else showResult(body.error ?? `Server returned ${response.status}`, true);
    } finally {
      status.textContent = '';
      runButton.disabled = false;
    }
  });

  copyButton.addEventListener('click', async () => {
    try {
      await navigator.clipboard.writeText(source);
    } catch {
      // Clipboard API needs a secure context; fall back to selecting a temporary field.
      const field = document.createElement('textarea');
      field.value = source; field.setAttribute('readonly', '');
      field.style.position = 'fixed'; field.style.opacity = '0';
      document.body.append(field); field.select();
      const copied = document.execCommand('copy');
      field.remove();
      if (!copied) { status.textContent = 'Copy failed. Select the code and copy it manually.'; return; }
    }
    status.textContent = 'Copied.';
    setTimeout(() => { if (status.textContent === 'Copied.') status.textContent = ''; }, 2000);
  });
})();
