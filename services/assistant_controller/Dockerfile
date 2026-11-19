FROM python:3.11-slim
WORKDIR /app
RUN apt-get update && apt-get install -y --no-install-recommends libgomp1 && rm -rf /var/lib/apt/lists/*
COPY requirements.txt pyproject.toml ./
COPY src ./src
COPY configs ./configs
COPY scenarios ./scenarios
COPY display ./display
COPY dmn ./dmn
COPY contracts ./contracts
RUN pip install --no-cache-dir -r requirements.txt && pip install --no-cache-dir -e .
ENV PYTHONPATH=/app/src
EXPOSE 8088
CMD ["python", "-m", "ac.main", "--config", "/app/configs/default.yaml", "--mqtt-optional"]
