FROM node:20-bookworm-slim AS frontend
WORKDIR /src
COPY frontend/package.json frontend/yarn.lock ./
RUN corepack enable && corepack prepare yarn@1.22.22 --activate \
    && yarn install --frozen-lockfile
COPY frontend/ ./
ENV REACT_APP_BACKEND_URL=
ENV DISABLE_ESLINT_PLUGIN=true
ENV GENERATE_SOURCEMAP=false
ENV CI=false
RUN yarn build \
    && ! grep -R "undefined/api" build/static/js

FROM python:3.11-slim-bookworm
RUN apt-get update && apt-get install -y --no-install-recommends \
        build-essential \
        ca-certificates \
        curl \
        nginx \
        tzdata

WORKDIR /app
COPY backend/requirements.txt /tmp/requirements.txt
# The portal does not import emergentintegrations or litellm, and those two pins
# conflict with each other during resolution.
RUN grep -v -E '^(emergentintegrations==|litellm )' /tmp/requirements.txt > /tmp/requirements.docker.txt \
    && pip install --no-cache-dir -r /tmp/requirements.docker.txt \
    && apt-get purge -y build-essential \
    && apt-get autoremove -y \
    && rm -rf /var/lib/apt/lists/* /root/.cache

COPY backend/ /app/backend/
COPY --from=frontend /src/build /usr/share/nginx/html
COPY docker/nginx.conf /etc/nginx/conf.d/default.conf
RUN rm -f /etc/nginx/sites-enabled/default \
    && mkdir -p /app/local_storage

COPY docker/entrypoint.sh /entrypoint.sh
RUN chmod +x /entrypoint.sh

ENV APP_TIMEZONE=Asia/Kolkata \
    STORAGE_MODE=local \
    LOCAL_STORAGE_DIR=/app/local_storage \
    COOKIE_SECURE=false

EXPOSE 80
CMD ["/entrypoint.sh"]
