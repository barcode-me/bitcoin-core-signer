#!/usr/bin/env python3
"""
BIP39 mnemonic + passphrase -> xprv descriptors for Bitcoin Core.
Run this offline, because the output contains private keys.
"""
import argparse
import json
import sys
from getpass import getpass
from embit import bip39, bip32
from embit.descriptor import Descriptor
from embit.descriptor.checksum import add_checksum
from embit.networks import NETWORKS

# Address Standard, BIP purpose, descriptor template (receive/change path filled in below)
SCRIPT_TYPES = [
    {
        "key": "legacy",
        "name": "Legacy (P2PKH)",
        "purpose": "44h",
        "wrap": "pkh({})",
    },
    {
        "key": "nested-segwit",
        "name": "Nested SegWit (P2SH-P2WPKH)",
        "purpose": "49h",
        "wrap": "sh(wpkh({}))",
    },
    {
        "key": "native-segwit",
        "name": "Native SegWit (P2WPKH)",
        "purpose": "84h",
        "wrap": "wpkh({})",
    },
    {
        "key": "taproot",
        "name": "Taproot (P2TR)",
        "purpose": "86h",
        "wrap": "tr({})",
    },
]


def main():
  parser = argparse.ArgumentParser()
  parser.add_argument(
    "--show-input",
    action="store_true",
    help="Echo the mnemonic and passphrase to the screen as you type them (hidden by default)",
  )
  parser.add_argument(
    "--type",
    choices=[t["key"] for t in SCRIPT_TYPES] + ["all"],
    default="all",
    help="Which script type(s) to derive descriptors for (default: all)",
  )
  parser.add_argument(
    "--bitcoin-core",
    action="store_true",
    help="Print only a bitcoin-cli importdescriptors command to stdout (messages go to stderr)",
  )
  parser.add_argument(
    "--wallet",
    default="my-wallet",
    help="Wallet name used in the --bitcoin-core command (default: my-wallet)",
  )
  args = parser.parse_args()
  out = sys.stderr if args.bitcoin_core else sys.stdout

  def prompt_input(prompt):
    if not args.show_input:
      return getpass(prompt, stream=out)
    out.write(prompt)
    out.flush()
    return input()

  if not args.show_input:
    print("Input is hidden. Pass --show-input to see what you type.", file=out)

  mnemonic = " ".join(prompt_input("Mnemonic: ").strip().lower().split())

  if not bip39.mnemonic_is_valid(mnemonic):
    raise SystemExit("Invalid BIP39 mnemonic (bad word or checksum)")

  passphrase = prompt_input("BIP39 passphrase (empty for none):")
  if passphrase:
    print("Using a BIP39 passphrase.", file=out)
  else:
    print("No BIP39 passphrase.", file=out)

  net = NETWORKS["main"]
  seed_no_passphrase = bip39.mnemonic_to_seed(mnemonic, password="")
  root_no_passphrase = bip32.HDKey.from_seed(seed_no_passphrase, version=net["xprv"])

  seed = bip39.mnemonic_to_seed(mnemonic, password=passphrase)
  root = bip32.HDKey.from_seed(seed, version=net["xprv"])

  master_xprv = root.to_base58()
  fingerprint = root.my_fingerprint.hex()
  fingerprint_no_passphrase = root_no_passphrase.my_fingerprint.hex()
  script_types = SCRIPT_TYPES if args.type == "all" else [
    t for t in SCRIPT_TYPES if t["key"] == args.type
  ]

  print("Master fingerprint (no passphrase):", fingerprint_no_passphrase, file=out)
  print("Master fingerprint:", fingerprint, file=out)

  imports = []
  for script_type in script_types:
    # Same form as Bitcoin Core's own `listdescriptors true`: master xprv followed by the full path
    receive, change = (
      add_checksum(str(Descriptor.from_string(
        script_type["wrap"].format(f"{master_xprv}/{script_type['purpose']}/0h/0h/{branch}/*")
      )))
      for branch in (0, 1)
    )
    imports += [
      {"desc": receive, "active": True, "internal": False, "range": [0, 999], "timestamp": "now"},
      {"desc": change, "active": True, "internal": True, "range": [0, 999], "timestamp": "now"},
    ]

    if not args.bitcoin_core:
      print(file=out)
      print(f"-- {script_type['name']} --", file=out)
      print("Receive :", receive, file=out)
      print("Change  :", change, file=out)

  if args.bitcoin_core:
    requests = ",\n".join("  " + json.dumps(request) for request in imports)
    print(f"bitcoin-cli -rpcwallet={args.wallet} importdescriptors '[\n{requests}\n]'")

if __name__ == "__main__":
  main()
