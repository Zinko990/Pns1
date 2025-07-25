import threading
import queue
import random
import time
import os
from web3 import Web3, HTTPProvider
from eth_account import Account
from hexbytes import HexBytes
import logging
from typing import List, Tuple
import requests
from concurrent.futures import ThreadPoolExecutor
from urllib3.exceptions import HTTPError

# Configure logging
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

# Configuration
CONFIG = {
    'RPC_URL': "https://testnet.dplabs-internal.com",
    'CONTROLLER_ADDRESS': "0x51be1ef20a1fd5179419738fc71d95a8b6f8a175",
    'DURATION': 31536000,
    'RESOLVER': "0x9a43dcA1C3BB268546b98eb2AB1401bFc5b58505",
    'DATA': [],
    'REVERSE_RECORD': True,
    'OWNER_CONTROLLED_FUSES': 0,
    'REG_PER_KEY': 1,
    'MAX_CONCURRENCY': 10
}

# Minimal ABI for the controller contract
CONTROLLER_ABI = [
    {
        "constant": True,
        "inputs": [
            {"name": "name", "type": "string"},
            {"name": "owner", "type": "address"},
            {"name": "duration", "type": "uint256"},
            {"name": "secret", "type": "bytes32"},
            {"name": "resolver", "type": "address"},
            {"name": "data", "type": "bytes[]"},
            {"name": "reverseRecord", "type": "bool"},
            {"name": "ownerControlledFuses", "type": "uint16"}
        ],
        "name": "makeCommitment",
        "outputs": [{"name": "", "type": "bytes32"}],
        "stateMutability": "pure",
        "type": "function"
    },
    {
        "constant": False,
        "inputs": [{"name": "commitment", "type": "bytes32"}],
        "name": "commit",
        "outputs": [],
        "stateMutability": "nonpayable",
        "type": "function"
    },
    {
        "constant": True,
        "inputs": [
            {"name": "name", "type": "string"},
            {"name": "duration", "type": "uint256"}
        ],
        "name": "rentPrice",
        "outputs": [
            {
                "components": [
                    {"name": "base", "type": "uint256"},
                    {"name": "premium", "type": "uint256"}
                ],
                "name": "",
                "type": "tuple"
            }
        ],
        "stateMutability": "view",
        "type": "function"
    },
    {
        "constant": False,
        "inputs": [
            {"name": "name", "type": "string"},
            {"name": "owner", "type": "address"},
            {"name": "duration", "type": "uint256"},
            {"name": "secret", "type": "bytes32"},
            {"name": "resolver", "type": "address"},
            {"name": "data", "type": "bytes[]"},
            {"name": "reverseRecord", "type": "bool"},
            {"name": "ownerControlledFuses", "type": "uint16"}
        ],
        "name": "register",
        "outputs": [],
        "stateMutability": "payable",
        "type": "function"
    }
]

def load_file_lines(filename: str) -> List[str]:
    try:
        with open(filename, 'r') as f:
            return [line.strip() for line in f if line.strip()]
    except FileNotFoundError:
        logger.error(f"Tệp {filename} không tìm thấy")
        return []

def random_name(length: int = 9) -> str:
    chars = 'abcdefghijklmnopqrstuvwxyz'
    return ''.join(random.choice(chars) for _ in range(length))

def test_proxy(proxy: str) -> bool:
    """Kiểm tra proxy có hoạt động hay không"""
    try:
        response = requests.get('https://api.ipify.org', proxies={'http': proxy, 'https': proxy}, timeout=5)
        return response.status_code == 200
    except (requests.RequestException, HTTPError):
        return False

def create_web3_instance(proxy: str = None) -> Web3:
    if proxy:
        session = requests.Session()
        session.proxies = {'http': proxy, 'https': proxy}
        return Web3(HTTPProvider(CONFIG['RPC_URL'], session=session))
    return Web3(HTTPProvider(CONFIG['RPC_URL']))

def validate_private_key(private_key: str) -> bool:
    """Kiểm tra khóa riêng hợp lệ"""
    if private_key.startswith('0x'):
        private_key = private_key[2:]
    if len(private_key) != 64 or not all(c in '0123456789abcdefABCDEF' for c in private_key):
        return False
    return True

def register_domain(private_key: str, index: int, reg_index: int, proxy: str = None) -> None:
    MAX_RETRY = 5
    retry = 0
    
    if not validate_private_key(private_key):
        logger.error(f"[Wallet #{index+1} | Attempt {reg_index}] Khóa riêng không hợp lệ")
        return

    w3 = create_web3_instance(proxy)
    
    try:
        controller_address = w3.to_checksum_address(CONFIG['CONTROLLER_ADDRESS'])
        resolver_address = w3.to_checksum_address(CONFIG['RESOLVER'])
    except ValueError as e:
        logger.error(f"[Wallet #{index+1} | Attempt {reg_index}] Địa chỉ không hợp lệ trong cấu hình: {e}")
        return

    while retry < MAX_RETRY:
        try:
            account = Account.from_key(private_key)
            controller = w3.eth.contract(address=controller_address, abi=CONTROLLER_ABI)
            
            owner = account.address
            name = random_name()
            secret = '0x' + os.urandom(32).hex()
            
            logger.info(f"[Wallet #{index+1} | Attempt {reg_index}] Wallet: {owner}, Name: {name}.phrs")

            # 1. Tạo commitment
            commitment = controller.functions.makeCommitment(
                name,
                owner,
                CONFIG['DURATION'],
                HexBytes(secret),
                resolver_address,
                CONFIG['DATA'],
                CONFIG['REVERSE_RECORD'],
                CONFIG['OWNER_CONTROLLED_FUSES']
            ).call()
            logger.info(f"[Wallet #{index+1} | Attempt {reg_index}] Commitment: {commitment.hex()}")

            # 2. Gửi commit
            tx = controller.functions.commit(commitment).build_transaction({
                'from': owner,
                'nonce': w3.eth.get_transaction_count(owner),
                'gas': 200000,
                'gasPrice': w3.eth.gas_price
            })
            signed_tx = w3.eth.account.sign_transaction(tx, private_key)
            tx_hash = w3.eth.send_raw_transaction(signed_tx.raw_transaction)
            w3.eth.wait_for_transaction_receipt(tx_hash)
            logger.info(f"[Wallet #{index+1} | Attempt {reg_index}] Đã gửi commitment!")

            # 3. Chờ minCommitmentAge
            logger.info(f"[Wallet #{index+1} | Attempt {reg_index}] Đang chờ minCommitmentAge 60s...")
            time.sleep(60)

            # 4. Tính giá
            price = controller.functions.rentPrice(name, CONFIG['DURATION']).call()
            value = price[0] + price[1]
            logger.info(f"[Wallet #{index+1} | Attempt {reg_index}] Giá: {w3.from_wei(value, 'ether')} ETH")

            # 5. Đăng ký
            tx = controller.functions.register(
                name,
                owner,
                CONFIG['DURATION'],
                HexBytes(secret),
                resolver_address,
                CONFIG['DATA'],
                CONFIG['REVERSE_RECORD'],
                CONFIG['OWNER_CONTROLLED_FUSES']
            ).build_transaction({
                'from': owner,
                'nonce': w3.eth.get_transaction_count(owner),
                'gas': 300000,
                'gasPrice': w3.eth.gas_price,
                'value': value
            })
            signed_tx = w3.eth.account.sign_transaction(tx, private_key)
            tx_hash = w3.eth.send_raw_transaction(signed_tx.raw_transaction)
            w3.eth.wait_for_transaction_receipt(tx_hash)
            logger.info(f"[Wallet #{index+1} | Attempt {reg_index}] Đăng ký thành công!")
            break

        except Exception as err:
            retry += 1
            msg = str(err)[:120] + '...' if len(str(err)) > 120 else str(err)
            if retry < MAX_RETRY:
                logger.warning(f"[Wallet #{index+1} | Attempt {reg_index}] Lỗi: {msg} - chờ 60s trước khi thử lại {retry}/{MAX_RETRY}...")
                time.sleep(60)
            else:
                logger.error(f"[Wallet #{index+1} | Attempt {reg_index}] Thất bại sau {MAX_RETRY} lần thử: {msg}")
                break

def main():
    pk_list = load_file_lines("pk.txt")
    proxy_list = [proxy for proxy in load_file_lines("proxy.txt") if test_proxy(proxy)]
    
    if not pk_list:
        logger.error("Không tìm thấy khóa riêng trong pk.txt")
        return

    tasks = [(pk, idx, i + 1) for idx, pk in enumerate(pk_list) for i in range(CONFIG['REG_PER_KEY'])]

    with ThreadPoolExecutor(max_workers=CONFIG['MAX_CONCURRENCY']) as executor:
        futures = [executor.submit(register_domain, pk, idx, reg_idx, random.choice(proxy_list) if proxy_list else None)
                   for pk, idx, reg_idx in tasks]
        for future in futures:
            future.result()  # Chờ tất cả tác vụ hoàn thành

    logger.info("Tất cả tác vụ đã hoàn thành!")

if __name__ == "__main__":
    while True:
        try:
            main()
            break
        except Exception as err:
            logger.error(f"Lỗi nghiêm trọng trong main: {str(err)}")
            logger.info("Chờ 60s trước khi thử lại tất cả...")
            time.sleep(60)
