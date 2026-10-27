#!/usr/bin/env python3
"""
Local server that lets the guide's pages run the scripts in this folder. Run this
offline, because requests carry secrets such as seed phrases.

It listens on 127.0.0.1 only and accepts POST /run with a JSON body:
  {"script": "decrypt-backup-to-bip39", "inputs": {"backup": "...", ...}}
It imports the named script and calls its function with the inputs. Only scripts
listed in SCRIPTS can run, and each one only accepts the inputs listed for it.
"""
import argparse
import importlib.util
import json
import sys
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

SCRIPT_DIR = Path(__file__).resolve().parent
MAX_BODY_BYTES = 64 * 1024

# script name -> file, function to call, required inputs and optional inputs
SCRIPTS = {
    "decrypt-backup-to-bip39": {
        "function": "decrypt_backup",
        "required": {"backup", "encoding", "words", "passphrase"},
        "optional": {"otp"},
    },
    "delete-wallet": {
        "function": "delete_wallet",
        "required": {"wallet", "confirm"},
        "optional": {"datadir"},
    },
    "list-public-descriptors": {
        "function": "list_public_descriptors",
        "required": {"wallet"},
        "optional": {"datadir"},
    },
    "descriptors-to-sb58": {
        "function": "encode_sb58",
        "required": {"descriptors"},
        "optional": set(),
    },
    "import-public-descriptors": {
        "function": "import_public_descriptors",
        "required": {"wallet", "descriptors"},
        "optional": {"datadir", "rescan_since", "create_wallet"},
    },
    "create-psbt": {
        "function": "create_psbt",
        "required": {"wallet", "address", "amount", "unit", "subtract_fee"},
        "optional": {"fee_rate", "change_type", "datadir"},
    },
    "decode-psbt": {
        "function": "decode_psbt",
        "required": {"psbt"},
        "optional": {"wallet", "datadir"},
    },
    "sign-psbt": {
        "function": "sign_psbt",
        "required": {"psbt", "wallet"},
        "optional": {"datadir"},
    },
    "import-descriptors": {
        "function": "import_descriptors",
        "required": {"wallet", "requests"},
        "optional": {"datadir"},
    },
    "convert-bip39-to-core": {
        "function": "convert_to_core",
        "required": {"mnemonic"},
        "optional": {"passphrase", "script_types", "wallet"},
    },
}


def run_script(name, inputs):
  spec = SCRIPTS.get(name)
  if spec is None:
      raise ValueError(f"Unknown script: {name}")
  if not isinstance(inputs, dict):
      raise ValueError("Inputs must be an object")
  allowed = spec["required"] | spec["optional"]
  unexpected = sorted(set(inputs) - allowed)
  missing = sorted(spec["required"] - set(inputs))
  if unexpected:
      raise ValueError(f"Unexpected inputs: {', '.join(unexpected)}")
  if missing:
      raise ValueError(f"Missing inputs: {', '.join(missing)}")
  # Import on every request so edits to a script apply without restarting.
  module_spec = importlib.util.spec_from_file_location(
      name.replace("-", "_"), SCRIPT_DIR / f"{name}.py"
  )
  module = importlib.util.module_from_spec(module_spec)
  module_spec.loader.exec_module(module)
  return getattr(module, spec["function"])(**inputs)


def make_handler(port, allowed_origins):
  allowed_hosts = {f"127.0.0.1:{port}", f"localhost:{port}"}

  class Handler(BaseHTTPRequestHandler):
      def send_json(self, status, body):
          data = json.dumps(body).encode()
          self.send_response(status)
          origin = self.headers.get("Origin")
          if origin in allowed_origins:
              self.send_header("Access-Control-Allow-Origin", origin)
              self.send_header("Vary", "Origin")
          self.send_header("Content-Type", "application/json")
          self.send_header("Content-Length", str(len(data)))
          self.send_header("Cache-Control", "no-store")
          self.end_headers()
          self.wfile.write(data)

      def reject(self, reason, hint=""):
          # Hosts and origins are not secret, and naming them shows what to allow.
          print(f"Rejected {self.command} {self.path}: {reason}{hint}", file=sys.stderr)
          self.send_json(403, {"error": f"{reason}{hint}"})

      def allowed(self):
          # The Host check stops DNS rebinding, the Origin check stops other websites.
          host = self.headers.get("Host")
          if host not in allowed_hosts:
              self.reject(f"Host not allowed: {host}")
              return False
          origin = self.headers.get("Origin")
          if origin is not None and origin not in allowed_origins:
              if origin == "null":
                  hint = ". The page was opened from a file. From the project folder, serve it with python3 -m http.server 8000 and open http://localhost:8000/build/"
              else:
                  hint = f". Serve the pages from an allowed origin or restart the server with --allow-origin {origin}"
              self.reject(f"Origin not allowed: {origin}", hint)
              return False
          return True

      def do_OPTIONS(self):
          if not self.allowed():
              return
          self.send_response(204)
          origin = self.headers.get("Origin")
          if origin in allowed_origins:
              self.send_header("Access-Control-Allow-Origin", origin)
              self.send_header("Vary", "Origin")
          self.send_header("Access-Control-Allow-Methods", "POST, GET")
          self.send_header("Access-Control-Allow-Headers", "Content-Type")
          self.send_header("Content-Length", "0")
          self.end_headers()

      def do_GET(self):
          if not self.allowed():
              return
          if self.path == "/health":
              self.send_json(200, {"status": "ok"})
          else:
              self.send_json(404, {"error": "Not found"})

      def do_POST(self):
          if not self.allowed():
              return
          if self.path != "/run":
              return self.send_json(404, {"error": "Not found"})
          # Requiring JSON makes browsers send a preflight for cross-origin requests.
          if self.headers.get("Content-Type", "").split(";")[0].strip() != "application/json":
              return self.send_json(415, {"error": "Content-Type must be application/json"})
          try:
              length = int(self.headers.get("Content-Length", ""))
          except ValueError:
              return self.send_json(411, {"error": "Content-Length required"})
          if not 0 <= length <= MAX_BODY_BYTES:
              return self.send_json(413, {"error": "Request too large"})
          try:
              request = json.loads(self.rfile.read(length))
              result = run_script(request["script"], request.get("inputs", {}))
          except ValueError as error:
              # Also covers bad JSON. Messages are written by the scripts and never echo inputs.
              return self.send_json(400, {"error": str(error)})
          except (KeyError, TypeError):
              return self.send_json(400, {"error": "Request must include a script name and inputs"})
          except ImportError as error:
              return self.send_json(500, {"error": f"Missing Python dependency: {error}"})
          except Exception as error:
              return self.send_json(500, {"error": f"{type(error).__name__} while running the script"})
          self.send_json(200, {"result": result})

  return Handler


def main():
  parser = argparse.ArgumentParser()
  parser.add_argument("--port", type=int, default=8765, help="Port to listen on (default: 8765)")
  parser.add_argument(
      "--allow-origin",
      action="append",
      help="Origin of the guide's pages (default: http://localhost:8000 and http://127.0.0.1:8000)",
  )
  args = parser.parse_args()
  origins = set(args.allow_origin or ["http://localhost:8000", "http://127.0.0.1:8000"])

  server = ThreadingHTTPServer(("127.0.0.1", args.port), make_handler(args.port, origins))
  print(f"Listening on http://127.0.0.1:{args.port} for pages from: {', '.join(sorted(origins))}")
  print("Press Ctrl-C to stop.")
  try:
      server.serve_forever()
  except KeyboardInterrupt:
      print()


if __name__ == "__main__":
  main()
