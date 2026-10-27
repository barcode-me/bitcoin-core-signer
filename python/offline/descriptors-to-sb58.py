#!/usr/bin/env python3
"""
Encode public descriptors as Super Base 58 (SB58) lines to type into another device.

The descriptors of one wallet share the master fingerprint, and each address type
has one account xpub for both its receive (/0/*) and change (/1/*) descriptor.
Only those are sent, as bytes:

  [master fingerprint: 4 bytes][address types: 1 byte][xpub: 78 bytes per type]

The address type byte has one bit per type: 1 = Legacy (pkh, 44h), 2 = Nested
SegWit (sh(wpkh), 49h), 4 = Native SegWit (wpkh, 84h), 8 = Taproot (tr, 86h). The
xpubs follow in that order, as their 78 bytes without the Base58Check checksum.
The other device rebuilds the receive and change descriptors of each type, with
the path <purpose>/0h/0h, and their checksums. On a test network the xpubs are
tpubs and the path is <purpose>/1h/0h. The xpub's version bytes tell which, so
the other device knows the network too.

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

Run this offline. Refuses private descriptors.
"""
import hashlib
import re
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
# Address types in bit order: bit, name, descriptor start, BIP purpose
SCRIPT_TYPES = [
    (1, "Legacy (P2PKH)", "pkh(", "44"),
    (2, "Nested SegWit (P2SH-P2WPKH)", "sh(wpkh(", "49"),
    (4, "Native SegWit (P2WPKH)", "wpkh(", "84"),
    (8, "Taproot (P2TR)", "tr(", "86"),
]
# xpub version -> BIP44 coin type: mainnet xpub, or tpub on every test network
XPUB_COIN_TYPES = {bytes.fromhex("0488b21e"): "0", bytes.fromhex("043587cf"): "1"}
ACCOUNT_CHILD = (0x80000000).to_bytes(4, "big")
# wpkh([d34db33f/84h/0h/0h]xpub.../0/*)#checksum, as listed by Bitcoin Core. ' is accepted for h.
DESCRIPTOR = re.compile(
    r"(pkh\(|sh\(wpkh\(|wpkh\(|tr\()\[([0-9a-f]{8})/(\d+)[h']/([01])[h']/0[h']\]"
    r"([xt]pub[1-9A-HJ-NP-Za-km-z]+)/([01])/\*(\)+)#([a-z0-9]{8})"
)
CHECKSUM_INPUT = "0123456789()[],'/*abcdefgh@:$%{}IJKLMNOPQRSTUVWXYZ&+-.;<=>?!^_|~ijklmnopqrstuvwxyzABCDEFGH`#\"\\ "
CHECKSUM_CHARS = "qpzry9x8gf2tvdw0s3jn54khce6mua7l"


def base58_encode(data):
  number = int.from_bytes(data, "big")
  encoded = ""
  while number:
      number, remainder = divmod(number, 58)
      encoded = BASE58[remainder] + encoded
  # Each leading zero byte is written as "1"
  return "1" * (len(data) - len(data.lstrip(b"\0"))) + encoded


def base58_decode(text):
  number = 0
  for char in text:
      number = number * 58 + BASE58.index(char)
  data = number.to_bytes((number.bit_length() + 7) // 8, "big")
  return b"\0" * (len(text) - len(text.lstrip("1"))) + data


def descriptor_checksum(descriptor):
  # The descriptor checksum from Bitcoin Core's descriptor.cpp (BIP 380)
  def polymod(c, value):
      top = c >> 35
      c = ((c & 0x7FFFFFFFF) << 5) ^ value
      for bit, generator in enumerate((0xF5DEE51989, 0xA9FDCA3312, 0x1BAB10E32D, 0x3706B1677A, 0x644D626FFD)):
          if top >> bit & 1:
              c ^= generator
      return c

  c, cls, count = 1, 0, 0
  for char in descriptor:
      position = CHECKSUM_INPUT.find(char)
      if position < 0:
          raise ValueError(f"Invalid character in descriptor: {char!r}")
      c = polymod(c, position & 31)
      cls = cls * 3 + (position >> 5)
      count += 1
      if count == 3:
          c, cls, count = polymod(c, cls), 0, 0
  if count:
      c = polymod(c, cls)
  for _ in range(8):
      c = polymod(c, 0)
  c ^= 1
  return "".join(CHECKSUM_CHARS[(c >> (5 * (7 - i))) & 31] for i in range(8))


def xpub_bytes(xpub):
  # 78 bytes: version, depth, parent fingerprint, child number, chain code, public key
  data = base58_decode(xpub)
  payload, check = data[:-4], data[-4:]
  if len(payload) != 78 or hashlib.sha256(hashlib.sha256(payload).digest()).digest()[:4] != check:
      raise ValueError(f"{xpub[:12]}… is not a valid xpub. Check that it was copied completely")
  if payload[:4] not in XPUB_COIN_TYPES or payload[4] != 3 or payload[9:13] != ACCOUNT_CHILD or payload[45] not in (2, 3):
      raise ValueError(f"{xpub[:12]}… is not an account xpub or tpub at <purpose>/<coin type>/0h")
  return payload


def char_word(char):
  return DIGIT_WORDS[int(char) - 1] if char.isdigit() else LETTER_WORDS[char.lower()]


def checksum_char(chars):
  return BASE58[sum(BASE58.index(char) for char in chars) % 58]


def compact_descriptors(descriptors):
  """Returns the bytes [fingerprint][address type bits][xpub per type] and the address type names."""
  if not isinstance(descriptors, list) or not descriptors:
      raise ValueError("Expected at least one descriptor")
  fingerprint = None
  xpubs = {}
  for number, descriptor in enumerate(descriptors, 1):
      if not isinstance(descriptor, str):
          raise ValueError(f"Descriptor {number} must be text")
      if "prv" in descriptor:
          raise ValueError("Refusing to encode a private key. Only transfer public descriptors")
      match = DESCRIPTOR.fullmatch(descriptor)
      if not match:
          raise ValueError(
              f"Descriptor {number} is not a single-key wallet descriptor like "
              "wpkh([fingerprint/84h/0h/0h]xpub.../0/*)#checksum, or tpub with 1h on a test network"
          )
      start, descriptor_fingerprint, purpose, coin_type, xpub, _, closing, checksum = match.groups()
      script_type = next((t for t in SCRIPT_TYPES if t[2] == start and t[3] == purpose), None)
      if script_type is None or closing != ")" * start.count("("):
          raise ValueError(f"Descriptor {number} does not use a standard path for its address type, such as 84h for wpkh")
      if descriptor_checksum(descriptor.split("#")[0]) != checksum:
          raise ValueError(f"Descriptor {number} has the wrong checksum. Check that it was copied completely")
      if fingerprint not in (None, descriptor_fingerprint):
          raise ValueError("The descriptors have different master fingerprints. Only transfer the descriptors of one wallet")
      fingerprint = descriptor_fingerprint
      key = xpub_bytes(xpub)
      if XPUB_COIN_TYPES[key[:4]] != coin_type:
          raise ValueError(f"Descriptor {number} uses coin type {coin_type}h, but its key is for {'mainnet' if coin_type == '1' else 'a test network'}")
      if xpubs and next(iter(xpubs.values()))[:4] != key[:4]:
          raise ValueError("The descriptors mix mainnet and test network keys. Only transfer the descriptors of one wallet")
      if xpubs.get(script_type[0], key) != key:
          raise ValueError(f"The {script_type[1]} descriptors have different xpubs. Only transfer the descriptors of one wallet")
      xpubs[script_type[0]] = key

  bits = sum(xpubs)
  data = bytes.fromhex(fingerprint) + bytes([bits]) + b"".join(xpubs[t[0]] for t in SCRIPT_TYPES if t[0] in xpubs)
  return data, [t[1] for t in SCRIPT_TYPES if t[0] in xpubs]


def encode_sb58(descriptors):
  payload, script_types = compact_descriptors(descriptors)
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
  return {
      "lines": lines, "final_checksum": final_checksum, "bytes": len(payload),
      "base58_chars": len(encoded), "script_types": script_types, "hex": payload.hex(),
  }


def main():
  print("Paste the public descriptors, one per line, then press Ctrl-D.", file=sys.stderr)
  try:
      encoded = encode_sb58([line.strip() for line in sys.stdin if line.strip()])
  except ValueError as error:
      raise SystemExit(str(error))
  print(f"Address types: {', '.join(encoded['script_types'])}", file=sys.stderr)
  for number, line in enumerate(encoded["lines"], 1):
      print(f"{number:>4}  {line}")
  print(f"{len(encoded['lines']) + 1:>4}  {encoded['final_checksum']}  (final checksum)")


if __name__ == "__main__":
  main()
