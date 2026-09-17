FROM python:3.11-slim

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1

WORKDIR /app
COPY pyproject.toml ./
COPY src ./src
COPY migrations ./migrations
RUN pip install --no-cache-dir .

RUN useradd --create-home --uid 10001 quantbet
USER quantbet

CMD ["python", "-m", "h2h.entrypoint"]
