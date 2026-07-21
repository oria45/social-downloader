FROM python:3.12-slim

RUN apt-get update \
    && apt-get install -y --no-install-recommends ffmpeg git nodejs npm \
    && rm -rf /var/lib/apt/lists/*

# PO token provider for yt-dlp (script mode): lets YouTube requests pass
# Render's bot-check instead of hitting "Sign in to confirm you're not a bot".
RUN git clone --single-branch --branch 1.3.1 --depth 1 \
    https://github.com/Brainicism/bgutil-ytdlp-pot-provider.git /opt/bgutil-ytdlp-pot-provider \
    && cd /opt/bgutil-ytdlp-pot-provider/server \
    && npm ci \
    && npx tsc

WORKDIR /app

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY . .

CMD uvicorn app.main:app --app-dir /app --host 0.0.0.0 --port $PORT
