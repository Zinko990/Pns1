import os
import random
import time
import requests
from tqdm import tqdm
from colorama import Fore, Style, init
from web3 import Web3
from eth_account import Account
from fake_useragent import UserAgent

from ens_contract import CONTRACT_ADDRESS, CONTRACT_ABI

init(autoreset=True)

# === CONFIG ===
CHAIN_ID = 688688
RPC_URL = "https://api.zan.top/node/v1/pharos/testnet/1e9277f51"
GAS_LIMIT = 400000
REGISTRATION_DURATION = 60 * 60 * 24 * 365  # 1 tahun
RESOLVER = Web3.to_checksum_address("0x0000000000000000000000000000000000000000")

# === Daftar Nama ===
names = ["david", "alex", "nina", "fajar", "intan", "leo", "indra", "siti", "ken", "rina"]

def generate_name():
    return random.choice(names) + str(random.randint(1000, 9999))

# === Load akun dan proxy ===
script_dir = os.path.dirname(os.path.abspath(__file__))
file_path = os.path.join(script_dir, "accounts.txt")

try:
    with open(file_path) as f:
        PRIVATE_KEYS = [line.strip() for line in f if line.strip()]
except FileNotFoundError:
    print(Fore.RED + f"❌ accounts.txt file not found at: {file_path}")
    PRIVATE_KEYS = []

# === Proses utama ===
def run_bot(private_key):
    try:
        w3 = Web3(Web3.HTTPProvider(RPC_URL))

        if not w3.is_connected():
            print(Fore.RED + "❌ RPC connection failed. Check your RPC_URL.")
            return

        account = Account.from_key(private_key)
        address = account.address

        name = generate_name()
        full_name = f"{name}.phrs"
        secret = w3.keccak(text=str(random.randint(0, 99999999)))

        contract = w3.eth.contract(address=CONTRACT_ADDRESS, abi=CONTRACT_ABI)

        # === STEP 1: COMMIT ===
        print(Fore.YELLOW + f"🔒 Step 1: Commit name {full_name}")
        commitment = contract.functions.makeCommitment(
            name, address, REGISTRATION_DURATION, secret, RESOLVER, [], False, 0
        ).call()

        tx = contract.functions.commit(commitment).build_transaction({
            "from": address,
            "gas": GAS_LIMIT,
            "chainId": CHAIN_ID,
            "nonce": w3.eth.get_transaction_count(address)
        })

        signed_tx = w3.eth.account.sign_transaction(tx, private_key)
        tx_hash = w3.eth.send_raw_transaction(signed_tx.rawTransaction)
        print(Fore.GREEN + f"✅ Commit tx hash: {tx_hash.hex()}")

        # === TUNGGU 60 DETIK ===
        print(Fore.BLUE + f"⏳ Waiting 60 seconds before registering...")
        for _ in tqdm(range(60), desc="Waiting", bar_format="{l_bar}{bar}| {remaining}s"):
            time.sleep(1)

        # === STEP 2: REGISTER ===
        print(Fore.YELLOW + f"📝 Step 2: Register name {full_name}")
        tx = contract.functions.register(
            name, address, REGISTRATION_DURATION, secret, RESOLVER, [], False, 0
        ).build_transaction({
            "from": address,
            "gas": GAS_LIMIT,
            "value": Web3.to_wei("0.02", "ether"),
            "nonce": w3.eth.get_transaction_count(address),
            "chainId": CHAIN_ID
        })

        signed_tx = w3.eth.account.sign_transaction(tx, private_key)
        tx_hash = w3.eth.send_raw_transaction(signed_tx.rawTransaction)
        print(Fore.GREEN + f"🎉 Register tx hash: {tx_hash.hex()}")

    except Exception as e:
        print(Fore.RED + f"❌ Error: {str(e)}")

# === Loop semua akun ===
if PRIVATE_KEYS:
    for i, pk in enumerate(PRIVATE_KEYS):
        for _ in range(110):
            run_bot(pk)
            print(Fore.MAGENTA + "-" * 60)
else:
    print(Fore.RED + "❌ No private keys loaded. Please check accounts.txt.")
