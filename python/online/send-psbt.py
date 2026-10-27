#!/usr/bin/env python3
"""
Send a signed transaction (PSBT) to the Bitcoin network with Bitcoin Core.

Bitcoin Core turns the signed PSBT into the final transaction with finalizepsbt,
then broadcasts it with sendrawtransaction. If the PSBT is not fully signed, nothing
is sent. Both are sent to bitcoin-cli on stdin (-stdin). Once sent, a transaction
cannot be undone.
"""
import argparse
import json
import re
import subprocess
import sys

BITCOIN_CLI = "bitcoin-cli"
TIMEOUT_SECONDS = 120
BASE64 = re.compile(r"[A-Za-z0-9+/]+={0,2}")
TXID = re.compile(r"[0-9a-f]{64}")


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
      raise ValueError((done.stderr or done.stdout).strip() or f"{BITCOIN_CLI} exited with status {done.returncode}")
  return done.stdout


def send_psbt(psbt, datadir=None):
  psbt = psbt.strip() if isinstance(psbt, str) else psbt
  if not isinstance(psbt, str) or not BASE64.fullmatch(psbt):
      raise ValueError("The PSBT must be base64")
  datadir = datadir.strip() if isinstance(datadir, str) else datadir
  if datadir is not None and (
      not isinstance(datadir, str) or len(datadir) > 4096 or not datadir.isprintable()
  ):
      raise ValueError("Data directory must be a path without control characters")

  output = run_cli(["-stdin", "finalizepsbt"], psbt + "\n", datadir)
  try:
      finalized = json.loads(output)
  except ValueError:
      raise ValueError(f"Unexpected output from {BITCOIN_CLI}")
  if not finalized.get("complete") or not finalized.get("hex"):
      raise ValueError("This transaction is not fully signed, so it was not sent. Sign it on the offline device first")

  txid = run_cli(["-stdin", "sendrawtransaction"], finalized["hex"] + "\n", datadir).strip()
  if not TXID.fullmatch(txid):
      raise ValueError(f"Unexpected output from {BITCOIN_CLI}")
  return {"txid": txid}


def main():
  parser = argparse.ArgumentParser()
  parser.add_argument("--datadir", help="Bitcoin Core data directory (default: Bitcoin Core's own default)")
  args = parser.parse_args()
  print("Paste the signed PSBT in base64, then press Ctrl-D.", file=sys.stderr)
  try:
      sent = send_psbt(sys.stdin.read(), args.datadir)
  except ValueError as error:
      raise SystemExit(str(error))
  print(f"Sent. Transaction ID: {sent['txid']}")


if __name__ == "__main__":
  main()
