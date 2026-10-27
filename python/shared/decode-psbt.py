#!/usr/bin/env python3
"""
Show what an unsigned transaction (PSBT) does before signing it: where each output
goes, how much, and the fee. Bitcoin Core reads the PSBT with decodepsbt and
analyzepsbt. With a wallet name, it also asks the wallet (getaddressinfo) which
outputs pay back to it, which is the change. Nothing is signed or sent.

The PSBT is base64, sent to bitcoin-cli on stdin (-stdin). Bitcoin Core does not need
to be online for this.
"""
import argparse
import json
import re
import subprocess
import sys
from decimal import Decimal

BITCOIN_CLI = "bitcoin-cli"
TIMEOUT_SECONDS = 120
WALLET_NAME = re.compile(r"[A-Za-z0-9._-]+")
BASE64 = re.compile(r"[A-Za-z0-9+/]+={0,2}")
WALLET_NOT_LOADED = "error code: -18"
SATS_PER_BTC = 100_000_000
# analyzepsbt "next": who works on the PSBT next
NEXT_STEPS = {
    "creator": "not created yet",
    "updater": "missing information to sign it",
    "signer": "not signed yet",
    "finalizer": "signed, not finalized",
    "extractor": "signed and ready to send",
}


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


def run_cli_json(args, stdin=None, datadir=None):
  output = run_cli(args, stdin, datadir)
  try:
      return json.loads(output, parse_float=Decimal)
  except ValueError:
      raise ValueError(f"Unexpected output from {BITCOIN_CLI}")


def to_sats(btc):
  return int(Decimal(btc) * SATS_PER_BTC)


def decode_psbt(psbt, wallet=None, datadir=None):
  psbt = psbt.strip() if isinstance(psbt, str) else psbt
  if not isinstance(psbt, str) or not BASE64.fullmatch(psbt):
      raise ValueError("The PSBT must be base64")
  if wallet is not None and (not isinstance(wallet, str) or not WALLET_NAME.fullmatch(wallet)):
      raise ValueError("Wallet name may only contain letters, digits, dots, dashes and underscores")
  datadir = datadir.strip() if isinstance(datadir, str) else datadir
  if datadir is not None and (
      not isinstance(datadir, str) or len(datadir) > 4096 or not datadir.isprintable()
  ):
      raise ValueError("Data directory must be a path without control characters")

  decoded = run_cli_json(["-stdin", "decodepsbt"], psbt + "\n", datadir)
  analyzed = run_cli_json(["-stdin", "analyzepsbt"], psbt + "\n", datadir)

  def is_mine(address):
      if wallet is None or address is None:
          return None
      args = [f"-rpcwallet={wallet}", "getaddressinfo", address]
      try:
          return bool(run_cli_json(args, datadir=datadir).get("ismine"))
      except ValueError as error:
          if WALLET_NOT_LOADED not in str(error):
              raise
          # The wallet exists on disk but is not loaded: load it, then ask again
          run_cli(["loadwallet", wallet], datadir=datadir)
          return bool(run_cli_json(args, datadir=datadir).get("ismine"))

  outputs = [
      {
          "address": output["scriptPubKey"].get("address"),
          "amount_sats": to_sats(output["value"]),
          "is_mine": is_mine(output["scriptPubKey"].get("address")),
      }
      for output in decoded["tx"]["vout"]
  ]
  fee = decoded.get("fee")
  vsize = analyzed.get("estimated_vsize")
  next_step = analyzed.get("next")
  return {
      "txid": decoded["tx"]["txid"],
      "inputs": len(decoded["tx"]["vin"]),
      "outputs": outputs,
      # Only known when the PSBT includes the coins it spends
      "fee_sats": None if fee is None else to_sats(fee),
      "vsize": vsize,
      "fee_rate": None if fee is None or not vsize else f"{Decimal(to_sats(fee)) / vsize:.2f}",
      "status": NEXT_STEPS.get(next_step, next_step),
      "wallet": wallet,
  }


def main():
  parser = argparse.ArgumentParser()
  parser.add_argument("--wallet", help="Wallet to ask which outputs are change (default: none)")
  parser.add_argument("--datadir", help="Bitcoin Core data directory (default: Bitcoin Core's own default)")
  args = parser.parse_args()
  print("Paste the PSBT in base64, then press Ctrl-D.", file=sys.stderr)
  try:
      decoded = decode_psbt(sys.stdin.read(), args.wallet, args.datadir)
  except ValueError as error:
      raise SystemExit(str(error))
  for output in decoded["outputs"]:
      mine = {True: "  (this wallet: change)", False: "", None: ""}[output["is_mine"]]
      print(f"{output['amount_sats']:>16,} sats  to {output['address'] or '(no address)'}{mine}")
  fee = "unknown" if decoded["fee_sats"] is None else f"{decoded['fee_sats']:,} sats ({decoded['fee_rate']} sat/vB)"
  print(f"Fee: {fee}\nInputs: {decoded['inputs']}\nStatus: {decoded['status']}\nTransaction ID: {decoded['txid']}")


if __name__ == "__main__":
  main()
