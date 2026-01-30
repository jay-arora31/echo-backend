"""LiveKit Voice Agent implementation."""

import asyncio
import logging
import logfire
import json
import time as time_module
import os
from pathlib import Path
from typing import AsyncIterable, Optional

# Load .env file FIRST before importing settings
# This is critical for subprocess environments where .env might not be auto-loaded
from dotenv import load_dotenv
_env_path = Path(__file__).parent.parent.parent / ".env"
load_dotenv(_env_path)

from livekit import rtc
from livekit.agents import (
    Agent,
    AgentSession,
    JobContext,
    WorkerOptions,
    cli,
    function_tool,
    ModelSettings,
)
from livekit.plugins import deepgram, cartesia, openai, silero
import livekit.plugins.bey as bey

from app.agent.prompts import get_system_prompt
from app.config import Settings

# Create settings instance - env vars are now loaded via dotenv
settings = Settings()


# Note: Custom TTS streaming removed - was causing "no audio frames pushed" errors
# Text streaming is handled via conversation_item_added event instead


# Set up logging
logging.basicConfig(level=logging.DEBUG)
logger = logging.getLogger(__name__)

# Initialize Logfire for voice agent process
if settings.logfire_token:
    logfire.configure(
        token=settings.logfire_token,
        service_name="superbryn-voice-agent",
        environment=settings.app_env,
    )

# Session data storage (in-memory for this implementation)
session_data = {}

# Global room reference for tool event broadcasting
_current_room = None

def set_current_room(room):
    """Set the current room for tool event broadcasting."""
    global _current_room
    _current_room = room

async def broadcast_tool_event(tool_name: str, event_type: str, result: str = None):
    """Broadcast a tool event to the frontend via LiveKit data channel."""
    global _current_room
    if _current_room is None:
        logger.warning(f"No room set for tool event: {tool_name}")
        return
    
    import json
    event = {
        "type": f"tool_{event_type}",  # tool_start or tool_end
        "tool": tool_name,
        "timestamp": time_module.time(),
    }
    if result and event_type == "end":
        event["result"] = result[:200] if len(result) > 200 else result  # Truncate long results
    
    try:
        await _current_room.local_participant.publish_data(
            json.dumps(event).encode(),
            reliable=True,
            topic="tool_events"
        )
        logger.info(f"Tool {event_type}: {tool_name}")
    except Exception as e:
        logger.error(f"Failed to broadcast tool event: {e}")


# Database imports for direct access
from sqlalchemy import select, and_
from sqlalchemy.orm import Session
from app.database import SessionLocal
from app.models import User, Appointment, CallSummary
from datetime import time as dt_time
from datetime import datetime, date, timedelta


def get_db():
    """Get database session."""
    db = SessionLocal()
    try:
        return db
    except Exception:
        db.close()
        raise


def get_upcoming_appointments_filter():
    """
    Returns filter conditions for upcoming appointments.
    - Future days: all appointments
    - Today: only appointments where time > current time
    """
    from sqlalchemy import or_
    today = date.today()
    current_time = datetime.now().time()
    
    # Either: appointment is after today
    # Or: appointment is today AND time is in the future
    return or_(
        Appointment.appointment_date > today,
        and_(
            Appointment.appointment_date == today,
            Appointment.appointment_time > current_time
        )
    )



@function_tool
async def identify_user(phone_number: str) -> str:
    """Look up a user by phone number. Returns user info or indicates new user."""
    await broadcast_tool_event("identify_user", "start")
    logfire.info("tool_identify_user", phone=phone_number)
    
    try:
        db = get_db()
        try:
            user = db.query(User).filter(User.phone_number == phone_number).first()
            
            if user:
                # Get their upcoming appointments (today's future + all future days)
                appointments = db.query(Appointment).filter(
                    Appointment.user_id == user.id,
                    Appointment.status == 'scheduled',
                    get_upcoming_appointments_filter()  # Filters out past appointments including today's past times
                ).order_by(Appointment.appointment_date, Appointment.appointment_time).limit(5).all()
                
                # Update session data
                session_id = list(session_data.keys())[-1] if session_data else "unknown"
                if session_id in session_data:
                    session_data[session_id]["user_id"] = str(user.id)
                    session_data[session_id]["user_name"] = user.name or "Unknown"
                    session_data[session_id]["user_phone"] = phone_number
                
                apt_list = []
                for apt in appointments:
                    apt_list.append(f"{apt.appointment_date} at {apt.appointment_time}")
                
                result = f"Found user: {user.name or 'No name'}. "
                if apt_list:
                    result += f"Upcoming appointments: {', '.join(apt_list)}"
                else:
                    result += "No upcoming appointments."
                return result
            else:
                return f"New user with phone {phone_number}. Ask for their name to create account."
        finally:
            db.close()
    except Exception as e:
        logfire.error("identify_user_error", error=str(e))
        return f"Error looking up user: {str(e)}"


@function_tool
async def create_user(phone_number: str, name: str) -> str:
    """Create a new user account."""
    await broadcast_tool_event("create_user", "start")
    logfire.info("tool_create_user", phone=phone_number, name=name)
    
    try:
        db = get_db()
        try:
            # Check if user already exists
            existing = db.query(User).filter(User.phone_number == phone_number).first()
            if existing:
                return f"User already exists: {existing.name}"
            
            user = User(phone_number=phone_number, name=name)
            db.add(user)
            db.commit()
            db.refresh(user)
            
            # Update session data
            session_id = list(session_data.keys())[-1] if session_data else "unknown"
            if session_id in session_data:
                session_data[session_id]["user_id"] = str(user.id)
                session_data[session_id]["user_name"] = name
                session_data[session_id]["user_phone"] = phone_number
            
            return f"Created account for {name}."
        finally:
            db.close()
    except Exception as e:
        logfire.error("create_user_error", error=str(e))
        return f"Error creating user: {str(e)}"


def generate_slots_for_date(check_date: date) -> list:
    """Generate available time slots for a date (9 AM - 5 PM, hourly)."""
    slots = []
    for hour in range(9, 17):  # 9 AM to 4 PM (last slot)
        slots.append(dt_time(hour, 0))
    return slots


def get_available_slots(db, check_date: date) -> list:
    """Get available slots for a date by checking against existing appointments."""
    all_slots = generate_slots_for_date(check_date)
    
    # Get booked appointments for this date
    booked = db.query(Appointment).filter(
        Appointment.appointment_date == check_date,
        Appointment.status == 'scheduled'
    ).all()
    booked_times = {apt.appointment_time for apt in booked}
    
    # Return slots that aren't booked
    return [slot for slot in all_slots if slot not in booked_times]


@function_tool
async def get_availability(date_str: Optional[str] = None) -> str:
    """Get available appointment slots. If no date provided, shows today's slots first, then offers other days."""
    await broadcast_tool_event("get_availability", "start")
    logfire.info("tool_get_availability", date=date_str)
    
    try:
        db = get_db()
        try:
            today = date.today()
            current_time = datetime.now().time()
            
            if date_str:
                # Parse the specific date requested
                target_date = None
                date_lower = date_str.lower().strip()
                
                if "today" in date_lower:
                    target_date = today
                elif "tomorrow" in date_lower:
                    target_date = today + timedelta(days=1)
                else:
                    # Try various date formats
                    for fmt in ["%Y-%m-%d", "%m/%d/%Y", "%d/%m/%Y", "%B %d, %Y", "%b %d, %Y", "%B %d", "%b %d"]:
                        try:
                            target_date = datetime.strptime(date_str, fmt).date()
                            if target_date.year == 1900:
                                target_date = target_date.replace(year=today.year)
                            break
                        except ValueError:
                            continue
                    
                    # Try weekday names
                    if not target_date:
                        weekdays = ["monday", "tuesday", "wednesday", "thursday", "friday", "saturday", "sunday"]
                        for i, day in enumerate(weekdays):
                            if day in date_lower:
                                days_ahead = i - today.weekday()
                                if days_ahead <= 0:
                                    days_ahead += 7
                                target_date = today + timedelta(days=days_ahead)
                                break
                
                if not target_date:
                    return f"I couldn't understand the date '{date_str}'. Could you say it differently? Like 'tomorrow' or 'next Monday'?"
                
                available = get_available_slots(db, target_date)
                
                # Filter out past slots if it's today
                if target_date == today:
                    available = [t for t in available if t > current_time]
                
                if available:
                    times = [t.strftime("%I:%M %p").lstrip("0") for t in available]
                    
                    # Natural day name
                    if target_date == today:
                        day_label = "today"
                    elif target_date == today + timedelta(days=1):
                        day_label = "tomorrow"
                    else:
                        day_label = "on " + target_date.strftime("%A, %B %d")
                    
                    if len(times) == 1:
                        return f"I have one slot available {day_label} at {times[0]}. Would you like to book it?"
                    else:
                        times_text = ", ".join(times[:-1]) + " and " + times[-1]
                        return f"I have {len(times)} slots available {day_label}: {times_text}. Which time works for you?"
                else:
                    return f"Sorry, no slots available {day_label if 'day_label' in dir() else 'on that day'}. Would you like to check another day?"
            
            else:
                # No date specified - show TODAY's slots first, then offer other options
                today_available = get_available_slots(db, today)
                # Filter out past times for today
                today_available = [t for t in today_available if t > current_time]
                
                tomorrow = today + timedelta(days=1)
                tomorrow_available = get_available_slots(db, tomorrow)
                
                response_parts = []
                
                # Today's slots - show actual times
                if today_available:
                    times = [t.strftime("%I:%M %p").lstrip("0") for t in today_available[:6]]
                    if len(times) == 1:
                        response_parts.append(f"Today I have one slot at {times[0]}")
                    else:
                        times_text = ", ".join(times[:-1]) + " and " + times[-1]
                        response_parts.append(f"Today I have slots at {times_text}")
                else:
                    response_parts.append("No slots available today")
                
                # Tomorrow - brief mention
                if tomorrow_available:
                    response_parts.append(f"Tomorrow I have {len(tomorrow_available)} slots starting at {tomorrow_available[0].strftime('%I:%M %p').lstrip('0')}")
                
                # Check if there's availability in next 10 days
                has_more = False
                for i in range(2, 10):
                    check_date = today + timedelta(days=i)
                    if get_available_slots(db, check_date):
                        has_more = True
                        break
                
                if has_more:
                    response_parts.append("I also have availability later this week")
                
                result = ". ".join(response_parts) + ". Which day and time works best for you?"
                return result
                
        finally:
            db.close()
    except Exception as e:
        logfire.error("get_availability_error", error=str(e))
        return f"Error getting availability: {str(e)}"


@function_tool
async def book_appointment(phone_number: str, date_str: str, time_str: str, notes: Optional[str] = None) -> str:
    """Book an appointment. Args: phone_number (str), date_str (str): Date (YYYY-MM-DD or 'today'/'tomorrow'), time_str (str): Time (e.g. '2 PM')."""
    await broadcast_tool_event("book_appointment", "start")
    logfire.info("tool_book_appointment", phone=phone_number, date=date_str, time=time_str)
    
    try:
        db = get_db()
        try:
            # Parse date - handle various formats
            parsed_date = None
            today = date.today()
            
            date_lower = date_str.lower()
            if "today" in date_lower:
                parsed_date = today
            elif "tomorrow" in date_lower:
                parsed_date = today + timedelta(days=1)
            else:
                # Try various date formats
                for fmt in ["%Y-%m-%d", "%m/%d/%Y", "%d/%m/%Y", "%B %d", "%b %d"]:
                    try:
                        parsed_date = datetime.strptime(date_str, fmt).date()
                        # If no year in format, assume current year
                        if parsed_date.year == 1900:
                            parsed_date = parsed_date.replace(year=today.year)
                        break
                    except ValueError:
                        continue
                
                # Try weekday names
                if not parsed_date:
                    weekdays = ["monday", "tuesday", "wednesday", "thursday", "friday", "saturday", "sunday"]
                    for i, day in enumerate(weekdays):
                        if day in date_lower:
                            # Find the next occurrence of this weekday
                            days_ahead = i - today.weekday()
                            if days_ahead <= 0:  # Target day is today or in the past
                                days_ahead += 7
                            parsed_date = today + timedelta(days=days_ahead)
                            break
            
            if not parsed_date:
                return f"I couldn't understand the date '{date_str}'. Could you say it differently? Like 'tomorrow' or 'next Monday'?"
            
            # Parse time - handle various formats  
            parsed_time = None
            time_lower = time_str.lower().strip()
            
            # Try standard formats
            for fmt in ["%I:%M %p", "%I:%M%p", "%H:%M", "%I %p", "%I%p"]:
                try:
                    parsed_time = datetime.strptime(time_str.upper(), fmt).time()
                    break
                except ValueError:
                    continue
            
            # Handle casual time like "2", "2pm", "14"
            if not parsed_time:
                import re
                match = re.match(r'^(\d{1,2})\s*(am|pm)?$', time_lower)
                if match:
                    hour = int(match.group(1))
                    period = match.group(2)
                    if period == 'pm' and hour < 12:
                        hour += 12
                    elif period == 'am' and hour == 12:
                        hour = 0
                    elif not period and hour < 9:
                        hour += 12  # Assume PM for hours 1-8 without am/pm
                    if 0 <= hour <= 23:
                        parsed_time = dt_time(hour, 0)
            
            if not parsed_time:
                return f"I couldn't understand the time '{time_str}'. Could you try something like '2 PM' or '14:00'?"
            
            # Validate business hours (9 AM - 5 PM)
            if parsed_time.hour < 9 or parsed_time.hour >= 17:
                return f"Our hours are 9 AM to 5 PM. Would you like a morning or afternoon slot?"
            
            # Check slot availability
            existing = db.query(Appointment).filter(
                Appointment.appointment_date == parsed_date,
                Appointment.appointment_time == parsed_time,
                Appointment.status == 'scheduled'
            ).first()
            
            if existing:
                # Get nearby available slots
                available = get_available_slots(db, parsed_date)
                if available:
                    nearby = [t.strftime("%I:%M %p").lstrip("0") for t in available[:3]]
                    return f"Sorry, {parsed_time.strftime('%I:%M %p')} is taken. How about {', '.join(nearby)}?"
                return f"Sorry, {parsed_time.strftime('%I:%M %p')} is already booked. Would you like to try a different time?"
            
            # Find user by phone number
            user = db.query(User).filter(User.phone_number == phone_number).first()
            if not user:
                return f"No account found for {phone_number}. Please identify the user first."
            
            # Create appointment
            appointment = Appointment(
                user_id=user.id,
                appointment_date=parsed_date,
                appointment_time=parsed_time,
                status='scheduled',
                notes=notes
            )
            db.add(appointment)
            db.commit()
            db.refresh(appointment)
            
            # Track in session data
            session_id = list(session_data.keys())[-1] if session_data else "unknown"
            if session_id in session_data:
                data = session_data[session_id]
                data["appointments_booked"].append({
                    "id": str(appointment.id),
                    "date": str(parsed_date),
                    "time": str(parsed_time),
                    "notes": notes
                })
            
            formatted_date = parsed_date.strftime("%A, %B %d")
            formatted_time = parsed_time.strftime("%I:%M %p").lstrip("0")
            
            # Broadcast completion with formatted date and time for frontend display
            await broadcast_tool_event("book_appointment", "end", f"{formatted_date} at {formatted_time}")
            
            return f"Appointment confirmed for {user.name or phone_number} on {formatted_date} at {formatted_time}."
            
        finally:
            db.close()
    except Exception as e:
        logfire.error("book_appointment_error", error=str(e))
        return f"I ran into an issue booking that appointment. Could you try again?"


@function_tool
async def cancel_appointment(phone_number: str, date_str: Optional[str] = None) -> str:
    """Cancel an appointment. Args: phone_number (str), date_str (str, optional): Date to cancel (YYYY-MM-DD or 'today'/'tomorrow')."""
    await broadcast_tool_event("cancel_appointment", "start")
    logfire.info("tool_cancel_appointment", phone=phone_number, date=date_str)
    
    try:
        db = get_db()
        try:
            user = db.query(User).filter(User.phone_number == phone_number).first()
            if not user:
                return f"I don't have any appointments on file for {phone_number}."
            
            # Only allow canceling upcoming appointments (today's future + all future days)
            query = db.query(Appointment).filter(
                Appointment.user_id == user.id,
                Appointment.status == 'scheduled',
                get_upcoming_appointments_filter()  # Filters out past appointments
            )
            
            if date_str:
                # Parse the date
                parsed_date = None
                today = date.today()
                date_lower = date_str.lower()
                
                if "today" in date_lower:
                    parsed_date = today
                elif "tomorrow" in date_lower:
                    parsed_date = today + timedelta(days=1)
                else:
                    for fmt in ["%Y-%m-%d", "%m/%d/%Y", "%B %d", "%b %d"]:
                        try:
                            parsed_date = datetime.strptime(date_str, fmt).date()
                            break
                        except ValueError:
                            continue
                
                if parsed_date:
                    query = query.filter(Appointment.appointment_date == parsed_date)
            
            appointments = query.order_by(Appointment.appointment_date).all()
            
            if not appointments:
                return f"I couldn't find any upcoming appointments for {user.name or phone_number}."
            
            if len(appointments) > 1 and not date_str:
                # Multiple appointments - ask which one
                apt_list = [f"{a.appointment_date.strftime('%B %d')} at {a.appointment_time.strftime('%I:%M %p')}" for a in appointments[:3]]
                return f"{user.name or 'You'} have {len(appointments)} appointments. Which one would you like to cancel? {', '.join(apt_list)}"
            
            # Cancel the first/only matching appointment
            appointment = appointments[0]
            formatted = f"{appointment.appointment_date.strftime('%A, %B %d')} at {appointment.appointment_time.strftime('%I:%M %p')}"
            appointment.status = 'cancelled'
            db.commit()
            
            await broadcast_tool_event("cancel_appointment", "end", f"Cancelled for {user.name} on {formatted}")
            return f"I've cancelled the appointment for {user.name or phone_number} on {formatted}."
        finally:
            db.close()
    except Exception as e:
        logfire.error("cancel_appointment_error", error=str(e), phone=phone_number, date_input=date_str)
        return f"I ran into an error cancelling the appointment: {str(e)}"


@function_tool
async def modify_appointment(phone_number: str, new_date_str: str, new_time_str: str, old_date_str: Optional[str] = None) -> str:
    """Modify an existing appointment to a new date and/or time."""
    await broadcast_tool_event("modify_appointment", "start")
    logfire.info("tool_modify_appointment", phone=phone_number, new_date=new_date_str, new_time=new_time_str)
    
    try:
        db = get_db()
        try:
            # Find user by phone
            user = db.query(User).filter(User.phone_number == phone_number).first()
            if not user:
                return f"I couldn't find an account with phone number {phone_number}. Please verify your number."
            
            # Find their scheduled appointments (today's future + all future days)
            query = db.query(Appointment).filter(
                Appointment.user_id == user.id,
                Appointment.status == 'scheduled',
                get_upcoming_appointments_filter()  # Filters out past appointments
            )
            
            # If old date specified, filter by it
            if old_date_str:
                try:
                    old_date = datetime.strptime(old_date_str, "%Y-%m-%d").date()
                    query = query.filter(Appointment.appointment_date == old_date)
                except ValueError:
                    pass
            
            appointments = query.order_by(Appointment.appointment_date).all()
            
            if not appointments:
                return f"I don't see any scheduled appointments to modify for {user.name or phone_number}."
            
            if len(appointments) > 1 and not old_date_str:
                apt_list = [f"{apt.appointment_date.strftime('%B %d')} at {apt.appointment_time.strftime('%I:%M %p')}" 
                           for apt in appointments[:3]]
                return f"You have multiple appointments: {', '.join(apt_list)}. Which one would you like to modify? Please specify the date."
            
            # Parse new date
            new_date = None
            today = date.today()
            new_date_lower = new_date_str.lower().strip()
            
            if new_date_lower == "today":
                new_date = today
            elif new_date_lower == "tomorrow":
                new_date = today + timedelta(days=1)
            else:
                # Try various date formats
                for fmt in ["%Y-%m-%d", "%m/%d/%Y", "%B %d", "%b %d", "%B %d, %Y"]:
                    try:
                        parsed = datetime.strptime(new_date_str, fmt)
                        new_date = parsed.date()
                        if new_date.year == 1900:  # Format without year
                            new_date = new_date.replace(year=today.year)
                        break
                    except ValueError:
                        continue
            
            if not new_date:
                return f"I couldn't understand the date '{new_date_str}'. Could you say it like 'January 30' or 'tomorrow'?"
            
            # Parse new time
            new_time = None
            for fmt in ["%I:%M %p", "%I%p", "%I %p", "%H:%M"]:
                try:
                    new_time = datetime.strptime(new_time_str.upper().strip(), fmt).time()
                    break
                except ValueError:
                    continue
            
            if not new_time:
                return f"I couldn't understand the time '{new_time_str}'. Could you say it like '2 PM' or '14:00'?"
            
            # Check if new slot is available
            existing = db.query(Appointment).filter(
                Appointment.appointment_date == new_date,
                Appointment.appointment_time == new_time,
                Appointment.status == 'scheduled'
            ).first()
            
            if existing and existing.id != appointments[0].id:
                return f"Sorry, {new_date.strftime('%B %d')} at {new_time.strftime('%I:%M %p')} is already booked. Would you like a different time?"
            
            # Modify the appointment
            old_formatted = f"{appointments[0].appointment_date.strftime('%B %d')} at {appointments[0].appointment_time.strftime('%I:%M %p')}"
            appointments[0].appointment_date = new_date
            appointments[0].appointment_time = new_time
            db.commit()
            
            new_formatted = f"{new_date.strftime('%A, %B %d')} at {new_time.strftime('%I:%M %p')}"
            return f"I've updated your appointment from {old_formatted} to {new_formatted}."
        finally:
            db.close()
    except Exception as e:
        logfire.error("modify_appointment_error", error=str(e))
        return "I ran into an issue modifying that appointment. Could you try again?"

@function_tool
async def get_appointments(phone_number: str) -> str:
    """Get all appointments for a user. Args: phone_number (str)."""
    await broadcast_tool_event("get_appointments", "start")
    logfire.info("tool_get_appointments", phone=phone_number)
    
    try:
        db = get_db()
        try:
            user = db.query(User).filter(User.phone_number == phone_number).first()
            if not user:
                return f"I don't have any appointments on file for {phone_number}."
            
            # Only get upcoming appointments (today's future + all future days)
            appointments = db.query(Appointment).filter(
                Appointment.user_id == user.id,
                Appointment.status == 'scheduled',
                get_upcoming_appointments_filter()  # Filters out past appointments
            ).order_by(Appointment.appointment_date, Appointment.appointment_time).all()
            
            if not appointments:
                return f"{user.name or 'You'} don't have any upcoming appointments scheduled."
            
            apt_list = []
            for apt in appointments[:5]:
                formatted_date = apt.appointment_date.strftime('%A, %B %d')
                formatted_time = apt.appointment_time.strftime('%I:%M %p').lstrip('0')
                apt_list.append(f"{formatted_date} at {formatted_time}")
            
            if len(appointments) == 1:
                return f"{user.name or 'You'} have one appointment: {apt_list[0]}."
            else:
                result = f"{user.name or 'You'} have {len(appointments)} appointments: " + "; ".join(apt_list)
                if len(appointments) > 5:
                    result += f" (and {len(appointments) - 5} more)"
                return result
        finally:
            db.close()
    except Exception as e:
        logfire.error("get_appointments_error", error=str(e))
        return "I had trouble looking up those appointments. Could you try again?"


@function_tool
async def end_conversation(session_id: str) -> str:
    """End the conversation and generate a summary."""
    await broadcast_tool_event("end_conversation", "start")
    logfire.info("tool_end_conversation", session=session_id)
    
    try:
        data = session_data.get(session_id, {})
        conversation_history = data.get("conversation_history", [])
        
        # Use OpenAI to generate AI summary from conversation
        summary_text = "Call ended."
        try:
            import openai
            from app.config import settings
            
            # Format conversation for summary
            if conversation_history:
                conversation_text = "\n".join([
                    f"{msg['role'].capitalize()}: {msg['content']}" 
                    for msg in conversation_history[-20:]  # Last 20 messages max
                ])
                
                # Call OpenAI for AI-generated summary
                client = openai.AsyncOpenAI(api_key=settings.openai_api_key)
                response = await client.chat.completions.create(
                    model="gpt-4o-mini",  # Fast and cheap
                    messages=[
                        {
                            "role": "system",
                            "content": """You are summarizing a voice call between a user and an AI appointment booking assistant.
Generate a concise but detailed summary including:
- Who the caller was (name/phone if mentioned)
- What actions were taken (appointments booked, cancelled, modified)
- Key details (dates, times, any issues encountered)
- User's preferences or requests

Keep it to 2-3 sentences max. Be specific about dates and times mentioned."""
                        },
                        {
                            "role": "user", 
                            "content": f"Summarize this conversation:\n\n{conversation_text}"
                        }
                    ],
                    max_tokens=150,
                    temperature=0.3,
                )
                summary_text = response.choices[0].message.content or "Call completed."
                logger.info(f"AI-generated summary: {summary_text}")
        except Exception as e:
            logger.error(f"AI summary generation failed: {e}")
            # Fallback to structured summary
            summary_parts = []
            if data.get("user_name"):
                summary_parts.append(f"User: {data['user_name']}")
            if data.get("user_phone"):
                summary_parts.append(f"Phone: {data['user_phone']}")
            if data.get("appointments_booked"):
                apt_count = len(data["appointments_booked"])
                summary_parts.append(f"Booked {apt_count} appointment(s)")
            summary_text = " | ".join(summary_parts) if summary_parts else "No actions taken."
        
        logfire.info("Generated summary", summary=summary_text)
        
        # Save to database
        try:
            db = get_db()
            try:
                prefs = data.get("user_preferences", {})
                clean_prefs = {k: v for k, v in prefs.items() if v}
                call_summary = CallSummary(
                    user_id=data.get("user_id"),
                    session_id=session_id,
                    summary=summary_text,
                    appointments_booked=data.get("appointments_booked"),
                    user_preferences=clean_prefs,
                    duration_seconds=None,
                )
                db.add(call_summary)
                db.commit()
            finally:
                db.close()
        except Exception as e:
            logfire.error("save_summary_error", error=str(e))
        
        # Send summary to frontend via data channel
        try:
            if _current_room:
                import json
                await _current_room.local_participant.publish_data(
                    json.dumps({
                        "type": "summary",
                        "summary": summary_text,
                        "user_name": data.get("user_name"),
                        "user_phone": data.get("user_phone"),
                        "appointments_booked": data.get("appointments_booked", []),
                    }).encode(),
                    reliable=True,
                    topic="summary"
                )
                logger.info(f"Summary sent to frontend: {summary_text[:100]}")
        except Exception as e:
            logger.error(f"Failed to send summary: {e}")
        
        return summary_text
    except Exception as e:
        logfire.error("end_conversation_error", error=str(e))
        return f"Error generating summary: {str(e)}"


async def entrypoint(ctx: JobContext):
    """Main entrypoint for the voice agent."""
    start_time = time_module.time()
    
    def log_timing(msg: str):
        elapsed = time_module.time() - start_time
        logger.info(f"⏱️ [{elapsed:.2f}s] {msg}")
    
    log_timing("Voice agent starting...")
    
    try:
        # Initialize session
        session_id = f"session_{ctx.room.name}_{int(time_module.time())}"
        session_data[session_id] = {
            "user_id": None,
            "user_name": None,
            "user_phone": None,
            "appointments_booked": [],
            "conversation_history": [],  # Track all messages for AI summary
            "tool_calls": [],  # Track tool calls made
            "user_preferences": {
                "preferred_times": [],
                "preferred_days": [],
                "notes": [],
            },
        }
        log_timing("Session initialized")
        
        # Connect to room
        log_timing("Connecting to room...")
        await ctx.connect()
        log_timing("Connected to room!")
        
        # Set global room reference for tool event broadcasting
        set_current_room(ctx.room)
        
        # Subscribe to audio tracks
        @ctx.room.on("track_published")
        def on_track_published(publication, participant):
            if publication.kind == "audio":
                logger.info(f"Subscribing to audio from {participant.identity}")
                publication.set_subscribed(True)
        
        # Subscribe to existing tracks
        for participant in ctx.room.remote_participants.values():
            for publication in participant.track_publications.values():
                if publication.kind == "audio" and not publication.subscribed:
                    publication.set_subscribed(True)
        
        log_timing("Track subscriptions set up")
        
        # Configure components
        # VAD - Lower values for faster response (reduces latency)
        vad = silero.VAD.load(
            min_silence_duration=0.15,  # Reduced from 0.2 for faster turn detection
            min_speech_duration=0.05,   # Reduced from 0.08 for faster speech detection
        )
        
        # STT - Optimized for low latency streaming
        stt = deepgram.STT(
            model="nova-2-general",
            language="en",
            smart_format=True,
            punctuate=True,
            filler_words=False,          # Disabled - removes filler word processing delay
            endpointing_ms=100,           # Reduced from 200ms for faster turn-taking
            no_delay=True,                # Stream transcription without delay
            interim_results=True,         # Enable faster streaming results
            api_key=settings.deepgram_api_key,
        )
        
        llm = openai.LLM(
            model="gpt-4o-mini",
            temperature=0.3,
            api_key=settings.openai_api_key,
        )
        
        tts = cartesia.TTS(
            model="sonic-2",
            voice="5345cf08-6f37-424d-a5d9-8ae1101b9377",  # "Maria" voice
            api_key=settings.cartesia_api_key,
        )
        
        log_timing("Components configured")
        
        # Define tools per assignment requirements
        tools = [
            identify_user,       # Identify user by phone number
            create_user,         # Create new user with phone + name
            get_availability,    # Get available appointment slots (fetch_slots)
            book_appointment,    # Book appointment
            cancel_appointment,  # Cancel appointment
            modify_appointment,  # Modify appointment date/time
            get_appointments,    # Retrieve past appointments
            end_conversation,    # End call
        ]
        
        # Create agent with tools (tools are passed to Agent, not session)
        agent = Agent(
            instructions=get_system_prompt(),
            tools=tools,
        )
        
        # Create session with low latency settings
        session = AgentSession(
            vad=vad,
            stt=stt,
            llm=llm,
            tts=tts,
            min_endpointing_delay=0.1,   # Reduced from 0.2 for faster response
        )
        
        log_timing("Agent and session created")
        
        # Helper to send data to frontend
        async def send_to_frontend(data: dict):
            try:
                payload = json.dumps(data).encode('utf-8')
                await ctx.room.local_participant.publish_data(payload, reliable=True)
                logger.debug(f"Sent to frontend: {data.get('type')}")
            except Exception as e:
                logger.warning(f"Failed to send to frontend: {e}")
        
        # Set up event handlers
        sent_messages = set()
        user_speech_time = 0
        
        @session.on("user_started_speaking")
        def on_user_started_speaking():
            nonlocal user_speech_time
            user_speech_time = time_module.time()
            logger.info("User started speaking")
        
        @session.on("user_stopped_speaking")
        def on_user_stopped_speaking():
            logger.info("User stopped speaking")
        
        @session.on("agent_started_speaking")
        def on_agent_started_speaking():
            logger.info("Agent started speaking")
            asyncio.create_task(send_to_frontend({
                "type": "agent_speaking_start",
                "timestamp": time_module.time(),
            }))
        
        @session.on("agent_stopped_speaking")
        def on_agent_stopped_speaking():
            logger.info("Agent stopped speaking")
            asyncio.create_task(send_to_frontend({
                "type": "agent_speaking_stop",
                "timestamp": time_module.time(),
            }))
        
        @session.on("agent_speech_interrupted")
        def on_agent_speech_interrupted():
            logger.info("Agent speech interrupted by user")
        
        @session.on("user_input_transcribed")
        def on_user_input_transcribed(event):
            if event.is_final:
                logger.info(f"User said: {event.transcript}")
                # Track in conversation history for AI summary
                if session_id in session_data:
                    session_data[session_id]["conversation_history"].append({
                        "role": "user",
                        "content": event.transcript
                    })
                asyncio.create_task(send_to_frontend({
                    "type": "transcript",
                    "role": "user",
                    "content": event.transcript,
                    "timestamp": time_module.time(),
                }))
        
        @session.on("function_tools_executed")
        def on_function_tools_executed(event):
            """Called after all function tools complete for a user input."""
            try:
                for call in event.function_calls:
                    tool_name = getattr(call, 'name', 'unknown')
                    logger.info(f"Tool executed: {tool_name}")
                    asyncio.create_task(send_to_frontend({
                        "type": "tool_end",
                        "tool": tool_name,
                        "timestamp": time_module.time(),
                    }))
            except Exception as e:
                logger.error(f"Error in function_tools_executed handler: {e}")
        
        @session.on("agent_speech_committed")
        def on_agent_speech_committed(message):
            """Called when LLM commits text - send immediately for reliable delivery."""
            nonlocal user_speech_time
            try:
                content = getattr(message, 'content', None) or getattr(message, 'text', None)
                if isinstance(content, list):
                    content = ' '.join(str(c) for c in content)
                
                if content:
                    content_hash = hash(content[:50]) if len(content) > 50 else hash(content)
                    if content_hash in sent_messages:
                        return
                    sent_messages.add(content_hash)
                    
                    # Track in conversation history for AI summary
                    if session_id in session_data:
                        session_data[session_id]["conversation_history"].append({
                            "role": "assistant",
                            "content": content
                        })
                    
                    response_time = 0
                    if user_speech_time > 0:
                        response_time = round(time_module.time() - user_speech_time, 2)
                        logger.info(f"Response latency: {response_time}s")
                    
                    # Send transcript immediately
                    logger.info(f"Sending transcript: {content[:50]}...")
                    asyncio.create_task(send_to_frontend({
                        "type": "transcript",
                        "role": "assistant",
                        "content": content,
                        "timestamp": time_module.time(),
                        "response_time": response_time,
                    }))
            except Exception as e:
                logger.debug(f"Speech committed event: {e}")
        
        @session.on("conversation_item_added")
        def on_conversation_item_added(event):
            nonlocal user_speech_time
            try:
                item = getattr(event, 'item', event)
                role = getattr(item, 'role', None)
                content = getattr(item, 'content', None) or getattr(item, 'text', None)
                
                if isinstance(content, list):
                    content = ' '.join(str(c) for c in content)
                
                if role == 'assistant' and content:
                    logger.info(f"Conversation item (assistant): {content}")
                    
                    content_hash = hash(content[:50]) if len(content) > 50 else hash(content)
                    if content_hash in sent_messages:
                        return
                    sent_messages.add(content_hash)
                    
                    response_time = 0
                    if user_speech_time > 0:
                        response_time = round(time_module.time() - user_speech_time, 2)
                        logger.info(f"Response latency: {response_time}s")
                    
                    asyncio.create_task(send_to_frontend({
                        "type": "transcript",
                        "role": "assistant",
                        "content": content,
                        "timestamp": time_module.time(),
                        "response_time": response_time,
                    }))
            except Exception as e:
                logger.debug(f"Conversation item event: {e}")
        
        # Set up shutdown handling
        shutdown_event = asyncio.Event()
        
        async def on_shutdown():
            logger.info("Shutdown requested")
            shutdown_event.set()
        
        ctx.add_shutdown_callback(on_shutdown)
        
        @ctx.room.on("disconnected")
        def on_disconnect():
            logger.info("Room disconnected")
            shutdown_event.set()
        
        # Start the session
        log_timing("Starting agent session...")
        with logfire.span("agent_session_start"):
            await session.start(
                agent=agent,
                room=ctx.room,
            )
        log_timing("Agent session started!")
        
        # NEW FLOW: Wait for avatar to ACTUALLY load BEFORE greeting
        # (Not static time - wait for actual video track from avatar participant)
        
        async def send_avatar_status(status: str, message: str = ""):
            """Send avatar status to frontend."""
            try:
                payload = json.dumps({
                    "type": "avatar_status",
                    "status": status,
                    "message": message,
                    "timestamp": time_module.time(),
                }).encode('utf-8')
                await ctx.room.local_participant.publish_data(payload, reliable=True)
                logger.info(f"Avatar status sent: {status}")
            except Exception as e:
                logger.warning(f"Failed to send avatar status: {e}")
        
        # Check if Beyond Presence avatar is configured
        avatar_ready = False
        if settings.beyond_presence_api_key and settings.beyond_presence_avatar_id:
            # Send "loading" status to frontend
            await send_avatar_status("loading", "Connecting to avatar...")
            log_timing("Starting Beyond Presence avatar...")
            
            try:
                # Create an event to wait for avatar video track
                avatar_video_ready = asyncio.Event()
                avatar_participant_identity = None  # Will be set when avatar joins
                
                def on_participant_connected(participant):
                    """Detect when avatar participant joins the room."""
                    nonlocal avatar_participant_identity
                    # Beyond Presence avatar typically has "avatar" or "bey" in identity
                    identity = participant.identity.lower()
                    if "avatar" in identity or "bey" in identity or "beyond" in identity:
                        avatar_participant_identity = participant.identity
                        logger.info(f"Avatar participant connected: {participant.identity}")
                        # Check if video track already published
                        for pub in participant.track_publications.values():
                            if pub.kind == rtc.TrackKind.KIND_VIDEO and pub.track:
                                logger.info("Avatar video track already available!")
                                avatar_video_ready.set()
                                return
                
                def on_track_published(publication, participant):
                    """Detect when avatar publishes video track."""
                    if publication.kind == rtc.TrackKind.KIND_VIDEO:
                        identity = participant.identity.lower()
                        if "avatar" in identity or "bey" in identity or "beyond" in identity:
                            logger.info(f"Avatar video track published by {participant.identity}")
                            avatar_video_ready.set()
                
                def on_track_subscribed(track, publication, participant):
                    """Detect when avatar video track is subscribed."""
                    if track.kind == rtc.TrackKind.KIND_VIDEO:
                        identity = participant.identity.lower()
                        if "avatar" in identity or "bey" in identity or "beyond" in identity:
                            logger.info(f"Avatar video track subscribed from {participant.identity}")
                            avatar_video_ready.set()
                
                # Register event handlers
                ctx.room.on("participant_connected", on_participant_connected)
                ctx.room.on("track_published", on_track_published)
                ctx.room.on("track_subscribed", on_track_subscribed)
                
                # Check existing participants (avatar might already be connected)
                for participant in ctx.room.remote_participants.values():
                    identity = participant.identity.lower()
                    if "avatar" in identity or "bey" in identity or "beyond" in identity:
                        avatar_participant_identity = participant.identity
                        logger.info(f"Avatar participant already in room: {participant.identity}")
                        for pub in participant.track_publications.values():
                            if pub.kind == rtc.TrackKind.KIND_VIDEO:
                                logger.info("Avatar video track already available!")
                                avatar_video_ready.set()
                                break
                
                # Start the avatar session (this initiates the connection)
                avatar_session = bey.AvatarSession(
                    api_key=settings.beyond_presence_api_key,
                    avatar_id=settings.beyond_presence_avatar_id,
                )
                await avatar_session.start(room=ctx.room, agent_session=session)
                log_timing("Beyond Presence avatar session started, waiting for video track...")
                
                # Wait for avatar video track with timeout (max 30 seconds)
                try:
                    await asyncio.wait_for(avatar_video_ready.wait(), timeout=30.0)
                    log_timing("✅ Avatar video track ready!")
                    avatar_ready = True
                    await send_avatar_status("ready", "Avatar connected!")
                except asyncio.TimeoutError:
                    logger.warning("Timeout waiting for avatar video track (30s)")
                    log_timing("⚠️ Avatar timeout - continuing without video confirmation")
                    # Still mark as ready since avatar session started
                    avatar_ready = True
                    await send_avatar_status("ready", "Avatar connected (video pending)")
                
            except Exception as e:
                logger.warning(f"Failed to start Beyond Presence avatar: {e}")
                logger.info("Continuing without avatar...")
                await send_avatar_status("failed", "Avatar unavailable")
        else:
            log_timing("Beyond Presence avatar not configured (skipping)")
            await send_avatar_status("ready", "Connected!")
        
        # NOW send the greeting - after avatar is ready
        log_timing("Sending greeting...")
        
        # Small delay to let audio track stabilize before first TTS output
        # This prevents the "disturbed" audio on the first message
        await asyncio.sleep(0.5)
        
        greeting = "Hi there! How can I help you today?"
        logfire.info("tts_greeting_start", message=greeting)
        speech_handle = session.say(greeting, allow_interruptions=True)
        log_timing("Greeting queued (TTS runs in background)")
        
        # Keep running until disconnect
        log_timing("Agent running - listening for user input...")
        await shutdown_event.wait()
        log_timing("Session ended")
        
    except Exception as e:
        logger.exception(f"Error in voice agent: {e}")
        raise


def run_agent():
    """Run the voice agent worker."""
    logger.info("=" * 50)
    logger.info("Starting LiveKit Voice Agent Worker")
    logger.info("=" * 50)
    
    cli.run_app(
        WorkerOptions(
            entrypoint_fnc=entrypoint,
            api_key=settings.livekit_api_key,
            api_secret=settings.livekit_api_secret,
            ws_url=settings.livekit_url,
        )
    )


if __name__ == "__main__":
    run_agent()
