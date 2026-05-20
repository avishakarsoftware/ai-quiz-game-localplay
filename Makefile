.PHONY: dev dev-backend dev-frontend install test test-e2e test-frontend-e2e test-remote-prod test-remote-gamma build lint clean

# Hot-reload development
dev:
	@echo "Starting backend + frontend in parallel..."
	$(MAKE) dev-backend & $(MAKE) dev-frontend & wait

dev-backend:
	cd backend && ../backend/venv/bin/python3 -m uvicorn main:app --reload --host 0.0.0.0 --port 9100

dev-frontend:
	cd frontend && npm run dev -- --host 0.0.0.0 --port 9200

# Install dependencies
install:
	cd backend && python3 -m venv venv && venv/bin/pip install -r requirements.txt
	cd frontend && npm install

# Testing
test:
	cd backend && venv/bin/python3 -m pytest tests/ -v --ignore=tests/test_e2e.py --ignore=tests/test_websocket_integration.py

test-e2e:
	cd backend && venv/bin/python3 -m pytest tests/test_e2e.py -v -s

test-frontend-e2e:
	cd frontend && npm run test:e2e

test-all:
	cd backend && venv/bin/python3 -m pytest tests/ -v
	cd frontend && npm test -- --run
	cd frontend && npm run test:e2e

test-remote-prod:
	.venv/bin/python scripts/smoke-remote.py --base-url https://gamesapi.revelryapp.me

test-remote-gamma:
	.venv/bin/python scripts/smoke-remote.py --base-url https://gamesapi-gamma.revelryapp.me

# Build
build:
	cd frontend && npm run build

# Lint (if configured)
lint:
	cd frontend && npx tsc --noEmit

# Clean
clean:
	rm -rf frontend/dist
	find backend -type d -name __pycache__ -exec rm -rf {} + 2>/dev/null || true
