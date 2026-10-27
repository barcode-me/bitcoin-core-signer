#!/usr/bin/env python3
"""
Encode public descriptors as Super Base 58 (SB58) lines to type into another device.

The descriptors become a compact JSON array of strings, which is encoded as Base58.
Every 4 Base58 characters make one line:

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

Run this offline. Refuses private descriptors.
"""
import hashlib
import json
import sys

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
MAX_DESCRIPTORS = 16


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


def encode_sb58(descriptors):
  if not isinstance(descriptors, list) or not 1 <= len(descriptors) <= MAX_DESCRIPTORS:
      raise ValueError(f"Expected 1 to {MAX_DESCRIPTORS} descriptors")
  for descriptor in descriptors:
      if not isinstance(descriptor, str) or not descriptor or not descriptor.isascii() or not descriptor.isprintable() or " " in descriptor:
          raise ValueError("Each descriptor must be one line of text without spaces")
      if "prv" in descriptor:
          raise ValueError("Refusing to encode a private key. Only transfer public descriptors")

  payload = json.dumps(descriptors, separators=(",", ":")).encode()
  encoded = base58_encode(payload)
  lines = []
  for start in range(0, len(encoded), CHARS_PER_LINE):
      chunk = encoded[start:start + CHARS_PER_LINE]
      words = " ".join(char_word(char) for char in chunk)
      check = checksum_char(chunk)
      casing = "".join("1" if char.isupper() else "0" for char in chunk + check)
      lines.append(f"{words} {casing} {char_word(check)}")
  digest = hashlib.sha256("\n".join(lines).encode("utf-8")).digest()
  final_checksum = f"{int.from_bytes(digest[-2:], 'big'):05d}"
  return {"lines": lines, "final_checksum": final_checksum, "bytes": len(payload), "base58_chars": len(encoded)}


def main():
  print("Paste the public descriptors, one per line, then press Ctrl-D.", file=sys.stderr)
  try:
      encoded = encode_sb58([line.strip() for line in sys.stdin if line.strip()])
  except ValueError as error:
      raise SystemExit(str(error))
  for number, line in enumerate(encoded["lines"], 1):
      print(f"{number:>4}  {line}")
  print(f"{len(encoded['lines']) + 1:>4}  {encoded['final_checksum']}  (final checksum)")


if __name__ == "__main__":
  main()
