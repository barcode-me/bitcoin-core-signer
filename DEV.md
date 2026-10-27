Build the static pages with Node.js and npm:

```sh
npm install
npm run build
```

For automatic rebuilds while editing (Node.js 22 or newer):

```sh
npm run dev
```

This builds once, then watches templates, assets, and the build script for changes. Stop with Ctrl-C. It does not start a web server or refresh the browser automatically; reload the page after a rebuild.

Serve `build/` as the root of a static web server, for example:

```sh
python3 -m http.server 8000 --directory build
```

Visit http://localhost:8000/. Routes use directory indexes, such as `/setup-devices/prepare/`, `/setup-devices/export/`, and `/setup-devices/inspect/`. A static server serves each route's `index.html`; no client-side router or Node.js runtime is needed. Links and assets are relative to each generated page, so the build can also be hosted under a subdirectory. Navigation explicitly includes `index.html`, so opening `build/index.html` directly also supports all step links. Static servers can still serve the equivalent clean directory URLs.

Only generated HTML and assets are placed in `build/`. Handlebars and `node_modules/` are build-time dependencies and are not included.

## Editing pages

- Shared HTML shell and site navigation: `pages/templates/shared/layout.hbs`
- Table of contents page: `pages/templates/index.hbs`
- Backup step templates and ordered metadata: `pages/templates/setup-devices/`
- Shared stylesheet: `pages/assets/style.css`
- Build script and top-level table of contents entries: `scripts/build-pages.mjs`

To add a backup step, add an entry to `pages/templates/setup-devices/steps.json` with a unique `slug`, `title`, and `description`. Create a matching `<slug>.hbs` file in that same directory:

```handlebars
{{#> layout}}
{{> flow-header}}
<section>
  <h2>Your step heading</h2>
  <p>Your instructions.</p>
</section>
{{> flow-navigation}}
{{/layout}}
```

The build generates `/setup-devices/<slug>/index.html`. Step numbering and Back/Next links follow the order in `steps.json`. The first step links back to Contents; the last links back to Contents after completion.

Run `npm run build` after editing. The build replaces the generated `build/` directory, so edit source templates rather than generated files.

Existing `pages/index.html`, `pages/test.html`, and `pages/app.js` are preserved as original notes and are not included in the build.

## Shared code blocks

Use the `code-block` partial for shell, Python, or plain-text examples:

```handlebars
{{#> code-block}}echo "Hello"
echo "World"{{/code-block}}
```

The defaults are `caption="Shell"` and `language="bash"`. Override them with `caption="Python" language="python"` for Python, or `caption="Text" language="text"` for plain text. Code blocks do not use IDs. Keep the first code character immediately after the opening partial call and the closing call immediately after the last code character; all whitespace inside the block is preserved. Escape HTML characters in the code (`&lt;`, `&gt;`, `&amp;`) as in ordinary HTML templates.

The wrapper, accessible caption, and language class are defined once in `pages/templates/shared/code-block.hbs`.

## Shared flows

`pages/templates/shared/` contains the common layout, flow header, Back/Next navigation, code block, and IMPORTANT callout. Both flows use these partials.

## Python scripts

The lean flow's scripts live in `python/lean/` and run in a terminal; the pages only show the commands. Third-party packages go in `python/requirements.txt`. Set up the environment with `python3 -m venv python/venv`, `source python/venv/bin/activate` and `pip3 install -r python/requirements.txt`. `python/venv/` is git-ignored.

## Publishing

`.github/workflows/publish.yml` builds the pages on every push to `main` and deploys `build/` to GitHub Pages. In the repository settings, set Pages → Source to "GitHub Actions" once.

To publish a release, push a tag starting with `v`:

```sh
git tag v1.0.0
git push origin v1.0.0
```

The workflow then creates a GitHub release for the tag with `bitcoin-core-signer-v1.0.0.zip`, containing the built pages (`build/`), the Python scripts (`python/`) and `README.md`.

## Testing with bitcoin regtest

```sh
mkdir -p ~/btc-regtest
printf 'regtest=1\nfallbackfee=0.0001\n' > ~/btc-regtest/bitcoin.conf
bitcoind -datadir=$HOME/btc-regtest -daemon

alias rcli="bitcoin-cli -datadir=$HOME/btc-regtest"
rcli createwallet my-wallet
# Mine 101 blocks to the wallet: the first block's 50 BTC can be spent after 100 more
rcli -rpcwallet=my-wallet generatetoaddress 101 $(rcli -rpcwallet=my-wallet getnewaddress)
rcli -rpcwallet=my-wallet getbalance          # 50.00000000
rcli -rpcwallet=my-wallet getnewaddress       # a bcrt1q... address to send to
```