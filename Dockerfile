FROM python:3.12-slim

WORKDIR /app
ENV PYTHONUNBUFFERED=1 \
    PYTHONPATH=/app \
    PIP_INDEX_URL=https://pypi.tuna.tsinghua.edu.cn/simple \
    PIP_DEFAULT_TIMEOUT=120

COPY requirements.txt .
# 先装 CPU 版 torch，避免 sentence-transformers 拉取 CUDA 依赖（体积差 10 倍）
RUN pip install --no-cache-dir \
    --find-links https://mirrors.aliyun.com/pytorch-wheels/cpu/ \
    --index-url https://pypi.tuna.tsinghua.edu.cn/simple torch
RUN pip install --no-cache-dir -r requirements.txt

COPY src src
EXPOSE 8000
CMD ["python", "-m", "src.api_view.web_main"]
