/* Lean flow: builds bitcoin-cli commands from what is typed on the page, to copy into a terminal.
   Step 5 turns the output of `bitcoin-cli listdescriptors` into the command that imports the public descriptors
   on the online device. Step 8 makes the walletcreatefundedpsbt command for a payment. Nothing is sent anywhere. */
(() => {
  // Single quotes keep the shell from touching the JSON; a quote inside is closed, escaped and reopened.
  const shellQuote = text => `'${text.replaceAll("'", `'\\''`)}'`;
  const shellWord = text => /^[\w.-]+$/.test(text) ? text : shellQuote(text);

  // Shows the command makeCommand returns in the output's code block, or the message it throws.
  // makeCommand returns null while there is nothing to show yet.
  function setupCommand(output, inputs, makeCommand) {
    if (!output) return;
    const error = output.querySelector('.lean-command-error');
    const command = output.querySelector('.lean-command');
    const code = command.querySelector('.code-block code');
    const status = command.querySelector('.run-status');

    function update() {
      status.textContent = '';
      try {
        const text = makeCommand();
        output.hidden = text === null;
        if (text === null) return;
        code.textContent = text;
        error.hidden = true;
        command.hidden = false;
      } catch (failure) {
        output.hidden = false;
        error.textContent = failure.message;
        error.hidden = false;
        command.hidden = true;
      }
    }
    for (const input of inputs) input.addEventListener('input', update);
    update();

    command.querySelector('[data-action=copy-result]').addEventListener('click', async () => {
      try {
        await navigator.clipboard.writeText(code.textContent);
        status.textContent = 'Copied.';
      } catch {
        status.textContent = 'Copy failed. Select the command and copy it manually.';
      }
    });
  }

  const listing = document.querySelector('#listdescriptors-output');
  setupCommand(document.querySelector('#lean-import-output'), [listing], () => {
    const text = listing.value.trim();
    if (!text) return null;
    let parsed;
    try {
      parsed = JSON.parse(text);
    } catch {
      throw new Error('This is not valid JSON. Paste the whole output of listdescriptors, from the first { to the last }.');
    }
    const { wallet_name: wallet, descriptors } = parsed ?? {};
    if (typeof wallet !== 'string' || !wallet || !Array.isArray(descriptors) || !descriptors.length) {
      throw new Error('Expected a wallet_name and a list of descriptors, as printed by listdescriptors.');
    }
    const requests = descriptors.map((descriptor, index) => {
      if (typeof descriptor?.desc !== 'string') throw new Error(`Descriptor ${index + 1} has no desc.`);
      // Extended private keys start with xprv (mainnet) or tprv (test networks).
      if (/[xt]prv/.test(descriptor.desc)) {
        throw new Error('This contains a private descriptor. Run listdescriptors without true, and never move private keys to the online device.');
      }
      const request = { desc: descriptor.desc, timestamp: descriptor.timestamp ?? 'now' };
      if ('active' in descriptor) request.active = descriptor.active;
      if ('internal' in descriptor) request.internal = descriptor.internal;
      if ('range' in descriptor) request.range = descriptor.range;
      // Keep handing out addresses from where this wallet stopped.
      if ('next_index' in descriptor || 'next' in descriptor) request.next_index = descriptor.next_index ?? descriptor.next;
      return request;
    });
    const json = `[\n${requests.map(request => `  ${JSON.stringify(request)}`).join(',\n')}\n]`;
    return `bitcoin-cli -rpcwallet=${shellWord(wallet)} importdescriptors ${shellQuote(json)}`;
  });

  // Same limits as python/online/create-psbt.py. Numbers are checked as text and written as typed,
  // so the amount is never rounded by a float.
  const wallet = document.querySelector('#psbt-wallet');
  const address = document.querySelector('#psbt-address');
  const amount = document.querySelector('#psbt-amount');
  const feeRate = document.querySelector('#psbt-fee-rate');
  setupCommand(document.querySelector('#lean-psbt-output'), [wallet, address, amount, feeRate], () => {
    const values = [wallet, address, amount, feeRate].map(input => input.value.trim());
    const [walletName, destination, btc, rate] = values;
    if (!destination || !btc) return null;
    if (!/^[A-Za-z0-9._-]+$/.test(walletName)) throw new Error('The wallet name may only contain letters, digits, dots, dashes and underscores.');
    if (!/^[A-Za-z0-9]{14,90}$/.test(destination)) throw new Error('The destination must be a Bitcoin address of letters and digits only.');
    if (!/^(0|[1-9]\d*)(\.\d{1,8})?$/.test(btc) || !(Number(btc) > 0) || Number(btc) > 21_000_000) {
      throw new Error('The amount must be in BTC, more than 0 and at most 21,000,000, with at most 8 decimals, for example 0.001.');
    }
    if (rate && (!/^(0|[1-9]\d*)(\.\d{1,3})?$/.test(rate) || !(Number(rate) > 0) || Number(rate) > 10_000)) {
      throw new Error('The fee rate must be in sat/vB, more than 0 and at most 10000, with at most 3 decimals.');
    }
    const outputs = `[{${JSON.stringify(destination)}: ${btc}}]`;
    // Without a fee rate Bitcoin Core estimates one.
    const options = rate ? ` options=${shellQuote(`{"fee_rate": ${rate}}`)}` : '';
    return `bitcoin-cli -rpcwallet=${walletName} -named walletcreatefundedpsbt outputs=${shellQuote(outputs)}${options} | jq -r '.psbt' > ~/Desktop/unsigned.psbt`;
  });
})();
