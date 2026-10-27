#!/usr/bin/env python3
"""
Generate a BIP39 mnemonic from cryptographically secure randomness, or from
user-supplied entropy (hex). Run this offline, because the output is a seed phrase.
"""
import argparse
import secrets
import sys
from getpass import getpass
from embit import bip39

WORD_COUNT_TO_BYTES = {12: 16, 24: 32}

def main():
  parser = argparse.ArgumentParser()
  parser.add_argument(
      "--words",
      type=int,
      choices=sorted(WORD_COUNT_TO_BYTES),
      required=True,
      help="Number of words in the seed phrase",
  )
  args = parser.parse_args()

  def prompt_input(prompt):
      sys.stdout.write(prompt)
      sys.stdout.flush()
      return input()

  entropy_bytes = WORD_COUNT_TO_BYTES[args.words]

  custom_entropy = prompt_input(
      f"Custom entropy as hex ({entropy_bytes} bytes / {entropy_bytes * 2} hex chars, "
      "leave empty to generate securely): "
  ).strip()

  if custom_entropy:
      try:
          entropy = bytes.fromhex(custom_entropy)
      except ValueError:
          raise SystemExit("Entropy must be a valid hex string")
      if len(entropy) != entropy_bytes:
          raise SystemExit(
              f"Entropy must be exactly {entropy_bytes} bytes "
              f"({entropy_bytes * 2} hex chars) for a {args.words}-word mnemonic, "
              f"got {len(entropy)} bytes"
          )
      print("Using user-supplied entropy.", file=sys.stdout)
  else:
      entropy = secrets.token_bytes(entropy_bytes)
      print("Using securely generated entropy.", file=sys.stdout)

  mnemonic = bip39.mnemonic_from_bytes(entropy)

  print(mnemonic)


if __name__ == "__main__":
  main()
