#!/usr/bin/env python3
import argparse
import string
import sys


WORD_COUNT_TO_HEX_COUNT = {12: 33, 24: 66}


def main():
  parser = argparse.ArgumentParser(description="Convert a 33 or 66 char hex backup to a decimal integer")
  parser.add_argument(
      "--words",
      type=int,
      choices=sorted(WORD_COUNT_TO_HEX_COUNT),
      required=True,
      help="Number of words in the seed phrase",
  )
  args = parser.parse_args()

  def prompt_input(prompt):
      sys.stdout.write(prompt)
      sys.stdout.flush()
      return input()

  hex_count = WORD_COUNT_TO_HEX_COUNT[args.words]
  # Allow 2 char groups as printed by decimal-to-hex.py
  hex_input = "".join(prompt_input(f"Hex as {hex_count} chars: ").split())

  if len(hex_input) != hex_count:
      raise SystemExit(f"Hex must be exactly {hex_count} chars got {len(hex_input)} chars")

  # int(..., 16) also accepts "0x" prefixes and underscores, so check digits explicitly
  if not all(c in string.hexdigits for c in hex_input):
      raise SystemExit("Input must be a valid hex string")

  # Group digits in fours from the right, e.g. "12 3456 7890"
  decimal = str(int(hex_input, 16))
  groups = [decimal[max(i - 4, 0):i] for i in range(len(decimal), 0, -4)]
  print(" ".join(reversed(groups)))


if __name__ == "__main__":
  main()
