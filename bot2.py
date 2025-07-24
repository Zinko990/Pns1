import random
import time
from tqdm import tqdm
from colorama import Fore, init
from web3 import Web3
from eth_account import Account

from ens_contract import CONTRACT_ADDRESS, CONTRACT_ABI  # ✅ သင့်ဖိုင်ထဲမှာပါ

init(autoreset=True)

# === CONFIG ===
CHAIN_ID = 688688
RPC_URL = "https://your-rpc-url-here"  # ✅ Pharos testnet RPC
GAS_LIMIT = 400000
REGISTRATION_DURATION = 60 * 60 * 24 * 365  # 1 year
RESOLVER = Web3.to_checksum_address("0x0000000000000000000000000000000000000000")

# === NAMES ===
names = ["david", "alex", "nina", "fajar", "intan", "leo", "indra", "siti", "ken", "rina"]

def generate_name():
    return random.choice(names) + str(random.randint(1000, 9999))

# === Load Accounts ===
with open("accounts.txt") as f:
    PRIVATE_KEYS = [line.strip() for line in f if line.strip()]

# === Main Bot Function ===
def run_bot(private_key):
    try:
        w3 = Web3(Web3.HTTPProvider(RPC_URL))
        if not w3.is_connected():
            print(Fore.RED + "❌ RPC connection failed!")
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

        commit_tx = contract.functions.commit(commitment).build_transaction({
            "from": address,
            "gas": GAS_LIMIT,
            "chainId": CHAIN_ID,
            "nonce": w3.eth.get_transaction_count(address),
        })

        signed_commit = w3.eth.account.sign_transaction(commit_tx, private_key)
        commit_tx_hash = w3.eth.send_raw_transaction(signed_commit.raw_transaction)
        print(Fore.GREEN + f"✅ Commit tx hash: {commit_tx_hash.hex()}")

        # Wait 65 seconds (respect commitment age)
        print(Fore.BLUE + f"⏳ Waiting 65 seconds before registering...")
        for _ in tqdm(range(65), desc="Waiting", bar_format="{l_bar}{bar}| {remaining}s"):
            time.sleep(1)

        # === STEP 2: REGISTER ===
        print(Fore.YELLOW + f"📝 Step 2: Register name {full_name}")

        # If price checking is supported:
        # price = contract.functions.rentPrice(name, REGISTRATION_DURATION).call()

        register_tx = contract.functions.register(
            name, address, REGISTRATION_DURATION, secret, RESOLVER, [], False, 0
        ).build_transaction({
            "from": address,
            "gas": GAS_LIMIT,
            "value": Web3.to_wei("0.02", "ether"),  # Or replace with `price` above
            "nonce": w3.eth.get_transaction_count(address),
            "chainId": CHAIN_ID
        })

        signed_register = w3.eth.account.sign_transaction(register_tx, private_key)
        register_tx_hash = w3.eth.send_raw_transaction(signed_register.raw_transaction)
        print(Fore.GREEN + f"🎉 Register tx hash: {register_tx_hash.hex()}")

    except Exception as e:
        print(Fore.RED + f"❌ Error: {str(e)}")

# === Run For All Accounts ===
for i, pk in enumerate(PRIVATE_KEYS):
    print(Fore.MAGENTA + f"🌐 Starting registration for Account #{i+1}")
    run_bot(pk)
    print(Fore.MAGENTA + "-" * 60)
    time.sleep(5)  # Optional: avoid sending too 
