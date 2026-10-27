import { createHash } from 'node:crypto';
import { spawn } from 'node:child_process';
import { readdir, readFile } from 'node:fs/promises';
import { join } from 'node:path';
import { fileURLToPath } from 'node:url';
import { setTimeout as delay } from 'node:timers/promises';

const root = fileURLToPath(new URL('../', import.meta.url));
const sources = ['pages/templates', 'pages/assets', 'python', 'scripts/build-pages.mjs'];
let stopping = false;
let child;

// Compare actual source contents: build output and filesystem metadata events
// cannot trigger a rebuild. Polling also works on Linux and mounted folders.
async function fingerprint() {
  const hash = createHash('sha256');
  async function visit(path) {
    let entries;
    try {
      entries = await readdir(join(root, path), { withFileTypes: true });
    } catch (error) {
      if (error.code === 'ENOENT') return;
      if (error.code !== 'ENOTDIR') throw error;
      hash.update(JSON.stringify(path));
      hash.update(createHash('sha256').update(await readFile(join(root, path))).digest());
      return;
    }
    for (const entry of entries.sort((a, b) => a.name.localeCompare(b.name))) {
      if (entry.isDirectory() || entry.isFile()) await visit(join(path, entry.name));
    }
  }
  for (const source of sources) await visit(source);
  return hash.digest('hex');
}

async function build() {
  await new Promise(resolve => {
    child = spawn(process.execPath, ['scripts/build-pages.mjs'], { cwd: root, stdio: 'inherit' });
    child.once('error', error => console.error(`Build could not start: ${error.message}`));
    child.once('close', code => {
      child = undefined;
      if (code && !stopping) console.error('Build failed. Waiting for source changes.');
      resolve();
    });
  });
}

for (const signal of ['SIGINT', 'SIGTERM']) {
  process.on(signal, () => { stopping = true; child?.kill(signal); });
}

let previous = await fingerprint();
await build();
console.log('Watching templates, assets, and build script for content changes. Press Ctrl-C to stop.');
while (!stopping) {
  await delay(750);
  if (stopping) break;
  try {
    const current = await fingerprint();
    if (current === previous) continue;
    // Wait for a save burst to settle before starting a build.
    await delay(150);
    if (stopping) break;
    const settled = await fingerprint();
    if (current !== settled) continue;
    previous = settled;
    await build();
  } catch (error) {
    console.error(`Could not check sources: ${error.message}`);
  }
}
