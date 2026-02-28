from threading import Lock

class SingletonLockMeta(type):
    _instances = {}

    def __call__(cls, *args, **kwargs):
        if cls not in cls._instances:
            with Lock():
                if cls not in cls._instances:
                    cls._instances[cls] = super().__call__(*args, **kwargs)
        return cls._instances[cls]
    

class AgentsFactoryMeta(type):
    _instances: dict = {}

    def __call__(cls, *args, tg_id: int | str | None = None, **kwargs):
        key = (cls, tg_id)
        if key not in cls._instances:
            instance = super().__call__(*args, tg_id=tg_id, **kwargs)
            cls._instances[key] = instance
        return cls._instances[key]

    def reset(cls, tg_id: int | str | None = None):
        if tg_id is None:
            cls._instances.clear()
        else:
            cls._instances.pop((cls, tg_id), None)