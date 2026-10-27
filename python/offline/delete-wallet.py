#!/usr/bin/env python3
"""
Delete a wallet from Bitcoin Core by its name. Bitcoin Core has no command for this,
so the wallet is unloaded and its folder is removed from the wallets directory
(<data directory>/wallets/<name>). This cannot be undone: if the wallet holds private
keys, make sure you can restore it from your backup.

Safety checks, in order: Bitcoin Core must be running and list a wallet with this
name, the folder must be a real folder directly inside the wallets directory, and
it may only contain known wallet files. If anything else is in it, nothing is
deleted. Only the default wallets directory is supported: <data directory>/wallets
on mainnet, or <data directory>/<network>/wallets on a test network.
"""
import argparse
import json
import re
import subprocess
import sys
from pathlib import Path

BITCOIN_CLI = "bitcoin-cli"
TIMEOUT_SECONDS = 120
WALLET_NAME = re.compile(r"[A-Za-z0-9._-]+")
WALLET_NOT_LOADED = "error code: -18"
# Bitcoin Core chain name -> folder of that network inside the data directory
CHAIN_FOLDERS = {"main": "", "test": "testnet3", "testnet4": "testnet4", "signet": "signet", "regtest": "regtest"}
WALLET_FILES = {"wallet.dat", "wallet.dat-journal", "wallet.dat-shm", "wallet.dat-wal", ".walletlock", "db.log"}


def default_datadir():
  if sys.platform == "darwin":
      return Path.home() / "Library" / "Application Support" / "Bitcoin"
  if sys.platform == "win32":
      return Path.home() / "AppData" / "Roaming" / "Bitcoin"
  return Path.home() / ".bitcoin"


def run_cli(args, datadir=None):
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
      raise ValueError((done.stderr or done.stdout).strip() or f"{BITCOIN_CLI} exited with status {done.returncode}")
  return done.stdout


def delete_wallet(wallet, confirm, datadir=None):
  if not isinstance(wallet, str) or not WALLET_NAME.fullmatch(wallet) or wallet.startswith("."):
      raise ValueError("Wallet name may only contain letters, digits, dots, dashes and underscores, and cannot start with a dot")
  if confirm != wallet:
      raise ValueError("Type the wallet name to confirm that you want to delete it")
  datadir = datadir.strip() if isinstance(datadir, str) else datadir
  if datadir is not None and (
      not isinstance(datadir, str) or len(datadir) > 4096 or not datadir.isprintable()
  ):
      raise ValueError("Data directory must be a path without control characters")

  # Bitcoin Core must be running, so that the wallet can be unloaded and is not in use
  try:
      output = run_cli(["listwalletdir"], datadir)
  except ValueError as error:
      raise ValueError(f"{error}. Bitcoin Core must be running to delete a wallet safely")
  try:
      listed = json.loads(output)
  except ValueError:
      raise ValueError(f"Unexpected output from {BITCOIN_CLI}")
  if wallet not in {item["name"] for item in listed["wallets"]}:
      raise ValueError(f"Bitcoin Core has no wallet named {wallet}")

  output = run_cli(["getblockchaininfo"], datadir)
  try:
      chain_folder = CHAIN_FOLDERS[json.loads(output)["chain"]]
  except (ValueError, KeyError):
      raise ValueError(f"Unexpected output from {BITCOIN_CLI}")
  wallets_dir = (Path(datadir).expanduser() if datadir else default_datadir()) / chain_folder / "wallets"
  target = wallets_dir / wallet
  if not wallets_dir.is_dir() or not target.exists():
      raise ValueError(
          f"Bitcoin Core lists {wallet}, but there is no folder {target}. "
          "If you use -walletdir, delete the wallet folder by hand"
      )
  if target.is_symlink() or not target.is_dir() or target.resolve().parent != wallets_dir.resolve():
      raise ValueError(f"{target} is not a plain wallet folder, so it was not deleted")
  files = sorted(target.iterdir())
  unexpected = [path.name for path in files if path.name not in WALLET_FILES or path.is_symlink() or not path.is_file()]
  if unexpected or not (target / "wallet.dat").is_file():
      raise ValueError(
          f"{target} does not look like a descriptor wallet folder"
          + (f" (unexpected: {', '.join(unexpected)})" if unexpected else "")
          + ", so nothing was deleted"
      )

  try:
      run_cli(["unloadwallet", wallet], datadir)
  except ValueError as error:
      if WALLET_NOT_LOADED not in str(error):
          raise

  for path in files:
      path.unlink()
  target.rmdir()
  return {"wallet": wallet, "path": str(target)}


def main():
  parser = argparse.ArgumentParser()
  parser.add_argument("wallet", help="Name of the wallet to delete")
  parser.add_argument("--datadir", help="Bitcoin Core data directory (default: Bitcoin Core's own default)")
  args = parser.parse_args()
  print(f"This permanently deletes the wallet {args.wallet}.", file=sys.stderr)
  confirm = input(f"Type {args.wallet} to confirm: ")
  try:
      deleted = delete_wallet(args.wallet, confirm, args.datadir)
  except ValueError as error:
      raise SystemExit(str(error))
  print(f"Deleted wallet {deleted['wallet']}: removed {deleted['path']}")


if __name__ == "__main__":
  main()
