import uvicorn
from contextlib import asynccontextmanager
from fastapi.responses import RedirectResponse
from fastapi import FastAPI, Request, HTTPException, Depends

from src.factories.service import ServiceFactory
from src.models.user_response import UserCreate, UserResponse
from src.models.events import CreateEventRequest, EventsResponse
from src.services.calendar.google_calendar import GoogleCalendarService

from db.database import database
from data.init_configs import init, get_config

@asynccontextmanager
async def lifespan(app: FastAPI):
    init()
    await database.setup()
    await database.create_tables()
    print("✅ App started")
    yield
    await database.close()
    print("✅ App stopped")


app = FastAPI(title="Google Calendar API", lifespan=lifespan)

async def get_calendar_service():
    async with database.transaction() as session:
        service, _ = await ServiceFactory.create_google_calendar_service(session)
        yield service

@app.get("/auth_url")
async def auth_url(
    tg_id: int,
    calendar_service: GoogleCalendarService = Depends(get_calendar_service)
):
    try:
        url = await calendar_service.get_auth_url(tg_id)
        return {"auth_url": url}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@app.get("/oauth/callback")
async def oauth_callback(
    request: Request,
    calendar_service: GoogleCalendarService = Depends(get_calendar_service)
):
    code = request.query_params.get("code")
    state = request.query_params.get("state")

    if not code or not state:
        raise HTTPException(status_code=400, detail="Invalid OAuth callback")

    user = await calendar_service.users_repo.get_user_by_google_id(state)
    if not user:
        raise HTTPException(status_code=400, detail="Invalid state")

    await calendar_service.exchange_code(user.tg_id, code)

    return RedirectResponse(url="/success")


@app.get("/events", response_model=EventsResponse)
async def get_events(
    tg_id: int,
    calendar_service: GoogleCalendarService = Depends(get_calendar_service)
):
    if not await calendar_service.load_credentials(tg_id):
        raise HTTPException(status_code=401, detail="Not authorized")

    events = await calendar_service.get_events(tg_id)
    return EventsResponse(events=events)

@app.get("/users/{tg_id}", response_model=UserResponse)
async def get_user(
    tg_id: int,
    calendar_service: GoogleCalendarService = Depends(get_calendar_service)
):
    user = await calendar_service.users_repo.get_user_by_tg_id(tg_id)
    if not user:
        raise HTTPException(status_code=404, detail="User not found")

    has_token = await calendar_service.tokens_repo.token_exists(user.id)

    return UserResponse.model_validate({
        **user.__dict__,
        "has_google_token": has_token
    })

@app.post("/users", response_model=UserResponse)
async def create_user(
    data: UserCreate,
    calendar_service: GoogleCalendarService = Depends(get_calendar_service)
):
    user = await calendar_service.users_repo.add_user(
        tg_id=data.tg_id,
        tg_nick=data.tg_nick,
        email=data.email,
        google_id=data.google_id
    )

    has_token = await calendar_service.tokens_repo.token_exists(user.id)

    return UserResponse.model_validate({
        **user.__dict__,
        "has_google_token": has_token
    })

@app.post("/create_event")
async def create_event(
    data: CreateEventRequest,
    calendar_service: GoogleCalendarService = Depends(get_calendar_service)
):
    tg_id = int(data.user_id)

    if not await calendar_service.load_credentials(tg_id):
        raise HTTPException(status_code=401, detail="Not authorized")

    event = await calendar_service.create_event(
        tg_id=tg_id,
        title=data.title,
        start_time=data.start_time,
        end_time=data.end_time,
        description=data.description,
        location=data.location,
    )

    return {"status": "success", "event": event}


@app.delete("/event/{event_id}")
async def delete_event(
    event_id: str,
    tg_id: int,
    calendar_service: GoogleCalendarService = Depends(get_calendar_service)
):
    if not await calendar_service.load_credentials(tg_id):
        raise HTTPException(status_code=401, detail="Not authorized")

    await calendar_service.delete_event(tg_id, event_id)

    return {"status": "deleted"}

@app.delete("/revoke_access")
async def revoke_access(
    tg_id: int,
    calendar_service: GoogleCalendarService = Depends(get_calendar_service)
):
    success = await calendar_service.revoke_access(tg_id)

    if not success:
        raise HTTPException(status_code=404, detail="User not found")

    return {"status": "revoked"}

@app.get("/success")
async def success_url():
    return {'status': 'Calendar подключен!'}

@app.get("/health")
async def health_check():
    cfg = get_config()
    return {
        "status": "healthy",
        "database": database.db_type,
        "database_initialized": database.is_initialized,
        "config_initialized": cfg.is_initialized
    }


if __name__ == "__main__":
    uvicorn.run(app, host="0.0.0.0", port=8000)
