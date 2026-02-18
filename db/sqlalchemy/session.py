from data import get_config
from sqlalchemy.ext.asyncio import create_async_engine, AsyncSession, async_sessionmaker

DB_CONFIG = get_config().DB_CONFIG

class SQLAlchemyManager:
    def __init__(self):
        self.engine = None
        self.session_maker = None
    
    def init(self):
        if self.engine is not None:
            return  
        
        database_url = DB_CONFIG.url
        
        self.engine = create_async_engine(
            database_url,
            echo=DB_CONFIG.DB_DEBUG,
            pool_pre_ping=True,
            pool_size=5,
            max_overflow=10,
        )
        
        self.session_maker = async_sessionmaker(
            self.engine,
            class_=AsyncSession,
            expire_on_commit=False,
        )
        
        print(f"✅ SQLAlchemy engine initialized")
    
    def get_session(self) -> AsyncSession:
        if self.session_maker is None:
            raise RuntimeError(
                "SQLAlchemy не инициализирована, для начала init()"
            )
        
        return self.session_maker()
    
    async def close(self):
        if self.engine:
            await self.engine.dispose()
            print("✅ SQLAlchemy мотор остановлен")
    
    def get_engine(self):
        if self.engine is None:
            raise RuntimeError(
                "SQLAlchemy не инициализирована, для начала init()"
            )
        return self.engine


# единственный экземпляр менеджера
sqlalchemy_manager = SQLAlchemyManager()