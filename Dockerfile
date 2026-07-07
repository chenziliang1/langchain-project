# 使用 Python 3.10 作為基礎映像檔
FROM python:3.10-slim

# 設定工作目錄
WORKDIR /app

# 安裝系統依賴（若連接 MySQL 可能需要一些 C 函式庫）
RUN apt-get update && apt-get install -y default-libmysqlclient-dev build-essential && rm -rf /var/lib/apt/lists/*

# 複製依賴清單並安裝
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# 複製專案所有檔案
COPY . .

# 預設指令（保持容器運行或直接啟動 bash）
CMD ["bash"]