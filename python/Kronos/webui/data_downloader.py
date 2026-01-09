"""
Yahoo Finance 数据下载模块
从雅虎金融接口获取指定股票的历史数据
"""

import os
import pandas as pd
import requests
from datetime import datetime, timedelta
import time


def download_yahoo_finance_data(
    symbol: str,
    start_date: str = None,
    end_date: str = None,
    interval: str = "1d",
    save_dir: str = None
) -> tuple[pd.DataFrame, str]:
    """
    从雅虎金融下载股票历史数据
    
    Args:
        symbol: 股票代码 (如 AAPL, MSFT, 600519.SS 等)
                美股直接使用代码，如 AAPL
                A股需要加后缀：上海 .SS，深圳 .SZ，如 600519.SS
        start_date: 开始日期 (格式: YYYY-MM-DD)，默认为1年前
        end_date: 结束日期 (格式: YYYY-MM-DD)，默认为今天
        interval: 数据间隔，可选值:
                  1m, 2m, 5m, 15m, 30m, 60m, 90m (分钟级别，最多7天)
                  1h (小时级别，最多730天)
                  1d, 5d (日级别)
                  1wk (周级别)
                  1mo, 3mo (月级别)
        save_dir: 保存目录，默认为项目 data 目录
    
    Returns:
        tuple: (DataFrame, 保存的文件路径)
    """
    # 设置默认日期
    if end_date is None:
        end_date = datetime.now().strftime("%Y-%m-%d")
    
    if start_date is None:
        # 根据间隔设置默认开始日期
        if interval in ["1m", "2m", "5m", "15m", "30m", "60m", "90m"]:
            # 分钟级别最多7天
            start_date = (datetime.now() - timedelta(days=7)).strftime("%Y-%m-%d")
        elif interval == "1h":
            # 小时级别最多730天
            start_date = (datetime.now() - timedelta(days=60)).strftime("%Y-%m-%d")
        else:
            # 日/周/月级别默认1年
            start_date = (datetime.now() - timedelta(days=365)).strftime("%Y-%m-%d")
    
    # 转换日期为时间戳
    start_timestamp = int(datetime.strptime(start_date, "%Y-%m-%d").timestamp())
    end_timestamp = int(datetime.strptime(end_date, "%Y-%m-%d").timestamp()) + 86400  # 加一天确保包含结束日期
    
    # 构建请求URL
    url = f"https://query1.finance.yahoo.com/v8/finance/chart/{symbol}"
    
    params = {
        "period1": start_timestamp,
        "period2": end_timestamp,
        "interval": interval,
        "includePrePost": "false",
        "events": "div,splits"
    }
    
    headers = {
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
    }
    
    try:
        response = requests.get(url, params=params, headers=headers, timeout=30)
        response.raise_for_status()
        data = response.json()
        
        # 解析数据
        if "chart" not in data or "result" not in data["chart"] or not data["chart"]["result"]:
            raise ValueError(f"无法获取 {symbol} 的数据，请检查股票代码是否正确")
        
        result = data["chart"]["result"][0]
        
        # 获取时间戳
        timestamps = result.get("timestamp", [])
        if not timestamps:
            raise ValueError(f"没有获取到 {symbol} 的历史数据")
        
        # 获取报价数据
        quote = result["indicators"]["quote"][0]
        
        # 构建DataFrame
        df = pd.DataFrame({
            "timestamps": pd.to_datetime(timestamps, unit="s"),
            "open": quote.get("open", []),
            "high": quote.get("high", []),
            "low": quote.get("low", []),
            "close": quote.get("close", []),
            "volume": quote.get("volume", []),
        })
        
        # 计算 amount (成交额 = 成交量 * 平均价格)
        # 雅虎金融不直接提供成交额，这里用 volume * (open + close) / 2 估算
        df["amount"] = df["volume"] * (df["open"] + df["close"]) / 2
        
        # 删除包含空值的行
        df = df.dropna()
        
        # 按时间排序
        df = df.sort_values("timestamps").reset_index(drop=True)
        
        # 设置保存目录
        if save_dir is None:
            save_dir = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "data")
        
        # 确保目录存在
        os.makedirs(save_dir, exist_ok=True)
        
        # 生成文件名
        # 清理股票代码中的特殊字符
        clean_symbol = symbol.replace(".", "_").replace("-", "_")
        filename = f"{clean_symbol}_{interval}_{start_date}_{end_date}.csv"
        filepath = os.path.join(save_dir, filename)
        
        # 保存为CSV
        df.to_csv(filepath, index=False)
        
        print(f"数据下载成功！")
        print(f"股票代码: {symbol}")
        print(f"数据范围: {df['timestamps'].min()} ~ {df['timestamps'].max()}")
        print(f"数据条数: {len(df)}")
        print(f"保存路径: {filepath}")
        
        return df, filepath
        
    except requests.exceptions.RequestException as e:
        raise ConnectionError(f"网络请求失败: {str(e)}")
    except Exception as e:
        raise Exception(f"下载数据失败: {str(e)}")


def get_popular_symbols():
    """获取常用股票代码列表"""
    return {
        "美股": {
            "AAPL": "苹果",
            "MSFT": "微软",
            "GOOGL": "谷歌",
            "AMZN": "亚马逊",
            "TSLA": "特斯拉",
            "NVDA": "英伟达",
            "META": "Meta",
            "NFLX": "奈飞",
            "AMD": "AMD",
            "INTC": "英特尔"
        },
        "A股(上海)": {
            "600519.SS": "贵州茅台",
            "601318.SS": "中国平安",
            "600036.SS": "招商银行",
            "600276.SS": "恒瑞医药",
            "601166.SS": "兴业银行"
        },
        "A股(深圳)": {
            "000858.SZ": "五粮液",
            "000333.SZ": "美的集团",
            "002594.SZ": "比亚迪",
            "000001.SZ": "平安银行",
            "002415.SZ": "海康威视"
        },
        "港股": {
            "0700.HK": "腾讯控股",
            "9988.HK": "阿里巴巴",
            "9999.HK": "网易",
            "3690.HK": "美团",
            "1810.HK": "小米集团"
        },
        "指数": {
            "^GSPC": "标普500",
            "^DJI": "道琼斯",
            "^IXIC": "纳斯达克",
            "^HSI": "恒生指数",
            "000001.SS": "上证指数"
        }
    }


def list_available_intervals():
    """列出可用的数据间隔"""
    return {
        "1m": "1分钟 (最多7天数据)",
        "2m": "2分钟 (最多7天数据)",
        "5m": "5分钟 (最多7天数据)",
        "15m": "15分钟 (最多7天数据)",
        "30m": "30分钟 (最多7天数据)",
        "60m": "60分钟 (最多7天数据)",
        "90m": "90分钟 (最多7天数据)",
        "1h": "1小时 (最多730天数据)",
        "1d": "1天",
        "5d": "5天",
        "1wk": "1周",
        "1mo": "1月",
        "3mo": "3月"
    }


if __name__ == "__main__":
    # 测试下载
    print("=" * 50)
    print("Yahoo Finance 数据下载测试")
    print("=" * 50)
    
    # 下载苹果公司日线数据
    try:
        df, filepath = download_yahoo_finance_data(
            symbol="AAPL",
            interval="1d",
            start_date="2024-01-01"
        )
        print(f"\n数据预览:\n{df.head()}")
    except Exception as e:
        print(f"下载失败: {e}")
