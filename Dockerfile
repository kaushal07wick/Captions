FROM python:3.10-slim

# Install ffmpeg + deps
RUN apt-get update && apt-get install -y ffmpeg && rm -rf /var/lib/apt/lists/*

WORKDIR /app
COPY . .

RUN pip install --no-cache-dir -r api/requirements.txt

ENV PORT=8000
EXPOSE 8000

CMD ["python", "api/main.py"]
