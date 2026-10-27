import { cp, mkdir, readFile, rm, writeFile } from 'node:fs/promises';
import { dirname, join, posix, relative } from 'node:path';
import { fileURLToPath } from 'node:url';
import Handlebars from 'handlebars';

const root = fileURLToPath(new URL('../', import.meta.url));
const templates = join(root, 'pages/templates');
const output = join(root, 'build');
const sections = [
  { slug: 'setup-devices', title: 'Setup Devices', description: 'Setup devices needed for signing transactions.' },
  { slug: 'create-wallet', title: 'Create Wallet', description: 'Create a wallet securely and privatetly.' },
  { slug: 'sign-transaction', title: 'Sign Transaction', description: 'How to sign a transaction in Bitcoin Core with BIP39.' },
  { slug: 'transport-backup', title: 'Transport Backup', description: 'How to transport backups securely and privately.' },
  { slug: 'recover-from-backup', title: 'Recover from backup', description: 'Restore your wallet and verify recovery.' },
  { slug: 'encrypt-your-backups', title: 'Encrypt your backups', description: 'Encrypt a seed phrase or extended private key backup.' },
  { slug: 'faq', title: 'FAQ', description: 'Frequently asked questions.', standalone: true },
];
for (const section of sections) {
  if (section.standalone) {
    section.href = `/${section.slug}/`;
    continue;
  }
  const steps = JSON.parse(await readFile(join(templates, section.slug, 'steps.json'), 'utf8'));
  if (!steps.length || steps.some(step => !/^[a-z0-9]+(?:-[a-z0-9]+)*$/.test(step.slug)) || new Set(steps.map(step => step.slug)).size !== steps.length) {
    throw new Error(`${section.title}: steps must have unique URL-safe slugs.`);
  }
  section.steps = steps.map((step, index) => ({ ...step, href: `/${section.slug}/${step.slug}/`, number: index + 1 }));
  section.href = section.steps[0].href;
}

// Render first so a template error does not remove the previous successful build.
Handlebars.registerPartial('layout', await readFile(join(templates, 'shared/layout.hbs'), 'utf8'));
Handlebars.registerPartial('code-block', await readFile(join(templates, 'shared/code-block.hbs'), 'utf8'));
Handlebars.registerPartial('important-callout', await readFile(join(templates, 'shared/important-callout.hbs'), 'utf8'));
Handlebars.registerPartial('flow-header', await readFile(join(templates, 'shared/flow-header.hbs'), 'utf8'));
Handlebars.registerPartial('flow-navigation', await readFile(join(templates, 'shared/flow-navigation.hbs'), 'utf8'));
Handlebars.registerPartial('node-settings', await readFile(join(templates, 'shared/node-settings.hbs'), 'utf8'));
const rendered = [];
// Python files a step shows and runs, read once so the page and the script cannot drift apart.
async function readScripts(step) {
  return Object.fromEntries(await Promise.all(Object.entries(step.scripts ?? {}).map(
    async ([name, file]) => [name, (await readFile(join(root, file), 'utf8')).trimEnd()],
  )));
}
async function renderPage(template, filename, context = {}) {
  const render = Handlebars.compile(await readFile(join(templates, template), 'utf8'), { preventIndent: true });
  // Resolve site routes from this output page, not from the web server root.
  const pageDirectory = posix.dirname(filename);
  const pageHref = href => {
    const target = href.replace(/^\//, '');
    return posix.relative(pageDirectory, href.endsWith('/') ? `${target}index.html` : target);
  };
  const localLink = item => ({ ...item, href: pageHref(item.href) });
  const html = render({
    siteTitle: 'Bitcoin Core BIP39 Signer',
    isIndex: filename === 'index.html',
    sections: sections.map(section => ({
      ...localLink(section),
      isCurrentFlow: filename.startsWith(`${section.slug}/`),
      isCurrent: filename === `${section.slug}/index.html`,
      steps: section.steps?.map(step => ({ ...localLink(step), isCurrent: filename === `${section.slug}/${step.slug}/index.html` })),
    })),
    ...context,
    homeHref: pageHref('/'),
    assetsHref: pageHref('/assets'),
    stylesheetHref: pageHref('/assets/style.css'),
    steps: context.steps?.map(localLink),
    previous: context.previous && localLink(context.previous),
    next: context.next && localLink(context.next),
  });
  rendered.push({ filename, html });
}
await renderPage('index.hbs', 'index.html');
for (const section of sections) {
 if (section.standalone) {
  await renderPage(`${section.slug}/index.hbs`, `${section.slug}/index.html`, {
    pageTitle: section.title,
    description: section.description,
  });
  continue;
 }
 const steps = section.steps;
 for (const [index, step] of steps.entries()) {
  await renderPage(`${section.slug}/${step.slug}.hbs`, `${section.slug}/${step.slug}/index.html`, {
    pageTitle: `${step.title} · ${section.title}`,
    flowTitle: section.title,
    description: step.description,
    stepTitle: step.title,
    stepNumber: step.number,
    scripts: await readScripts(step),
    stepCount: steps.length,
    steps: steps.map(item => ({ ...item, isCurrent: item.slug === step.slug })),
    previous: index ? steps[index - 1] : { href: '/', title: 'Contents' },
    next: steps[index + 1] || { href: '/', title: 'Back to contents' },
    isLastStep: index === steps.length - 1,
  });
 }
}
await rm(output, { recursive: true, force: true });
await mkdir(output, { recursive: true });
for (const { filename, html } of rendered) {
  await mkdir(dirname(join(output, filename)), { recursive: true });
  await writeFile(join(output, filename), html);
}
await cp(join(root, 'pages/assets'), join(output, 'assets'), { recursive: true });
console.log(`Built ${rendered.length} pages in ${relative(root, output)}/`);
