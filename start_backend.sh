#!/bin/bash
cd /Users/lee/Documents/beiyi/duizhangdanxitong
python3 -c "
import sys
sys.path.insert(0, 'backend')
from main import app
import uvicorn
print('启动服务器...')
uvicorn.run(app, host='0.0.0.0', port=8000, log_level='info')
"