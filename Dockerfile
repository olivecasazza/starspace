FROM python:3.12-slim

WORKDIR /app

COPY backend/requirements.txt ./
RUN pip install --no-cache-dir -r requirements.txt

COPY . .

# Initialize state file
RUN cp state.sample.json state.json

ENV STAR_BACKEND_PORT=19000
ENV STAR_OFFICE_ENV=production
EXPOSE 19000

HEALTHCHECK --interval=30s --timeout=5s --start-period=10s \
    CMD python -c "import urllib.request; urllib.request.urlopen('http://localhost:19000/health')" || exit 1

WORKDIR /app/backend
CMD ["python3", "app.py"]
