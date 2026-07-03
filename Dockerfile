FROM python:3.12-slim

WORKDIR /app

# System dependencies
RUN apt-get update && apt-get install -y \
    ffmpeg \
    nodejs \
    npm \
    && rm -rf /var/lib/apt/lists/*

# Install latest yt-dlp directly from GitHub (not PyPI)
RUN pip install --upgrade pip
RUN pip install "https://github.com/yt-dlp/yt-dlp/archive/master.zip"

COPY requirements.txt .
RUN pip install -r requirements.txt

COPY . .

CMD ["python", "bot.py"]
