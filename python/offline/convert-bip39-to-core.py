#!/usr/bin/env python3
"""
BIP39 mnemonic + passphrase -> xprv descriptors for Bitcoin Core.
Run this offline, because the output contains private keys.

On a test network (testnet, signet, regtest) the keys are tprv and the BIP44 coin
type in the path is 1h instead of 0h, as Bitcoin Core expects there.
"""
import argparse
import json
import re
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


# Bitcoin Core chain names. Every test network uses the same key versions and coin type.
NETWORK_NAMES = {"main", "test", "testnet4", "signet", "regtest"}


def convert_to_core(mnemonic, passphrase="", script_types=None, wallet="my-wallet", network="main"):
  mnemonic = " ".join(mnemonic.strip().lower().split())
  if not bip39.mnemonic_is_valid(mnemonic):
    raise ValueError("Invalid BIP39 mnemonic (bad word or checksum)")
  # None means every address type. Output keeps the order of SCRIPT_TYPES.
  keys = [t["key"] for t in SCRIPT_TYPES] if script_types is None else script_types
  unknown = [key for key in keys if key not in {t["key"] for t in SCRIPT_TYPES}]
  if unknown:
    raise ValueError(f"Unknown address type: {', '.join(map(str, unknown))}")
  selected = [t for t in SCRIPT_TYPES if t["key"] in keys]
  if not selected:
    raise ValueError("Select at least one address type")
  # The wallet name ends up inside a shell command, so keep it to plain characters.
  if not re.fullmatch(r"[A-Za-z0-9._-]+", wallet):
    raise ValueError("Wallet name may only contain letters, digits, dots, dashes and underscores")

  if network not in NETWORK_NAMES:
    raise ValueError(f"Unknown network: {network}")
  net = NETWORKS["main" if network == "main" else "test"]
  coin_type = "0h" if network == "main" else "1h"
  seed_no_passphrase = bip39.mnemonic_to_seed(mnemonic, password="")
  root_no_passphrase = bip32.HDKey.from_seed(seed_no_passphrase, version=net["xprv"])

  seed = bip39.mnemonic_to_seed(mnemonic, password=passphrase)
  root = bip32.HDKey.from_seed(seed, version=net["xprv"])

  master_xprv = root.to_base58()
  imports = []
  descriptors = []
  for script_type in selected:
    # Same form as Bitcoin Core's own `listdescriptors true`: master xprv followed by the full path
    receive, change = (
      add_checksum(str(Descriptor.from_string(
        script_type["wrap"].format(f"{master_xprv}/{script_type['purpose']}/{coin_type}/0h/{branch}/*")
      )))
      for branch in (0, 1)
    )
    imports += [
      {"desc": receive, "active": True, "internal": False, "range": [0, 999], "timestamp": "now"},
      {"desc": change, "active": True, "internal": True, "range": [0, 999], "timestamp": "now"},
    ]
    descriptors.append({"name": script_type["name"], "receive": receive, "change": change})

  requests = ",\n".join("  " + json.dumps(request) for request in imports)
  return {
    "fingerprint": root.my_fingerprint.hex(),
    "fingerprint_no_passphrase": root_no_passphrase.my_fingerprint.hex(),
    "descriptors": descriptors,
    "requests": imports,
    "command": f"bitcoin-cli -rpcwallet={wallet} importdescriptors '[\n{requests}\n]'",
  }


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
  parser.add_argument(
    "--network",
    choices=sorted(NETWORK_NAMES),
    default="main",
    help="Bitcoin network, as Bitcoin Core names it (default: main)",
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

  mnemonic = prompt_input("Mnemonic: ")
  passphrase = prompt_input("BIP39 passphrase (empty for none):")
  if passphrase:
    print("Using a BIP39 passphrase.", file=out)
  else:
    print("No BIP39 passphrase.", file=out)

  try:
    converted = convert_to_core(
      mnemonic, passphrase, None if args.type == "all" else [args.type], args.wallet, args.network
    )
  except ValueError as error:
    raise SystemExit(str(error))

  print("Master fingerprint (no passphrase):", converted["fingerprint_no_passphrase"], file=out)
  print("Master fingerprint:", converted["fingerprint"], file=out)
  for descriptor in converted["descriptors"]:
    print(file=out)
    print(f"-- {descriptor['name']} --", file=out)
    print("Receive :", descriptor["receive"], file=out)
    print("Change  :", descriptor["change"], file=out)

  if args.bitcoin_core:
    print(converted["command"])


if __name__ == "__main__":
  main()
