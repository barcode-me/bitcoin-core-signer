/* Runs the Python shown on the page through the local server in python/server.py. Requests only go to localhost. */
(() => {
  const server = document.querySelector('[data-server]').dataset.server;
  const serverStatus = document.querySelector('#server-status');
  const notRunning = 'Cannot reach the local server. Start it with python3 python/server.py, or copy the code and run it yourself.';
  const choice = (form, name) => form.querySelector(`input[name=${name}]:checked`).value;

  async function checkServer() {
    try {
      const response = await fetch(`${server}/health`, { cache: 'no-store' });
      if (!response.ok) {
        const body = await response.json().catch(() => ({}));
        serverStatus.textContent = `The local server refused this page: ${body.error ?? response.status}`;
        return;
      }
      serverStatus.textContent = 'Local server is running.';
    } catch {
      serverStatus.textContent = notRunning;
    }
  }
  checkServer();

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

  // A cell is a code block with Run and Copy buttons and an output area, like a notebook.
  // collect() returns the script's inputs, show(value) renders its result as text.
  function setupCell(cell, { collect, show, clear = () => {} }) {
    const runButton = cell.querySelector('[data-action=run]');
    const status = cell.querySelector('.run-status');
    const output = cell.querySelector('.notebook-output');
    const result = cell.querySelector('.result');
    const source = cell.querySelector('.code-block code').textContent;

    function clearResult() { output.hidden = true; result.textContent = ''; result.classList.remove('is-error'); clear(); }
    function showResult(text, isError) {
      result.textContent = text; result.classList.toggle('is-error', isError); output.hidden = false;
    }

    runButton.addEventListener('click', async () => {
      clearResult();
      runButton.disabled = true;
      status.textContent = 'Running…';
      try {
        let response;
        try {
          response = await fetch(`${server}/run`, {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            cache: 'no-store',
            body: JSON.stringify({ script: cell.dataset.script, inputs: collect() }),
          });
        } catch {
          serverStatus.textContent = notRunning;
          return showResult(notRunning, true);
        }
        serverStatus.textContent = 'Local server is running.';
        const body = await response.json().catch(() => ({}));
        if (response.ok) showResult(show(body.result), false);
        else showResult(body.error ?? `Server returned ${response.status}`, true);
      } finally {
        status.textContent = '';
        runButton.disabled = false;
      }
    });
    cell.querySelector('[data-action=copy-code]').addEventListener('click', () => copyText(source, status));
    cell.querySelector('[data-action=copy-result]')?.addEventListener('click', () => copyText(result.textContent, status, 'Copied import command.'));
    return clearResult;
  }

  // Any edit makes the previous output stale, and the output holds secrets.
  function clearOnEdit(form, clearResult) {
    form.addEventListener('input', clearResult);
    form.addEventListener('change', clearResult);
  }

  // Part 1: encrypted backup -> seed phrase
  const decryptForm = document.querySelector('#decrypt-form');
  const backup = document.querySelector('#backup');
  const otp = document.querySelector('#otp');
  const sameAsPassphrase = document.querySelector('#same-as-passphrase');
  const passphrase = document.querySelector('#passphrase');
  const mnemonic = document.querySelector('#mnemonic');

  // Part 2: seed phrase + passphrase -> Bitcoin Core descriptors
  const deriveForm = document.querySelector('#derive-form');
  const bip39Passphrase = document.querySelector('#bip39-passphrase');
  const sameBip39Passphrase = document.querySelector('#same-bip39-passphrase');
  const wallet = document.querySelector('#wallet');
  const deriveCell = document.querySelector('[data-script=convert-bip39-to-core]');
  const fingerprints = deriveCell.querySelector('.fingerprints');
  const fingerprintNote = deriveCell.querySelector('.fingerprint-note');
  const resultActions = deriveCell.querySelector('.result-actions');

  const clearDerive = setupCell(deriveCell, {
    collect: () => ({
      mnemonic: mnemonic.value,
      passphrase: sameBip39Passphrase.checked ? passphrase.value : bip39Passphrase.value,
      wallet: wallet.value,
      script_types: [...deriveForm.querySelectorAll('input[name=script-type]:checked')].map(input => input.value),
    }),
    show: derived => {
      fingerprints.querySelector('[data-field=fingerprint]').textContent = derived.fingerprint;
      fingerprints.querySelector('[data-field=fingerprint-no-passphrase]').textContent = derived.fingerprint_no_passphrase;
      fingerprints.hidden = fingerprintNote.hidden = resultActions.hidden = false;
      return derived.command;
    },
    clear: () => { fingerprints.hidden = fingerprintNote.hidden = resultActions.hidden = true; },
  });
  clearOnEdit(deriveForm, clearDerive);
  // The passphrase from Part 1 is used live while "Same as" is checked.
  passphrase.addEventListener('input', () => { if (sameBip39Passphrase.checked) clearDerive(); });

  const clearDecrypt = setupCell(document.querySelector('[data-script=decrypt-backup-to-bip39]'), {
    collect: () => ({
      backup: backup.value, encoding: choice(decryptForm, 'encoding'), words: Number(choice(decryptForm, 'words')),
      passphrase: passphrase.value, ...(sameAsPassphrase.checked ? {} : { otp: otp.value }),
    }),
    show: phrase => {
      // Hand the seed phrase to Part 2.
      mnemonic.value = phrase; clearDerive();
      return `Mnemonic: ${phrase}`;
    },
  });
  clearOnEdit(decryptForm, clearDecrypt);

  sameAsPassphrase.addEventListener('change', () => {
    otp.disabled = sameAsPassphrase.checked;
    if (otp.disabled) otp.value = ''; else otp.focus();
  });
  sameBip39Passphrase.addEventListener('change', () => {
    bip39Passphrase.disabled = sameBip39Passphrase.checked;
    if (bip39Passphrase.disabled) bip39Passphrase.value = ''; else bip39Passphrase.focus();
  });
  document.querySelector('#show-secrets').addEventListener('change', event => {
    otp.type = passphrase.type = event.target.checked ? 'text' : 'password';
  });
  document.querySelector('#show-bip39-passphrase').addEventListener('change', event => {
    bip39Passphrase.type = event.target.checked ? 'text' : 'password';
  });
})();
