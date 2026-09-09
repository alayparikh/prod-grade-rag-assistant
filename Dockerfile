FROM python:3.13-slim

# tesseract + poppler are only needed for scanned documents; they are
# installed unconditionally because deciding at image-build time whether
# this share has scans is not possible, and the layer is small next to the
# embedding model.
RUN apt-get update \
    && apt-get install -y --no-install-recommends tesseract-ocr poppler-utils \
    && apt-get clean \
    && find /var/lib/apt/lists -mindepth 1 -delete

WORKDIR /app

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Bake the embedding model into the image. Downloading it at container
# start makes every deploy depend on the Hugging Face hub being reachable
# from a machine that is otherwise only allowed to talk to the NAS and the
# Anthropic API.
ARG EMBEDDING_MODEL=sentence-transformers/all-MiniLM-L6-v2
ENV RAG_EMBEDDING_MODEL=${EMBEDDING_MODEL}
RUN python -c "from langchain_huggingface import HuggingFaceEmbeddings; \
    HuggingFaceEmbeddings(model_name='${EMBEDDING_MODEL}')"

COPY . .

# Runs as a non-root user: this process reads a share full of personal
# records and talks to the network, and it never needs to write outside
# its own volumes.
RUN useradd --create-home --uid 10001 rag \
    && mkdir -p /data /app/logs \
    && chown -R rag:rag /data /app/logs
USER rag

ENV RAG_PERSIST_PATH=/data/chroma_db \
    RAG_META_DB=/data/meta.sqlite \
    RAG_LOG_PATH=/data/logs/events.jsonl \
    RAG_DOCS_PATH=/mnt/nas

EXPOSE 8501
CMD ["python", "-m", "streamlit", "run", "app.py", \
     "--server.address=0.0.0.0", "--server.port=8501", "--server.headless=true"]
