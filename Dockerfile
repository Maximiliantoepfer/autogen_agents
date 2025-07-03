# Datei: Dockerfile
FROM python:3.12-slim

# Systemtools installieren
RUN apt update && apt install -y git curl build-essential

# Arbeitsverzeichnis setzen
WORKDIR /app
