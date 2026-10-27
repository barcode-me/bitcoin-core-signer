/* Offline device steps: each part runs the Python shown on the page through the local server. */
(() => {
  const { setupCell, clearOnEdit } = globalThis.Notebook;
  const choice = (form, name) => form.querySelector(`input[name=${name}]:checked`).value;

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

  // Delete a wallet by the name entered in Part 2, in the data directory from Part 3
  const deleteCell = document.querySelector('[data-script=delete-wallet]');
  const confirmDelete = document.querySelector('#confirm-delete');
  const clearDelete = setupCell(deleteCell, {
    collect: () => {
      const name = wallet.value.trim();
      if (!name) throw new Error('Enter the wallet name in Part 2.');
      if (confirmDelete.value.trim() !== name) throw new Error(`Type ${name} in the box above to confirm. Nothing was deleted.`);
      const datadir = document.querySelector('#datadir').value.trim();
      return { wallet: name, confirm: confirmDelete.value.trim(), ...(datadir ? { datadir } : {}) };
    },
    show: deleted => {
      confirmDelete.value = '';
      // Part 3's output described this wallet, which is gone now.
      if (derived?.wallet === deleted.wallet) clearImport();
      return `Deleted wallet ${deleted.wallet}: removed ${deleted.path}`;
    },
  });
  clearOnEdit(document.querySelector('#delete-form'), clearDelete);
  // A different wallet name needs its own confirmation.
  wallet.addEventListener('input', () => { confirmDelete.value = ''; clearDelete(); });

  // Part 4: public descriptors -> Super Base 58 lines, shown one at a time
  const publicDescriptors = document.querySelector('#public-descriptors');
  const transferCell = document.querySelector('[data-script=descriptors-to-sb58]');
  const viewer = globalThis.SB58Viewer.setupViewer(transferCell.querySelector('.sb58-viewer'));

  const clearTransfer = setupCell(transferCell, {
    collect: () => {
      const descriptors = publicDescriptors.value.split('\n').map(line => line.trim()).filter(Boolean);
      if (!descriptors.length) throw new Error('Run Part 3 first, or paste the public descriptors above.');
      return { descriptors };
    },
    show: encoded => {
      viewer.show([...encoded.lines, encoded.final_checksum]);
      return `${encoded.lines.length + 1} lines: ${encoded.lines.length} data lines and the final checksum. They encode the master fingerprint and the xpubs of ${encoded.script_types.join(', ')}: ${encoded.bytes.toLocaleString('en-US')} bytes of data (${encoded.base58_chars.toLocaleString('en-US')} Base58 characters).`;
    },
    clear: viewer.clear,
  });
  clearOnEdit(document.querySelector('#transfer-form'), clearTransfer);

  // Part 3: import the Part 2 descriptors into a new Bitcoin Core wallet
  const importCell = document.querySelector('[data-script=import-descriptors]');
  const importWalletLabel = document.querySelector('[data-field=import-wallet]');
  const importActions = importCell.querySelector('.result-actions');
  let derived = null;
  // Part 3 uses exactly what Part 2 produced, so it is cleared with it.
  let clearImport = () => {};

  const clearDerive = setupCell(deriveCell, {
    collect: () => ({
      mnemonic: mnemonic.value,
      passphrase: sameBip39Passphrase.checked ? passphrase.value : bip39Passphrase.value,
      wallet: wallet.value,
      script_types: [...deriveForm.querySelectorAll('input[name=script-type]:checked')].map(input => input.value),
    }),
    show: result => {
      fingerprints.querySelector('[data-field=fingerprint]').textContent = result.fingerprint;
      fingerprints.querySelector('[data-field=fingerprint-no-passphrase]').textContent = result.fingerprint_no_passphrase;
      fingerprints.hidden = fingerprintNote.hidden = resultActions.hidden = false;
      derived = { wallet: wallet.value, requests: result.requests };
      importWalletLabel.textContent = derived.wallet;
      return result.command;
    },
    clear: () => { fingerprints.hidden = fingerprintNote.hidden = resultActions.hidden = true; derived = null; clearImport(); },
  });
  clearOnEdit(deriveForm, clearDerive);
  // The passphrase from Part 1 is used live while "Same as" is checked.
  passphrase.addEventListener('input', () => { if (sameBip39Passphrase.checked) clearDerive(); });

  clearImport = setupCell(importCell, {
    collect: () => {
      if (!derived) throw new Error('Run Part 2 first. Part 3 imports the descriptors it produces.');
      const datadir = document.querySelector('#datadir').value.trim();
      return { wallet: derived.wallet, requests: derived.requests, ...(datadir ? { datadir } : {}) };
    },
    show: imported => {
      importActions.hidden = false;
      publicDescriptors.value = imported.descriptors.map(item => item.desc).join('\n');
      clearTransfer();
      const lines = imported.descriptors.map(item => `${item.internal ? 'change ' : 'receive'}  ${item.desc}`);
      return `Created wallet ${imported.wallet} and imported the descriptors.\n\nPublic descriptors:\n${lines.join('\n')}`;
    },
    clear: () => { importActions.hidden = true; },
  });
  clearOnEdit(document.querySelector('#import-form'), clearImport);

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
