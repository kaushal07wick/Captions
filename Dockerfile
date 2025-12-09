# ---- Base image ----
FROM python:3.10-slim

# ---- System deps ----
RUN apt-get update && apt-get install -y --no-install-recommends ffmpeg && rm -rf /var/lib/apt/lists/*

# ---- Working dir ----
WORKDIR /app

# ---- Install dependencies ----
COPY api/requirements.txt ./requirements.txt
RUN pip install --no-cache-dir -r requirements.txt

# ---- Copy project ----
COPY . .

# ---- Environment ----
ENV PORT=8000
ENV PYTHONUNBUFFERED=1

# ---- Expose port ----
EXPOSE 8000

# ---- Start command ----
CMD ["./start.sh"]
