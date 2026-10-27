#!/usr/bin/env python3
import argparse
from getpass import getpass
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

  backup_hex_count = WORD_COUNT_TO_HEX_COUNT[args.words]
  backup_hex_input = prompt_input(f"Backup as {backup_hex_count} hex chars: ").strip()
  backup_bytes = None

  if backup_hex_input:
      if len(backup_hex_input) != backup_hex_count:
          raise SystemExit(f"Backup hex must be exactly {backup_hex_count} chars got {len(backup_hex_input)} chars")

      try:
          backup_bytes = bytes.fromhex(backup_hex_input + '0' * (backup_hex_count % 2))
      except ValueError:
          raise SystemExit("Backup must be a valid hex string")
  else:
      raise SystemExit("Backup not provided.")

  pad_pass_input = prompt_input(f"One-time-pad as passphrase input: ").strip()
  pad_hash_bytes = sha256(pad_pass_input.encode('utf-8')).digest()
  pad_hash_bytes2 = sha256(pad_hash_bytes).digest()
  decrypted_bytes = bytearray(c ^ k for c, k in zip(backup_bytes, pad_hash_bytes + pad_hash_bytes2))
  if backup_hex_count % 2:
      # The appended '0' nibble got XORed with the pad; clear it again
      decrypted_bytes[-1] &= 0xF0
  decrypted_bytes = bytes(decrypted_bytes)
  entropy_len = args.words * 4 // 3  # 16 bytes for 12 words, 32 for 24
  mnemonic = bip39.mnemonic_from_bytes(decrypted_bytes[:entropy_len])
  mnemonic_bytes = get_mnemonic_bytes(mnemonic)

  if mnemonic_bytes != decrypted_bytes:
      print('no match')
      print(" ".join(f"{byte:08b}" for byte in mnemonic_bytes))
      print(" ".join(f"{byte:08b}" for byte in decrypted_bytes))
  else:
    print(mnemonic)


if __name__ == "__main__":
  main()
