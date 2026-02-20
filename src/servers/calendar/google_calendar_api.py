from fastapi import APIRouter, Request, HTTPException, Depends
from fastapi.responses import RedirectResponse

from src.services.calendar.google_calendar import GoogleCalendarService
from src.models import UserCreate, UserResponse, CreateEventRequest, EventsResponse, status
from src.servers.calendar.dependencies import get_calendar_service, get_tokens_repo, get_users_repo

from db.database_protocol import UsersBase, GoogleTokensBase

router = APIRouter(prefix="/calendar", tags=["calendar"])

@router.get("/auth_url")
async def auth_url(
    tg_id: int,
    calendar: GoogleCalendarService = Depends(get_calendar_service)
):
    try:
        url = await calendar.get_auth_url(tg_id)
        return {"auth_url": url}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/oauth/callback")
async def oauth_callback(
    request: Request,
    users_repo: UsersBase = Depends(get_users_repo),
    calendar: GoogleCalendarService = Depends(get_calendar_service)
):
    code = request.query_params.get("code")
    state = request.query_params.get("state")

    if not code or not state:
        raise HTTPException(status_code=400, detail="Invalid OAuth callback")

    user = await users_repo.get_user_by_google_id(state)
    if not user:
        raise HTTPException(status_code=400, detail="Invalid state")

    await calendar.exchange_code(user.tg_id, code)
    return RedirectResponse(url="/calendar/success")


@router.delete("/revoke_access")
async def revoke_access(
    tg_id: int,
    calendar: GoogleCalendarService = Depends(get_calendar_service)
):
    success = await calendar.revoke_access(tg_id)
    if not success:
        raise HTTPException(status_code=404, detail="User not found")
    return await status('revoked')


@router.get("/users/{tg_id}", response_model=UserResponse)
async def get_user(
    tg_id: int,
    users_repo: UsersBase = Depends(get_users_repo),
    tokens_repo: GoogleTokensBase = Depends(get_tokens_repo)
):
    user = await users_repo.get_user_by_tg_id(tg_id)
    if not user:
        raise HTTPException(status_code=404, detail="User not found")

    has_token = await tokens_repo.token_exists(user.id)
    return UserResponse.model_validate({**user.model_dump(), "has_google_token": has_token})


@router.post("/users", response_model=UserResponse)
async def create_user(
    data: UserCreate,
    users_repo: UsersBase = Depends(get_users_repo),
    tokens_repo: GoogleTokensBase = Depends(get_tokens_repo)
):
    user = await users_repo.add_user(
        tg_id=data.tg_id,
        tg_nick=data.tg_nick,
        email=data.email,
        google_id=data.google_id
    )
    if not user:
        raise HTTPException(status_code=500, detail="Failed to create user")

    has_token = await tokens_repo.token_exists(user.id)
    return UserResponse.model_validate({**user.model_dump(), "has_google_token": has_token})


@router.get("/events", response_model=EventsResponse, response_model_exclude_none=True)
async def get_events(
    tg_id: int,
    calendar: GoogleCalendarService = Depends(get_calendar_service)
):
    try:
        if not await calendar.load_credentials(tg_id):
            raise HTTPException(status_code=401, detail="Not authorized")

        events = await calendar.get_events(tg_id)
    except TimeoutError:
        raise HTTPException(status_code=408, detail="Request timeout")
    return EventsResponse(events=events)


@router.post("/create_event")
async def create_event(
    data: CreateEventRequest,
    calendar: GoogleCalendarService = Depends(get_calendar_service)
):
    tg_id = int(data.user_id)
    if not await calendar.load_credentials(tg_id):
        raise HTTPException(status_code=401, detail="Not authorized")

    event = await calendar.create_event(
        tg_id=tg_id,
        title=data.title,
        start_time=data.start_time,
        end_time=data.end_time,
        description=data.description,
        location=data.location,
    )
    return await status('success')  # TODO: добавить event в ответ когда будет готов метод


@router.delete("/event/{event_id}")
async def delete_event(
    event_id: str,
    tg_id: int,
    calendar: GoogleCalendarService = Depends(get_calendar_service)
):
    if not await calendar.load_credentials(tg_id):
        raise HTTPException(status_code=401, detail="Not authorized")

    await calendar.delete_event(tg_id, event_id)  # TODO
    return await status('deleted')


@router.get("/success")
async def success_url():
    return await status('Calendar подключен!')