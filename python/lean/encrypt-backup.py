#!/usr/bin/env python3
import argparse
import sys
from embit import bip39
from hashlib import sha256


WORD_COUNT_TO_HEX_COUNT = {12: 33, 24: 66}

def get_mnemonic_bytes(mnemonic):
  words = mnemonic.strip().split()

  bit_string = ""
  for word in words:
      if word not in bip39.WORDLIST:
          raise ValueError(f"Word '{word}' is not a valid BIP39 word.")

      index = bip39.WORDLIST.index(word)
      bit_string += f"{index:011b}"  # Pad with leading zeros to exactly 11 bits

  total_bits = len(bit_string)
  bit_string += "0" * (-total_bits % 8)
  total_bytes = len(bit_string) // 8
  combined_bytes = int(bit_string, 2).to_bytes(total_bytes, byteorder='big')
  return combined_bytes

def main():
  parser = argparse.ArgumentParser()
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

  mnemonic = " ".join(prompt_input(f"Seed phrase ({args.words} words): ").lower().split())
  if len(mnemonic.split()) != args.words:
      raise SystemExit(f"Seed phrase must be exactly {args.words} words got {len(mnemonic.split())} words")

  try:
      # Checks the words and the checksum
      bip39.mnemonic_to_bytes(mnemonic)
      mnemonic_bytes = get_mnemonic_bytes(mnemonic)
  except ValueError as e:
      raise SystemExit(f"Invalid seed phrase: {e}")

  pad_pass_input = prompt_input(f"One-time-pad as passphrase input: ").strip()
  if not pad_pass_input:
      raise SystemExit("Passphrase not provided.")

  pad_hash_bytes = sha256(pad_pass_input.encode('utf-8')).digest()
  pad_hash_bytes2 = sha256(pad_hash_bytes).digest()
  encrypted_bytes = bytes(m ^ k for m, k in zip(mnemonic_bytes, pad_hash_bytes + pad_hash_bytes2))

  # 12 words are 132 bits, so drop the padding nibble to get 33 hex chars
  backup_hex_count = WORD_COUNT_TO_HEX_COUNT[args.words]
  backup_hex = encrypted_bytes.hex()[:backup_hex_count]
  print(" ".join(backup_hex[i:i + 2] for i in range(0, len(backup_hex), 2)))


if __name__ == "__main__":
  main()
