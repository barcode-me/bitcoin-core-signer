/* Each transfer between the devices can use Super Base 58 lines or encrypted QR codes. QR codes are made by
   python/shared/qr-encode.py and scanned with the camera by python/shared/qr-scan.py, through the local server. */
(() => {
  const { runScript, copyText } = globalThis.Notebook;
  const passphraseInput = document.querySelector('#qr-passphrase');
  const passphrase = () => {
    if (!passphraseInput.value) throw new Error('Enter the QR passphrase at the top of the page first. Both devices must use the same one.');
    return passphraseInput.value;
  };
  // form is a transfer-mode form with sb58 and qr radios.
  const modeOf = form => form.querySelector('input[type=radio]:checked').value;
  const secondsPerCode = 1;

  document.querySelector('#show-qr-passphrase').addEventListener('change', event => {
    passphraseInput.type = event.target.checked ? 'text' : 'password';
  });

  // panel holds a .sb58-viewer and a .qr-viewer. kind is checked when decrypting, so QR codes of a PSBT cannot be read as signatures.
  function setupSender(form, panel, kind) {
    const sb58 = globalThis.SB58Viewer.setupViewer(panel.querySelector('.sb58-viewer'));
    const viewer = panel.querySelector('.qr-viewer');
    const image = viewer.querySelector('.qr-image');
    const progress = viewer.querySelector('.qr-progress');
    const status = viewer.querySelector('.qr-status');
    const playButton = viewer.querySelector('[data-action=qr-play]');
    let data = null; // { lines, hex } of the last result
    let images = [];
    let current = 0;
    let timer = null;
    let revision = 0;

    function select(index) {
      if (!images.length) return;
      current = (index + images.length) % images.length;
      image.src = images[current];
      image.alt = `QR code ${current + 1} of ${images.length}`;
      progress.textContent = `QR code ${current + 1} of ${images.length}`;
    }
    function pause() { clearInterval(timer); timer = null; playButton.textContent = 'Play'; }
    function play() {
      pause();
      if (images.length < 2) return;
      timer = setInterval(() => select(current + 1), secondsPerCode * 1000);
      playButton.textContent = 'Pause';
    }
    function hideQr(message = '') {
      pause();
      images = [];
      image.hidden = true; image.removeAttribute('src');
      progress.textContent = '';
      status.textContent = message;
      status.classList.toggle('is-error', Boolean(message));
      viewer.hidden = !message;
    }

    async function render() {
      const version = ++revision;
      hideQr(); sb58.clear();
      if (!data) return;
      if (modeOf(form) === 'sb58') return sb58.show(data.lines);
      viewer.hidden = false;
      progress.textContent = 'Encrypting and making the QR codes…';
      let encoded;
      try {
        encoded = await runScript('qr-encode', { data: data.hex, kind, passphrase: passphrase() });
      } catch (error) {
        if (version === revision) hideQr(error.message);
        return;
      }
      if (version !== revision) return;
      images = encoded.images;
      image.hidden = false;
      status.textContent = `${encoded.slices} QR ${encoded.slices === 1 ? 'code' : 'codes'} of up to 128 bytes each: ${encoded.bytes.toLocaleString('en-US')} bytes of data, ${encoded.encrypted_bytes.toLocaleString('en-US')} bytes encrypted.`;
      select(0);
      play();
    }

    viewer.querySelector('[data-action=qr-previous]').addEventListener('click', () => { pause(); select(current - 1); });
    viewer.querySelector('[data-action=qr-next]').addEventListener('click', () => { pause(); select(current + 1); });
    playButton.addEventListener('click', () => { if (timer) pause(); else play(); });
    viewer.addEventListener('keydown', event => {
      if (event.target !== viewer) return;
      if (event.key === 'ArrowRight') { pause(); select(current + 1); } else if (event.key === 'ArrowLeft') { pause(); select(current - 1); } else if (event.key === ' ') { if (timer) pause(); else play(); } else return;
      event.preventDefault();
    });
    form.addEventListener('change', render);
    // Codes made with the old passphrase cannot be read with the new one. They are made again once it is entered.
    passphraseInput.addEventListener('input', () => {
      if (!data || modeOf(form) !== 'qr') return;
      revision++;
      hideQr('The QR passphrase changed. Press Enter in it, or click elsewhere, to make the QR codes again.');
    });
    passphraseInput.addEventListener('change', () => { if (data && modeOf(form) === 'qr') render(); });

    return {
      // lines are the SB58 lines and the final checksum, hex the same data for QR codes.
      show(lines, hex) { data = { lines, hex }; render(); },
      clear() { data = null; revision++; hideQr(); sb58.clear(); },
    };
  }

  // panel holds a .sb58-receiver, the container for SB58.setupEditor, and a .qr-scanner.
  // decode, show and onChange are as for SB58.setupEditor, and onChange hears the value of the chosen way only.
  function setupReceiver(form, panel, kind, { decode, show, onChange = () => {} }) {
    const sb58Panel = panel.querySelector('.sb58-receiver');
    const scanner = panel.querySelector('.qr-scanner');
    const scanButton = scanner.querySelector('[data-action=scan]');
    const status = scanner.querySelector('.qr-scan-status');
    const result = scanner.querySelector('.qr-result');
    const output = scanner.querySelector('.qr-output');
    const values = { sb58: null, qr: null };
    function announce(mode, value) {
      if (values[mode] === value) return;
      values[mode] = value;
      if (modeOf(form) === mode) onChange(value);
    }
    function showStatus(text, isError = false) { status.textContent = text; status.classList.toggle('is-error', isError); }

    globalThis.SB58.setupEditor(sb58Panel, { decode, show, onChange: value => announce('sb58', value) });

    scanButton.addEventListener('click', async () => {
      announce('qr', null);
      result.hidden = true;
      scanButton.disabled = true;
      showStatus('A camera window is open on this device. Hold the camera to the QR codes on the other device until every one is read. Press q in the window to stop.');
      try {
        const scanned = await runScript('qr-scan', { kind, passphrase: passphrase() });
        const bytes = Uint8Array.from(scanned.hex.match(/../g) ?? [], pair => parseInt(pair, 16));
        let value;
        try {
          value = await decode(bytes);
        } catch (error) {
          throw new Error(`The QR codes were decrypted, but they do not hold what this step expects. ${error.message}`);
        }
        const shown = show(value);
        output.textContent = shown.text;
        result.hidden = false;
        showStatus(`${shown.status} Decrypted from ${scanned.slices} QR ${scanned.slices === 1 ? 'code' : 'codes'}.`);
        announce('qr', value);
      } catch (error) {
        showStatus(error.message, true);
      } finally {
        scanButton.disabled = false;
      }
    });
    scanner.querySelector('.qr-copy').addEventListener('click', () => copyText(output.textContent, status));

    function apply() {
      const mode = modeOf(form);
      sb58Panel.hidden = mode !== 'sb58';
      scanner.hidden = mode !== 'qr';
    }
    form.addEventListener('change', () => { apply(); onChange(values[modeOf(form)]); });
    apply();
  }

  globalThis.QrTransfer = { setupSender, setupReceiver };
})();
