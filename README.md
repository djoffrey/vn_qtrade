# vn_qtrade
A sever-side trade engine based on vnpy and ccxt for realtime trading.

Features
1. event driven vnpy framework and ccxt to extend complex order requests
2. automate + REPL command for all actions (I like it this way)

simple, fast, extensible

### How to use:

1. create local_setting.py

```
okex_setting: dict = {
    "API Key": "",
    "Secret Key": "",
    "Passphrase": "",
    "Server": ["REAL", "AWS", "DEMO"],
    "Proxy Host": "",
    "Proxy Port": "",
}
```

2. try to edit the demo.py

```
python run.py  

# will load demo.py
# press Ctrl+c to pause if you want to debug or inspect the program
# press Ctrl+c twice will exit the program
```

