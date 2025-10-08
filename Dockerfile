FROM python:3.11-slim

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1

WORKDIR /app

# Install uv (fast dependency manager) and use lockfile for reproducible installs
RUN pip install --no-cache-dir uv

COPY pyproject.toml uv.lock /app/
RUN uv pip install --system --frozen

COPY . /app

EXPOSE 8080

CMD ["python", "local_server.py"]
