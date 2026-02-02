# 🎙️ Echo Voice Agent - Backend

A real-time AI voice agent backend built with FastAPI and LiveKit Agents for appointment booking. Features natural conversation, visual avatar, and intelligent tool calling.

![Python](https://img.shields.io/badge/Python-3.11+-blue?logo=python&logoColor=white)
![FastAPI](https://img.shields.io/badge/FastAPI-0.100+-green?logo=fastapi&logoColor=white)
![LiveKit](https://img.shields.io/badge/LiveKit-Agents-purple)

## ✨ Features

| Feature | Description |
|---------|-------------|
| 🗣️ **Voice Conversation** | Natural speech-to-text and text-to-speech using Deepgram and Cartesia |
| 🤖 **AI-Powered** | OpenAI GPT-4o-mini for intelligent responses and context awareness |
| 👤 **Real-time Avatar** | Beyond Presence integration for visual avatar with lip-sync |
| 🔧 **Tool Calling** | 7 appointment management tools with direct database access |
| 💰 **Cost Tracking** | Estimates usage costs per call (STT, TTS, LLM, Avatar) |
| 📊 **AI Summaries** | Auto-generated call summaries using GPT |

## 🛠️ Tech Stack

| Component | Technology |
|-----------|------------|
| **Framework** | FastAPI + LiveKit Agents SDK |
| **STT** | Deepgram (nova-2-general) |
| **TTS** | Cartesia (sonic-2, Maria voice) |
| **LLM** | OpenAI (gpt-4o-mini) |
| **Avatar** | Beyond Presence |
| **Database** | Supabase (PostgreSQL) + SQLAlchemy |
| **Monitoring** | Logfire |

## 📋 Prerequisites

- Python 3.11+
- [Supabase](https://supabase.com/) database
- API keys for:
  - [LiveKit](https://livekit.io/) - Voice infrastructure
  - [Deepgram](https://deepgram.com/) - Speech-to-text
  - [Cartesia](https://cartesia.ai/) - Text-to-speech
  - [OpenAI](https://openai.com/) - LLM
  - [Beyond Presence](https://beyondpresence.ai/) - Avatar

## 🚀 Quick Start

### 1. Clone & Install

```bash
git clone https://github.com/jay-arora31/echo-backend
cd echo-backend

# Install UV (fast Python package manager)
curl -LsSf https://astral.sh/uv/install.sh | sh

# Install dependencies
uv sync
```

### 2. Configure Environment

```bash
cp .env.example .env
```

Edit `.env` with your API keys:

```env
# Database
DATABASE_URL=postgresql+asyncpg://postgres.[project-ref]:[password]@aws-0-[region].pooler.supabase.com:6543/postgres

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
DEBUG=true
```

### 3. Setup Database

Run Alembic migrations to create tables in your Supabase database:

```bash
uv run alembic upgrade head
```

### 4. Run

```bash
uv run start.py
```

This starts both:

- 🌐 FastAPI server on `http://localhost:8000`
- 🎙️ LiveKit Voice Agent worker

## 🔧 Voice Agent Tools

The AI agent can call these tools during conversation:

| Tool | Description |
|------|-------------|
| `identify_user` | Look up user by phone number |
| `create_user` | Create new user account |
| `get_availability` | Check available appointment slots |
| `book_appointment` | Book an appointment |
| `cancel_appointment` | Cancel an appointment |
| `modify_appointment` | Reschedule an appointment |
| `get_appointments` | Get user's upcoming appointments |
| `end_conversation` | End call and generate summary |

## 📁 Project Structure

```
backend/
├── app/
│   ├── agent/
│   │   ├── voice_agent.py  # Main voice agent + tools
│   │   └── prompts.py      # System prompts
│   ├── api/
│   │   ├── deps.py         # Dependency injection
│   │   └── routes/         # API endpoints
│   │       ├── room.py
│   │       ├── users.py
│   │       ├── appointments.py
│   │       └── summaries.py
│   ├── services/           # Business logic
│   ├── models/             # SQLAlchemy models
│   ├── schemas/            # Pydantic schemas
│   ├── config.py           # Settings
│   ├── database.py         # Database setup
│   └── main.py             # FastAPI app
├── start.py                # Entry point
├── pyproject.toml          # Dependencies
└── .env.example            # Environment template
```

## ⚠️ Known Limitations

| Limitation | Details |
|------------|---------|
| **Avatar Cold Start** | Beyond Presence takes ~15-20 seconds on first connection |
| **Single Worker** | LiveKit agent runs with 2 worker processes |

## 📝 Environment Variables Reference

| Variable | Required | Description |
|----------|----------|-------------|
| `DATABASE_URL` | ✅ | PostgreSQL connection string |
| `LIVEKIT_URL` | ✅ | LiveKit Cloud WebSocket URL |
| `LIVEKIT_API_KEY` | ✅ | LiveKit API key |
| `LIVEKIT_API_SECRET` | ✅ | LiveKit API secret |
| `DEEPGRAM_API_KEY` | ✅ | Deepgram STT API key |
| `CARTESIA_API_KEY` | ✅ | Cartesia TTS API key |
| `OPENAI_API_KEY` | ✅ | OpenAI API key |
| `BEYOND_PRESENCE_API_KEY` | ✅ | Beyond Presence API key |
| `BEYOND_PRESENCE_AVATAR_ID` | ✅ | Avatar ID from Beyond Presence |
| `LOGFIRE_TOKEN` | ❌ | Logfire monitoring token |
| `APP_ENV` | ❌ | Environment (development/production) |
| `CORS_ORIGINS` | ❌ | Allowed CORS origins |
