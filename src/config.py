"""Central configuration. Override via environment variables."""
import os
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
KB_DIR = Path(os.environ.get("KB_DIR", ROOT / "data" / "kb"))
INDEX_DIR = Path(os.environ.get("INDEX_DIR", ROOT / "data" / "index"))

# Default source documents (can be overridden when running ingest)
PDF_PATH = os.environ.get(
    "PDF_PATH",
    "/home/ubuntu/attachments/0b086761-2407-4f07-a14a-94e4779ffa86/V2.5.pdf",
)
XLSX_PATH = os.environ.get("XLSX_PATH", "/home/ubuntu/答疑文档.xlsx")

# Embedding model (local, CPU, multilingual/Chinese). No API key needed.
EMBED_MODEL = os.environ.get("EMBED_MODEL", "BAAI/bge-small-zh-v1.5")

# LLM backend: Qwen-VL via DashScope OpenAI-compatible endpoint.
DASHSCOPE_API_KEY = os.environ.get("DASHSCOPE_API_KEY", "")
DASHSCOPE_BASE_URL = os.environ.get(
    "DASHSCOPE_BASE_URL", "https://dashscope.aliyuncs.com/compatible-mode/v1"
)
VL_MODEL = os.environ.get("VL_MODEL", "qwen-vl-max")

# Retrieval / generation knobs
TOP_K = int(os.environ.get("TOP_K", "6"))
MAX_CONTEXT_IMAGES = int(os.environ.get("MAX_CONTEXT_IMAGES", "6"))
# Below this best-match cosine score, treat retrieval as weak and tell the model
# to admit uncertainty instead of guessing.
MIN_RELEVANCE = float(os.environ.get("MIN_RELEVANCE", "0.45"))
