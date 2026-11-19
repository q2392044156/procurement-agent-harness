# 沙箱运行时镜像：Python 3.11 + 图表/数据分析依赖 + 中文字体
#
# 为什么需要预装：
# - 沙箱根文件系统是只读的，运行时 pip install 只能落到 tmpfs（/workspace 256m），
#   matplotlib + numpy + pandas 解包会超出配额（Errno 28 No space left on device）。
# - python:3.11-slim 只有 DejaVu 字体，中文标签会渲染成方框，因此补装 Noto CJK。
#
# 构建：docker build -t procuremind-sandbox:latest docker/sandbox
FROM python:3.11-slim

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    MPLBACKEND=Agg

RUN apt-get update \
    && apt-get install -y --no-install-recommends fonts-noto-cjk \
    && rm -rf /var/lib/apt/lists/*

RUN pip install --no-cache-dir matplotlib numpy pandas

# 预编译字体缓存，首张图表不必再扫描全部字体
RUN python -c "import matplotlib.font_manager as fm; fm._load_fontmanager(try_read_cache=False)"

WORKDIR /workspace
