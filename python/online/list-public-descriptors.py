#!/usr/bin/env python3
"""
List the public descriptors of a wallet that already exists in Bitcoin Core, by its
name. The wallet is loaded first if it is not loaded yet. Only public descriptors
are returned: listdescriptors is never asked for private keys.
"""
import argparse
import json
import re
import subprocess
import sys

BITCOIN_CLI = "bitcoin-cli"
TIMEOUT_SECONDS = 120
WALLET_NAME = re.compile(r"[A-Za-z0-9._-]+")
PRIVATE_KEY = re.compile(r"[xt]prv[1-9A-HJ-NP-Za-km-z]+")
WALLET_NOT_LOADED = "error code: -18"


def run_cli(args, datadir=None):
  # Mainnet only: without -datadir, bitcoin-cli uses Bitcoin Core's default data directory
  options = [f"-datadir={datadir}"] if datadir else []
  try:
      done = subprocess.run(
          [BITCOIN_CLI, *options, *args],
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


def list_public_descriptors(wallet, datadir=None):
  if not isinstance(wallet, str) or not WALLET_NAME.fullmatch(wallet):
      raise ValueError("Wallet name may only contain letters, digits, dots, dashes and underscores")
  datadir = datadir.strip() if isinstance(datadir, str) else datadir
  if datadir is not None and (
      not isinstance(datadir, str) or len(datadir) > 4096 or not datadir.isprintable()
  ):
      raise ValueError("Data directory must be a path without control characters")

  list_args = [f"-rpcwallet={wallet}", "listdescriptors"]
  try:
      output = run_cli(list_args, datadir)
  except ValueError as error:
      if WALLET_NOT_LOADED not in str(error):
          raise
      # The wallet exists on disk but is not loaded: load it, then ask again
      run_cli(["loadwallet", wallet], datadir)
      output = run_cli(list_args, datadir)
  try:
      listed = json.loads(output)
  except ValueError:
      raise ValueError(f"Unexpected output from {BITCOIN_CLI}")

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
  parser.add_argument("wallet", help="Name of the wallet in Bitcoin Core")
  parser.add_argument("--datadir", help="Bitcoin Core data directory (default: Bitcoin Core's own default)")
  args = parser.parse_args()
  try:
      listed = list_public_descriptors(args.wallet, args.datadir)
  except ValueError as error:
      raise SystemExit(str(error))
  for descriptor in listed["descriptors"]:
      print("change " if descriptor["internal"] else "receive", descriptor["desc"])


if __name__ == "__main__":
  main()
