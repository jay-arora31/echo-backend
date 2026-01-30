from fastapi import APIRouter
from app.api.routes import room, users, appointments, summaries

api_router = APIRouter()

api_router.include_router(room.router, prefix="/room", tags=["Room"])
api_router.include_router(users.router, prefix="/users", tags=["Users"])
api_router.include_router(appointments.router, prefix="/appointments", tags=["Appointments"])
api_router.include_router(summaries.router, prefix="/summaries", tags=["Summaries"])

