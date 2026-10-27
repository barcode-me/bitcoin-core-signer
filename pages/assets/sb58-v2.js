/* Super Base 58 v2 page: encodes text as lowercase Base58 in groups of 4, each followed by a hex casing character, with a
   checksum every 25 groups and a final checksum, and decodes typed text back. Nothing is sent anywhere. */
(() => {
  const alphabet = '123456789ABCDEFGHJKLMNPQRSTUVWXYZabcdefghijkmnopqrstuvwxyz';
  const groupChars = 4;
  const groupSize = groupChars + 1;
  const groupsPerBlock = 25;
  const groupsPerRow = 5;
  const checksumSize = 4;
  // A full block is 100 Base58 characters typed as 125, then its checksum.
  const blockLength = groupsPerBlock * groupSize;
  const stride = blockLength + checksumSize;

  function base58Encode(bytes) {
    let number = 0n;
    for (const byte of bytes) number = number * 256n + BigInt(byte);
    let encoded = '';
    while (number) { encoded = alphabet[Number(number % 58n)] + encoded; number /= 58n; }
    for (const byte of bytes) { if (byte) break; encoded = `1${encoded}`; }
    return encoded;
  }

  function base58Decode(chars) {
    let number = 0n;
    for (const char of chars) number = number * 58n + BigInt(alphabet.indexOf(char));
    const bytes = [];
    while (number) { bytes.unshift(Number(number & 255n)); number >>= 8n; }
    for (const char of chars) { if (char !== '1') break; bytes.unshift(0); }
    return new Uint8Array(bytes);
  }

  // The last two bytes of SHA-256, as 4 hex characters.
  async function checksum(bytes) {
    // The browser only offers SHA-256 on secure pages such as http://localhost or http://127.0.0.1.
    if (!globalThis.crypto?.subtle) throw new Error('This browser cannot compute checksums on this address. Open the page from http://localhost:8000 or http://127.0.0.1:8000.');
    const digest = new Uint8Array(await crypto.subtle.digest('SHA-256', bytes));
    return [...digest.slice(-2)].map(byte => byte.toString(16).padStart(2, '0')).join('');
  }
  // A block checksum covers its groups as typed, casing characters included, in lowercase and without spaces.
  const blockChecksums = new Map();
  async function blockChecksum(typed) {
    const key = typed.toLowerCase();
    if (!blockChecksums.has(key)) blockChecksums.set(key, await checksum(new TextEncoder().encode(key)));
    return blockChecksums.get(key);
  }

  // A group is up to 4 Base58 characters in lowercase and a hex character for their casing: the first character is the
  // top bit, uppercase is 1, lowercase and numbers are 0. A shorter last group pads its low bits with 0.
  function encodeGroup(chars) {
    const bits = [...chars].reduce((sum, char, index) => /[A-Z]/.test(char) ? sum | 8 >> index : sum, 0);
    return chars.toLowerCase() + bits.toString(16);
  }

  // Returns the Base58 characters of typed groups with their casing restored, or an error naming the group.
  function decodeGroups(typed, block) {
    let chars = '';
    for (const [index, group] of (typed.match(/.{1,5}/g) ?? []).entries()) {
      const name = `Block ${block} group ${index + 1} "${group}"`;
      if (group.length < 2) return { error: `${name} needs at least one character and its casing character.` };
      const base = group.slice(0, -1).toLowerCase();
      const casing = group.at(-1).toLowerCase();
      if (!/^[0-9a-f]$/.test(casing)) return { error: `${name} ends in "${casing}", but the casing character is hex: 0 to 9 or a to f.` };
      const bits = parseInt(casing, 16);
      if (bits & 0xf >> base.length) return { error: `${name} has ${base.length} ${base.length === 1 ? 'character' : 'characters'}, so its casing character cannot be "${casing}".` };
      for (const [position, char] of [...base].entries()) {
        const upper = (bits & 8 >> position) !== 0;
        const cased = upper ? char.toUpperCase() : char;
        if (!/[1-9a-z]/.test(char)) return { error: `${name}: "${char}" is not Base58.` };
        if (!alphabet.includes(cased) || (upper && /\d/.test(char))) return { error: `${name}: "${char}" cannot be ${upper ? 'uppercase' : 'lowercase'} in Base58. Check the casing character.` };
        chars += cased;
      }
    }
    return { chars };
  }

  // The rows to show and type: rows of 5 groups, a block checksum after every 25 groups, then the final checksum of the bytes.
  async function encode(bytes) {
    const encoded = base58Encode(bytes);
    const groups = encoded.match(/.{1,4}/g).map(encodeGroup);
    const rows = [];
    for (let start = 0; start < groups.length; start += groupsPerBlock) {
      const block = groups.slice(start, start + groupsPerBlock);
      const blockRows = [];
      for (let row = 0; row < block.length; row += groupsPerRow) blockRows.push({ kind: 'data', groups: block.slice(row, row + groupsPerRow) });
      blockRows.at(-1).checksum = await blockChecksum(block.join(''));
      rows.push(...blockRows);
    }
    rows.push({ kind: 'final', checksum: await checksum(bytes) });
    return { encoded, blockCount: Math.ceil(groups.length / groupsPerBlock), rows };
  }

  const rowText = row => [...row.groups ?? [], row.checksum].filter(Boolean).join(' ');
  const plural = (count, word) => `${count} ${word}${count === 1 ? '' : 's'}`;

  // Reads typed groups, ignoring whitespace. Full blocks of 125 characters and their checksum sit at fixed offsets, and
  // whatever follows them is the last, shorter block, its checksum and the final checksum.
  // Returns { bytes, encoded, blockCount } once every checksum matches, otherwise { status } or { error }.
  async function decode(text) {
    const typed = text.replace(/\s+/g, '');
    if (!typed) return { status: 'Waiting for the first group.' };
    const invalid = typed.match(/[^0-9a-z]/i);
    if (invalid) return { error: `"${invalid[0]}" is not a Base58 or hex character. Remove it.` };
    const checks = async (start, length) => typed.slice(start + length, start + length + checksumSize).toLowerCase() === await blockChecksum(typed.slice(start, start + length));

    let fullBlocks = 0;
    let chars = '';
    while ((fullBlocks + 1) * stride <= typed.length && await checks(fullBlocks * stride, blockLength)) {
      const decoded = decodeGroups(typed.slice(fullBlocks * stride, fullBlocks * stride + blockLength), fullBlocks + 1);
      if (decoded.error) return decoded;
      chars += decoded.chars;
      fullBlocks++;
    }
    const blocksPass = count => `${count === 1 ? 'Block 1 checks' : `Blocks 1 to ${count} check`} out.`;
    const passed = fullBlocks ? blocksPass(fullBlocks) : '';
    const block = fullBlocks + 1;
    const rest = typed.slice(fullBlocks * stride);
    const finish = async (dataChars, blockCount, typedChecksum) => {
      const bytes = base58Decode(dataChars);
      if (await checksum(bytes) === typedChecksum.toLowerCase()) return { bytes, encoded: dataChars, blockCount };
      return null;
    };

    // Data that fills its last block ends with that block's checksum, so only the final checksum follows.
    if (fullBlocks && rest.length === checksumSize) {
      const done = await finish(chars, fullBlocks, rest);
      return done ?? { status: `${passed} Keep typing block ${block}. If you are done, the final checksum does not match: a block may be missing or out of order, or the final checksum is mistyped.` };
    }

    // Groups before the last 8 characters are complete whether this is the last block or not, so check them now.
    const lastLength = rest.length - 2 * checksumSize;
    const complete = Math.min(Math.max(0, lastLength), blockLength);
    const early = decodeGroups(rest.slice(0, complete - complete % groupSize), block);
    if (early.error) return early;

    // The last block is shorter than a full one and cannot end in a group with no Base58 character. Once a full block's
    // worth has been typed and it is not the last block either, the block is wrong rather than still being typed.
    const isLast = lastLength > 0 && lastLength < blockLength && lastLength % groupSize !== 1 && await checks(fullBlocks * stride, lastLength);
    if (!isLast) {
      if (rest.length >= stride) return { error: `${passed} Block ${block} does not match its checksum. Check its groups and the 4-character checksum after them.`.trim() };
      return { status: `${passed} ${rest.length ? `${plural(rest.length, 'character')} of block ${block} typed. Keep typing.` : `Keep typing block ${block}.`}`.trim() };
    }
    const typing = `${blocksPass(block)} Keep typing.`;
    const last = decodeGroups(rest.slice(0, lastLength), block);
    if (last.error) return last;
    const done = await finish(chars + last.chars, block, rest.slice(-checksumSize));
    return done ?? { status: `${typing} If you are done, the final checksum does not match: a block may be missing or out of order, or the final checksum is mistyped.` };
  }

  // viewer is a .sb58-viewer with .sb58-progress, .sb58-lines, a Copy lines button and .sb58-copy-status.
  function setupViewer(viewer) {
    const lineList = viewer.querySelector('.sb58-lines');
    const lineProgress = viewer.querySelector('.sb58-progress');
    let shownRows = [];
    let currentLine = 0;

    function selectLine(index) {
      const items = lineList.children;
      currentLine = Math.max(0, Math.min(index, items.length - 1));
      [...items].forEach((item, position) => {
        item.classList.toggle('is-current', position === currentLine);
        if (position === currentLine) item.setAttribute('aria-current', 'true'); else item.removeAttribute('aria-current');
      });
      const item = items[currentLine];
      // Keep the current line in view inside the list without scrolling the page.
      if (item.offsetTop < lineList.scrollTop) lineList.scrollTop = item.offsetTop;
      else if (item.offsetTop + item.offsetHeight > lineList.scrollTop + lineList.clientHeight) lineList.scrollTop = item.offsetTop + item.offsetHeight - lineList.clientHeight;
      lineProgress.textContent = currentLine === items.length - 1 ? `Final checksum (line ${items.length} of ${items.length})` : `Line ${currentLine + 1} of ${items.length}`;
    }

    function show(rows) {
      shownRows = rows;
      const span = (className, ...content) => { const element = document.createElement('span'); element.className = className; element.append(...content); return element; };
      lineList.replaceChildren(...rows.map((row, index) => {
        const item = document.createElement('li');
        item.setAttribute('aria-label', `Line ${index + 1}: ${rowText(row)}`);
        item.append(span('line-number', String(index + 1)));
        if (row.groups) {
          // The casing character of each group is set apart by colour only, since it is typed straight after the group.
          const groups = row.groups.flatMap((group, position) => [position ? ' ' : '', group.slice(0, -1), span('line-casing', group.at(-1))]);
          item.append(span('line-words', ...groups));
        }
        if (row.checksum) item.append(span('line-checksum', row.checksum), span('line-label', row.kind === 'final' ? 'final checksum' : 'block checksum'));
        item.addEventListener('click', () => { selectLine(index); viewer.focus({ preventScroll: true }); });
        return item;
      }));
      viewer.hidden = false;
      selectLine(0);
      viewer.focus({ preventScroll: true });
    }

    function clear() { viewer.hidden = true; lineList.replaceChildren(); shownRows = []; }

    viewer.addEventListener('keydown', event => {
      // Keys on the Copy button belong to the button.
      if (event.target !== viewer) return;
      if (event.key === 'Enter' && !event.shiftKey || event.key === 'ArrowDown') selectLine(currentLine + 1);
      else if (event.key === 'Enter' || event.key === 'ArrowUp' || event.key === 'Backspace') selectLine(currentLine - 1);
      else if (event.key === 'Home') selectLine(0);
      else if (event.key === 'End') selectLine(lineList.children.length - 1);
      else return;
      event.preventDefault();
    });

    // Copies the lines as typed on the other device, without line numbers or labels.
    viewer.querySelector('[data-action=copy-lines]').addEventListener('click', () => copyText(shownRows.map(rowText).join('\n'), viewer.querySelector('.sb58-copy-status')));

    return { show, clear };
  }

  async function copyText(text, status) {
    try {
      await navigator.clipboard.writeText(text);
      status.textContent = 'Copied.';
    } catch {
      status.textContent = 'Copy failed. Select the text and copy it manually.';
    }
  }

  const form = document.querySelector('#sb58v2-encode-form');
  const text = document.querySelector('#sb58v2-encode-text');
  const encodeStatus = document.querySelector('#sb58v2-encode-status');
  const viewer = setupViewer(document.querySelector('#sb58v2-encode-viewer'));
  const base58 = document.querySelector('#sb58v2-encode-base58');
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
    if (!bytes.length) { encodeStatus.textContent = 'Enter the text to send first.'; return; }
    try {
      const encoded = await encode(bytes);
      encodeStatus.textContent = `${plural(bytes.length, 'byte')} as ${encoded.encoded.length} Base58 characters in ${plural(encoded.blockCount, 'block')}, then the final checksum.`;
      base58Output.textContent = encoded.encoded;
      base58.hidden = false;
      viewer.show(encoded.rows);
    } catch (error) {
      encodeStatus.textContent = error.message;
    }
  });
  // Lines of older text must not be read out by mistake.
  text.addEventListener('input', () => { clear(); encodeStatus.textContent = ''; });
  base58.querySelector('.sb58-copy').addEventListener('click', () => copyText(base58Output.textContent, base58CopyStatus));

  const decoder = document.querySelector('#sb58v2-decoder');
  const input = decoder.querySelector('.sb58v2-input');
  const decodeStatus = decoder.querySelector('.sb58-status');
  const errorList = decoder.querySelector('.sb58-errors');
  const result = decoder.querySelector('.sb58-result');
  const output = result.querySelector('.sb58-output');
  let revision = 0;

  function showError(message) {
    const item = document.createElement('li');
    item.textContent = message;
    errorList.replaceChildren(item);
  }

  async function update() {
    const version = ++revision;
    result.hidden = true;
    errorList.replaceChildren();
    let decoded;
    try {
      decoded = await decode(input.value);
    } catch (error) {
      decoded = { error: error.message };
    }
    if (version !== revision) return;
    if (decoded.error) { decodeStatus.textContent = 'Something needs attention.'; showError(decoded.error); return; }
    if (decoded.status) { decodeStatus.textContent = decoded.status; return; }
    let value;
    try {
      value = new TextDecoder('utf-8', { fatal: true }).decode(decoded.bytes);
    } catch {
      decodeStatus.textContent = 'Something needs attention.';
      showError('Every checksum matches, but the data is not UTF-8 text.');
      return;
    }
    output.textContent = value;
    result.hidden = false;
    decodeStatus.textContent = `Recovered ${plural([...value].length, 'character')} from ${plural(decoded.blockCount, 'block')}. Every block checksum and the final checksum match.`;
  }
  input.addEventListener('input', update);
  result.querySelector('.sb58-copy').addEventListener('click', () => copyText(output.textContent, decodeStatus));
  update();
})();
