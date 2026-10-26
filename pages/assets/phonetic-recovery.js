/* Local-only recovery, compatible with python/hex_to_yeti.py. */
(() => {
  const base58 = '123456789ABCDEFGHJKLMNPQRSTUVWXYZabcdefghijkmnopqrstuvwxyz';
  const nato = 'alfa bravo charlie delta echo foxtrot golf hotel india juliett kilo lima mike november oscar papa quebec romeo sierra tango uniform victor whiskey x-ray yankee zulu'.split(' ');
  const digits = 'ZERO ONE TWO THREE FOUR FIVE SIX SEVEN EIGHT NINE'.split(' ');
  const wordToChar = new Map();
  nato.forEach((word, i) => {
    wordToChar.set(word, String.fromCharCode(97 + i));
    wordToChar.set(word.toUpperCase(), String.fromCharCode(65 + i));
  });
  digits.slice(1).forEach((word, i) => wordToChar.set(word, String(i + 1)));
  const charToWord = new Map([...wordToChar].map(([word, char]) => [char, word]));
  const vocabulary = [...wordToChar.keys(), 'ZERO'];
  const tokens = value => value.trim() ? value.trim().split(/\s+/) : [];

  function rowError(value, last = false) {
    const words = tokens(value);
    if (words.length !== 5 && !(last && words.length >= 2 && words.length <= 5)) {
      return last ? 'Enter 2–5 complete words in the last data row, including its checksum word.' : 'Enter exactly 5 complete words, including the checksum word.';
    }
    if (words.some(word => !wordToChar.has(word) || !base58.includes(wordToChar.get(word)))) return 'Use complete, case-sensitive Base58 phonetic words.';
    const chars = words.map(word => wordToChar.get(word));
    const expected = base58[chars.slice(0, -1).reduce((sum, char) => sum + base58.indexOf(char), 0) % 58];
    return chars.at(-1) === expected ? '' : `Checksum word does not match. Expected ${charToWord.get(expected)}.`;
  }

  function currentWord(value, caret) {
    if (!caret || /\s/.test(value[caret - 1])) return null;
    let start = caret, end = caret;
    while (start > 0 && !/\s/.test(value[start - 1])) start--;
    while (end < value.length && !/\s/.test(value[end])) end++;
    const word = value.slice(start, end);
    if (vocabulary.includes(word)) return null;
    return { start, end, first: word[0] };
  }
  function suggestions(value, caret) {
    const token = currentWord(value, caret);
    if (!token) return [];
    return vocabulary.filter(word => word[0].toLowerCase() === token.first.toLowerCase())
      .sort((a, b) => Number(b[0] === token.first) - Number(a[0] === token.first));
  }
  async function recover(header, rows, finalLine) {
    if (!/^[a-fA-F0-9]{8}=$/.test(header.trim())) throw new Error('Enter 8 hex characters followed by = for the backup checksum.');
    if (!rows.length) throw new Error('Enter at least one data row.');
    rows.forEach((row, index) => {
      const error = rowError(row, index === rows.length - 1);
      if (error) throw new Error(`Row ${index + 1}: ${error}`);
    });
    const finalWords = tokens(finalLine);
    if (finalWords.length !== 5 || finalWords.some(word => !digits.includes(word))) throw new Error('Final checksum: enter exactly 5 uppercase digit words, ZERO through NINE.');
    const supplied = Number(finalWords.map(word => digits.indexOf(word)).join(''));
    if (supplied > 65535) throw new Error('Final checksum must represent a number from 0 to 65535.');
    const text = rows.map(row => tokens(row).join(' ')).join('\n').trim();
    const hash = new Uint8Array(await crypto.subtle.digest('SHA-256', new TextEncoder().encode(text)));
    if (supplied !== hash[30] * 256 + hash[31]) throw new Error('Final checksum does not match the word list.');
    const encoded = rows.flatMap(row => tokens(row).slice(0, -1).map(word => wordToChar.get(word))).join('');
    let number = 0n;
    for (const char of encoded) number = number * 58n + BigInt(base58.indexOf(char));
    const bytes = [];
    while (number) { bytes.unshift(Number(number & 255n)); number >>= 8n; }
    for (const char of encoded) { if (char !== '1') break; bytes.unshift(0); }
    if (bytes.length !== 32) throw new Error(`Expected 32 decoded bytes; got ${bytes.length}. Check the number of rows.`);
    return header.trim().toLowerCase() + bytes.map(byte => byte.toString(16).padStart(2, '0')).join('');
  }
  globalThis.YetiRecovery = { rowError, currentWord, suggestions, recover };
  if (typeof document === 'undefined') return;
  const form = document.querySelector('#phonetic-form');
  const rowContainer = document.querySelector('#word-rows');
  const header = document.querySelector('#backup-checksum');
  const final = document.querySelector('#final-checksum');
  const result = document.querySelector('#recovery-result');
  const output = document.querySelector('#recovered-hex');
  const generalError = document.querySelector('#recovery-error');
  let revision = 0;
  function clearResult() { revision++; result.hidden = true; output.value = ''; generalError.textContent = ''; }
  function showError(input, message) {
    input.closest('.phonetic-field').querySelector('.field-error').textContent = message;
    input.classList.toggle('has-error', Boolean(message));
  }
  function autocomplete(input) {
    const menu = input.parentElement.querySelector('.word-suggestions');
    let dismissed = false;
    function update() {
      menu.replaceChildren();
      const matches = dismissed ? [] : suggestions(input.value, input.selectionStart);
      menu.hidden = !matches.length;
      for (const word of matches) {
        const button = document.createElement('button');
        button.type = 'button'; button.textContent = word;
        button.addEventListener('mousedown', event => event.preventDefault());
        button.addEventListener('click', () => {
          const token = currentWord(input.value, input.selectionStart);
          if (!token) return;
          input.setRangeText(word, token.start, token.end, 'end');
          clearResult(); showError(input, ''); input.focus(); update();
        });
        menu.append(button);
      }
    }
    ['input', 'click', 'focus'].forEach(event => input.addEventListener(event, () => { dismissed = false; update(); }));
    input.addEventListener('keyup', event => { if (event.key !== 'Escape') update(); });
    input.addEventListener('keydown', event => { if (event.key === 'Escape') { dismissed = true; menu.hidden = true; } });
    input.addEventListener('blur', () => { setTimeout(() => { if (!input.parentElement.contains(document.activeElement)) menu.hidden = true; }, 0); });
  }
  function addRow() {
    const number = rowContainer.children.length + 1;
    const field = document.createElement('div'); field.className = 'phonetic-field';
    const label = document.createElement('label'); label.htmlFor = `word-row-${number}`; label.textContent = `Data row ${number}`;
    const input = document.createElement('input'); input.id = label.htmlFor; input.spellcheck = false; input.autocomplete = 'off'; input.setAttribute('autocapitalize', 'off');
    const menu = document.createElement('div'); menu.className = 'word-suggestions'; menu.hidden = true;
    const error = document.createElement('p'); error.className = 'field-error';
    field.append(label, input, menu, error); rowContainer.append(field);
    autocomplete(input);
    input.addEventListener('blur', () => showError(input, rowError(input.value, field === rowContainer.lastElementChild)));
    clearResult();
  }
  for (let i = 0; i < 11; i++) addRow();
  autocomplete(final);
  header.addEventListener('blur', () => showError(header, /^[a-fA-F0-9]{8}=$/.test(header.value.trim()) ? '' : 'Enter 8 hex characters followed by =.'));
  form.addEventListener('input', event => { clearResult(); showError(event.target, ''); });
  document.querySelector('#add-row').addEventListener('click', addRow);
  document.querySelector('#remove-row').addEventListener('click', () => { if (rowContainer.children.length > 1) { rowContainer.lastElementChild.remove(); clearResult(); } });
  form.addEventListener('submit', async event => {
    event.preventDefault(); clearResult(); showError(final, '');
    const version = revision;
    try {
      const recovered = await recover(header.value, [...rowContainer.querySelectorAll('input')].map(input => input.value), final.value);
      if (version !== revision) return;
      output.value = recovered; result.hidden = false;
    } catch (error) {
      if (version !== revision) return;
      if (error.message.startsWith('Final checksum')) showError(final, error.message);
      else generalError.textContent = error.message;
    }
  });
})();
