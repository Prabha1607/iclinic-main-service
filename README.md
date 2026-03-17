# Main Service

Handles appointments, available slots, appointment types, Twilio voice assistant, and all non-auth business logic.

## Port: 8000

## Responsibilities
- Appointment booking, updating, cancelling, listing
- Available slot management
- Appointment type management
- Twilio voice assistant (LangGraph AI call flow)
- Twilio phone verification (OTP, lookup, caller-id)
- Proxies user/provider requests to auth-service

## Depends On
- **auth-service** running at `AUTH_SERVICE_URL` (default: http://localhost:8001)
  - Token validation uses the shared JWT secret directly (no HTTP call needed)
  - User lookups (for voice flow) call `GET /api/v1/internal/users/by-identifier`

## Routes
| Method | Path | Auth Required |
|--------|------|---------------|
| POST | /api/v1/booking/create | Bearer |
| PUT  | /api/v1/booking/update/{id} | Bearer |
| PATCH| /api/v1/booking/cancel/{id} | Bearer |
| GET  | /api/v1/booking/list | Bearer |
| GET  | /api/v1/appointment-types | Bearer |
| GET  | /api/v1/users/providers/{id}/slots | Bearer |
| POST | /api/v1/voice/make-call | Bearer |
| POST | /api/v1/voice/voice-response | No (Twilio webhook) |
| POST | /api/v1/verify/lookup | No |
| POST | /api/v1/verify/send-otp | No |
| POST | /api/v1/verify/check-otp | No |
| POST | /api/v1/verify/caller-id | No |
| GET  | /api/v1/health | No |

## Setup
```bash
cp .env.example .env
# fill in your values including AUTH_SERVICE_URL
uvicorn src.api.rest.app:app --host 0.0.0.0 --port 8000 --reload
```

## Docker
```bash
docker-compose up --build
```
