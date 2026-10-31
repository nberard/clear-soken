# --- 1. Build de la PWA ---
FROM node:22-bookworm-slim AS web
WORKDIR /web
COPY frontend/package.json frontend/package-lock.json ./
RUN npm ci
COPY frontend/ ./
RUN npm run build

# --- 2. Build de l'API Rust ---
FROM rust:1-slim-bookworm AS api
WORKDIR /api
COPY backend/Cargo.toml backend/Cargo.lock ./
# Pré-compile les dépendances (cache Docker) avant de copier le code
RUN mkdir src && echo 'fn main() {}' > src/main.rs && cargo build --release && rm -rf src
COPY backend/src ./src
RUN touch src/main.rs && cargo build --release

# --- 3. Image finale ---
FROM debian:bookworm-slim
RUN useradd --system --uid 10001 app
WORKDIR /app
# Comptes des potes (volume Docker « comptes », voir make compte) : le volume prend ce propriétaire
RUN mkdir /app/comptes && chown app /app/comptes
COPY --from=api /api/target/release/clear-soken-api /app/clear-soken-api
COPY --from=web /web/build /app/static
COPY backend/data /app/data
ENV BIND=0.0.0.0:8080 STATIC_DIR=/app/static RESOURCES_FILE=/app/data/resources.json COMPTES_FILE=/app/comptes/comptes.json
USER app
EXPOSE 8080
HEALTHCHECK --interval=30s --timeout=3s CMD ["/app/clear-soken-api", "--healthcheck"]
CMD ["/app/clear-soken-api"]
