# vn_qtrade 文档

## 简介

`vn_qtrade` 是一个基于 `vnpy` 和 `ccxt` 的服务器端交易引擎，专为实时加密货币交易而设计。它采用事件驱动架构，支持自动化交易和通过REPL（读取-求值-打印循环）进行手动控制。该项目的核心理念是简洁、快速和可扩展。

### 主要功能

*   **事件驱动**：基于 `vnpy` 的事件驱动框架，实现高效的异步操作。
*   **扩展的订单请求**：利用 `ccxt` 库来支持复杂的订单类型。
*   **自动化与手动控制**：既能执行自动化交易策略，也提供了REPL命令行界面，方便在运行时进行调试和手动干预。
*   **可扩展的策略**：用户可以轻松编写自己的交易策略。
*   **强大的交易功能**：内置止损、止盈、追踪止损和条件委托等高级功能。
*   **OKX交易所支持**：深度集成OKX交易所的交易和行情接口。

## 安装与配置

1.  **克隆项目**：
    ```bash
    git clone <repository_url>
    cd vn_qtrade
    ```

2.  **安装依赖**：
    建议使用虚拟环境。
    ```bash
    python -m venv venv
    source venv/bin/activate  # On Windows use `venv\Scripts\activate`
    pip install -r requirements.txt 
    ```
    *注意：项目中未提供 `requirements.txt` 文件，您需要根据 `imports` 手动安装依赖，主要包括 `vnpy_evo`, `ccxt`, `pandas`, `ipython`, `nest_asyncio`。*

3.  **创建 `local_setting.py`**：
    在项目根目录下创建一个名为 `local_setting.py` 的文件，并填入您的OKX API密钥信息。这是运行引擎所必需的。

    ```python
    # local_setting.py
    okx_setting: dict = {
        "API Key": "YOUR_API_KEY",
        "Secret Key": "YOUR_SECRET_KEY",
        "Passphrase": "YOUR_PASSPHRASE",
        "Server": "AWS",  # REAL, AWS, DEMO
        "Proxy Host": "",
        "Proxy Port": "",
    }
    ```

## 如何使用

1.  **编辑策略**：
    打开 `strategy/demo.py` 文件，您可以根据自己的需求修改交易逻辑。

2.  **运行引擎**：
    执行 `strategy/run.py` 脚本来启动交易引擎。
    ```bash
    python strategy/run.py
    ```
    默认情况下，`run.py` 会加载并执行 `demo.py` 中的策略。

3.  **交互式调试**：
    *   程序运行时，按 `Ctrl+C` 可以暂停策略执行，并进入IPython的交互式命令行（REPL）。
    *   在交互模式下，您可以检查引擎状态、变量，或手动执行代码。
    *   再次按 `Ctrl+C` 将退出程序。

## 核心概念

### 事件驱动架构

`vn_qtrade` 继承了 `vnpy` 的事件驱动模型。系统的核心是一个事件引擎（`EventEngine`），它负责接收和分发事件。各个模块（如交易网关、策略引擎）之间通过事件进行解耦和通信。

*   **EventEngine**: 事件引擎，负责事件的注册和分发。
*   **MainEngine**: 主引擎，管理所有其他模块。
*   **Gateway**: 交易网关，负责与交易所的连接和交互。

### `CryptoEngineBase`

`vn_qtrade/base.py` 中的 `CryptoEngineBase` 是所有加密货币交易引擎的基类。它提供了与 `vnpy` 框架交互的基础功能，包括：

*   启动和停止策略。
*   连接到交易网关。
*   发送和取消订单。
*   查询账户、持仓、订单和行情数据。
*   日志记录。

### `OKXEngine`

`vn_qtrade/okx_engine.py` 中的 `OKXEngine` 继承自 `CryptoEngineBase`，并专门为OKX交易所进行了功能增强。它利用 `ccxt` 库实现了更高级的订单和交易功能。

*   **`ccxt` 集成**：通过 `ccxt` 库，`OKXEngine` 可以发送 `vnpy` 标准接口之外的复杂订单类型，如条件委托（止损/止盈单）。
*   **止损止盈 (SL/TP)**：实现了基于持仓盈亏比例的自动止损和止盈逻辑。
*   **追踪止损**：可以根据市场价格动态调整止损价格。
*   **条件委托**：支持创建在未来某个价格触发的订单。
*   **事件处理**：监听并处理 `TICK`, `ORDER`, `TRADE`, `POSITION` 等关键事件。

## 交易策略

交易策略是 `vn_qtrade` 的核心应用部分。您可以通过编写自己的Python脚本来实现自动化交易逻辑。

### 编写策略

一个策略脚本通常是一个包含 `run(engine)` 函数的Python文件。`engine` 参数是 `OKXEngine` 的一个实例，您可以调用它的方法来实现交易逻辑。

`strategy/demo.py` 是一个很好的入门示例：

```python
from time import sleep
from vn_qtrade.okx_engine import OKXEngine

def run(engine: OKXEngine):
    """
    示例策略
    """
    # 定义要交易的合约代码
    vt_symbols = ["BTC-USDT-SWAP.OKEX", "ETH-USDT-SWAP.OKEX"]
    sleep(1) # 等待连接稳定

    # 订阅行情
    engine.subscribe(vt_symbols)
    engine.offset = 0.1

    # 设置止损止盈参数
    for vt_symbol in vt_symbols:
        engine.sltp_cfg[vt_symbol] = {'stoploss': -0.5, 'takeprofit': 4.5}

    # 获取合约信息
    for vt_symbol in vt_symbols:
        contract = engine.get_contract(vt_symbol)
        engine.write_log(f"合约信息: {contract}")

    # 持续运行
    while engine.strategy_active:
        # 轮询获取行情
        for vt_symbol in vt_symbols:
            tick = engine.get_tick(vt_symbol)
            if tick:
                msg = f"\n{tick.vt_symbol} ask:{tick.ask_price_1} {tick.ask_volume_1}                 bid: {tick.bid_price_1} {tick.bid_volume_1}"
                # engine.write_log(msg)

        # 查询账户、持仓和订单
        accounts = engine.get_all_accounts(use_df=True)
        positions = engine.get_all_positions(use_df=True)
        orders = engine.get_all_active_orders(use_df=True)
        
        # 等待进入下一轮
        sleep(0.1)
```

### 启动策略

在 `strategy/run.py` 中，您可以修改 `engine.start_strategy('demo.py')` 来加载并运行您的策略文件。

## API 参考

### `OKXEngine` (常用方法)

以下是 `OKXEngine` 类中一些常用方法的摘要。

#### 账户和持仓
*   `get_all_accounts(use_df=True)`: 获取所有账户信息。
*   `get_all_positions(use_df=True)`: 获取所有持仓信息。
*   `get_all_active_orders(use_df=True)`: 获取所有活动订单。
*   `get_contract(vt_symbol)`: 获取合约详细信息。
*   `get_tick(vt_symbol)`: 获取最新行情。

#### 交易操作
*   `buy(vt_symbol, price, volume, order_type=OrderType.LIMIT)`: 买入开多。
*   `sell(vt_symbol, price, volume, order_type=OrderType.LIMIT)`: 卖出平多。
*   `short(vt_symbol, price, volume, order_type=OrderType.LIMIT)`: 卖出开空。
*   `cover(vt_symbol, price, volume, order_type=OrderType.LIMIT)`: 买入平空。
*   `cancel_order(vt_orderid)`: 取消订单。
*   `cancel_all_trigger_orders(symbol, side='all')`: 取消所有条件委托。

#### 高级功能
*   `set_lever(vt_symbol, lever)`: 设置杠杆。
*   `set_sl(vt_symbol, sl)`: 为指定合约设置止损比例。
*   `set_all_sl(sl)`: 为所有合约设置止损比例。
*   `set_tp(vt_symbol, tp)`: 为指定合约设置止盈比例。
*   `set_all_tp(tp)`: 为所有合约设置止盈比例。
*   `cover_position(position)`: 平掉指定持仓。
*   `set_trigger_cover_positions(...)`: 为当前持仓创建条件委托（用于止损）。
*   `send_trigger_order(...)`: 发送条件委托。
*   `get_kline(vt_symbol, frequency="1h")`: 获取K线数据。

## `utils.py` 实用工具

`vn_qtrade/utils.py` 提供了一系列处理时间和日期的实用函数，方便在策略中进行时间相关的计算。

*   `kline_to_dataframe(kline_arr)`: 将K线数组转换为Pandas DataFrame。
*   `kline_resample(_df, _freq)`: 对K线数据进行重采样（例如，从1分钟线合成5分钟线）。
*   **时间戳和日期转换**：
    *   `get_cur_timestamp()`: 获取当前时间戳。
    *   `get_cur_time_str()`: 获取当前时间字符串。
    *   `get_datetime_from_ts(ts)`: 从时间戳获取`datetime`对象。
    *   `get_ts_from_str(time_str)`: 从时间字符串获取时间戳。
    *   以及其他大量用于获取特定时间点（如今日开盘、上一个小时）的函数。

## 许可证

该项目采用 **The Unlicense** 许可证，意味着它被完全释放到公共领域，您可以自由地使用、修改、分发和销售该软件，无需任何限制。详情请参阅 `LICENSE` 文件。
