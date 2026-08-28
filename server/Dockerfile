FROM python:3.12-slim

WORKDIR /app

# System deps for tree-sitter compiled grammars.
# `apt-get upgrade` pulls in Debian security patches (e.g. openssl/libssl) that
# have shipped since the base image was last built, so Trivy's OS-package scan
# doesn't flag CVEs the base image is simply stale on.
RUN apt-get update && apt-get upgrade -y && apt-get install -y --no-install-recommends \
    curl \
    && rm -rf /var/lib/apt/lists/*

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY . .

EXPOSE 8000

CMD ["uvicorn", "main:app", "--host", "0.0.0.0", "--port", "8000"]
