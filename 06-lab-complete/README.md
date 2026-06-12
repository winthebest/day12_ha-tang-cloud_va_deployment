# Lab 12 — Complete Production Agent

Kết hợp tất cả concepts Day 12: Docker, security, scaling, Redis stateless design.

## Cấu trúc

```
06-lab-complete/
├── app/
│   ├── main.py           # FastAPI entry point
│   ├── config.py         # 12-factor config
│   ├── auth.py           # API Key authentication
│   ├── rate_limiter.py   # Redis sliding window (10 req/min)
│   ├── cost_guard.py     # Monthly budget guard ($10/user)
│   └── redis_store.py    # Conversation history in Redis
├── utils/mock_llm.py
├── nginx/nginx.conf      # Load balancer
├── Dockerfile            # Multi-stage (~247 MB)
├── docker-compose.yml
├── railway.toml
├── render.yaml
└── check_production_ready.py
```

## Chạy local

```bash
cd 06-lab-complete
docker compose up -d --scale agent=3

# Health
curl http://localhost/health
curl http://localhost/ready

# Ask (API key trong docker-compose.yml)
curl -X POST http://localhost/ask \
  -H "X-API-Key: lab-secret-key-123" \
  -H "Content-Type: application/json" \
  -d '{"user_id":"student1","question":"What is deployment?"}'
```

## Kiểm tra production readiness

```bash
python check_production_ready.py
```

## Deploy cloud

Xem [DEPLOYMENT.md](../DEPLOYMENT.md) và `railway.toml` / `render.yaml`.
