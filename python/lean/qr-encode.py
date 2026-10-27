#!/usr/bin/env python3
"""
Write any data as a series of QR codes, to scan on another device with qr-scan.py.

The data is cut into chunks of 64 bytes. Each chunk becomes one QR code holding
the text <id>:<chunk number>:<chunk count>:<chunk in base64>, where id is the
first 8 hex chars of the data's SHA-256. qr-scan.py checks the whole data against
it, and codes of two different transfers are never mixed. The data is not
encrypted.

In render mode (the default) a window shows the QR codes one after another,
looping, so qr-scan.py on the other device can read them all. Space pauses, q or
Esc stops. In file mode they are saved as qr-01.png, qr-02.png, ... Needs qrcode
with Pillow, and opencv-python for render mode.

  python3 qr-encode.py README.md                         # show a file's QR codes in a window
  python3 qr-encode.py README.md --mode file --out codes/  # save them as PNG files
  cat README.md | python3 qr-encode.py --interval 0.5
"""
import argparse
import base64
import hashlib
import sys
from pathlib import Path

import qrcode

CHUNK_BYTES = 64
MAX_CHUNKS = 999


def chunk_texts(data):
  if not data:
      raise ValueError("No data to encode")
  chunks = [data[start:start + CHUNK_BYTES] for start in range(0, len(data), CHUNK_BYTES)]
  if len(chunks) > MAX_CHUNKS:
      raise ValueError(f"The data needs more than {MAX_CHUNKS} QR codes ({MAX_CHUNKS * CHUNK_BYTES} bytes)")
  transfer = hashlib.sha256(data).hexdigest()[:8]
  return [f"{transfer}:{number}:{len(chunks)}:{base64.b64encode(chunk).decode()}" for number, chunk in enumerate(chunks, 1)]


def qr_image(text, box_size):
  code = qrcode.QRCode(error_correction=qrcode.constants.ERROR_CORRECT_M, box_size=box_size, border=4)
  code.add_data(text)
  code.make(fit=True)
  return code.make_image()


def save_files(texts, out):
  width = max(2, len(str(len(texts))))
  for number, text in enumerate(texts, 1):
      path = Path(out) / f"qr-{number:0{width}d}.png"
      qr_image(text, 8).save(path)
      print(path)


def render(texts, interval):
  """Shows the QR codes one after another in a window, looping until q, Esc or the window is closed."""
  import cv2
  import numpy

  frames = []
  for number, text in enumerate(texts, 1):
      image = qr_image(text, 12).get_image().convert("L")
      # A white band under the code with its number, outside the quiet zone
      frame = numpy.full((image.height + 48, image.width), 255, dtype=numpy.uint8)
      frame[:image.height] = numpy.array(image)
      cv2.putText(frame, f"{number} / {len(texts)}", (16, image.height + 32), cv2.FONT_HERSHEY_SIMPLEX, 0.9, 0, 2)
      frames.append(frame)

  window = "QR codes (space to pause, q to stop)"
  cv2.namedWindow(window, cv2.WINDOW_AUTOSIZE)
  index, paused = 0, False
  try:
      while True:
          cv2.imshow(window, frames[index])
          key = cv2.waitKey(int(interval * 1000)) & 0xFF
          if key in (ord("q"), 27) or cv2.getWindowProperty(window, cv2.WND_PROP_VISIBLE) < 1:
              break
          if key == ord(" "):
              paused = not paused
          if not paused:
              index = (index + 1) % len(frames)
  finally:
      cv2.destroyAllWindows()
      cv2.waitKey(1)


def main():
  parser = argparse.ArgumentParser(description="Encode any data as QR codes of 64-byte base64 chunks")
  parser.add_argument("file", nargs="?", help="File to encode (default: read standard input until Ctrl-D)")
  parser.add_argument("--mode", choices=["file", "render"], default="render", help="Show the QR codes in sequence in a window, or save them as PNG files (default: render)")
  parser.add_argument("--out", default=".", help="file mode: folder to save the QR codes in as qr-01.png, qr-02.png, ... (default: here)")
  parser.add_argument("--interval", type=float, default=1.0, help="render mode: seconds to show each QR code (default: 1)")
  args = parser.parse_args()
  if args.interval <= 0:
      parser.error("--interval must be more than 0")

  if args.file:
      data = Path(args.file).read_bytes()
  else:
      print("Paste or pipe the data, then press Ctrl-D.", file=sys.stderr)
      data = sys.stdin.buffer.read()

  try:
      texts = chunk_texts(data)
  except ValueError as error:
      raise SystemExit(str(error))

  print(f"{len(texts)} QR codes for {len(data)} bytes", file=sys.stderr)
  if args.mode == "file":
      save_files(texts, args.out)
  else:
      render(texts, args.interval)


if __name__ == "__main__":
  main()
