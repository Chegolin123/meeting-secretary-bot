FROM python:3.12-slim

WORKDIR /app

COPY pyproject.toml ./
COPY src ./src

RUN pip install --no-cache-dir .

COPY web ./web

ENV PYTHONUNBUFFERED=1
EXPOSE 8000

CMD ["python", "-m", "secretary.bot"]