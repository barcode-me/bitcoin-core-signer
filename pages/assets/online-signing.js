/* Online device steps: choose the public descriptors and the address type used to create transactions. */
(() => {
  const types = [
    { key: 'legacy', name: 'Legacy (P2PKH)', prefix: 'pkh(' },
    { key: 'nested-segwit', name: 'Nested SegWit (P2SH-P2WPKH)', prefix: 'sh(wpkh(' },
    { key: 'native-segwit', name: 'Native SegWit (P2WPKH)', prefix: 'wpkh(' },
    { key: 'taproot', name: 'Taproot (P2TR)', prefix: 'tr(' },
  ];

  // Sorts descriptors into receive and change by address type. The branch is the 0 or 1 before /*.
  // A multipath descriptor, <0;1>, is both.
  function groupByType(descriptors) {
    const groups = {};
    for (const descriptor of descriptors) {
      const type = types.find(candidate => descriptor.startsWith(candidate.prefix));
      const branch = /\/(<0;1>|\d+)\/\*\)/.exec(descriptor)?.[1];
      if (!type || !branch) continue;
      const group = groups[type.key] ??= {};
      if (branch === '0' || branch === '<0;1>') group.receive ??= descriptor;
      if (branch === '1' || branch === '<0;1>') group.change ??= descriptor;
    }
    return groups;
  }

  // What later steps read to create a transaction: the descriptors of the one chosen address type.
  const state = globalThis.signerState = { descriptors: [], groups: {}, scriptType: null, receive: null, change: null };
  globalThis.OnlineSigner = { groupByType };
  if (typeof document === 'undefined') return;

  const { setupCell, clearOnEdit } = globalThis.Notebook;
  const sourceForm = document.querySelector('#source-form');
  const receivedPanel = document.querySelector('#source-received');
  const walletPanel = document.querySelector('#source-wallet');
  const typeGroup = document.querySelector('#script-type-group');
  const typeStatus = document.querySelector('#type-status');
  const typeRadios = [...document.querySelectorAll('input[name=script-type]')];
  const summary = document.querySelector('#selected-descriptors');
  const walletForm = document.querySelector('#wallet-form');
  const walletCell = document.querySelector('[data-script=list-public-descriptors]');

  let received = null;   // descriptors recovered from the typed SB58 lines
  let fromWallet = null; // descriptors listed from a Bitcoin Core wallet
  const source = () => sourceForm.querySelector('input[name=source]:checked').value;

  function publish() {
    const group = state.groups[state.scriptType] ?? {};
    state.receive = group.receive ?? null;
    state.change = group.change ?? null;
    document.dispatchEvent(new CustomEvent('signer-state', { detail: state }));
  }

  function renderType() {
    const chosen = typeRadios.find(radio => radio.checked)?.value ?? null;
    state.scriptType = chosen;
    publish();
    if (!chosen) {
      summary.hidden = true;
      typeStatus.textContent = state.descriptors.length ? 'Choose the address type to create transactions with.' : 'Load the public descriptors to choose an address type.';
      return;
    }
    const name = types.find(type => type.key === chosen).name;
    summary.textContent = `Address type: ${name}\nReceive: ${state.receive ?? '(not found)'}\nChange:  ${state.change ?? '(not found)'}`;
    summary.hidden = false;
    typeStatus.textContent = `Transactions will be created with ${name}.`;
  }

  // Use a new set of descriptors. Only the address types they contain can be chosen.
  function setDescriptors(descriptors) {
    state.descriptors = descriptors ?? [];
    state.groups = groupByType(state.descriptors);
    const available = types.filter(type => state.groups[type.key]?.receive);
    typeGroup.disabled = !available.length;
    for (const radio of typeRadios) {
      const isAvailable = available.some(type => type.key === radio.value);
      radio.disabled = !isAvailable;
      const label = radio.closest('label');
      label.title = isAvailable ? '' : 'These descriptors do not include this address type.';
      label.classList.toggle('is-unavailable', !isAvailable);
    }
    // Keep the choice if it is still possible. A single possible type is chosen for you.
    const keep = typeRadios.find(radio => radio.checked && !radio.disabled);
    typeRadios.forEach(radio => { radio.checked = false; });
    if (keep) keep.checked = true;
    else if (available.length === 1) typeRadios.find(radio => radio.value === available[0].key).checked = true;
    renderType();
    if (state.descriptors.length && !available.length) typeStatus.textContent = 'These descriptors have no receive descriptor of a supported address type.';
  }

  function apply() {
    const useWallet = source() === 'wallet';
    walletPanel.hidden = !useWallet;
    receivedPanel.hidden = useWallet;
    setDescriptors(useWallet ? fromWallet : received);
  }

  // Tells the rest of the page which descriptors the typed lines recovered, or null when they no longer do.
  globalThis.SB58.setupEditor(document.querySelector('#descriptor-receiver'), {
    decode: bytes => globalThis.SB58.rebuildDescriptors(bytes),
    show: descriptors => ({
      text: descriptors.join('\n'),
      status: `Recovered ${descriptors.length} ${descriptors.length === 1 ? 'descriptor' : 'descriptors'}. The final checksum matches.`,
    }),
    onChange: descriptors => document.dispatchEvent(new CustomEvent('sb58-recovered', { detail: descriptors })),
  });
  document.addEventListener('sb58-recovered', event => {
    received = event.detail;
    if (source() === 'received') apply();
  });
  sourceForm.addEventListener('change', apply);
  typeRadios.forEach(radio => radio.addEventListener('change', renderType));

  const clearWallet = setupCell(walletCell, {
    collect: () => {
      const wallet = document.querySelector('#wallet-name').value.trim();
      if (!wallet) throw new Error('Enter the name of the wallet.');
      const datadir = document.querySelector('#datadir').value.trim();
      return { wallet, ...(datadir ? { datadir } : {}) };
    },
    show: listed => {
      fromWallet = listed.descriptors.map(item => item.desc);
      // Part 3 creates transactions with this wallet.
      document.querySelector('#psbt-wallet-name').value = listed.wallet;
      if (source() === 'wallet') apply();
      return `Loaded ${fromWallet.length} public ${fromWallet.length === 1 ? 'descriptor' : 'descriptors'} from wallet ${listed.wallet}.`;
    },
    clear: () => {
      if (fromWallet === null) return;
      fromWallet = null;
      if (source() === 'wallet') apply();
    },
  });
  clearOnEdit(walletForm, clearWallet);

  // Part 2: import the typed descriptors into a new watch-only wallet
  const importForm = document.querySelector('#import-form');
  const clearImport = setupCell(document.querySelector('[data-script=import-public-descriptors]'), {
    collect: () => {
      if (source() === 'wallet') throw new Error('These descriptors were loaded from a wallet in Bitcoin Core, which already has them. Nothing to import.');
      if (!received) throw new Error('Type the Super Base 58 lines in Part 1 first. Part 2 imports the descriptors they recover.');
      const wallet = document.querySelector('#import-wallet-name').value.trim();
      if (!wallet) throw new Error('Enter a name for the wallet.');
      const rescanSince = document.querySelector('#rescan-since').value;
      const datadir = document.querySelector('#datadir').value.trim();
      const createWallet = document.querySelector('#create-wallet').checked;
      return { wallet, descriptors: received, create_wallet: createWallet, network: document.querySelector('#network').value, ...(rescanSince ? { rescan_since: rescanSince } : {}), ...(datadir ? { datadir } : {}) };
    },
    show: imported => {
      const scanned = imported.rescan_since ? `Scanned the blockchain from ${imported.rescan_since}.` : 'No past transactions were looked for.';
      const action = imported.created ? 'Created watch-only wallet' : 'Imported into wallet';
      // Part 3 creates transactions with this wallet.
      document.querySelector('#psbt-wallet-name').value = imported.wallet;
      return `${action} ${imported.wallet}: ${imported.imported} public descriptors. ${scanned}\nBalance: ${imported.balance.toFixed(8)} BTC`;
    },
  });
  clearOnEdit(importForm, clearImport);
  // New descriptors make the import result stale.
  document.addEventListener('sb58-recovered', clearImport);

  // Part 3: create an unsigned transaction with the wallet and show it as SB58 lines for the offline device
  const psbtForm = document.querySelector('#psbt-form');
  const psbtWallet = document.querySelector('#psbt-wallet-name');
  const psbtCell = document.querySelector('[data-script=create-psbt]');
  const psbtViewer = globalThis.SB58Viewer.setupViewer(psbtCell.querySelector('.sb58-viewer'));
  const sats = value => `${value.toLocaleString('en-US')} sats (${(value / 1e8).toFixed(8)} BTC)`;
  const clearPsbt = setupCell(psbtCell, {
    collect: () => {
      if (!state.scriptType) throw new Error('Choose the address type in Part 1 first. Change goes back to the wallet with that type.');
      const wallet = psbtWallet.value.trim();
      if (!wallet) throw new Error('Enter the name of the wallet.');
      const address = document.querySelector('#destination').value.trim();
      if (!address) throw new Error('Enter the destination address.');
      const amount = document.querySelector('#amount').value.trim();
      if (!amount) throw new Error('Enter the amount to send.');
      const feeRate = document.querySelector('#fee-rate').value.trim();
      const datadir = document.querySelector('#datadir').value.trim();
      return {
        wallet, address, amount,
        unit: psbtForm.querySelector('input[name=unit]:checked').value,
        subtract_fee: document.querySelector('#subtract-fee').checked,
        change_type: state.scriptType,
        ...(feeRate ? { fee_rate: feeRate } : {}),
        ...(datadir ? { datadir } : {}),
      };
    },
    show: created => {
      psbtViewer.show([...created.lines, created.final_checksum]);
      // Part 4 adds the signatures to this transaction.
      document.querySelector('#unsigned-psbt').value = created.psbt;
      document.querySelector('#unsigned-form').dispatchEvent(new Event('input'));
      const received = created.subtract_fee ? created.amount_sats - created.fee_sats : created.amount_sats;
      return [
        `To:       ${created.address}`,
        `Receives: ${sats(received)}`,
        `Fee:      ${sats(created.fee_sats)}${created.subtract_fee ? ', taken from the amount' : ', paid on top'}`,
        `Change:   ${created.has_change ? 'yes, back to this wallet' : 'none'}`,
        '',
        `${created.lines.length + 1} lines: ${created.lines.length} data lines and the final checksum. They encode the ${created.bytes.toLocaleString('en-US')}-byte PSBT (${created.base58_chars.toLocaleString('en-US')} Base58 characters).`,
        '',
        'Unsigned PSBT (base64). Part 4 needs it to add the signatures. Save it if you might reload this page before then:',
        created.psbt,
      ].join('\n');
    },
    clear: psbtViewer.clear,
  });
  clearOnEdit(psbtForm, clearPsbt);
  // Change goes to the address type chosen in Part 1, so a new choice makes the transaction stale.
  document.addEventListener('signer-state', clearPsbt);
  // Part 4: SB58 lines from the offline device -> signatures -> added to the Part 3 PSBT -> its details -> sent with Bitcoin Core
  const unsignedPsbt = document.querySelector('#unsigned-psbt');
  const addCell = document.querySelector('[data-script=add-signatures]');
  const signedDetailsCell = document.querySelector('#signed-details');
  const sendCell = document.querySelector('[data-script=send-psbt]');
  const confirmSend = document.querySelector('#confirm-send');
  // 4 bytes of the transaction ID, then 64 bytes per input, as in python/sign-psbt.py.
  const txidPrefixLength = 4;
  const signatureLength = 64;
  const btc = value => `${(value / 1e8).toFixed(8)} BTC (${value.toLocaleString('en-US')} sats)`;
  let signatures = null; // hex, from the typed SB58 lines
  let signedPsbt = null;  // the Part 3 PSBT with the signatures added, finalized
  const clearSignedDetails = setupCell(signedDetailsCell, {
    collect: () => {
      if (!signedPsbt) throw new Error('Type the SB58 lines from the offline device above and add the signatures first.');
      const wallet = psbtWallet.value.trim();
      const datadir = document.querySelector('#datadir').value.trim();
      return { psbt: signedPsbt, ...(wallet ? { wallet } : {}), ...(datadir ? { datadir } : {}) };
    },
    show: decoded => {
      const lines = decoded.outputs.map(output => {
        const note = output.is_mine ? `  (change, back to wallet ${decoded.wallet})` : '';
        return `  ${btc(output.amount_sats)} to ${output.address ?? '(an output without an address)'}${note}`;
      });
      const sent = decoded.outputs.filter(output => !output.is_mine).reduce((sum, output) => sum + output.amount_sats, 0);
      const fee = decoded.fee_sats === null ? 'unknown, the PSBT does not include the coins it spends' : `${btc(decoded.fee_sats)}, ${decoded.fee_rate} sat/vB`;
      return [
        'Outputs:', ...lines, '',
        decoded.wallet ? `Sent out of the wallet: ${btc(sent)}` : 'Enter the wallet name in Part 3 to tell the change apart.',
        `Fee: ${fee}`,
        `Inputs: ${decoded.inputs}`,
        `Status: ${decoded.status}`,
        `Transaction ID: ${decoded.txid}`,
      ].join('\n');
    },
  });
  const clearSend = setupCell(sendCell, {
    collect: () => {
      if (!signedPsbt) throw new Error('Type the SB58 lines from the offline device above and add the signatures first.');
      if (!confirmSend.checked) throw new Error('Check the transaction details, then tick the box above to confirm. Nothing was sent.');
      const datadir = document.querySelector('#datadir').value.trim();
      return { psbt: signedPsbt, ...(datadir ? { datadir } : {}) };
    },
    show: sent => {
      // One confirmation sends once.
      confirmSend.checked = false;
      return `Sent. Transaction ID: ${sent.txid}\nBitcoin Core will show it in the wallet as unconfirmed until it is mined into a block.`;
    },
  });
  const clearAdd = setupCell(addCell, {
    collect: () => {
      const psbt = unsignedPsbt.value.trim();
      if (!psbt) throw new Error('Create the transaction in Part 3, or paste the unsigned PSBT it showed above.');
      if (!signatures) throw new Error('Type the SB58 lines from the offline device above first.');
      const datadir = document.querySelector('#datadir').value.trim();
      return { psbt, signatures, ...(datadir ? { datadir } : {}) };
    },
    show: added => {
      signedPsbt = added.psbt;
      // Show the details as soon as the signatures are added.
      signedDetailsCell.querySelector('[data-action=run]').click();
      return `Added the signatures to transaction ${added.txid}. Bitcoin Core checked them with testmempoolaccept: it would accept this transaction.\n\nSigned PSBT (base64):\n${added.psbt}`;
    },
    clear: () => {
      signedPsbt = null;
      confirmSend.checked = false;
      clearSignedDetails();
      clearSend();
    },
  });
  // Signatures only fit the unsigned transaction they were made for.
  clearOnEdit(document.querySelector('#unsigned-form'), clearAdd);

  globalThis.SB58.setupEditor(document.querySelector('#signed-receiver'), {
    decode: bytes => {
      const count = (bytes.length - txidPrefixLength) / signatureLength;
      if (!Number.isInteger(count) || count < 1) throw new Error('The lines check out but do not hold signatures. Check that these are the lines shown after signing on the offline device.');
      return [...bytes].map(byte => byte.toString(16).padStart(2, '0')).join('');
    },
    show: hex => {
      const count = (hex.length / 2 - txidPrefixLength) / signatureLength;
      return { text: hex, status: `Received ${count} ${count === 1 ? 'signature' : 'signatures'}. The final checksum matches.` };
    },
    onChange: hex => {
      signatures = hex;
      if (hex) addCell.querySelector('[data-action=run]').click(); else clearAdd();
    },
  });

  // Every part runs bitcoin-cli with the data directory at the top, so a new one makes their results stale.
  clearOnEdit(document.querySelector('#datadir-form'), () => { clearWallet(); clearImport(); clearPsbt(); clearAdd(); });
  apply();
})();
