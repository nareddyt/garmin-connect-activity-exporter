FROM python:3.13-slim

WORKDIR /app

ENV TZ=Etc/UTC

RUN apt-get update && \
    apt-get install -y curl && \
    ln -snf /usr/share/zoneinfo/$TZ /etc/localtime && echo $TZ > /etc/timezone && \
    rm -rf /var/lib/apt/lists/*

COPY ../requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY source/ /app/source/
COPY main.py /app/main.py

RUN mkdir -p /app/garmin_downloads && \
    mkdir -p /app/garmin_session

ENV PYTHONUNBUFFERED=1

VOLUME ["/app/garmin_downloads", "/app/garmin_session"]

CMD ["python", "main.py"]
