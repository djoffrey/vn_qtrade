import pytz
import datetime
from typing import Sequence, Any, Callable

import pandas as pd
from pandas import DataFrame

def to_df(data_list: Sequence):
    """
    Convert a list of objects to DataFrame.
    """
    if not data_list:
        return None

    dict_list = [data.__dict__ for data in data_list if data is not None]
    df = DataFrame(dict_list)
    if 'datetime' in df.columns:
        df.index = df.datetime
    return df

def get_data(func: Callable, arg: Any = None, use_df: bool = True):
    """
    Helper function to call a function and optionally convert to DataFrame.
    """
    if not arg:
        data = func()
    else:
        data = func(arg)

    if not use_df:
        return data
    elif data is None:
        return data
    else:
        if not isinstance(data, list):
            data = [data]
        return to_df(data)

def kline_to_dataframe(kline_arr) -> pd.DataFrame:
    """
    Parse kline to pd.DataFrame with datetime index
    """
    df = pd.DataFrame(kline, columns=['ts', 'open', 'high', 'low', 'close', 'volume'])
    df['datetime'] = pd.to_datetime(df['ts'], unit='ms')
    df.index = df['datetime']
    del df['datetime']
    return df

def kline_resample(_df: pd.DataFrame, _freq: str) -> pd.DataFrame:
    """
    在resample的过程中，容易错误的填充其他数据
    1. 交易量为0的k线剔除出计算之外
    2. resample完成之后，空的K线高开低收价格填充为上一根不为空的k线的收盘价
    3. 不能把交易量填充掉
    """
    if _df is None:
        return None
    if _freq == '1M':
        freq = 'MS'
    # elif _freq == '1min':
    #    return _df
    else:
        freq = _freq
    ohlc = {
        'open': 'first',
        'high': 'max',
        'low': 'min',
        'close': 'last',
        'volume': 'sum',
        # 'quote_volume': 'sum'
    }
    # 先保存交易量，否则填充之后就无法过滤
    # 排除掉交易量为0的k线
    _df = _df[_df['volume'] != 0]
    df_unfill = _df.resample(freq, closed='right', label='right').agg(ohlc)
    # only close column will be used
    df = _df.resample(freq, closed='right', label='right').apply(ohlc).ffill()
    closes = df['close']
    df['open'] = df_unfill['open'].combine_first(closes)
    df['high'] = df_unfill['high'].combine_first(closes)
    df['low'] = df_unfill['low'].combine_first(closes)
    df['close'] = df_unfill['close'].combine_first(closes)
    # remove ffilled volume values
    # del df['volume']
    # replace the correct volume value
    df['volume'] = df_unfill['volume']
    # fill the NAN with zero
    df['volume'] = df['volume'].fillna(0)
    df['exchange'] = _df.iloc[0]['exchange']
    df['frequency'] = _freq
    df['base'] = _df.iloc[0]['base_symbol']
    df['quote'] = _df.iloc[0]['quote_symbol']
    rebuild_ts = [int(pd.datetime.timestamp(i)) for i in df.index]
    df['ts'] = rebuild_ts

    return df
