#銀行規定的python image
# FROM registry.fedoraproject.org/f33/python3
FROM python:3.9.17-slim-bullseye

# 設定工作目錄
WORKDIR /app

# 複製 requirements.txt 並安裝 Python 依賴項
COPY ./requirements.txt ./

# 安裝 Python 套件
RUN pip3 install --no-cache-dir -r requirements.txt

# 複製應用程式程式碼
COPY . .

# 設定環境變量
ENV PYTHONUNBUFFERED True
ENV PORT 8080

# 運行 Gunicorn WSGI 服務器
CMD exec gunicorn --bind :$PORT --workers 1 --threads 8 --timeout 0 main:app
