/* Receives public descriptors typed as Super Base 58 (SB58), compatible with python/descriptors-to-sb58.py. Input stays on this page. */
(() => {
  const base58 = '123456789ABCDEFGHJKLMNPQRSTUVWXYZabcdefghijkmnopqrstuvwxyz';
  const letterWords = {
    a: 'alfa', b: 'bravo', c: 'charlie', d: 'delta', e: 'echo', f: 'foxtrot', g: 'golf', h: 'hotel', i: 'india',
    j: 'juliett', k: 'kilo', l: 'lima', m: 'mike', n: 'november', o: 'oscar', p: 'papa', q: 'quebec', r: 'romeo',
    s: 'sierra', t: 'tango', u: 'uniform', v: 'victor', w: 'whiskey', x: 'x-ray', y: 'yankee', z: 'zulu',
  };
  const digitWords = ['one', 'two', 'three', 'four', 'five', 'six', 'seven', 'eight', 'nine'];
  const wordToChar = new Map([
    ...Object.entries(letterWords).map(([char, word]) => [word, char]),
    ...digitWords.map((word, index) => [word, String(index + 1)]),
  ]);
  const words = [...wordToChar.keys()];
  const listOf = items => items.length < 2 ? items.join('') : `${items.slice(0, -1).join(', ')} or ${items.at(-1)}`;
  const charWord = char => /\d/.test(char) ? digitWords[Number(char) - 1] : letterWords[char.toLowerCase()];
  const checksumChar = chars => base58[[...chars].reduce((sum, char) => sum + base58.indexOf(char), 0) % 58];
  const checksumWord = chars => charWord(checksumChar(chars));

  // A word can be completed from its first letters when only one word starts with them.
  function completeWord(token) {
    const prefix = token.toLowerCase();
    if (wordToChar.has(prefix)) return { word: prefix };
    const matches = words.filter(word => word.startsWith(prefix));
    if (matches.length === 1) return { word: matches[0] };
    if (!matches.length) return { message: `"${token}" is not the start of any word. Check the spelling.` };
    return { message: `"${token}" could be ${listOf(matches)}. Type more letters, then press space.` };
  }

  function resolveWord(token, label) {
    const key = token.toLowerCase();
    if (wordToChar.has(key)) return { key };
    const completed = completeWord(token);
    return { error: completed.word ? `${label} "${token}" is incomplete. Did you mean "${completed.word}"?` : `${label}: ${completed.message}` };
  }

  // tokens = words, casing string, checksum word. Only the last line may have fewer than 4 words.
  function checkDataLine(tokens, allowShort) {
    const wordCount = tokens.length - 2;
    if (allowShort ? tokens.length < 3 || wordCount > 4 : tokens.length !== 6) {
      return { error: allowShort
        ? `Expected 1 to 4 words, a casing string and a checksum word, found ${tokens.length} items.`
        : `Expected 4 words, a 5-digit casing string and a checksum word (6 items), found ${tokens.length}.` };
    }
    const casing = tokens[wordCount];
    if (!/^[01]+$/.test(casing)) return { error: `Expected the casing string of 0s and 1s before the checksum word, found "${casing}".` };
    if (casing.length !== wordCount + 1) return { error: `The casing string "${casing}" needs ${wordCount + 1} digits: one per word and one for the checksum word.` };
    const chars = [];
    for (const [index, token] of tokens.slice(0, wordCount).entries()) {
      const resolved = resolveWord(token, `Word ${index + 1}`);
      if (resolved.error) return resolved;
      const base = wordToChar.get(resolved.key);
      // Numbers ignore the casing bit.
      const char = casing[index] === '1' && /[a-z]/.test(base) ? base.toUpperCase() : base;
      if (!base58.includes(char)) return { error: `Word ${index + 1} "${resolved.key}" cannot be ${casing[index] === '1' ? 'uppercase' : 'lowercase'} in Base58. Check the casing string.` };
      chars.push(char);
    }
    const resolved = resolveWord(tokens.at(-1), 'Checksum word');
    if (resolved.error) return resolved;
    const expectedChar = checksumChar(chars);
    const expected = charWord(expectedChar);
    if (resolved.key !== expected) return { error: `The checksum word "${resolved.key}" does not match the words. Expected "${expected}". Check the words and the casing string.` };
    // The last casing digit is the case of the checksum character, which tells X from x. Numbers ignore it.
    if (/[A-Za-z]/.test(expectedChar) && (casing[wordCount] === '1') !== (expectedChar !== expectedChar.toLowerCase())) {
      return { error: `The casing string "${casing}" does not match the checksum. Check its digits.` };
    }
    return { chars: chars.join('') };
  }

  // Checks every line and returns errors with line numbers. A last line still being typed is not an error.
  function checkLines(text) {
    const lines = text.split('\n').map(line => line.trim());
    while (lines.length && !lines.at(-1)) lines.pop();
    const errors = [];
    const fail = (line, message) => errors.push({ line, message });
    const last = lines.length;
    const hasFinal = last > 0 && /^\d+$/.test(lines[last - 1]);
    const dataLines = hasFinal ? last - 1 : last;
    let chars = '';
    const rows = [];
    for (let index = 0; index < dataLines; index++) {
      const number = index + 1;
      const line = lines[index];
      if (!line) { fail(number, 'This line is empty. Remove it or type the line.'); continue; }
      if (/^\d+$/.test(line)) { fail(number, 'A line of digits is only valid as the final checksum on the last line.'); continue; }
      const tokens = line.split(/\s+/);
      const typing = !hasFinal && index === dataLines - 1;
      if (typing && tokens.length < 6) continue;
      const checked = checkDataLine(tokens, hasFinal && index === dataLines - 1);
      if (checked.error) fail(number, checked.error); else { chars += checked.chars; rows.push(tokens.map(token => token.toLowerCase()).join(' ')); }
    }
    if (hasFinal) {
      if (!dataLines) fail(last, 'Type the lines first. The final checksum goes on the last line.');
      else if (!/^\d{5}$/.test(lines[last - 1])) fail(last, `The final checksum is 5 digits, found ${lines[last - 1].length}.`);
    }
    return { errors, lineCount: lines.length, hasFinal, finalLine: last, rows, chars, finalDigits: hasFinal ? lines[last - 1] : '', complete: hasFinal && !errors.length };
  }

  async function recover(rows, chars, finalDigits) {
    // The browser only offers SHA-256 on secure pages such as http://localhost or http://127.0.0.1.
    if (!globalThis.crypto?.subtle) throw new Error('This browser cannot compute the checksum on this address. Open the page from http://localhost:8000 or http://127.0.0.1:8000.');
    // Final checksum: the last two bytes of SHA-256 over the lines joined by newlines, as 5 digits.
    const digest = new Uint8Array(await crypto.subtle.digest('SHA-256', new TextEncoder().encode(rows.join('\n'))));
    if (String(digest.at(-2) * 256 + digest.at(-1)).padStart(5, '0') !== finalDigits) {
      throw new Error('The final checksum does not match, although every line passed. A line may be missing, repeated or out of order, or the final checksum was mistyped.');
    }
    let number = 0n;
    for (const char of chars) number = number * 58n + BigInt(base58.indexOf(char));
    const bytes = [];
    while (number) { bytes.unshift(Number(number & 255n)); number >>= 8n; }
    for (const char of chars) { if (char !== '1') break; bytes.unshift(0); }
    const data = new Uint8Array(bytes);
    let descriptors;
    try {
      descriptors = JSON.parse(new TextDecoder('utf-8', { fatal: true }).decode(data));
    } catch {
      throw new Error('The data checks out but is not a list of descriptors.');
    }
    if (!Array.isArray(descriptors) || !descriptors.length || descriptors.some(item => typeof item !== 'string')) {
      throw new Error('The data checks out but is not a list of descriptors.');
    }
    if (descriptors.some(item => item.includes('prv'))) throw new Error('This data contains a private key. Do not use it. Only public descriptors should be transferred.');
    return descriptors;
  }

  globalThis.SB58 = { completeWord, checkLines, recover, checksumWord };
  if (typeof document === 'undefined') return;

  const input = document.querySelector('#sb58-input');
  const gutter = document.querySelector('#sb58-gutter');
  const status = document.querySelector('#sb58-status');
  const hint = document.querySelector('#sb58-hint');
  const errorList = document.querySelector('#sb58-errors');
  const result = document.querySelector('#sb58-result');
  const output = document.querySelector('#sb58-descriptors');
  const copyButton = document.querySelector('#sb58-copy');
  let revision = 0;
  let recovered = null;
  // Tells the rest of the page which descriptors the typed lines recovered, or null when they no longer do.
  function announce(descriptors) {
    if (descriptors === recovered) return;
    recovered = descriptors;
    document.dispatchEvent(new CustomEvent('sb58-recovered', { detail: descriptors }));
  }

  function renderGutter(errors) {
    const count = input.value.split('\n').length;
    const failed = new Set(errors.map(error => error.line));
    gutter.replaceChildren(...Array.from({ length: count }, (_, index) => {
      const row = document.createElement('div');
      row.textContent = index + 1;
      row.classList.toggle('has-error', failed.has(index + 1));
      return row;
    }));
    gutter.scrollTop = input.scrollTop;
  }
  function renderErrors(errors) {
    errorList.replaceChildren(...errors.map(error => {
      const item = document.createElement('li');
      item.textContent = `Line ${error.line}: ${error.message}`;
      return item;
    }));
  }
  function showStatus(text) { status.textContent = text; }

  async function update() {
    const version = ++revision;
    hint.textContent = '';
    result.hidden = true;
    announce(null);
    const checked = checkLines(input.value);
    renderGutter(checked.errors);
    renderErrors(checked.errors);
    if (checked.errors.length) return showStatus(`${checked.errors.length === 1 ? '1 line needs' : `${checked.errors.length} lines need`} attention.`);
    if (!checked.complete) {
      return showStatus(checked.lineCount ? `${checked.lineCount} ${checked.lineCount === 1 ? 'line' : 'lines'} entered. Keep typing, then type the final checksum on the last line.` : 'Waiting for the first line.');
    }
    showStatus('Every line checks out. Verifying the final checksum…');
    try {
      const descriptors = await recover(checked.rows, checked.chars, checked.finalDigits);
      if (version !== revision) return;
      output.textContent = descriptors.join('\n');
      result.hidden = false;
      announce(descriptors);
      showStatus(`Recovered ${descriptors.length} ${descriptors.length === 1 ? 'descriptor' : 'descriptors'}. The final checksum matches.`);
    } catch (error) {
      if (version !== revision) return;
      renderErrors([{ line: checked.finalLine, message: error.message }]);
      renderGutter([{ line: checked.finalLine }]);
      showStatus('The final checksum does not match.');
    }
  }

  // Space or Enter completes the word before the caret from its first letters, or says why it cannot.
  input.addEventListener('keydown', event => {
    if ((event.key !== ' ' && event.key !== 'Enter') || event.ctrlKey || event.metaKey || event.altKey || event.isComposing) return;
    const { value, selectionStart: caret, selectionEnd } = input;
    if (caret !== selectionEnd || (caret < value.length && !/\s/.test(value[caret]))) return;
    let start = caret;
    while (start > 0 && !/\s/.test(value[start - 1])) start--;
    const token = value.slice(start, caret);
    // Casing strings and the final checksum are digits, so only words are completed.
    if (!/^[a-z]/i.test(token)) return;
    const completed = completeWord(token);
    if (completed.word) {
      if (completed.word !== token) input.setRangeText(completed.word, start, caret, 'end');
      return;
    }
    event.preventDefault();
    hint.textContent = `Line ${value.slice(0, caret).split('\n').length}: ${completed.message}`;
  });
  input.addEventListener('input', update);
  input.addEventListener('scroll', () => { gutter.scrollTop = input.scrollTop; });
  errorList.addEventListener('click', event => {
    const match = /^Line (\d+):/.exec(event.target.textContent);
    if (!match) return;
    const offset = input.value.split('\n').slice(0, Number(match[1]) - 1).join('\n').length + (match[1] > 1 ? 1 : 0);
    input.focus(); input.setSelectionRange(offset, offset);
  });
  copyButton.addEventListener('click', async () => {
    try {
      await navigator.clipboard.writeText(output.textContent);
    } catch {
      const range = document.createRange(); range.selectNodeContents(output);
      getSelection().removeAllRanges(); getSelection().addRange(range);
      showStatus('Select and copy the descriptors above.');
      return;
    }
    showStatus('Copied the public descriptors.');
  });
  update();
})();
