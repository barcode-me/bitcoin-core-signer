#!/usr/bin/env python3
"""
Create an unsigned transaction (PSBT) with the watch-only wallet in Bitcoin Core and
encode it as Super Base 58 (SB58) lines to type into the offline device.

Bitcoin Core picks the coins to spend and adds change, with walletcreatefundedpsbt:
  bitcoin-cli -rpcwallet=<wallet> -named walletcreatefundedpsbt \\
    outputs='[{"<address>": <amount in BTC>}]' options='{"subtractFeeFromOutputs":[0]}'
The amount can be given in BTC or sats. With subtract fee, the address receives the
amount minus the fee. Otherwise the fee is paid on top. The fee rate is in sat/vB;
without it Bitcoin Core estimates one.

The PSBT is base64. Its bytes are encoded as Base58. Every 4 Base58 characters make
one line:

  seven charlie tango bravo 01101 lima

4 NATO words (digits are spelled out, letters ignore casing), a casing string, and
a checksum word. The casing string has one bit per word plus one for the checksum
word (1 = uppercase, numbers are always 0). The checksum word is the Base58
character at position (sum of the 4 characters' positions) mod 58, written as its
word, so its casing bit is needed to tell X from x. The last line may have 1 to 4
words and a casing string one bit longer than its words. After
the lines comes the final checksum: the unsigned big-endian value of the last two
bytes of the SHA-256 hash of all the lines above, joined by newlines, written as 5
digits. It catches a missing, repeated or reordered line.

The wallet is loaded first if it is not loaded yet. Nothing is signed or sent.
"""
import argparse
import base64
import binascii
import hashlib
import json
import re
import subprocess
import sys
from decimal import Decimal, InvalidOperation

BITCOIN_CLI = "bitcoin-cli"
TIMEOUT_SECONDS = 120
WALLET_NAME = re.compile(r"[A-Za-z0-9._-]+")
ADDRESS = re.compile(r"[A-Za-z0-9]{14,90}")
WALLET_NOT_LOADED = "error code: -18"
PSBT_MAGIC = b"psbt\xff"
SATS_PER_BTC = 100_000_000
MAX_SATS = 21_000_000 * SATS_PER_BTC
MAX_FEE_RATE = Decimal(10000)
# Address type from the page -> Bitcoin Core change_type
CHANGE_TYPES = {"legacy": "legacy", "nested-segwit": "p2sh-segwit", "native-segwit": "bech32", "taproot": "bech32m"}

BASE58 = "123456789ABCDEFGHJKLMNPQRSTUVWXYZabcdefghijkmnopqrstuvwxyz"
LETTER_WORDS = {
    "a": "alfa", "b": "bravo", "c": "charlie", "d": "delta", "e": "echo",
    "f": "foxtrot", "g": "golf", "h": "hotel", "i": "india", "j": "juliett",
    "k": "kilo", "l": "lima", "m": "mike", "n": "november", "o": "oscar",
    "p": "papa", "q": "quebec", "r": "romeo", "s": "sierra", "t": "tango",
    "u": "uniform", "v": "victor", "w": "whiskey", "x": "x-ray", "y": "yankee",
    "z": "zulu",
}
DIGIT_WORDS = ["one", "two", "three", "four", "five", "six", "seven", "eight", "nine"]
CHARS_PER_LINE = 4


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
      raise ValueError((done.stderr or done.stdout).strip() or f"{BITCOIN_CLI} exited with status {done.returncode}")
  return done.stdout


def base58_encode(data):
  number = int.from_bytes(data, "big")
  encoded = ""
  while number:
      number, remainder = divmod(number, 58)
      encoded = BASE58[remainder] + encoded
  # Each leading zero byte is written as "1"
  return "1" * (len(data) - len(data.lstrip(b"\0"))) + encoded


def char_word(char):
  return DIGIT_WORDS[int(char) - 1] if char.isdigit() else LETTER_WORDS[char.lower()]


def checksum_char(chars):
  return BASE58[sum(BASE58.index(char) for char in chars) % 58]


def encode_sb58(data):
  encoded = base58_encode(data)
  lines = []
  for start in range(0, len(encoded), CHARS_PER_LINE):
      chunk = encoded[start:start + CHARS_PER_LINE]
      words = " ".join(char_word(char) for char in chunk)
      check = checksum_char(chunk)
      casing = "".join("1" if char.isupper() else "0" for char in chunk + check)
      lines.append(f"{words} {casing} {char_word(check)}")
  digest = hashlib.sha256("\n".join(lines).encode("utf-8")).digest()
  final_checksum = f"{int.from_bytes(digest[-2:], 'big'):05d}"
  # hex is the same bytes, for QR codes instead of lines
  return {"lines": lines, "final_checksum": final_checksum, "bytes": len(data), "base58_chars": len(encoded), "hex": data.hex()}


def amount_in_sats(amount, unit):
  try:
      value = Decimal(str(amount).strip())
  except InvalidOperation:
      raise ValueError("The amount must be a number")
  if not value.is_finite():
      raise ValueError("The amount must be a number")
  if unit == "btc":
      if value.as_tuple().exponent < -8:
          raise ValueError("A BTC amount has at most 8 decimals")
      sats = value * SATS_PER_BTC
  elif unit == "sats":
      sats = value
  else:
      raise ValueError("The unit must be btc or sats")
  if sats != sats.to_integral_value():
      raise ValueError("An amount in sats must be a whole number")
  if not 0 < sats <= MAX_SATS:
      raise ValueError("The amount must be more than 0 and at most 21,000,000 BTC")
  return int(sats)


def create_psbt(wallet, address, amount, unit, subtract_fee, fee_rate=None, change_type=None, datadir=None):
  if not isinstance(wallet, str) or not WALLET_NAME.fullmatch(wallet):
      raise ValueError("Wallet name may only contain letters, digits, dots, dashes and underscores")
  address = address.strip() if isinstance(address, str) else address
  if not isinstance(address, str) or not ADDRESS.fullmatch(address):
      raise ValueError("The destination must be a Bitcoin address of letters and digits only")
  sats = amount_in_sats(amount, unit)
  if not isinstance(subtract_fee, bool):
      raise ValueError("subtract_fee must be true or false")
  options = {"subtractFeeFromOutputs": [0]} if subtract_fee else {}
  if fee_rate not in (None, ""):
      try:
          rate = Decimal(str(fee_rate).strip())
      except InvalidOperation:
          raise ValueError("The fee rate must be a number of sat/vB")
      if not rate.is_finite() or not 0 < rate <= MAX_FEE_RATE or rate.as_tuple().exponent < -3:
          raise ValueError(f"The fee rate must be more than 0 and at most {MAX_FEE_RATE} sat/vB, with at most 3 decimals")
      options["fee_rate"] = rate
  if change_type is not None:
      if change_type not in CHANGE_TYPES:
          raise ValueError(f"Unknown address type for change: {change_type}")
      options["change_type"] = CHANGE_TYPES[change_type]
  datadir = datadir.strip() if isinstance(datadir, str) else datadir
  if datadir is not None and (
      not isinstance(datadir, str) or len(datadir) > 4096 or not datadir.isprintable()
  ):
      raise ValueError("Data directory must be a path without control characters")

  # Amounts are written as exact decimals, never as floats
  btc = f"{Decimal(sats) / SATS_PER_BTC:.8f}"
  outputs = f"[{{{json.dumps(address)}: {btc}}}]"
  options_json = "{" + ", ".join(f"{json.dumps(key)}: {format(value, "f") if isinstance(value, Decimal) else json.dumps(value)}" for key, value in options.items()) + "}"
  args = [f"-rpcwallet={wallet}", "-named", "walletcreatefundedpsbt", f"outputs={outputs}", f"options={options_json}"]
  try:
      output = run_cli(args, datadir)
  except ValueError as error:
      if WALLET_NOT_LOADED not in str(error):
          raise
      # The wallet exists on disk but is not loaded: load it, then ask again
      run_cli(["loadwallet", wallet], datadir)
      output = run_cli(args, datadir)
  try:
      funded = json.loads(output, parse_float=Decimal)
      psbt = base64.b64decode(funded["psbt"], validate=True)
  except (ValueError, KeyError, TypeError, binascii.Error):
      raise ValueError(f"Unexpected output from {BITCOIN_CLI}")
  if not psbt.startswith(PSBT_MAGIC):
      raise ValueError(f"{BITCOIN_CLI} did not return a PSBT")

  return {
      **encode_sb58(psbt),
      "psbt": funded["psbt"],
      "address": address,
      "amount_sats": sats,
      "fee_sats": int(funded["fee"] * SATS_PER_BTC),
      "subtract_fee": subtract_fee,
      "has_change": funded["changepos"] != -1,
  }


def main():
  parser = argparse.ArgumentParser()
  parser.add_argument("--wallet", default="my-wallet", help="Name of the watch-only wallet (default: my-wallet)")
  parser.add_argument("--datadir", help="Bitcoin Core data directory (default: Bitcoin Core's own default)")
  parser.add_argument("--address", required=True, help="Destination address")
  parser.add_argument("--amount", required=True, help="Amount to send")
  parser.add_argument("--unit", choices=["btc", "sats"], default="btc", help="Unit of the amount (default: btc)")
  parser.add_argument("--subtract-fee", action="store_true", help="Take the fee out of the amount instead of paying it on top")
  parser.add_argument("--fee-rate", help="Fee rate in sat/vB (default: Bitcoin Core's estimate)")
  parser.add_argument("--change-type", choices=sorted(CHANGE_TYPES), help="Address type for change (default: Bitcoin Core's)")
  args = parser.parse_args()
  try:
      created = create_psbt(
          args.wallet, args.address, args.amount, args.unit, args.subtract_fee, args.fee_rate, args.change_type, args.datadir
      )
  except ValueError as error:
      raise SystemExit(str(error))
  print(f"Fee: {created['fee_sats']} sats. Unsigned PSBT (base64):\n{created['psbt']}\n", file=sys.stderr)
  for number, line in enumerate(created["lines"], 1):
      print(f"{number:>4}  {line}")
  print(f"{len(created['lines']) + 1:>4}  {created['final_checksum']}  (final checksum)")


if __name__ == "__main__":
  main()
