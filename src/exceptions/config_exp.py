class ConfigNotInitializedError(Exception):
    def __init__(self):
        super().__init__(
           "The configuration is not initialized. Call init() before using the configs."
        )
