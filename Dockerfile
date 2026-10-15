# Single-container image for cloud hosting (Render, Koyeb, Fly…): FastAPI on 127.0.0.1:8000 (internal)
# + Next.js on $PORT (public). The browser only talks to Next; /api/* is proxied to FastAPI (same origin).

# ---- frontend build ----
FROM node:22-slim AS web
WORKDIR /web
COPY frontend/package*.json ./
RUN npm ci
COPY frontend/ ./
ENV NEXT_PUBLIC_API_URL=""
RUN npm run build && npm prune --omit=dev

# ---- runtime ----
FROM python:3.11-slim
COPY --from=web /usr/local/bin/node /usr/local/bin/node
WORKDIR /app
COPY backend/requirements.txt backend/requirements.txt
RUN pip install --no-cache-dir -r backend/requirements.txt "psycopg[binary]>=3.1"
COPY backend/ backend/
COPY --from=web /web /app/frontend
COPY start.sh ./
RUN chmod +x start.sh && mkdir -p backend/data
ENV PORT=10000 PYTHONUNBUFFERED=1
EXPOSE 10000
CMD ["./start.sh"]
