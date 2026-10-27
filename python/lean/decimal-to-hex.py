#!/usr/bin/env python3
import argparse
import sys


WORD_COUNT_TO_HEX_COUNT = {12: 33, 24: 66}


def main():
  parser = argparse.ArgumentParser(description="Convert a decimal integer to a 33 or 66 char hex backup")
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

  # Allow 4 digit groups as printed by hex-to-decimal.py
  decimal_input = "".join(prompt_input("Decimal number: ").split())

  try:
      value = int(decimal_input, 10)
  except ValueError:
      raise SystemExit("Input must be a valid decimal integer")

  if value < 0:
      raise SystemExit("Input must not be negative")

  # Left-pad with zeros, since leading zero nibbles are lost in decimal form
  hex_count = WORD_COUNT_TO_HEX_COUNT[args.words]
  hex_output = f"{value:0{hex_count}x}"
  if len(hex_output) != hex_count:
      raise SystemExit(f"Hex must be exactly {hex_count} chars got {len(hex_output)} chars")

  # Group in 2 char bytes from the left, e.g. "00 00 18 ee ... d2"
  print(" ".join(hex_output[i:i + 2] for i in range(0, len(hex_output), 2)))


if __name__ == "__main__":
  main()
