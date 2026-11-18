FROM python:3.12-slim

WORKDIR /app
ENV PYTHONUNBUFFERED=1 \
    PYTHONPATH=/app \
    PIP_INDEX_URL=https://pypi.tuna.tsinghua.edu.cn/simple \
    PIP_DEFAULT_TIMEOUT=120

COPY requirements.txt .
# 直接用 CPU wheel，避免 PyTorch CPU index 的哈希校验/镜像同步问题
RUN pip install --no-cache-dir --no-deps \
    https://download.pytorch.org/whl/cpu/torch-2.7.1%2Bcpu-cp312-cp312-manylinux_2_28_x86_64.whl
RUN pip install --no-cache-dir \
    filelock typing-extensions sympy networkx jinja2 fsspec
RUN pip install --no-cache-dir -r requirements.txt

COPY src src
COPY skills skills
EXPOSE 8000
CMD ["python", "-m", "src.api_view.web_main"]
