# Deployable image (Hugging Face Spaces, Docker SDK). CPU-only torch keeps it small.
FROM python:3.12-slim

RUN useradd -m -u 1000 user
WORKDIR /home/user/app

RUN pip install --no-cache-dir torch==2.14.0 --index-url https://download.pytorch.org/whl/cpu
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY --chown=user . .
USER user
ENV HOME=/home/user PORT=7860
# Bake the sentence encoder into the image so cold starts don't download it.
RUN python -c "from sentence_transformers import SentenceTransformer as S; S('sentence-transformers/paraphrase-multilingual-MiniLM-L12-v2')" \
 && python -m dadi.seed

EXPOSE 7860
CMD ["sh", "-c", "uvicorn dadi.app:app --host 0.0.0.0 --port ${PORT}"]
