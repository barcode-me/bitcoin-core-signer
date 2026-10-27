#!/usr/bin/env python3
"""
Add the signatures from the offline device to the unsigned transaction (PSBT) this
device created, then let Bitcoin Core finalize it and check that it would be
accepted. Nothing is sent.

The signatures arrive as bytes:

  [transaction ID: first 4 bytes][signature: 64 bytes per input, in input order]

The transaction ID must match the unsigned PSBT's, so signatures for a different
transaction are refused. For a Taproot input the 64 bytes are its key path signature
(PSBT field 0x13). For other inputs they are the r and s of an ECDSA signature, which
is DER encoded with the SIGHASH_ALL byte and stored as a partial signature (PSBT
field 0x02) under the input's one public key, from its BIP32 derivation (0x06).

Bitcoin Core then finalizes the PSBT with finalizepsbt and checks the transaction
with testmempoolaccept, which verifies every signature. Both are sent to bitcoin-cli
on stdin (-stdin).
"""
import argparse
import base64
import binascii
import hashlib
import json
import re
import subprocess
import sys

BITCOIN_CLI = "bitcoin-cli"
TIMEOUT_SECONDS = 120
BASE64 = re.compile(r"[A-Za-z0-9+/]+={0,2}")
HEX = re.compile(r"(?:[0-9a-f]{2})+")
PSBT_MAGIC = b"psbt\xff"
SIGHASH_ALL = b"\x01"
SIGNATURE_LENGTH = 64
TXID_PREFIX_LENGTH = 4


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
      return json.loads(output)
  except ValueError:
      raise ValueError(f"Unexpected output from {BITCOIN_CLI}")


def read_compact_size(data, position):
  first = data[position]
  if first < 0xFD:
      return first, position + 1
  size = {0xFD: 2, 0xFE: 4, 0xFF: 8}[first]
  return int.from_bytes(data[position + 1:position + 1 + size], "little"), position + 1 + size


def compact_size(number):
  if number < 0xFD:
      return bytes([number])
  if number <= 0xFFFF:
      return b"\xfd" + number.to_bytes(2, "little")
  return b"\xfe" + number.to_bytes(4, "little")


def read_map(data, position):
  """A PSBT map: key-value pairs, each prefixed with its length, ending with a 0 byte."""
  pairs = []
  while True:
      key_length, position = read_compact_size(data, position)
      if key_length == 0:
          return pairs, position
      key = data[position:position + key_length]
      value_length, position = read_compact_size(data, position + key_length)
      value = data[position:position + value_length]
      if len(key) != key_length or len(value) != value_length:
          raise ValueError("The PSBT is cut short")
      pairs.append((key, value))
      position += value_length


def write_map(pairs):
  return b"".join(compact_size(len(key)) + key + compact_size(len(value)) + value for key, value in pairs) + b"\0"


def der_signature(signature):
  """64 bytes of r and s -> DER signature + SIGHASH_ALL byte."""
  def integer(value):
      # Minimal big-endian, with a 0 byte in front when the top bit is set
      number = int.from_bytes(value, "big")
      encoded = number.to_bytes((number.bit_length() + 8) // 8, "big")
      return b"\x02" + bytes([len(encoded)]) + encoded
  body = integer(signature[:32]) + integer(signature[32:])
  return b"\x30" + bytes([len(body)]) + body + SIGHASH_ALL


def insert_signatures(psbt, signatures):
  """Returns the PSBT with one signature added to each input, and the transaction ID."""
  data = base64.b64decode(psbt, validate=True)
  if not data.startswith(PSBT_MAGIC):
      raise ValueError("The unsigned transaction is not a PSBT")
  global_map, position = read_map(data, len(PSBT_MAGIC))
  unsigned_tx = dict(global_map).get(b"\x00")
  if unsigned_tx is None:
      raise ValueError("The unsigned transaction is not a version 0 PSBT")
  txid = hashlib.sha256(hashlib.sha256(unsigned_tx).digest()).digest()[::-1]
  input_count, _ = read_compact_size(unsigned_tx, 4)

  if len(signatures) < TXID_PREFIX_LENGTH or (len(signatures) - TXID_PREFIX_LENGTH) % SIGNATURE_LENGTH:
      raise ValueError("The signatures are not 4 bytes of transaction ID followed by 64 bytes per input")
  if signatures[:TXID_PREFIX_LENGTH] != txid[:TXID_PREFIX_LENGTH]:
      raise ValueError(
          "These signatures are for a different transaction than the unsigned one from Part 3. "
          "Check that the offline device signed this transaction"
      )
  count = (len(signatures) - TXID_PREFIX_LENGTH) // SIGNATURE_LENGTH
  if count != input_count:
      raise ValueError(f"Received {count} signatures, but the transaction has {input_count} inputs")

  inputs = []
  for number in range(input_count):
      pairs, position = read_map(data, position)
      signature = signatures[TXID_PREFIX_LENGTH + number * SIGNATURE_LENGTH:][:SIGNATURE_LENGTH]
      key_types = {key[0] for key, _ in pairs}
      if 0x17 in key_types:
          # Taproot: PSBT_IN_TAP_INTERNAL_KEY is present, so this is a key path signature
          field = (b"\x13", signature)
      else:
          public_keys = [key[1:] for key, _ in pairs if key[0] == 0x06 and len(key) == 34]
          if len(public_keys) != 1:
              raise ValueError(f"Input {number + 1} does not name exactly one public key, so its signature cannot be added")
          field = (b"\x02" + public_keys[0], der_signature(signature))
      inputs.append(write_map([pair for pair in pairs if pair[0] != field[0]] + [field]))
  # Everything after the input maps (the output maps) is copied as it is
  signed = data[:len(PSBT_MAGIC)] + write_map(global_map) + b"".join(inputs) + data[position:]
  return base64.b64encode(signed).decode(), txid.hex()


def add_signatures(psbt, signatures, datadir=None):
  psbt = psbt.strip() if isinstance(psbt, str) else psbt
  if not isinstance(psbt, str) or not BASE64.fullmatch(psbt):
      raise ValueError("The unsigned PSBT must be base64")
  if not isinstance(signatures, str) or not HEX.fullmatch(signatures):
      raise ValueError("The signatures must be hex")
  datadir = datadir.strip() if isinstance(datadir, str) else datadir
  if datadir is not None and (
      not isinstance(datadir, str) or len(datadir) > 4096 or not datadir.isprintable()
  ):
      raise ValueError("Data directory must be a path without control characters")
  try:
      combined, txid = insert_signatures(psbt, bytes.fromhex(signatures))
  except (IndexError, KeyError, binascii.Error):
      raise ValueError("The unsigned PSBT could not be read")

  finalized = run_cli_json(["-stdin", "finalizepsbt"], f"{combined}\nfalse\n", datadir)
  extracted = run_cli_json(["-stdin", "finalizepsbt"], combined + "\n", datadir)
  if not finalized.get("complete") or not extracted.get("hex"):
      raise ValueError("Bitcoin Core could not finalize the transaction with these signatures")
  accepted = run_cli_json(["-stdin", "testmempoolaccept"], json.dumps([extracted["hex"]]) + "\n", datadir)[0]
  if not accepted.get("allowed"):
      raise ValueError(f"Bitcoin Core would not accept this transaction: {accepted.get('reject-reason', 'unknown reason')}")
  return {"psbt": finalized["psbt"], "txid": txid}


def main():
  parser = argparse.ArgumentParser()
  parser.add_argument("--psbt", required=True, help="The unsigned PSBT from create-psbt.py, in base64")
  parser.add_argument("--datadir", help="Bitcoin Core data directory (default: Bitcoin Core's own default)")
  args = parser.parse_args()
  print("Paste the signatures in hex, then press Ctrl-D.", file=sys.stderr)
  try:
      added = add_signatures(args.psbt, sys.stdin.read().strip(), args.datadir)
  except ValueError as error:
      raise SystemExit(str(error))
  print(f"Signed transaction {added['txid']}, ready to send (base64):\n{added['psbt']}")


if __name__ == "__main__":
  main()
