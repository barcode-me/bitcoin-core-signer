/* Super Base 58 page: encodes typed text as SB58 lines to read out, and decodes typed lines back into text. Nothing is sent anywhere. */
(() => {
  const form = document.querySelector('#sb58-encode-form');
  const text = document.querySelector('#sb58-encode-text');
  const status = document.querySelector('#sb58-encode-status');
  const viewer = SB58Viewer.setupViewer(document.querySelector('#sb58-encode-viewer'));
  const base58 = document.querySelector('#sb58-encode-base58');
  const base58Output = base58.querySelector('.sb58-output');
  const base58CopyStatus = base58.querySelector('.sb58-copy-status');

  function clear() {
    viewer.clear();
    base58.hidden = true;
    base58Output.textContent = '';
    base58CopyStatus.textContent = '';
  }

  form.addEventListener('submit', async event => {
    event.preventDefault();
    const bytes = new TextEncoder().encode(text.value);
    clear();
    if (!bytes.length) { status.textContent = 'Enter the text to send first.'; return; }
    try {
      const lines = await SB58.encodeLines(bytes);
      const encoded = SB58.base58Encode(bytes);
      status.textContent = `${bytes.length} ${bytes.length === 1 ? 'byte' : 'bytes'} as ${encoded.length} Base58 characters, in ${lines.length - 1} ${lines.length === 2 ? 'line' : 'lines'} and the final checksum.`;
      base58Output.textContent = encoded;
      base58.hidden = false;
      viewer.show(lines);
    } catch (error) {
      status.textContent = error.message;
    }
  });
  // Lines of older text must not be read out by mistake.
  text.addEventListener('input', () => { clear(); status.textContent = ''; });

  base58.querySelector('.sb58-copy').addEventListener('click', async () => {
    try {
      await navigator.clipboard.writeText(base58Output.textContent);
      base58CopyStatus.textContent = 'Copied.';
    } catch {
      base58CopyStatus.textContent = 'Copy failed. Select the text above and copy it manually.';
    }
  });

  SB58.setupEditor(document.querySelector('#sb58-decoder'), {
    decode: bytes => {
      try {
        return new TextDecoder('utf-8', { fatal: true }).decode(bytes);
      } catch {
        throw new Error('The lines check out, but they do not hold UTF-8 text.');
      }
    },
    show: value => ({ text: value, status: `Recovered ${[...value].length} ${[...value].length === 1 ? 'character' : 'characters'}.` }),
  });
})();
