# WodApp API Documentation

Reverse-engineered API documentation for `ws.paynplan.nl` backend used by `app.wodapp.nl`.

## Base Configuration

- **Base URL**: `https://ws.paynplan.nl/`
- **Method**: All requests are `POST`
- **Content-Type**: `application/x-www-form-urlencoded`
- **Response Format**: JSON

## Common Parameters

All authenticated requests require these parameters:

| Parameter | Description |
|-----------|-------------|
| `data[app]` | Always `wodapp` |
| `data[language]` | Language code, e.g., `nl_NL` |
| `data[version]` | API version, e.g., `14.0` |
| `data[clientUserAgent]` | Client type, e.g., `browser` |
| `data[token]` | Auth token (from login response) |
| `data[id_appuser_li]` | User ID (from login response) |
| `data[id_gym]` | Gym ID |
| `data[idc]` | Company ID (same as gym ID) |

---

## Authentication

### Login

Authenticate a user and retrieve access token.

**Service**: `user`
**Method**: `login`

**Request Parameters**:
```
data[service]=user
data[method]=login
data[username]=<email>
data[pass]=<password>
data[gcl]=1
data[app]=wodapp
data[language]=nl_NL
data[version]=14.0
data[clientUserAgent]=browser
data[id_appuser_li]=
```

**Response**:
```json
{
  "status": "OK",
  "id_user": 388211,
  "username": "user@example.com",
  "firstname": "Sebastiaan",
  "token": "40fff8ae77408d6f9aed4e72a60a354c",
  "gyms": [
    {
      "id_gym": 2495,
      "idc": 2495,
      "name": "CrossFit Purmerend",
      "city": "Purmerend"
    }
  ]
}
```

**Key Response Fields**:
- `token` - Use this for all subsequent authenticated requests
- `id_user` - Your user ID (use as `id_appuser_li`)
- `gyms[].id_gym` - Gym ID for gym-specific requests

---

## Calendar / Schedule

### Get Day Schedule

Fetch all appointments for a specific date.

**Service**: `agenda`
**Method**: `day`

**Request Parameters**:
```
data[service]=agenda
data[method]=day
data[idc]=2495
data[type]=gym
data[id_agenda]=19488
data[dateInfo][date]=2026-04-15
data[token]=<token>
data[id_gym]=2495
data[id_appuser_li]=388211
```

**Response** (simplified):
```json
{
  "status": "OK",
  "resultset": [
    {
      "id_appointment": 5039978,
      "id_appointment_type": 574,
      "name": "CrossFit",
      "date_start": "2026-04-15 07:00:00",
      "date_end": "2026-04-15 08:00:00",
      "max_subscriptions": 17,
      "total_subscriptions": 11,
      "status": "open"
    }
  ]
}
```

**Appointment Status Values**:
- `open` - Spots available
- `closed` - Class is full
- `subscribed` - You are subscribed to this class

---

## Appointment Details

### Get Appointment Info

Get detailed info about an appointment **including participant list**.

**Service**: `agenda`
**Method**: `appointment`

**Request Parameters**:
```
data[service]=agenda
data[method]=appointment
data[idc]=2495
data[id_agenda]=19488
data[id]=5046413
data[date_start]=2026-04-19 11:00
data[date_end]=2026-04-19 12:00
data[token]=<token>
data[id_gym]=2495
data[id_appuser_li]=388211
```

**Response** (simplified):
```json
{
  "status": "OK",
  "resultset": {
    "id_appointment": 5046413,
    "name": "Olympic Lifting",
    "max_subscriptions": 17,
    "waiting_list": 1,
    "number_hours_before_subscription_opens": 168,
    "subscription_open_date": "12-04-2026 11:00",
    "subscribe_not_opened_yet": 0,
    "subscribe_closed": 0,
    "subscriptions": {
      "subscribed": 0,
      "total": 5,
      "full": 0,
      "members": [
        {
          "name": "Annika",
          "id_appuser": 353394,
          "imageURL": ""
        },
        {
          "name": "Jasper",
          "id_appuser": 364508,
          "imageURL": ""
        }
      ]
    },
    "waitinglist": {
      "total": 0,
      "members": []
    }
  }
}
```

**Key Fields for Your Features**:
- `subscriptions.members[]` - **List of people signed up** (for friends feature)
- `subscription_open_date` - Exact datetime when signup opens (shown in calendar)
- `subscribe_not_opened_yet` - `1` if signup hasn't opened yet
- `waiting_list` - `1` if waiting list is enabled

---

## Sign Up / Subscribe

### Subscribe to Appointment

Sign up for a class.

**Service**: `agenda`
**Method**: `subscribeAppointment`

**Request Parameters**:
```
data[service]=agenda
data[method]=subscribeAppointment
data[idc]=2495
data[id_agenda]=19488
data[id]=5046413
data[date_start_org]=2026-04-19 11:00
data[date_end_org]=2026-04-19 12:00
data[action]=subscribe
data[token]=<token>
data[id_gym]=2495
data[id_appuser_li]=388211
```

**Response**:
```json
{
  "status": "OK",
  "notice": "De inschrijving is succesvol\nEr is ingeschreven met abonnement",
  "subscribedWithSuccess": 1,
  "resultset": {
    "id_appointment": "5046413"
  }
}
```

### Subscribe to Waiting List

Join the waiting list when class is full.

**Service**: `agenda`
**Method**: `subscribeWaitingList`

**Request Parameters**:
```
data[service]=agenda
data[method]=subscribeWaitingList
data[idc]=2495
data[id_agenda]=19488
data[id]=5036777
data[date_start_org]=2026-04-19 10:00
data[date_end_org]=2026-04-19 11:00
data[action]=subscribe
data[token]=<token>
data[id_gym]=2495
data[id_appuser_li]=388211
```

**Response**:
```json
{
  "status": "OK",
  "notice": "Je bent ingeschreven voor de wachtlijst en wordt automatisch ingeschreven indien je aan de beurt komt",
  "resultset": {
    "id_appointment": "5036777"
  }
}
```

---

## Get Enabled Modules + Upcoming Reservations

Fetches gym modules and user widgets including upcoming reservations.

**Service**: `gym`
**Method**: `getModulesEnabledGym`

**Request Parameters**:
```
data[service]=gym
data[method]=getModulesEnabledGym
data[idc]=2495
data[id_gym]=2495
data[id_gym_group]=2495
data[gyms][0]=2495
data[companyImages]=0
data[numberOutstandingInvoices]=0
data[token]=<token>
data[id_appuser_li]=388211
```

**Response** (simplified):
```json
{
  "status": "OK",
  "widgets": {
    "reservations": {
      "enabled": 1,
      "data": [
        {
          "id_appointment": 5048373,
          "id_agenda": 19488,
          "name": "CrossFit",
          "date_start": "21-04-2026 16:30"
        },
        {
          "id_appointment": 5049539,
          "id_agenda": 19488,
          "name": "Strength Class",
          "date_start": "22-04-2026 18:30"
        }
      ]
    }
  }
}
```

**Key Fields**:
- `widgets.reservations.data[]` — upcoming classes the user is signed up for
- `date_start` — format `DD-MM-YYYY HH:MM` (note: day-first, unlike the `agenda.day` endpoint)
- `id_appointment` — same appointment ID used by other endpoints

---

## Other Endpoints

### Load Profile Image
- **Service**: `user`
- **Method**: `loadProfileImage`

### Get Agendas
- **Service**: `agenda`
- **Method**: `getAgendas`

### Initialize Settings
- **Service**: `agenda`
- **Method**: `initSettings`

---

## Implementation Notes

### Friends Feature

The `appointment` endpoint returns `subscriptions.members[]` with:
- `name` - First name of participant
- `id_appuser` - Unique user ID

**Strategy**:
1. Store a list of friend `id_appuser` values
2. For each day, fetch appointments using `day` method
3. For each appointment, fetch details using `appointment` method
4. Check if any friend's `id_appuser` is in `subscriptions.members[]`

---

## Your Account Info (from HAR)

- **User ID**: 388211
- **Gym ID**: 2495
- **Gym Name**: CrossFit Purmerend
- **Agenda ID**: 19488
