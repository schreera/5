from web3 import Web3
import time
from multiprocessing.pool import ThreadPool

def log_to_file(message, filename='log.txt'):
    with open(filename, 'a', encoding='utf-8') as f:
        f.write(f"{time.strftime('%Y-%m-%d %H:%M:%S')} - {message}\n")
        
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
                    print(f"Invalid key found: {key}")
        return private_keys
    except Exception as err:
        log_to_file(f"Failed to read private_keys.txt - {err}")
        print(f"Failed to read private_keys.txt - {err}")
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
        print(f"Error in address to withdraw - {err}")

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
        print(f"Invalid private key: {cleaned_private_key}")
        return
        
    for token in tokens:
        token_rpc = token[0]
        token_id = token[1]
        token_name = token[2]
        token_url = token[3]
        web3 = token[4]  # Use the previously created instance
        if len(token) < 5:
            print(f"Connection failed for {token[2]}, skipping.")
            continue
        
        web3 = token[4]  # Use the previously created instance

        if not web3.is_connected():
            log_to_file(f"Unable to connect to {token_rpc}") # Запись ошибки в лог
            continue

        try:
            account = web3.eth.account.from_key(private_key.strip())
            account_address = account.address
            nonce = web3.eth.get_transaction_count(account_address, "pending")

            balance = web3.eth.get_balance(account_address)
            estimate = web3.eth.estimate_gas({'to': to_address, 'from': account_address, 'value': balance})
            gas_cost = web3.eth.gas_price * estimate
            
            if balance <= gas_cost:
               # print(f"Insufficient balance in {token_name} for transaction fees.")
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
            print(f'Transferred {web3.fromWei(send_value, "ether")} {token_name} to {to_address}')
            log_message = f'Transferred {web3.fromWei(send_value, "ether")} {token_name} to {to_address}. Transaction hash: {token_url}{tx_hash.hex()}'
            log_to_file(log_message)
            print(log_message)
            with open('withdraw_results.txt', 'a', encoding='utf-8') as f:
                f.write(f'Sender address: {account_address}, transfer hash: {token_url}{tx_hash.hex()}, amount: {web3.fromWei(send_value, "ether")} {token_name}\n')

        except ValueError as e:
            print(e)
            log_to_file(str(e))
            if 'insufficient funds for gas' in str(e) or 'execution reverted' in str(e) or 'unknown account' in str(e):
                break
            if 'nonce' in str(e) or 'underpriced' in str(e) or 'already known' in str(e):
                time.sleep(0.5)
                continue
            if 'Client Error' in str(e) or 'Server Error' in str(e) or 'Could not decode' in str(e):
                time.sleep(3)
                continue
        except Exception as err:
            print(err)
            
address_to_withdraw = '0x6ba8b426b29432Eb3C48d436C42Fe2C29f7e7545'
private_keys = read_private_keys()
tokens = auto_withdraw(address_to_withdraw)

pool = ThreadPool()  # инициализация пула потоков

while True:
    try:
        print(f"Checking {len(private_keys)} private keys...")

        for private_key in private_keys:
            private_key = private_key.strip()  # Убираем возможные пробелы или переносы строки
            pool.apply_async(token_transfer, args=(private_key, tokens, address_to_withdraw))
            time.sleep(1)
            
    except Exception as err:
        log_to_file(f"Error while running autoWithdraw - {err}")
        print("Error while running autoWithdraw, trying again...")
        continue

