# WodPlanner

Custom frontend API for WodApp (CrossFit Purmerend) with auto-signup and friends tracking.

## Features

- **Calendar API** - View class schedules
- **Auto-signup queue** - Automatically sign up for classes when registration opens
- **Friends tracking** - See which classes your friends are attending

## Setup

### Prerequisites

- Python 3.11+
- A WodApp account (app.wodapp.nl)

### Installation

```bash
# Clone and enter directory
cd wodplanner

# Create virtual environment
python -m venv .venv
source .venv/bin/activate

# Install dependencies
pip install -e .
```

### Configuration

Create a `.env` file in the project root:

```bash
WODAPP_USERNAME=your@email.com
WODAPP_PASSWORD=yourpassword
```

## Running the Server

```bash
# Activate virtual environment
source .venv/bin/activate

# Start the server
uvicorn wodplanner.app.main:app --reload

# Or specify host/port
uvicorn wodplanner.app.main:app --host 0.0.0.0 --port 8000
```

The app will be available at http://127.0.0.1:8000

## Web Interface

| Page | Description |
|------|-------------|
| `/` | Calendar - view daily schedule, sign up for classes |
| `/friends` | Manage friends list |
| `/queue` | View and manage auto-signup queue |

### API Documentation

For API access, visit:
- **Swagger UI**: http://127.0.0.1:8000/docs
- **ReDoc**: http://127.0.0.1:8000/redoc

## API Endpoints

### Authentication
| Endpoint | Description |
|----------|-------------|
| `GET /auth/me` | Get current user info |

### Calendar
| Endpoint | Description |
|----------|-------------|
| `GET /calendar/day?day=YYYY-MM-DD` | Get schedule for a day |
| `GET /calendar/day?include_friends=true` | Include friends in classes |
| `GET /calendar/week?start_date=YYYY-MM-DD` | Get week schedule |

### Appointments
| Endpoint | Description |
|----------|-------------|
| `GET /appointments/{id}?date_start=...&date_end=...` | Get appointment details |
| `POST /appointments/{id}/subscribe` | Sign up for a class |
| `POST /appointments/{id}/waitinglist` | Join waiting list |

### Auto-Signup Queue
| Endpoint | Description |
|----------|-------------|
| `GET /queue` | List queued signups |
| `POST /queue` | Add class to auto-signup queue |
| `DELETE /queue/{id}` | Cancel queued signup |

### Friends
| Endpoint | Description |
|----------|-------------|
| `GET /friends` | List all friends |
| `POST /friends` | Add a friend |
| `DELETE /friends/{id}` | Remove a friend |

## Usage Examples

### Get today's schedule
```bash
curl http://127.0.0.1:8000/calendar/day
```

### Get schedule with friends
```bash
curl "http://127.0.0.1:8000/calendar/day?include_friends=true"
```

### Add a friend
```bash
curl -X POST http://127.0.0.1:8000/friends \
  -H "Content-Type: application/json" \
  -d '{"appuser_id": 12345, "name": "Friend Name"}'
```

### Queue auto-signup for a class
```bash
curl -X POST http://127.0.0.1:8000/queue \
  -H "Content-Type: application/json" \
  -d '{
    "appointment_id": 5046413,
    "date_start": "2026-04-19 11:00",
    "date_end": "2026-04-19 12:00"
  }'
```

## How Auto-Signup Works

1. Add a future class to the queue via `POST /queue`
2. The system fetches the signup opening time (7 days before class)
3. A background job is scheduled to run at that exact time
4. When triggered, it attempts to subscribe you to the class
5. If the class is full, it automatically joins the waiting list

## Database

The app uses SQLite (`wodplanner.db`) to store:
- Auto-signup queue
- Friends list

The database is created automatically on first run.

## Import schedules

```
python -m wodplanner.cli.import_schedule "/data/Bull 202603.pdf" --year 2026
```
