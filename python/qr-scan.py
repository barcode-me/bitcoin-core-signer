#!/usr/bin/env python3
"""
Scan the encrypted QR codes made by qr-encode.py with this device's camera, then
put the slices together and decrypt them with the passphrase.

OpenCV opens the camera in a window that shows how many QR codes were read. Hold
the camera to the other device's screen until every code is read, in any order.
Press q or Esc in the window to stop. Each QR code holds the text
BCSQ:<transfer id>:<slice number>:<slice count>:<slice in base64>. When a code of
another transfer appears, for example because the other device made new codes,
scanning starts over with that transfer.

The slices together are ["BCSQ"][salt: 16][nonce: 12][ciphertext + 16-byte tag],
decrypted with AES-256-GCM and a key from the passphrase with scrypt
(N=2^15, r=8, p=1). The kind of data is authenticated, so a wrong passphrase, the
wrong kind, or a changed slice fails instead of giving wrong data.

The camera runs in its own process, because macOS only shows windows from a
program's main thread, and the local server runs scripts on other threads.
Needs opencv-python and cryptography.
"""
import argparse
import base64
import binascii
import getpass
import hashlib
import json
import re
import subprocess
import sys
import time

import cv2
from cryptography.exceptions import InvalidTag
from cryptography.hazmat.primitives.ciphers.aead import AESGCM

MAGIC = b"BCSQ"
KINDS = {"descriptors", "psbt", "signatures"}
SLICE = re.compile(r"BCSQ:([0-9a-f]{8}):(\d{1,3}):(\d{1,3}):([A-Za-z0-9+/=]+)")
SLICE_BYTES = 128
MAX_SLICES = 255
WINDOW = "Scan the QR codes (q to stop)"
TIMEOUT_SECONDS = 300
# The same scrypt cost as qr-encode.py
SCRYPT = {"n": 2**15, "r": 8, "p": 1, "maxmem": 64 * 1024 * 1024, "dklen": 32}


def check_inputs(kind, passphrase):
  if kind not in KINDS:
      raise ValueError(f"Unknown kind of data: {kind}")
  if not isinstance(passphrase, str) or not passphrase:
      raise ValueError("Enter the QR passphrase at the top of the page. Both devices must use the same one")


def parse_slice(text):
  """Returns (transfer id, slice number, slice count, bytes), or None for a QR code that is not a slice."""
  match = SLICE.fullmatch(text.strip())
  if not match:
      return None
  transfer, number, count, encoded = match.groups()
  number, count = int(number), int(count)
  if not 1 <= number <= count <= MAX_SLICES:
      return None
  try:
      chunk = base64.b64decode(encoded, validate=True)
  except binascii.Error:
      return None
  # Every slice but the last is full
  if not chunk or len(chunk) > SLICE_BYTES or (number < count and len(chunk) != SLICE_BYTES):
      return None
  return transfer, number, count, chunk


def read_slices(camera=0, timeout=TIMEOUT_SECONDS):
  """Shows the camera until every slice of one transfer is read. Returns their texts in order."""
  capture = cv2.VideoCapture(camera)
  if not capture.isOpened():
      raise ValueError(f"Could not open camera {camera}. Check that it is connected and that this terminal may use it")
  detector = cv2.QRCodeDetector()
  transfer, count, slices = None, None, {}
  deadline = time.monotonic() + timeout
  try:
      while len(slices) != count:
          if time.monotonic() > deadline:
              raise ValueError(f"Stopped after {timeout} seconds with {len(slices)} of {count or '?'} QR codes read")
          ok, frame = capture.read()
          if not ok:
              raise ValueError("Could not read from the camera")
          text, points, _ = detector.detectAndDecode(frame)
          parsed = parse_slice(text) if text else None
          if parsed:
              if parsed[0] != transfer or parsed[2] != count:
                  # New codes on the other device: start over with them
                  transfer, count, slices = parsed[0], parsed[2], {}
              slices[parsed[1]] = text.strip()
          if points is not None:
              cv2.polylines(frame, [points.astype(int)], True, (0, 200, 0) if parsed else (0, 0, 220), 3)
          missing = [str(number) for number in range(1, (count or 0) + 1) if number not in slices]
          status = f"{len(slices)} of {count} read" + (f", missing {' '.join(missing[:12])}" if missing else "") if count else "Looking for a QR code"
          cv2.putText(frame, status, (16, 36), cv2.FONT_HERSHEY_SIMPLEX, 0.9, (0, 0, 0), 5)
          cv2.putText(frame, status, (16, 36), cv2.FONT_HERSHEY_SIMPLEX, 0.9, (255, 255, 255), 2)
          cv2.imshow(WINDOW, frame)
          if cv2.waitKey(1) & 0xFF in (ord("q"), 27):
              raise ValueError("Scanning was stopped before every QR code was read")
  finally:
      capture.release()
      cv2.destroyAllWindows()
      cv2.waitKey(1)
  return [slices[number] for number in range(1, count + 1)]


def decrypt(texts, kind, passphrase):
  parsed = [parse_slice(text) for text in texts]
  if not parsed or None in parsed or len({(item[0], item[2]) for item in parsed}) != 1 or [item[1] for item in parsed] != list(range(1, len(parsed) + 1)):
      raise ValueError("The QR codes are not one complete transfer")
  envelope = b"".join(item[3] for item in parsed)
  if len(envelope) < 4 + 16 + 12 + 16 or not envelope.startswith(MAGIC):
      raise ValueError("The QR codes do not hold encrypted data from qr-encode.py")
  salt, nonce, ciphertext = envelope[4:20], envelope[20:32], envelope[32:]
  key = hashlib.scrypt(passphrase.encode("utf-8"), salt=salt, **SCRYPT)
  try:
      return AESGCM(key).decrypt(nonce, ciphertext, MAGIC + kind.encode())
  except InvalidTag:
      raise ValueError(
          f"Could not decrypt the QR codes. Check that both devices use the same QR passphrase, "
          f"and that the other device is showing the {kind} QR codes for this step"
      )


def scan_qr(kind, passphrase, camera=0):
  """Scans in a separate process, then decrypts. Returns the data as hex."""
  check_inputs(kind, passphrase)
  if not isinstance(camera, int) or isinstance(camera, bool) or not 0 <= camera <= 9:
      raise ValueError("The camera must be a number from 0 to 9")
  try:
      finished = subprocess.run(
          [sys.executable, __file__, "--slices-only", "--camera", str(camera)],
          capture_output=True, text=True, timeout=TIMEOUT_SECONDS + 30,
      )
      scanned = json.loads(finished.stdout)
  except subprocess.TimeoutExpired:
      raise ValueError("The camera did not finish in time")
  except ValueError:
      raise ValueError("The camera process failed: " + (finished.stderr.strip().splitlines() or ["no output"])[-1])
  if "error" in scanned:
      raise ValueError(scanned["error"])
  data = decrypt(scanned["slices"], kind, passphrase)
  return {"hex": data.hex(), "bytes": len(data), "slices": len(scanned["slices"])}


def main():
  parser = argparse.ArgumentParser()
  parser.add_argument("--kind", choices=sorted(KINDS), help="Kind of data, as given to qr-encode.py")
  parser.add_argument("--camera", type=int, default=0, help="Camera number (default: 0)")
  # Used by scan_qr: scan, then print the slices as JSON without decrypting
  parser.add_argument("--slices-only", action="store_true", help=argparse.SUPPRESS)
  args = parser.parse_args()
  if args.slices_only:
      try:
          print(json.dumps({"slices": read_slices(args.camera)}))
      except ValueError as error:
          print(json.dumps({"error": str(error)}))
      return
  if not args.kind:
      parser.error("--kind is required")
  passphrase = getpass.getpass("QR passphrase: ")
  try:
      check_inputs(args.kind, passphrase)
      print(decrypt(read_slices(args.camera), args.kind, passphrase).hex())
  except ValueError as error:
      raise SystemExit(str(error))


if __name__ == "__main__":
  main()
