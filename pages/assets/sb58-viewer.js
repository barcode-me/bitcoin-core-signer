/* Shows Super Base 58 (SB58) lines one at a time, to type on the other device. Shared by the pages that send SB58. */
(() => {
  const { copyText } = globalThis.Notebook;

  // viewer is a .sb58-viewer with .sb58-progress, .sb58-lines, a Copy lines button and .sb58-copy-status.
  function setupViewer(viewer) {
    const lineList = viewer.querySelector('.sb58-lines');
    const lineProgress = viewer.querySelector('.sb58-progress');
    let shownLines = [];
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

    // lines are the data lines followed by the final checksum.
    function show(lines) {
      shownLines = lines;
      lineList.replaceChildren(...lines.map((line, index) => {
        const item = document.createElement('li');
        const tokens = line.split(' ');
        item.setAttribute('aria-label', `Line ${index + 1}: ${line}`);
        const number = document.createElement('span');
        number.className = 'line-number'; number.textContent = index + 1;
        item.append(number);
        if (index === lines.length - 1) {
          item.classList.add('is-final');
          const digits = document.createElement('span'); digits.className = 'line-words'; digits.textContent = line;
          const label = document.createElement('span'); label.className = 'line-label'; label.textContent = 'final checksum';
          item.append(digits, label);
        } else {
          const text = (className, value) => { const span = document.createElement('span'); span.className = className; span.textContent = value; return span; };
          item.append(text('line-words', tokens.slice(0, -2).join(' ')), text('line-casing', tokens.at(-2)), text('line-checksum', tokens.at(-1)));
        }
        item.addEventListener('click', () => { selectLine(index); viewer.focus({ preventScroll: true }); });
        return item;
      }));
      viewer.hidden = false;
      selectLine(0);
      viewer.focus({ preventScroll: true });
    }

    function clear() { viewer.hidden = true; lineList.replaceChildren(); shownLines = []; }

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

    // Copies the lines as typed on the other device: no line numbers, final checksum last.
    viewer.querySelector('[data-action=copy-lines]').addEventListener('click', () => copyText(shownLines.join('\n'), viewer.querySelector('.sb58-copy-status')));

    return { show, clear };
  }

  globalThis.SB58Viewer = { setupViewer };
})();
