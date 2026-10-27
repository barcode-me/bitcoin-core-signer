#!/usr/bin/env python3
"""
Create a blank wallet in Bitcoin Core, import private descriptors into it and list
the wallet's public descriptors. Run this offline, because the descriptors contain
private keys.

The descriptors are the "importdescriptors" requests from convert-bip39-to-core.py.
They are sent to bitcoin-cli on stdin (-stdin) instead of the command line, so they
do not show up in the process list. bitcoin-cli runs directly, without a shell.
"""
import argparse
import json
import re
import subprocess
import sys

BITCOIN_CLI = "bitcoin-cli"
TIMEOUT_SECONDS = 120
WALLET_NAME = re.compile(r"[A-Za-z0-9._-]+")
DESCRIPTOR = re.compile(r"[A-Za-z0-9()/*#]+")
PRIVATE_KEY = re.compile(r"[xt]prv[1-9A-HJ-NP-Za-km-z]+")
REQUEST_KEYS = {"desc", "active", "internal", "range", "timestamp"}
NETWORK_NAMES = {"main", "test", "testnet4", "signet", "regtest"}


def run_cli(args, stdin=None, datadir=None):
  # Mainnet only: without -datadir, bitcoin-cli uses Bitcoin Core's default data directory
  options = [f"-datadir={datadir}"] if datadir else []
  try:
      done = subprocess.run(
          [BITCOIN_CLI, *options, *args],
          input=stdin,
          capture_output=True,
          text=True,
          timeout=TIMEOUT_SECONDS,
      )
  except FileNotFoundError:
      raise ValueError(f"{BITCOIN_CLI} was not found. Install Bitcoin Core and make sure it is on your PATH")
  except subprocess.TimeoutExpired:
      raise ValueError(f"{BITCOIN_CLI} did not finish within {TIMEOUT_SECONDS} seconds")
  if done.returncode != 0:
      message = (done.stderr or done.stdout).strip() or f"{BITCOIN_CLI} exited with status {done.returncode}"
      raise ValueError(PRIVATE_KEY.sub("[private key hidden]", message))
  return done.stdout


def run_cli_json(args, stdin=None, datadir=None):
  output = run_cli(args, stdin, datadir)
  try:
      return json.loads(output)
  except ValueError:
      raise ValueError(f"Unexpected output from {BITCOIN_CLI}")


def check_requests(requests):
  if not isinstance(requests, list) or not 1 <= len(requests) <= 8:
      raise ValueError("Expected 1 to 8 descriptor import requests")
  for request in requests:
      if (
          not isinstance(request, dict)
          or set(request) != REQUEST_KEYS
          or not isinstance(request["desc"], str)
          or not DESCRIPTOR.fullmatch(request["desc"])
          or not isinstance(request["active"], bool)
          or not isinstance(request["internal"], bool)
          or request["timestamp"] != "now"
          or not isinstance(request["range"], list)
          or len(request["range"]) != 2
          or not all(type(n) is int and n >= 0 for n in request["range"])
      ):
          raise ValueError("Invalid descriptor import request")


def import_descriptors(wallet, requests, datadir=None, network="main"):
  if not isinstance(wallet, str) or not WALLET_NAME.fullmatch(wallet):
      raise ValueError("Wallet name may only contain letters, digits, dots, dashes and underscores")
  check_requests(requests)
  if network not in NETWORK_NAMES:
      raise ValueError(f"Unknown network: {network}")
  datadir = datadir.strip() if isinstance(datadir, str) else datadir
  if datadir is not None and (
      not isinstance(datadir, str) or len(datadir) > 4096 or not datadir.isprintable()
  ):
      raise ValueError("Data directory must be a path without control characters")

  # Mainnet keys (xprv/xpub) only work on mainnet, test network keys (tprv/tpub) only on test networks
  chain = run_cli_json(["getblockchaininfo"], datadir=datadir).get("chain")
  if chain != network:
      raise ValueError(
          f"Bitcoin Core is running on {chain}, but the network chosen on this page is {network}, "
          "so no wallet was created. Choose the network Bitcoin Core runs on, or check the data directory"
      )

  # Blank: the wallet makes no keys of its own, it only holds the imported descriptors
  run_cli(["-named", "createwallet", f"wallet_name={wallet}", "blank=true"], datadir=datadir)

  results = run_cli_json([f"-rpcwallet={wallet}", "-stdin", "importdescriptors"], json.dumps(requests) + "\n", datadir)
  failures = [
      f"descriptor {number}: {result.get('error', {}).get('message', 'failed')}"
      for number, result in enumerate(results, 1)
      if not result.get("success")
  ]
  if failures:
      # Bitcoin Core's messages quote the descriptor, private key included
      raise ValueError(PRIVATE_KEY.sub("[private key hidden]",
          f"Created wallet {wallet}, but {len(failures)} of {len(requests)} descriptors "
          f"were not imported ({'; '.join(failures)})"
      ))

  # Without "true", listdescriptors gives the public descriptors
  listed = run_cli_json([f"-rpcwallet={wallet}", "listdescriptors"], datadir=datadir)
  return {
      "wallet": wallet,
      "descriptors": [
          {
              "desc": PRIVATE_KEY.sub("[private key hidden]", item["desc"]),
              "internal": bool(item.get("internal")),
              "active": bool(item.get("active")),
          }
          for item in listed["descriptors"]
      ],
  }


def main():
  parser = argparse.ArgumentParser()
  parser.add_argument("--wallet", default="my-wallet", help="Name of the wallet to create (default: my-wallet)")
  parser.add_argument("--datadir", help="Bitcoin Core data directory (default: Bitcoin Core's own default)")
  parser.add_argument("--network", choices=sorted(NETWORK_NAMES), default="main", help="Bitcoin network, as Bitcoin Core names it (default: main)")
  args = parser.parse_args()

  print("Paste the importdescriptors requests as a JSON array, then press Ctrl-D.", file=sys.stderr)
  try:
      imported = import_descriptors(args.wallet, json.loads(sys.stdin.read()), args.datadir, args.network)
  except ValueError as error:
      raise SystemExit(str(error))

  print(f"Created wallet {imported['wallet']} and imported the descriptors.")
  for descriptor in imported["descriptors"]:
      print("change " if descriptor["internal"] else "receive", descriptor["desc"])


if __name__ == "__main__":
  main()
