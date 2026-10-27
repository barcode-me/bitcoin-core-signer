#!/usr/bin/env python3
"""
Sign a PSBT with the wallet in Bitcoin Core and encode only its signatures as Super
Base 58 (SB58) lines to type into the online device. Run this offline, because the
wallet holds the private keys.

Bitcoin Core signs it with walletprocesspsbt, without finalizing, and decodepsbt
lists the signatures. The PSBT is sent to bitcoin-cli on stdin (-stdin). If the
wallet cannot sign every input, for example because it was made from a different
seed phrase or passphrase, nothing is encoded.

The online device already has the unsigned PSBT, so only the signatures are sent,
as bytes:

  [transaction ID: first 4 bytes][signature: 64 bytes per input, in input order]

The transaction ID is the unsigned transaction's, as shown by Bitcoin Core. The
online device checks it, so signatures for a different transaction are refused. An
ECDSA signature (Legacy and SegWit inputs) is sent as its 32-byte r and s, without
its DER encoding and SIGHASH_ALL byte, which the online device adds back. A Taproot
signature is 64 bytes already (SIGHASH_DEFAULT).

The bytes are encoded as Base58. Every 4 Base58 characters make one line:

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

The wallet is loaded first if it is not loaded yet. Nothing is sent.
"""
import argparse
import hashlib
import json
import re
import subprocess
import sys

BITCOIN_CLI = "bitcoin-cli"
TIMEOUT_SECONDS = 120
WALLET_NAME = re.compile(r"[A-Za-z0-9._-]+")
BASE64 = re.compile(r"[A-Za-z0-9+/]+={0,2}")
WALLET_NOT_LOADED = "error code: -18"
SIGHASH_ALL = 0x01

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


def compact_ecdsa(signature):
  """DER signature + SIGHASH_ALL byte -> 64 bytes of r and s."""
  sig = bytes.fromhex(signature)
  if len(sig) < 9 or sig[0] != 0x30 or sig[1] != len(sig) - 3 or sig[-1] != SIGHASH_ALL or sig[2] != 0x02:
      raise ValueError("Bitcoin Core returned a signature this transfer does not support (only SIGHASH_ALL)")
  r_length = sig[3]
  r = sig[4:4 + r_length]
  if sig[4 + r_length] != 0x02:
      raise ValueError("Bitcoin Core returned a signature that is not DER encoded")
  s = sig[6 + r_length:6 + r_length + sig[5 + r_length]]
  return int.from_bytes(r, "big").to_bytes(32, "big") + int.from_bytes(s, "big").to_bytes(32, "big")


def sign_psbt(psbt, wallet, datadir=None):
  psbt = psbt.strip() if isinstance(psbt, str) else psbt
  if not isinstance(psbt, str) or not BASE64.fullmatch(psbt):
      raise ValueError("The PSBT must be base64")
  if not isinstance(wallet, str) or not WALLET_NAME.fullmatch(wallet):
      raise ValueError("Wallet name may only contain letters, digits, dots, dashes and underscores")
  datadir = datadir.strip() if isinstance(datadir, str) else datadir
  if datadir is not None and (
      not isinstance(datadir, str) or len(datadir) > 4096 or not datadir.isprintable()
  ):
      raise ValueError("Data directory must be a path without control characters")

  # Sign without finalizing, so the signatures stay readable in the PSBT
  args = [f"-rpcwallet={wallet}", "-named", "-stdin", "walletprocesspsbt"]
  stdin = f"psbt={psbt}\nfinalize=false\n"
  try:
      output = run_cli(args, stdin, datadir)
  except ValueError as error:
      if WALLET_NOT_LOADED not in str(error):
          raise
      # The wallet exists on disk but is not loaded: load it, then ask again
      run_cli(["loadwallet", wallet], datadir=datadir)
      output = run_cli(args, stdin, datadir)
  try:
      signed = json.loads(output)["psbt"]
  except (ValueError, KeyError, TypeError):
      raise ValueError(f"Unexpected output from {BITCOIN_CLI}")
  decoded_output = run_cli(["-stdin", "decodepsbt"], signed + "\n", datadir)
  analyzed_output = run_cli(["-stdin", "analyzepsbt"], signed + "\n", datadir)
  try:
      decoded = json.loads(decoded_output)
      txid = bytes.fromhex(decoded["tx"]["txid"])
      inputs = decoded["inputs"]
      next_step = json.loads(analyzed_output).get("next")
  except (ValueError, KeyError, TypeError):
      raise ValueError(f"Unexpected output from {BITCOIN_CLI}")
  # walletprocesspsbt only reports "complete" for finalized inputs, so ask analyzepsbt instead:
  # once every input has its signatures, the next step is the finalizer.
  if next_step not in ("finalizer", "extractor"):
      raise ValueError(
          f"Wallet {wallet} could not sign every input of this transaction, so it was not encoded. "
          "Check that the wallet was made from the same seed phrase and passphrase as the online device's wallet"
      )

  signatures = []
  for number, signed_input in enumerate(inputs, 1):
      taproot = signed_input.get("taproot_key_path_sig")
      partial = signed_input.get("partial_signatures", {})
      if taproot and not partial and len(taproot) == 128:
          signatures.append(bytes.fromhex(taproot))
      elif len(partial) == 1 and not taproot:
          signatures.append(compact_ecdsa(next(iter(partial.values()))))
      else:
          raise ValueError(f"Input {number} does not have exactly one signature from a single-key address, so it cannot be transferred")
  data = txid[:4] + b"".join(signatures)
  return {**encode_sb58(data), "wallet": wallet, "txid": decoded["tx"]["txid"], "signatures": len(signatures)}


def main():
  parser = argparse.ArgumentParser()
  parser.add_argument("--wallet", default="my-wallet", help="Name of the wallet that signs (default: my-wallet)")
  parser.add_argument("--datadir", help="Bitcoin Core data directory (default: Bitcoin Core's own default)")
  args = parser.parse_args()
  print("Paste the PSBT in base64, then press Ctrl-D.", file=sys.stderr)
  try:
      signed = sign_psbt(sys.stdin.read(), args.wallet, args.datadir)
  except ValueError as error:
      raise SystemExit(str(error))
  print(f"Signed {signed['signatures']} inputs of transaction {signed['txid']}", file=sys.stderr)
  for number, line in enumerate(signed["lines"], 1):
      print(f"{number:>4}  {line}")
  print(f"{len(signed['lines']) + 1:>4}  {signed['final_checksum']}  (final checksum)")


if __name__ == "__main__":
  main()
