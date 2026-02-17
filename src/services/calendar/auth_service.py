import logging
from google_auth_oauthlib.flow import Flow
from utils.const import SCOPES, REDIRECT_URI

from db.database_protocol import UsersBase
from src.services.calendar.token_service import TokenService
from src.services.calendar.creds_manager import CredentialsManager

class GoogleAuthService:
    def __init__(self, users_repo: UsersBase, token_service: TokenService,
                 credentials_manager: CredentialsManager, client_id: str, client_secret: str):
        self.users_repo = users_repo
        self.token_service = token_service
        self.credentials_manager = credentials_manager
        self.client_id = client_id
        self.client_secret = client_secret
        self.logger = logging.getLogger(self.__class__.__name__)

    def _get_flow(self) -> Flow:
        return Flow.from_client_config(
            {
                "web": {
                    "client_id": self.client_id,
                    "client_secret": self.client_secret,
                    "auth_uri": "https://accounts.google.com/o/oauth2/auth",
                    "token_uri": "https://oauth2.googleapis.com/token",
                    "redirect_uris": [REDIRECT_URI]
                }
            },
            scopes=SCOPES,
            redirect_uri=REDIRECT_URI
        )

    async def get_auth_url(self, tg_id: int) -> str:
        if not await self.users_repo.user_exists(tg_id=tg_id):
            await self.users_repo.add_user(tg_id)

        flow = self._get_flow()
        auth_url, state = flow.authorization_url(access_type="offline", prompt="consent")
        await self.users_repo.update_user(tg_id, google_id=state)

        self.logger.info(f"Generated auth URL for tg_id={tg_id}")
        return auth_url

    async def exchange_code(self, tg_id: int, code: str) -> bool:
        user = await self.users_repo.get_user_by_tg_id(tg_id)
        if not user:
            raise ValueError("Пользователь не найден")

        flow = self._get_flow()
        await self.credentials_manager._run_sync(flow.fetch_token, code=code)
        credentials = flow.credentials

        await self.token_service.save_token(
            user_id=user.id,
            access_token=credentials.token,
            refresh_token=credentials.refresh_token,
            expiry=credentials.expiry,
            scopes=SCOPES,
        )

        self.logger.info(f"Exchanged code for tg_id={tg_id}")
        return True

    async def revoke_access(self, tg_id: int) -> bool:
        user = await self.users_repo.get_user_by_tg_id(tg_id)
        if not user:
            return False

        await self.token_service.delete_token(user.id)
        self.logger.info(f"Revoked access for tg_id={tg_id}")
        return True

    async def is_authorized(self, tg_id: int) -> bool:
        user = await self.users_repo.get_user_by_tg_id(tg_id)
        if not user:
            return False
        return await self.token_service.token_exists(user.id)