#!/usr/bin/env python3
"""
Decrypt a one-time-pad encrypted backup into a BIP39 mnemonic. Run this offline,
because the output is a seed phrase.

The backup is the full BIP39 bit stream: 11 bits per word, so 132 bits for 12
words and 264 bits for 24 words, written in hex (33 or 66 digits) or decimal.
The one-time pad is the first 132 or 264 bits of SHA-256(secret), followed if
more bits are needed by SHA-256 of the previous hash. The secret is the
one-time pad text, or the passphrase when no separate one-time pad is given.
XOR gives the BIP39 bits: the entropy followed by its checksum, which is
verified to catch a wrong secret or a typing mistake.
"""
import argparse
import hashlib
from getpass import getpass
from embit import bip39

WORD_COUNT_TO_BITS = {12: 12 * 11, 24: 24 * 11}


def parse_backup(text, encoding, total_bits):
  text = "".join(text.split())
  if encoding == "hex":
      if text[:2].lower() == "0x":
          text = text[2:]
      if len(text) != total_bits // 4:
          raise ValueError(
              f"Hex backup must be exactly {total_bits // 4} hex chars "
              f"({total_bits} bits), got {len(text)}"
          )
      if not set(text) <= set("0123456789abcdefABCDEF"):
          raise ValueError("Hex backup may only contain 0-9 and a-f")
      return int(text, 16)
  if encoding == "decimal":
      if not (text.isascii() and text.isdigit()):
          raise ValueError("Decimal backup may only contain the digits 0-9")
      # 2**total_bits has at most 80 decimal digits, so longer input can never fit.
      if len(text) > 80 or int(text) >> total_bits:
          raise ValueError(f"Decimal backup does not fit in {total_bits} bits")
      return int(text)
  raise ValueError("Encoding must be 'hex' or 'decimal'")


def one_time_pad(secret, bits):
  if not secret:
      raise ValueError("The passphrase or one-time pad must not be empty")
  # One SHA-256 gives 256 bits. A 24-word backup needs 264, so keep hashing the previous block.
  pad = b""
  block = secret.encode("utf-8")
  while len(pad) * 8 < bits:
      block = hashlib.sha256(block).digest()
      pad += block
  return int.from_bytes(pad, "big") >> (len(pad) * 8 - bits)


def decrypt_backup(backup, encoding, words, passphrase, otp=None):
  total_bits = WORD_COUNT_TO_BITS[words]
  checksum_bits = words // 3
  encrypted = parse_backup(backup, encoding, total_bits)
  bits = encrypted ^ one_time_pad(otp if otp else passphrase, total_bits)

  entropy = (bits >> checksum_bits).to_bytes((total_bits - checksum_bits) // 8, "big")
  expected_checksum = hashlib.sha256(entropy).digest()[0] >> (8 - checksum_bits)
  if bits & ((1 << checksum_bits) - 1) != expected_checksum:
      raise ValueError(
          "Checksum mismatch: wrong passphrase or one-time pad, or a typing mistake in the backup"
      )
  return bip39.mnemonic_from_bytes(entropy)


def main():
  parser = argparse.ArgumentParser()
  parser.add_argument(
      "--words",
      type=int,
      choices=sorted(WORD_COUNT_TO_BYTES),
      required=True,
      help="Number of words in the seed phrase",
  )
  parser.add_argument(
      "--encoding",
      choices=["hex", "decimal"],
      default="hex",
      help="How the encrypted backup is written (default: hex)",
  )
  args = parser.parse_args()

  backup = getpass("Encrypted backup: ")
  passphrase = getpass("Passphrase: ")
  otp = getpass("One-time pad (leave empty to use the passphrase): ")

  try:
      print("Mnemonic:", decrypt_backup(backup, args.encoding, args.words, passphrase, otp))
  except ValueError as error:
      raise SystemExit(str(error))


if __name__ == "__main__":
  main()
