# --- 1. Build de la PWA ---
FROM node:22-alpine AS web
WORKDIR /web
COPY frontend/package.json frontend/package-lock.json ./
RUN npm ci
COPY frontend/ ./
RUN npm run build

# --- 2. Build de l'API Rust ---
FROM rust:1-slim AS api
WORKDIR /api
COPY backend/ ./
RUN cargo build --release

# --- 3. Image finale ---
FROM debian:bookworm-slim
RUN useradd --system --uid 10001 app
WORKDIR /app
COPY --from=api /api/target/release/clear-soken-api /app/clear-soken-api
COPY --from=web /web/build /app/static
COPY backend/data /app/data
ENV BIND=0.0.0.0:8080 STATIC_DIR=/app/static RESOURCES_FILE=/app/data/resources.json
USER app
EXPOSE 8080
CMD ["/app/clear-soken-api"]
