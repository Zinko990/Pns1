def register_domain(private_key: str, name: str, task_index: int, proxy: str = None) -> None:
    MAX_RETRY = 5
    retry = 0

    if not validate_private_key(private_key):
        logger.error(f"[Task #{task_index}] Invalid private key for domain {name}.phrs")
        return

    w3 = create_web3_instance(proxy)

    try:
        controller_address = w3.to_checksum_address(CONFIG['CONTROLLER_ADDRESS'])
        resolver_address = w3.to_checksum_address(CONFIG['RESOLVER'])
    except ValueError as e:
        logger.error(f"[Task #{task_index}] Invalid address in config: {e}")
        return

    while retry < MAX_RETRY:
        try:
            account = Account.from_key(private_key)
            controller = w3.eth.contract(address=controller_address, abi=CONTROLLER_ABI)

            owner = account.address
            secret = '0x' + os.urandom(32).hex()

            logger.info(f"[Task #{task_index}] Wallet: {owner}, Domain: {name}.phrs")

            # Step 1: Make Commitment
            commitment = controller.functions.makeCommitment(
                name, owner, CONFIG['DURATION'], HexBytes(secret), 
                resolver_address, CONFIG['DATA'], CONFIG['REVERSE_RECORD'], 
                CONFIG['OWNER_CONTROLLED_FUSES']
            ).call()
            logger.info(f"[Task #{task_index}] Commitment: {commitment.hex()}")

            # Estimate gas for commit transaction
            commit_tx = controller.functions.commit(commitment).build_transaction({
                'from': owner,
                'nonce': w3.eth.get_transaction_count(owner),
                'gasPrice': w3.to_wei(2, 'gwei'),  # Lower gas price
            })
            commit_tx['gas'] = controller.functions.commit(commitment).estimate_gas({
                'from': owner
            })

            signed_tx = w3.eth.account.sign_transaction(commit_tx, private_key)
            tx_hash = w3.eth.send_raw_transaction(signed_tx.raw_transaction)
            receipt = w3.eth.wait_for_transaction_receipt(tx_hash, timeout=120)
            logger.info(f"[Task #{task_index}] Commitment sent for {name}.phrs! Gas Used: {receipt['gasUsed']}")

            # Step 2: Wait for minCommitmentAge
            logger.info(f"[Task #{task_index}] Waiting 60 seconds for minCommitmentAge...")
            time.sleep(60)  # Adjust if minCommitmentAge differs

            # Step 3: Get rent price
            price = controller.functions.rentPrice(name, CONFIG['DURATION']).call()
            value = price[0] + price[1]
            logger.info(f"[Task #{task_index}] Price for {name}.phrs: {w3.from_wei(value, 'ether')} PHRS")

            # Step 4: Register domain with estimated gas
            register_tx = controller.functions.register(
                name, owner, CONFIG['DURATION'], HexBytes(secret), 
                resolver_address, CONFIG['DATA'], CONFIG['REVERSE_RECORD'], 
                CONFIG['OWNER_CONTROLLED_FUSES']
            ).build_transaction({
                'from': owner,
                'nonce': w3.eth.get_transaction_count(owner),
                'gasPrice': w3.to_wei(2, 'gwei'),  # Lower gas price
                'value': value
            })
            register_tx['gas'] = controller.functions.register(
                name, owner, CONFIG['DURATION'], HexBytes(secret), 
                resolver_address, CONFIG['DATA'], CONFIG['REVERSE_RECORD'], 
                CONFIG['OWNER_CONTROLLED_FUSES']
            ).estimate_gas({
                'from': owner,
                'value': value
            })

            signed_tx = w3.eth.account.sign_transaction(register_tx, private_key)
            tx_hash = w3.eth.send_raw_transaction(signed_tx.raw_transaction)
            receipt = w3.eth.wait_for_transaction_receipt(tx_hash, timeout=120)
            logger.info(f"✅ [Task #{task_index}] Successfully registered {name}.phrs, Gas Used: {receipt['gasUsed']}")
            break

        except ValueError as ve:
            retry += 1
            msg = str(ve)[:120] + '...' if len(str(ve)) > 120 else str(ve)
            if "nonce too low" in msg or "replacement transaction underpriced" in msg:
                logger.warning(f"[Task #{task_index}] Nonce issue on {name}.phrs: {msg} - retrying {retry}/{MAX_RETRY}...")
                time.sleep(10)  # Shorter wait for nonce issues
            elif "insufficient funds" in msg:
                logger.error(f"[Task #{task_index}] Insufficient funds for {name}.phrs: {msg}")
                break
            elif retry < MAX_RETRY:
                logger.warning(f"[Task #{task_index}] Error on {name}.phrs: {msg} - retrying {retry}/{MAX_RETRY} after 60 seconds...")
                time.sleep(60)
            else:
                logger.error(f"❌ [Task #{task_index}] Failed to register {name}.phrs after {MAX_RETRY} retries: {msg}")
                break
        except Exception as err:
            retry += 1
            msg = str(err)[:120] + '...' if len(str(err)) > 120 else str(err)
            if retry < MAX_RETRY:
                logger.warning(f"[Task #{task_index}] Error on {name}.phrs: {msg} - retrying {retry}/{MAX_RETRY} after 60 seconds...")
                time.sleep(60)
            else:
                logger.error(f"❌ [Task #{task_index}] Failed to register {name}.phrs after {MAX_RETRY} retries: {msg}")
                break
