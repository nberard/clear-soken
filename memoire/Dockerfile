FROM python:3.12-slim
WORKDIR /app
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt
COPY casquettes.toml .
COPY memoire ./memoire
RUN useradd -u 1000 -m app && mkdir -p /data && chown -R app /data
USER app
ENV MEMOIRE_DB=/data/memoire.db
EXPOSE 8770
CMD ["uvicorn", "memoire.web:app", "--host", "0.0.0.0", "--port", "8770"]
