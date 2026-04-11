from src.enum import DatabaseType
from sqlalchemy.ext.asyncio import create_async_engine, AsyncSession, async_sessionmaker

class SQLAlchemyManager:
    def __init__(self):
        self.engine = None
        self.session_maker = None
    
    def init(self):
        if self.engine is not None:
            return

        from data import get_config
        cfg = get_config().DB_CONFIG

        engine_kwargs = {
            "echo": cfg.DB_DEBUG,
            "pool_pre_ping": True,
        }

        if cfg.DB_TYPE != DatabaseType.SQLITE:
            engine_kwargs["pool_size"] = 5
            engine_kwargs["max_overflow"] = 10

        self.engine = create_async_engine(cfg.url, **engine_kwargs)
        self.session_maker = async_sessionmaker(
            self.engine,
            class_=AsyncSession,
            expire_on_commit=False,
        )
        
    def get_session(self) -> AsyncSession:
        if self.session_maker is None:
            raise RuntimeError(
                "SQLAlchemy is not initialized, use init() to start"
            )
        
        return self.session_maker()
    
    async def close(self):
        if self.engine:
            await self.engine.dispose()
            print("✅ SQLAlchemy мотор остановлен")
    
    def get_engine(self):
        if self.engine is None:
            raise RuntimeError(
                "SQLAlchemy is not initialized, use init() to start"
            )
        return self.engine


# the only instance of the manager
sqlalchemy_manager = SQLAlchemyManager()