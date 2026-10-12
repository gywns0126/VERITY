FROM python:3.11-slim

WORKDIR /app

COPY server/requirements.txt ./server/requirements.txt
RUN pip install --no-cache-dir -r server/requirements.txt

COPY server/ ./server/

# Public discovery dependency closure only; no operator package initializers,
# local data, credentials, AI worker, or member storage enters this image.
COPY scripts/member-map/run-live-refresh.py ./scripts/member-map/run-live-refresh.py
COPY api/collectors/member_map_listing_delta.py api/collectors/member_map_live_refresh.py api/collectors/member_map_refresh_store.py ./api/collectors/
COPY api/observability/member_map_freshness.py ./api/observability/member_map_freshness.py
COPY api/intelligence/portfolio_public_sources.py ./api/intelligence/portfolio_public_sources.py

EXPOSE 8000

CMD ["uvicorn", "server.main:app", "--host", "0.0.0.0", "--port", "8000"]
