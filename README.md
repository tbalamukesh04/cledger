# Cledger - WhatsApp Finance Application

## Architecture Overview
This application is designed to record financial transactions for businesses via WhatsApp.

* **Backend Framework:** Python (Uvicorn / ASGI)
* **Primary Database:** PostgreSQL 16 (Restricted local binding, SCRAM-SHA-256)
* **Message Broker/Cache:** Redis (Password protected)
* **Web Server / Reverse Proxy:** Nginx (HTTPS enforced, TLS enabled)
* **Host OS:** Ubuntu 24.04 LTS

## Branching Strategy
* `main` - Production-ready, stable code.
* `develop` - Active integration branch for next release.
* `feature/*` - Ephemeral branches for new features or fixes.