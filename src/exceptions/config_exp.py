class ConfigNotInitializedError(Exception):
    def __init__(self):
        super().__init__(
            "Конфигурация не инициализирована. Вызовите init() перед использованием конфигов."
        )
