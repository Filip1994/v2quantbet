FROM python:3.11-slim

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1

WORKDIR /app
COPY pyproject.toml ./
COPY src ./src
COPY migrations ./migrations
COPY ops_query.py ./ops_query.py
RUN pip install --no-cache-dir .

RUN useradd --create-home --uid 10001 quantbet
USER quantbet

CMD ["python", "ops_query.py"]
