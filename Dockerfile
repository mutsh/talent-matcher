FROM python:3.12-slim

ENV PYTHONDONTWRITEBYTECODE=1 PYTHONUNBUFFERED=1 PIP_NO_CACHE_DIR=1 PORT=8080
WORKDIR /app

COPY requirements.txt .
RUN pip install -r requirements.txt

COPY . .

# Run as an unprivileged user, never root
RUN useradd --create-home --uid 10001 appuser && chown -R appuser /app
USER appuser

EXPOSE 8080
HEALTHCHECK --interval=30s --timeout=5s --start-period=20s \
  CMD python -c "import urllib.request,os; urllib.request.urlopen(f'http://localhost:{os.environ[\"PORT\"]}/_stcore/health')"

# Hosts such as Render inject PORT; default 8080
CMD streamlit run app.py --server.port=${PORT} --server.address=0.0.0.0
