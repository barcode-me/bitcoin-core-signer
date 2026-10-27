/* Reads and shows the bytes sent by the Super Base 58 pages as UTF-8 text or hex. Shared by both pages. */
(() => {
  // The format picked in a format-choice fieldset: 'utf8' or 'hex'.
  const selected = (container, name) => container.querySelector(`input[name="${name}"]:checked`).value;

  // Hex ignores whitespace and a leading 0x, and takes two characters per byte.
  function parse(value, format) {
    if (format === 'utf8') return new TextEncoder().encode(value);
    const hex = value.replace(/\s+/g, '').replace(/^0x/i, '');
    const invalid = hex.match(/[^0-9a-f]/i);
    if (invalid) throw new Error(`"${invalid[0]}" is not a hex character. Use 0 to 9 and a to f, or choose UTF-8 text.`);
    if (hex.length % 2) throw new Error(`Hex takes two characters per byte, but ${hex.length} characters were entered.`);
    return new Uint8Array((hex.match(/../g) ?? []).map(pair => parseInt(pair, 16)));
  }

  // Returns { text, count } where count names the characters or bytes shown, or throws when the bytes are not UTF-8.
  function show(bytes, format) {
    const plural = (count, word) => `${count} ${word}${count === 1 ? '' : 's'}`;
    if (format === 'hex') return { text: [...bytes].map(byte => byte.toString(16).padStart(2, '0')).join(''), count: plural(bytes.length, 'byte') };
    let text;
    try {
      text = new TextDecoder('utf-8', { fatal: true }).decode(bytes);
    } catch {
      throw new Error('The data is not UTF-8 text. Choose Hex to see its bytes.');
    }
    return { text, count: plural([...text].length, 'character') };
  }

  globalThis.ByteFormat = { selected, parse, show };
})();
