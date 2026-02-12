
import pandas as pd
import numpy as np
import time
import os
import sys

# Add backend to path to import logic
sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), '../backend')))

from logic import parse_business_data_preview, load_config

def generate_large_excel(filename, rows=100000, cols=20):
    print(f"Generating {filename} with {rows} rows and {cols} columns...")
    df = pd.DataFrame(np.random.randint(0, 100, size=(rows, cols)), columns=[f"Col_{i}" for i in range(cols)])
    # Add some specific columns used in logic
    df["年份"] = 2023
    df["月份"] = np.random.randint(1, 13, size=rows)
    df["服务提供方"] = "TestProvider"
    
    start = time.time()
    df.to_excel(filename, index=False)
    print(f"File generation took {time.time() - start:.2f} seconds")
    return filename

def test_parsing(filename):
    print(f"Testing parsing of {filename}...")
    file_size = os.path.getsize(filename) / (1024 * 1024)
    print(f"File size: {file_size:.2f} MB")

    start = time.time()
    # Simulate what happens in backend/main.py -> logic.py
    # Note: parse_business_data_preview loads config which queries DB. 
    # We might need to mock config or ensure DB is accessible. 
    # Assuming DB is at backend/data/app.db which logic.py expects.
    
    # We will just call pd.read_excel directly first to isolate pandas performance
    print("Step 1: Raw pd.read_excel (default openpyxl)...")
    start = time.time()
    df = pd.read_excel(filename)
    read_time = time.time() - start
    print(f"Raw pd.read_excel took {read_time:.2f} seconds")
    
    print("Step 1b: pd.read_excel (calamine)...")
    try:
        start = time.time()
        df = pd.read_excel(filename, engine='calamine')
        read_time = time.time() - start
        print(f"Raw pd.read_excel (calamine) took {read_time:.2f} seconds")
    except Exception as e:
        print(f"Calamine test failed: {e}")
    
    # Now test full logic if possible (might fail if DB not found/locked)
    try:
        start = time.time()
        print("Step 2: Full logic parse_business_data_preview...")
        # We need to change CWD or setup paths for logic to find DB
        # logic.py uses relative path for DB: Path(__file__)....
        # So it should be fine if imported correctly.
        
        result = parse_business_data_preview(filename, period="2023-01")
        logic_time = time.time() - start
        print(f"Full logic parsing took {logic_time:.2f} seconds")
    except Exception as e:
        print(f"Full logic test failed: {e}")

if __name__ == "__main__":
    filename = "test/large_test.xlsx"
    # 500,000 rows to approximate 50MB+?
    # 100k rows * 20 cols * 8 bytes (int64) ~= 16MB raw data. 
    # Excel XML overhead is huge. 100k rows might be 5-10MB.
    # Let's try 300,000 rows.
    if not os.path.exists(filename):
        generate_large_excel(filename, rows=100000, cols=20)
    
    test_parsing(filename)
