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
DICE_TO_BITS = {"1": "00", "2": "01", "3": "10", "4": "11", "5": "0", "6": "1"}

def read_dice_entropy(entropy_bytes, prompt_input):
  required_bits = entropy_bytes * 8
  bits = ""
  while len(bits) < required_bits:
      rolls = prompt_input(f"Dice rolls 1-6 ({len(bits)} of {required_bits} bits): ")
      # Whitespace is dropped, any other char that is not 1-6 rejects the line.
      rolls = "".join(rolls.split())
      invalid = sorted(set(roll for roll in rolls if roll not in DICE_TO_BITS))
      if invalid:
          print(f"Invalid chars: {' '.join(invalid)}, enter that line again.")
          continue
      for roll in rolls:
          if len(bits) >= required_bits:
              print(f"Ignoring extra rolls from {roll} onward, enough bits collected.")
              break
          bits += DICE_TO_BITS[roll]
  # A 1-4 roll adds 2 bits, so the last roll can overshoot by one bit.
  bits = bits[:required_bits]
  print(f"Entropy: {len(bits)} of {required_bits} bits.")
  return int(bits, 2).to_bytes(entropy_bytes, byteorder="big")

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
      "--dice",
      action="store_true",
      help="Enter entropy as dice rolls (1=00, 2=01, 3=10, 4=11, 5=0, 6=1)",
  )
  args = parser.parse_args()

  def prompt_input(prompt):
      sys.stdout.write(prompt)
      sys.stdout.flush()
      return input()

  entropy_bytes = WORD_COUNT_TO_BYTES[args.words]

  if args.dice:
      entropy = read_dice_entropy(entropy_bytes, prompt_input)
      print(bip39.mnemonic_from_bytes(entropy))
      return

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
