FROM python:3.11-slim

WORKDIR /app

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY mcp_server.py core.py ./

EXPOSE 8001

ENV PYTHONUNBUFFERED=1

CMD ["python", "mcp_server.py", "--transport", "http", "--port", "8001"]
