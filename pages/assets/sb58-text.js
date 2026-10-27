/* Super Base 58 page: encodes typed text as SB58 lines to read out, and decodes typed lines back into text. Nothing is sent anywhere. */
(() => {
  const form = document.querySelector('#sb58-encode-form');
  const text = document.querySelector('#sb58-encode-text');
  const status = document.querySelector('#sb58-encode-status');
  const viewer = SB58Viewer.setupViewer(document.querySelector('#sb58-encode-viewer'));

  form.addEventListener('submit', async event => {
    event.preventDefault();
    const bytes = new TextEncoder().encode(text.value);
    if (!bytes.length) { viewer.clear(); status.textContent = 'Enter the text to send first.'; return; }
    try {
      const lines = await SB58.encodeLines(bytes);
      status.textContent = `${bytes.length} ${bytes.length === 1 ? 'byte' : 'bytes'} as ${lines.length - 1} ${lines.length === 2 ? 'line' : 'lines'} and the final checksum.`;
      viewer.show(lines);
    } catch (error) {
      viewer.clear();
      status.textContent = error.message;
    }
  });
  // Lines of older text must not be read out by mistake.
  text.addEventListener('input', () => { viewer.clear(); status.textContent = ''; });

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
