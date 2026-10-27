#!/usr/bin/env python3
"""
Scan the QR codes made by qr-encode.py with this device's camera and put the data
back together.

OpenCV opens the camera in a window that shows how many QR codes were read. Hold
the camera to the other device's screen until every code is read, in any order.
Press q or Esc in the window to stop. Each QR code holds the text
<id>:<chunk number>:<chunk count>:<chunk in base64>, with chunks of 64 bytes. When
a code of another transfer appears, scanning starts over with that transfer. The
joined data must match the id, the first 8 hex chars of its SHA-256.
Needs opencv-python.

  python3 qr-scan.py --out README.md   # write the data to a file
  python3 qr-scan.py                   # or print it to standard output
"""
import argparse
import base64
import binascii
import hashlib
import re
import sys
from pathlib import Path

import cv2

CHUNK = re.compile(r"([0-9a-f]{8}):(\d{1,3}):(\d{1,3}):([A-Za-z0-9+/=]+)")
CHUNK_BYTES = 64
WINDOW = "Scan the QR codes (q to stop)"


def parse_chunk(text):
  """Returns (id, chunk number, chunk count, bytes), or None for a QR code that is not a chunk."""
  match = CHUNK.fullmatch(text.strip())
  if not match:
      return None
  transfer, number, count, encoded = match.groups()
  number, count = int(number), int(count)
  if not 1 <= number <= count:
      return None
  try:
      chunk = base64.b64decode(encoded, validate=True)
  except binascii.Error:
      return None
  # Every chunk but the last is full
  if not chunk or len(chunk) > CHUNK_BYTES or (number < count and len(chunk) != CHUNK_BYTES):
      return None
  return transfer, number, count, chunk


def scan(camera):
  capture = cv2.VideoCapture(camera)
  if not capture.isOpened():
      raise ValueError(f"Could not open camera {camera}. Check that it is connected and that this terminal may use it")
  detector = cv2.QRCodeDetector()
  transfer, count, chunks = None, None, {}
  try:
      while len(chunks) != count:
          ok, frame = capture.read()
          if not ok:
              raise ValueError("Could not read from the camera")
          text, points, _ = detector.detectAndDecode(frame)
          parsed = parse_chunk(text) if text else None
          if parsed:
              if parsed[0] != transfer or parsed[2] != count:
                  # New codes on the other device: start over with them
                  transfer, count, chunks = parsed[0], parsed[2], {}
              chunks[parsed[1]] = parsed[3]
          if points is not None:
              cv2.polylines(frame, [points.astype(int)], True, (0, 200, 0) if parsed else (0, 0, 220), 3)
          status = f"{len(chunks)} of {count} read" if count else "Looking for a QR code"
          cv2.putText(frame, status, (16, 36), cv2.FONT_HERSHEY_SIMPLEX, 0.9, (0, 0, 0), 5)
          cv2.putText(frame, status, (16, 36), cv2.FONT_HERSHEY_SIMPLEX, 0.9, (255, 255, 255), 2)
          cv2.imshow(WINDOW, frame)
          if cv2.waitKey(1) & 0xFF in (ord("q"), 27):
              raise ValueError("Scanning was stopped before every QR code was read")
  finally:
      capture.release()
      cv2.destroyAllWindows()
      cv2.waitKey(1)
  data = b"".join(chunks[number] for number in range(1, count + 1))
  if hashlib.sha256(data).hexdigest()[:8] != transfer:
      raise ValueError("The scanned data does not match its id. Scan the QR codes again")
  return data


def main():
  parser = argparse.ArgumentParser(description="Scan QR codes from qr-encode.py and join the data")
  parser.add_argument("--camera", type=int, default=0, help="Camera number (default: 0)")
  parser.add_argument("--out", help="File to write the data to (default: standard output)")
  args = parser.parse_args()

  try:
      data = scan(args.camera)
  except ValueError as error:
      raise SystemExit(str(error))

  if args.out:
      Path(args.out).write_bytes(data)
      print(f"Wrote {len(data)} bytes to {args.out}", file=sys.stderr)
  else:
      sys.stdout.buffer.write(data)
      sys.stdout.flush()


if __name__ == "__main__":
  main()
