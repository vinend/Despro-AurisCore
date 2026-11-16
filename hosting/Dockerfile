FROM node:24-bookworm-slim AS web-build
WORKDIR /build/WebApp
ENV NEXT_TELEMETRY_DISABLED=1
COPY WebApp/package.json WebApp/package-lock.json ./
RUN npm ci
COPY WebApp/src ./src
COPY WebApp/public ./public
COPY WebApp/next.config.ts WebApp/tsconfig.json WebApp/postcss.config.mjs ./
RUN npm run build && npm run typecheck

FROM python:3.13-slim-bookworm AS web
COPY --from=web-build /usr/local/bin/node /usr/local/bin/node
RUN apt-get update && apt-get install -y --no-install-recommends libsndfile1 libgomp1 \
    && rm -rf /var/lib/apt/lists/*
COPY hosting/requirements.txt /tmp/requirements.txt
RUN pip install --no-cache-dir -r /tmp/requirements.txt
RUN useradd --uid 10001 --create-home appuser
WORKDIR /app/WebApp
COPY --from=web-build /build/WebApp/.next/standalone ./
COPY --from=web-build /build/WebApp/.next/static ./.next/static
COPY --from=web-build /build/WebApp/public ./public
COPY AI-Pipeline/src /app/AI-Pipeline/src
COPY AI-Pipeline/scripts/analyze_recording.py AI-Pipeline/scripts/_bootstrap.py /app/AI-Pipeline/scripts/
COPY hosting/verify_models.py /app/hosting/verify_models.py
ENV NODE_ENV=production NEXT_TELEMETRY_DISABLED=1 HOSTNAME=0.0.0.0 PORT=3000 \
    AURISCORE_PIPELINE_DIR=/app/AI-Pipeline AURISCORE_PYTHON=/usr/local/bin/python \
    AURISCORE_ENGINEERING_MODELS=/models/manifest.json CUDA_VISIBLE_DEVICES=-1 \
    PYTHONDONTWRITEBYTECODE=1 NUMBA_CACHE_DIR=/tmp/numba MPLCONFIGDIR=/tmp/matplotlib
USER 10001:10001
EXPOSE 3000
CMD ["sh", "-c", "python /app/hosting/verify_models.py && exec node server.js"]

FROM node:24-bookworm-slim AS gateway
WORKDIR /app/WebApp/mini-services/device-gateway
COPY WebApp/mini-services/device-gateway/package.json WebApp/mini-services/device-gateway/package-lock.json ./
RUN npm ci
COPY WebApp/mini-services/device-gateway/index.ts WebApp/mini-services/device-gateway/gateway.ts ./
# gateway.ts retains its existing relative codec import.
COPY WebApp/src/lib/auriscore/device-protocol.ts /app/WebApp/src/lib/auriscore/device-protocol.ts
USER node
ENV AURISCORE_GATEWAY_HOST=0.0.0.0 AURISCORE_GATEWAY_PORT=8082
EXPOSE 8082
CMD ["node", "node_modules/tsx/dist/cli.mjs", "index.ts"]
