# 2D/3D 混合标注答疑助手 (Annotation Q&A Assistant)

面向自动驾驶 **2D 图像 + 3D 点云联合标注**工作的多模态问答助手。它把
《联合标注规则 V2.5》(PDF) 与历史答疑表格 (XLSX) 解析成带图片的知识库，
基于**多模态 RAG**：检索相关规则/答疑片段及示例图片，交给 **Qwen-VL** 视觉模型
理解后作答。

你可以**带图提问**——上传正在标注的截图，模型会结合你的图片 + 答疑库里的示例图片，
像真人助手一样告诉你「标 / 不标 / 怎么标 / 归哪个类别」并给出规则依据。

## 功能
- PDF 规则文档解析：按页/章节切块，渲染整页图 + 抽取内嵌示例图。
- XLSX 答疑表解析：从 OPC 容器中按单元格抽取内嵌图片并关联到对应问答行。
- 本地向量检索：`BAAI/bge-small-zh-v1.5`（中文优化，CPU 可跑，无需联网鉴权）。
- 多模态作答：Qwen-VL (DashScope)，后端可切换（改 `config.py` 即可换 GPT-4o/Claude）。
- Web 界面 (Gradio)：文字提问 + 多图上传，展示回答、引用来源、检索到的示例图。

## 目录结构
```
src/
  config.py        # 路径、模型名、API key 等配置（读环境变量）
  ingest_pdf.py    # 解析 PDF → data/kb/pdf_records.jsonl + 图片
  ingest_xlsx.py   # 解析 XLSX → data/kb/xlsx_records.jsonl + 图片
  kb.py            # 构建向量索引 + 检索 (Retriever)
  llm.py           # Qwen-VL 多模态后端
  server.py        # FastAPI 后端 + 提供前端
web/
  index.html       # xAI 风格深色前端
  style.css
  app.js
scripts/
  ingest_all.sh    # 一键解析两份文档并建索引
data/
  kb/              # 解析产物（jsonl 记录 + images/ + pdf_pages/，图片已 gitignore）
  index/           # 向量索引（embeddings.npy + docs.pkl，已 gitignore）
```

## 快速开始
```bash
pip install -r requirements.txt

# 1) 指向你的源文档并构建知识库 + 索引
export PDF_PATH=/path/to/联合标注规则V2.5.pdf
export XLSX_PATH=/path/to/答疑文档.xlsx
bash scripts/ingest_all.sh

# 2) 设置 Qwen-VL 的 API key（阿里云百炼 https://bailian.console.aliyun.com/）
export DASHSCOPE_API_KEY=sk-xxxx

# 3) 启动 Web 界面
python3 src/server.py     # 打开 http://localhost:7860
```

## 配置（环境变量，见 `src/config.py`）
| 变量 | 默认值 | 说明 |
|------|--------|------|
| `PDF_PATH` / `XLSX_PATH` | — | 源文档路径 |
| `DASHSCOPE_API_KEY` | — | Qwen-VL API key（必填，作答用） |
| `VL_MODEL` | `qwen-vl-max` | 视觉模型，可改 `qwen-vl-plus` 省钱 |
| `EMBED_MODEL` | `BAAI/bge-small-zh-v1.5` | 本地检索嵌入模型 |
| `TOP_K` | `6` | 检索条数 |
| `MAX_CONTEXT_IMAGES` | `6` | 单次最多送入模型的示例图数 |

## 切换模型后端
`llm.py` 走 OpenAI 兼容协议。把 `DASHSCOPE_BASE_URL` 与 `VL_MODEL` 改成
OpenAI / 任意兼容服务（如 GPT-4o）即可，无需改其他代码。

## 说明
- 知识库图片体积较大（约 260MB），已 `.gitignore`；克隆后请用源文档自行 `ingest_all.sh` 重建。
- 检索为本地免费模型，只有最终作答调用 Qwen-VL（按量计费，qwen-vl 很便宜）。
