FROM python:3.12-slim

WORKDIR /app

RUN apt-get update && apt-get install -y \
    ffmpeg nodejs npm curl \
    && apt-get clean \
    && rm -rf /var/lib/apt/lists/*

RUN pip install --upgrade pip
RUN pip install "https://github.com/yt-dlp/yt-dlp/archive/master.zip"

COPY requirements.txt .
RUN pip install -r requirements.txt

COPY . .

CMD ["python", "-u", "main.py"]
