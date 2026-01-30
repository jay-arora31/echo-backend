# SuperBryn Voice Agent - Backend

A real-time AI voice agent backend built with FastAPI and LiveKit Agents for appointment booking.

## Features

- **Voice Conversation**: Natural speech-to-text and text-to-speech using Deepgram and Cartesia
- **AI-Powered**: OpenAI GPT-4o-mini for intelligent responses
- **Real-time Avatar**: Beyond Presence integration for visual avatar with lip-sync
- **Tool Calling**: 7 appointment management tools with direct database access
- **Low Latency**: Optimized for <3 second response times

## Tech Stack

- **Framework**: FastAPI + LiveKit Agents SDK
- **STT**: Deepgram (nova-2-general)
- **TTS**: Cartesia (sonic-2)
- **LLM**: OpenAI (gpt-4o-mini)
- **Avatar**: Beyond Presence
- **Database**: PostgreSQL + SQLAlchemy
- **Monitoring**: Logfire

## Prerequisites

- Python 3.11+
- PostgreSQL database
- API keys for: LiveKit, Deepgram, Cartesia, OpenAI, Beyond Presence

## Installation

1. **Clone the repository**

   ```bash
   git clone <your-repo-url>
   cd backend
   ```

2. **Install UV (Python package manager)**

   ```bash
   curl -LsSf https://astral.sh/uv/install.sh | sh
   ```

3. **Install dependencies**

   ```bash
   uv sync
   ```

4. **Set up environment variables**

   ```bash
   cp .env.example .env
   # Edit .env with your API keys
   ```

5. **Set up the database**

   ```bash
   # The database tables are created automatically on startup
   ```

## Configuration

Create a `.env` file with the following variables:

```env
# Database
DATABASE_URL=postgresql+asyncpg://user:password@host:5432/dbname

# LiveKit
LIVEKIT_URL=wss://your-project.livekit.cloud
LIVEKIT_API_KEY=your_api_key
LIVEKIT_API_SECRET=your_api_secret

# Deepgram (STT)
DEEPGRAM_API_KEY=your_deepgram_key

# Cartesia (TTS)
CARTESIA_API_KEY=your_cartesia_key

# OpenAI (LLM)
OPENAI_API_KEY=your_openai_key

# Beyond Presence (Avatar)
BEYOND_PRESENCE_API_KEY=your_beyond_presence_key
BEYOND_PRESENCE_AVATAR_ID=your_avatar_id

# Logfire (Optional monitoring)
LOGFIRE_TOKEN=your_logfire_token

# App
APP_ENV=development
```

## Running Locally

Start both the FastAPI server and LiveKit Agent worker:

```bash
uv run start.py
```

This will:

- Start FastAPI on `http://localhost:8000`
- Start the LiveKit Voice Agent worker
- Auto-reload on code changes

### Individual Services

**FastAPI only:**

```bash
uv run uvicorn app.main:app --reload --port 8000
```

**Voice Agent only:**

```bash
uv run python -c "import sys; sys.argv = ['agent', 'start']; from app.agent.voice_agent import run_agent; run_agent()"
```

## API Endpoints

### Health & Info

- `GET /` - Health check
- `GET /health` - Detailed health status

### LiveKit

- `POST /api/livekit/room` - Create a new room
- `POST /api/livekit/token` - Get access token

### Users

- `POST /api/users/identify` - Identify/create user by phone
- `GET /api/users/{user_id}` - Get user details

### Appointments

- `GET /api/appointments/slots` - Get available slots
- `POST /api/appointments/` - Book appointment
- `GET /api/appointments/user/{user_id}` - Get user's appointments
- `PATCH /api/appointments/{id}` - Modify appointment
- `DELETE /api/appointments/{id}` - Cancel appointment

### Summaries

- `POST /api/summaries/` - Save call summary
- `GET /api/summaries/{session_id}` - Get summary

## Voice Agent Tools

The agent has access to these tools:

| Tool | Description |
|------|-------------|
| `identify_user` | Look up user by phone number |
| `create_user` | Create new user account |
| `get_availability` | Check available appointment slots |
| `book_appointment` | Book an appointment |
| `cancel_appointment` | Cancel an appointment |
| `get_user_appointments` | Get user's appointments |
| `end_conversation` | End call and generate summary |

## Project Structure

```
backend/
├── app/
│   ├── agent/
│   │   ├── voice_agent.py  # Main voice agent logic + tool definitions
│   │   └── prompts.py      # System prompts
│   ├── api/
│   │   ├── deps.py         # Dependency injection
│   │   └── routes/
│   │       ├── room.py         # LiveKit room endpoints
│   │       ├── users.py        # User endpoints
│   │       ├── appointments.py # Appointment endpoints
│   │       └── summaries.py    # Summary endpoints
│   ├── services/           # Business logic layer
│   │   ├── user_service.py
│   │   ├── appointment_service.py
│   │   └── summary_service.py
│   ├── models/             # SQLAlchemy models
│   ├── schemas/            # Pydantic schemas
│   ├── config.py           # Settings
│   ├── database.py         # Database setup
│   └── main.py             # FastAPI app
├── alembic/                # Database migrations
├── start.py                # Entry point
├── pyproject.toml          # Dependencies
├── render.yaml             # Render deployment config
└── .env.example            # Environment template
```

## Deployment

### Render

1. Create a new Web Service on Render
2. Connect your GitHub repo
3. Set build command: `pip install uv && uv sync`
4. Set start command: `uv run start.py`
5. Add environment variables

### Railway

1. Create new project from GitHub
2. Add PostgreSQL database
3. Set environment variables
4. Deploy

### Docker

```dockerfile
FROM python:3.12-slim
WORKDIR /app
RUN pip install uv
COPY . .
RUN uv sync
CMD ["uv", "run", "start.py"]
```

## Known Limitations

1. **Avatar Cold Start**: Beyond Presence takes ~12-15 seconds on first connection
2. **Slot Generation**: Slots are generated dynamically (9 AM - 5 PM, hourly)
3. **Single Region**: LiveKit worker runs in one region

## License

MIT
