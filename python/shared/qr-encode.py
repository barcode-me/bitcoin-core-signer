#!/usr/bin/env python3
"""
Encrypt data with a passphrase and write it as a series of QR codes to scan on the
other device with qr-scan.py, instead of typing Super Base 58 lines.

The data is encrypted with AES-256-GCM. The key comes from the passphrase with
scrypt (N=2^15, r=8, p=1) and a random 16-byte salt, so each transfer has its own
key. The kind of data (descriptors, psbt or signatures) is authenticated with it,
so QR codes of one kind cannot be read as another. The encrypted bytes are:

  ["BCSQ"][salt: 16 bytes][nonce: 12 bytes][ciphertext + 16-byte tag]

They are cut into slices of 128 bytes. Each slice becomes one QR code holding the
text BCSQ:<transfer id>:<slice number>:<slice count>:<slice in base64>. The
transfer id is random, so slices of two transfers are never mixed. The slices can
be scanned in any order. A wrong passphrase, a wrong kind, or a changed slice
fails to decrypt instead of giving wrong data.

Each QR code is returned as a PNG image. Needs qrcode with Pillow, and cryptography.
"""
import argparse
import base64
import getpass
import hashlib
import io
import re
import secrets
import sys
from pathlib import Path

import qrcode
from cryptography.hazmat.primitives.ciphers.aead import AESGCM

MAGIC = b"BCSQ"
KINDS = {"descriptors", "psbt", "signatures"}
SLICE_BYTES = 128
MAX_SLICES = 255
MAX_DATA_BYTES = 16 * 1024
HEX = re.compile(r"(?:[0-9a-fA-F]{2})+")
# scrypt cost: about 32 MiB and a fraction of a second, once per transfer
SCRYPT = {"n": 2**15, "r": 8, "p": 1, "maxmem": 64 * 1024 * 1024, "dklen": 32}


def check_inputs(kind, passphrase):
  if kind not in KINDS:
      raise ValueError(f"Unknown kind of data: {kind}")
  if not isinstance(passphrase, str) or not passphrase:
      raise ValueError("Enter the QR passphrase at the top of the page. Both devices must use the same one")


def encrypt(data, kind, passphrase):
  salt, nonce = secrets.token_bytes(16), secrets.token_bytes(12)
  key = hashlib.scrypt(passphrase.encode("utf-8"), salt=salt, **SCRYPT)
  return MAGIC + salt + nonce + AESGCM(key).encrypt(nonce, data, MAGIC + kind.encode())


def slice_texts(envelope):
  slices = [envelope[start:start + SLICE_BYTES] for start in range(0, len(envelope), SLICE_BYTES)]
  if len(slices) > MAX_SLICES:
      raise ValueError(f"The data needs more than {MAX_SLICES} QR codes. Use Super Base 58 lines instead")
  transfer = secrets.token_hex(4)
  return [f"BCSQ:{transfer}:{number}:{len(slices)}:{base64.b64encode(chunk).decode()}" for number, chunk in enumerate(slices, 1)]


def png(text):
  code = qrcode.QRCode(error_correction=qrcode.constants.ERROR_CORRECT_M, box_size=8, border=4)
  code.add_data(text)
  code.make(fit=True)
  buffer = io.BytesIO()
  code.make_image().save(buffer, format="PNG")
  return buffer.getvalue()


def encode_qr(data, kind, passphrase):
  """data is hex. Returns the QR codes as PNG data URLs, in slice order."""
  check_inputs(kind, passphrase)
  if not isinstance(data, str) or not HEX.fullmatch(data):
      raise ValueError("The data to encode must be hex")
  payload = bytes.fromhex(data)
  if len(payload) > MAX_DATA_BYTES:
      raise ValueError(f"The data is larger than {MAX_DATA_BYTES} bytes. Use Super Base 58 lines instead")
  envelope = encrypt(payload, kind, passphrase)
  texts = slice_texts(envelope)
  images = [f"data:image/png;base64,{base64.b64encode(png(text)).decode()}" for text in texts]
  return {"images": images, "slices": len(texts), "bytes": len(payload), "encrypted_bytes": len(envelope)}


def main():
  parser = argparse.ArgumentParser()
  parser.add_argument("--kind", required=True, choices=sorted(KINDS), help="Kind of data, checked by qr-scan.py")
  parser.add_argument("--out", default=".", help="Folder to save the QR codes in as qr-01.png, qr-02.png, ... (default: here)")
  args = parser.parse_args()
  print("Paste the data in hex, then press Ctrl-D.", file=sys.stderr)
  data = "".join(sys.stdin.read().split())
  passphrase = getpass.getpass("QR passphrase: ")
  try:
      encoded = encode_qr(data, args.kind, passphrase)
  except ValueError as error:
      raise SystemExit(str(error))
  for number, image in enumerate(encoded["images"], 1):
      path = Path(args.out) / f"qr-{number:02d}.png"
      path.write_bytes(base64.b64decode(image.split(",", 1)[1]))
      print(path)
  print(f"{encoded['slices']} QR codes for {encoded['bytes']} bytes ({encoded['encrypted_bytes']} encrypted)", file=sys.stderr)


if __name__ == "__main__":
  main()
