FROM python:3.12-slim

WORKDIR /workspace
COPY backend /workspace/backend

RUN pip install --no-cache-dir -e /workspace/backend

ENV PYTHONPATH=/workspace/backend
WORKDIR /workspace/backend
EXPOSE 8000
CMD ["python", "-m", "uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000"]
