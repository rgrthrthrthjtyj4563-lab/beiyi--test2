import pandas as pd
import sys

try:
    df = pd.read_excel('测试业务使用数据.xlsx')
    print(df.to_string())
except Exception as e:
    print(f"Error reading excel: {e}")
