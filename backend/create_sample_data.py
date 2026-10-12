"""
Create a sample Excel file for testing the data report generator.
"""

import numpy as np
import pandas as pd

np.random.seed(42)

# Generate sample sales data
n_records = 500
dates = pd.date_range("2024-01-01", periods=365, freq="D")
regions = ["华东", "华南", "华北", "西南", "华中"]
categories = ["电子产品", "服装", "食品", "家居", "美妆"]
products = {
    "电子产品": ["手机", "笔记本电脑", "平板", "耳机", "智能手表"],
    "服装": ["上衣", "裤子", "裙子", "外套", "内衣"],
    "食品": ["零食", "饮料", "粮油", "水果", "乳制品"],
    "家居": ["沙发", "床垫", "灯具", "厨具", "收纳"],
    "美妆": ["护肤", "彩妆", "香水", "洗护", "防晒"],
}

data = []
for _ in range(n_records):
    date = np.random.choice(dates)
    region = np.random.choice(regions)
    category = np.random.choice(categories)
    product = np.random.choice(products[category])
    quantity = np.random.randint(1, 50)
    unit_price = round(np.random.uniform(10, 2000), 2)
    sales = round(quantity * unit_price, 2)
    profit = round(sales * np.random.uniform(0.1, 0.4), 2)

    data.append({
        "日期": date,
        "地区": region,
        "品类": category,
        "商品": product,
        "销量": quantity,
        "单价": unit_price,
        "销售额": sales,
        "利润": profit,
    })

df = pd.DataFrame(data)
df = df.sort_values("日期").reset_index(drop=True)

# Save to Excel
output_path = "../sample_data.xlsx"
df.to_excel(output_path, index=False, engine="openpyxl")
print(f"Sample data saved to {output_path}")
print(f"Shape: {df.shape}")
print(f"Columns: {list(df.columns)}")
print(df.head(10))