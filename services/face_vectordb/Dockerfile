FROM python:3.11-slim
WORKDIR /app
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt
COPY app.py .
ENV FACE_VDB_DATA=/data
ENV FACE_VDB_API_KEY=dev-face-vdb-key
ENV FACE_VDB_SEED_DEMO=1
VOLUME ["/data"]
EXPOSE 8100
CMD ["uvicorn", "app:app", "--host", "0.0.0.0", "--port", "8100"]
