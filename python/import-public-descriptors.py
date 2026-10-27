#!/usr/bin/env python3
"""
Create an empty watch-only wallet in Bitcoin Core and import public descriptors
into it, or import them into a watch-only wallet that already exists (it is loaded
first if needed). The wallet has no private keys: it can see balances and create
transactions to be signed on the offline device, but cannot spend by itself.

Each descriptor must end in /0/* (receive) or /1/* (change). Both are imported as
active descriptors for addresses 0 to 999. Bitcoin Core only finds transactions
made after the date to look from, so give the date the wallet was created when it
has received bitcoin before. Leaving it empty imports from now, which is instant.
Scanning the blockchain from an older date can take hours, and needs the blocks of
that time, which a pruned node does not have.

bitcoin-cli runs directly, without a shell, with the descriptors on stdin (-stdin).
"""
import argparse
import json
import re
import subprocess
import sys
from datetime import datetime, timezone

BITCOIN_CLI = "bitcoin-cli"
TIMEOUT_SECONDS = 120
WALLET_NAME = re.compile(r"[A-Za-z0-9._-]+")
DESCRIPTOR = re.compile(r"[A-Za-z0-9()\[\]/*'#]+")
BRANCH = re.compile(r"/([01])/\*\)+#[a-z0-9]{8}")
MAX_DESCRIPTORS = 8
WALLET_NOT_LOADED = "error code: -18"


def run_cli(args, stdin=None, datadir=None, timeout=TIMEOUT_SECONDS):
  # Mainnet only: without -datadir, bitcoin-cli uses Bitcoin Core's default data directory
  options = [f"-datadir={datadir}"] if datadir else []
  # A rescan has no time limit, so bitcoin-cli must wait for it too
  if timeout is None:
      options.append("-rpcclienttimeout=0")
  try:
      done = subprocess.run(
          [BITCOIN_CLI, *options, *args],
          input=stdin,
          capture_output=True,
          text=True,
          timeout=timeout,
      )
  except FileNotFoundError:
      raise ValueError(f"{BITCOIN_CLI} was not found. Install Bitcoin Core and make sure it is on your PATH")
  except subprocess.TimeoutExpired:
      raise ValueError(f"{BITCOIN_CLI} did not finish within {TIMEOUT_SECONDS} seconds")
  if done.returncode != 0:
      raise ValueError((done.stderr or done.stdout).strip() or f"{BITCOIN_CLI} exited with status {done.returncode}")
  return done.stdout


def run_cli_json(args, stdin=None, datadir=None, timeout=TIMEOUT_SECONDS):
  output = run_cli(args, stdin, datadir, timeout)
  try:
      return json.loads(output)
  except ValueError:
      raise ValueError(f"Unexpected output from {BITCOIN_CLI}")


def make_requests(descriptors, timestamp):
  if not isinstance(descriptors, list) or not 1 <= len(descriptors) <= MAX_DESCRIPTORS:
      raise ValueError(f"Expected 1 to {MAX_DESCRIPTORS} public descriptors")
  requests = []
  for number, descriptor in enumerate(descriptors, 1):
      if not isinstance(descriptor, str) or not DESCRIPTOR.fullmatch(descriptor):
          raise ValueError(f"Descriptor {number} is not a descriptor with a checksum")
      if "prv" in descriptor:
          raise ValueError("Refusing to import a private key. This wallet only holds public descriptors")
      branch = BRANCH.search(descriptor)
      if not branch or branch.end() != len(descriptor):
          raise ValueError(f"Descriptor {number} must end in /0/* (receive) or /1/* (change) and a checksum")
      requests.append({
          "desc": descriptor, "active": True, "internal": branch.group(1) == "1",
          "range": [0, 999], "timestamp": timestamp,
      })
  return requests


def import_public_descriptors(wallet, descriptors, datadir=None, rescan_since=None, create_wallet=True):
  if not isinstance(wallet, str) or not WALLET_NAME.fullmatch(wallet):
      raise ValueError("Wallet name may only contain letters, digits, dots, dashes and underscores")
  datadir = datadir.strip() if isinstance(datadir, str) else datadir
  if datadir is not None and (
      not isinstance(datadir, str) or len(datadir) > 4096 or not datadir.isprintable()
  ):
      raise ValueError("Data directory must be a path without control characters")
  timestamp = "now"
  if rescan_since:
      try:
          since = datetime.strptime(rescan_since, "%Y-%m-%d").replace(tzinfo=timezone.utc)
      except (TypeError, ValueError):
          raise ValueError("The date to look for transactions from must be like 2024-01-31")
      if since > datetime.now(timezone.utc):
          raise ValueError("The date to look for transactions from is in the future")
      timestamp = int(since.timestamp())
  requests = make_requests(descriptors, timestamp)

  if not isinstance(create_wallet, bool):
      raise ValueError("create_wallet must be true or false")
  if create_wallet:
      # wallet_name disable_private_keys blank passphrase avoid_reuse descriptors: an empty descriptor
      # wallet. Bitcoin Core only imports descriptors without private keys into a wallet without them.
      run_cli(["createwallet", wallet, "true", "true", "", "false", "true"], datadir=datadir)
  else:
      try:
          run_cli([f"-rpcwallet={wallet}", "getwalletinfo"], datadir=datadir)
      except ValueError as error:
          if WALLET_NOT_LOADED not in str(error):
              raise
          # The wallet exists on disk but is not loaded: load it first
          run_cli(["loadwallet", wallet], datadir=datadir)

  results = run_cli_json(
      [f"-rpcwallet={wallet}", "-stdin", "importdescriptors"], json.dumps(requests) + "\n", datadir,
      timeout=None if rescan_since else TIMEOUT_SECONDS,
  )
  failures = [
      f"descriptor {number}: {result.get('error', {}).get('message', 'failed')}"
      for number, result in enumerate(results, 1)
      if not result.get("success")
  ]
  if failures:
      raise ValueError(
          f"{'Created' if create_wallet else 'Using'} wallet {wallet}, but {len(failures)} of {len(requests)} descriptors "
          f"were not imported ({'; '.join(failures)})"
      )

  info = run_cli_json([f"-rpcwallet={wallet}", "getbalances"], datadir=datadir)
  return {
      "wallet": wallet,
      "created": create_wallet,
      "imported": len(requests),
      "rescan_since": rescan_since or None,
      "balance": info["mine"]["trusted"] + info["mine"]["untrusted_pending"],
  }


def main():
  parser = argparse.ArgumentParser()
  parser.add_argument("--wallet", default="my-wallet", help="Name of the watch-only wallet (default: my-wallet)")
  parser.add_argument("--existing", action="store_true", help="Import into a wallet that already exists instead of creating an empty one")
  parser.add_argument("--datadir", help="Bitcoin Core data directory (default: Bitcoin Core's own default)")
  parser.add_argument("--rescan-since", help="Look for transactions from this date, like 2024-01-31 (default: from now)")
  args = parser.parse_args()

  print("Paste the public descriptors, one per line, then press Ctrl-D.", file=sys.stderr)
  try:
      imported = import_public_descriptors(
          args.wallet, [line.strip() for line in sys.stdin if line.strip()], args.datadir, args.rescan_since, not args.existing
      )
  except ValueError as error:
      raise SystemExit(str(error))
  action = "Created watch-only wallet" if imported["created"] else "Imported into wallet"
  print(f"{action} {imported['wallet']}: {imported['imported']} public descriptors.")
  print(f"Balance: {imported['balance']:.8f} BTC")


if __name__ == "__main__":
  main()
