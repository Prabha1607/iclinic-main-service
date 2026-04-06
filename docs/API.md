# Main Service API Reference

## Base URL
Starting URL for all endpoints is `/api/v1`.

## Authentication Method
Requests require `Authorization: Bearer <token>` relying on JWTs minted by the `auth-service`. The internal authorization middleware validates token scope prior to routing.

---

## Appointments Endpoints

### GET `/appointments`
**Description**: Fetch all scheduled records tied to the authenticated caller.

**Response** (200 OK):
```json
[
  {
    "id": 105,
    "user_id": 1,
    "slot_id": 20,
    "status": "confirmed",
    "appointment_type_id": 3
  }
]
```

### POST `/appointments`
**Description**: Books a new appointment slot for a patient.

**Request**:
```json
{
  "slot_id": 20,
  "appointment_type_id": 3,
  "notes": "First time visit"
}
```

**Response** (200 OK):
```json
{
  "id": 106,
  "status": "confirmed",
  "message": "Appointment created"
}
```

---

## Twilio Verification Endpoints

### POST `/twilio_verify/send-otp`
**Description**: Triggers an SMS verification code to the registered user number.

**Response** (200 OK):
```json
{
  "status": "pending",
  "message": "OTP sent out successfully"
}
```

---

## Voice Assistance Endpoints

### POST `/voice/make-call`
**Description**: Initiates an outbound AI-driven phone call to schedule or assist a user.

**Request Query Params**:
- `to_number` (string) - E.164 formatted target phone number.

**Response** (200 OK):
```json
{
  "status": "call_placed",
  "call_sid": "CA1234567890abcdef"
}
```

### POST `/voice/voice-response`
**Description**: Twilio Webhook receiving live transcription and returning TwiML instructions indicating how the AI should reply.

**Request**: standard Twilio `<Gather>` webhook URL encoded form.

**Response** (200 OK):
`application/xml` TwiML document.
