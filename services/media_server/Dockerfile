FROM python:3.11-slim
WORKDIR /app
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt
COPY app ./app
ENV MEDIA_ROOT=/data
ENV MEDIA_PUBLIC_BASE=http://103.249.117.203:9010
ENV MQTT_HOST=mqtt
ENV MQTT_PORT=1883
ENV MQTT_USERNAME=vision
ENV MEDIA_STATIONS=station-01
VOLUME ["/data"]
EXPOSE 9010
CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "9010"]
