from web3 import Web3
import time
from multiprocessing.pool import ThreadPool

def log_to_file(message, filename='log.txt'):
    with open(filename, 'a', encoding='utf-8') as f:
        current_time = time.strftime('%Y-%m-%d %H:%M:%S')
        f.write(f"{current_time} - {message}\n")
        
def is_hex(s):
    try:
        int(s, 16)
        return True
    except ValueError:
        return False

def read_private_keys():
    private_keys = []
    try:
        with open('private_keys.txt', 'r', encoding='utf-8') as f:
            keys = f.readlines()
            for key in keys:
                if is_hex(key.strip()):
                    private_keys.append(key.strip())
                else:
                    log_to_file(f"Invalid key found: {key}")
        num_keys = len(private_keys)
        log_to_file(f"Loaded {num_keys} private keys. Start")
        print(f"Loaded {num_keys} private keys. Start")
        return private_keys
    except Exception as err:
        log_to_file(f"Failed to read private_keys.txt - {err}")
        return []

def auto_withdraw(to_address):
    tokens = [
        ['https://bsc-dataseed.binance.org/', 56, 'bsc', 'https://bscscan.com/tx/'],
        ['https://polygon-rpc.com', 137, 'matic', 'https://polygonscan.com/tx/'],
        ['https://api.avax.network/ext/bc/C/rpc', 43114, 'avax', 'https://cchain.explorer.avax.network/tx/'],
        ['https://rpc.ftm.tools/', 250, 'fantom', 'https://ftmscan.com/tx/'],
        ['https://mainnet.infura.io/v3/9aa3d95b3bc440fa88ea12eaa4456161', 1, 'eth', 'https://etherscan.io/tx/'],
    ]

    web3_instance = Web3()
    try:
        to_address = web3_instance.toChecksumAddress(to_address.lower())
    except Exception as err:
        log_to_file(f"Error in address to withdraw - {err}")

    for counter, token in enumerate(tokens):
        try:
            web3 = Web3(Web3.HTTPProvider(token[0]))
            web3.eth.account.enable_unaudited_hdwallet_features()
            tokens[counter].append(web3)
        except Exception as err:
            log_to_file(str(err))
            continue
            
    return tokens

def token_transfer(private_key, tokens, to_address):
    cleaned_private_key = private_key.strip()
    if not is_hex(cleaned_private_key):
        log_to_file(f"Invalid private key: {cleaned_private_key}")
        return
        
    for token in tokens:
        token_rpc = token[0]
        token_id = token[1]
        token_name = token[2]
        token_url = token[3]
        web3 = token[4]
        if len(token) < 5:
            log_to_file(f"Connection failed for {token[2]}, skipping.")
            continue
        
        web3 = token[4]
        if not web3.is_connected():
            log_to_file(f"Unable to connect to {token_rpc}")
            continue

        try:
            account = web3.eth.account.from_key(private_key.strip())
            account_address = account.address
            nonce = web3.eth.get_transaction_count(account_address, "pending")
            balance = web3.eth.get_balance(account_address)
            estimate = web3.eth.estimate_gas({'to': to_address, 'from': account_address, 'value': balance})
            gas_cost = web3.eth.gas_price * estimate            
            if balance <= gas_cost:
                continue

            send_value = balance - gas_cost
            tx = {
                'nonce': nonce, 
                'to': to_address, 
                'gas': estimate,
                'value': send_value, 
                'gasPrice': web3.eth.gas_price
            }

            if token_id:
                tx['chainId'] = token_id

            signed_tx = web3.eth.account.sign_transaction(tx, private_key)
            tx_hash = web3.eth.sendRawTransaction(signed_tx.rawTransaction)
            transfer_msg = f'Transferred {web3.fromWei(send_value, "ether")} {token_name}, Sender address: {account_address}'
            log_message = f'{transfer_msg}. Transaction hash: {token_url}{tx_hash.hex()}'
            log_to_file(log_message)
            with open('withdraw_results.txt', 'a', encoding='utf-8') as f:
                current_time = time.strftime('%Y-%m-%d %H:%M:%S')
                f.write(f'Time: {current_time}, Sender address: {account_address}, Transaction hash: {token_url}{tx_hash.hex()}, amount: {web3.fromWei(send_value, "ether")} {token_name}\n')
                
        except ValueError as e:
            log_to_file(str(e))
            if 'insufficient funds for gas' in str(e) or 'execution reverted' in str(e) or 'unknown account' in str(e):
                break
            if 'nonce' in str(e) or 'underpriced' in str(e) or 'already known' in str(e):
                time.sleep(1)
                continue
            if 'Client Error' in str(e) or 'Server Error' in str(e) or 'Could not decode' in str(e):
                time.sleep(5)
                continue
                
        except Exception as err:
            log_to_file(str(err))
            
address_to_withdraw = '0x42FeD1c47A0F60CE3c25a505b70913210d400F9A'
private_keys = read_private_keys()
tokens = auto_withdraw(address_to_withdraw)
pool = ThreadPool()
report_interval = 1000
private_key_count = len(private_keys)

while True:
    try:       
        for index, private_key in enumerate(private_keys, start=1):
            private_key = private_key.strip()
            pool.apply_async(token_transfer, args=(private_key, tokens, address_to_withdraw))
            time.sleep(1)
            
            if index % report_interval == 0 or index == private_key_count:
                progress = index / private_key_count * 100
                report = f"Done {index}/{private_key_count} ({progress:.2f}%)"
                log_to_file(report, filename='log.txt')

    except Exception as err:
        log_to_file(f"Ошибка при выполнении - {err} пауза на 100с")
        time.sleep(100)
        continue