"""Application configuration."""

import os


class Config:
    """Base configuration."""

    SECRET_KEY = os.environ.get("SECRET_KEY", "dev-secret-change-in-production")

    # PostgreSQL connection
    DB_HOST = os.environ.get("DB_HOST", "localhost")
    DB_PORT = int(os.environ.get("DB_PORT", 5432))
    DB_NAME = os.environ.get("DB_NAME", "hotel_booking")
    DB_USER = os.environ.get("DB_USER", "hotel_user")
    DB_PASSWORD = os.environ.get("DB_PASSWORD", "hotel_pass")

    @property
    def database_url(self) -> str:
        return (
            f"postgresql://{self.DB_USER}:{self.DB_PASSWORD}"
            f"@{self.DB_HOST}:{self.DB_PORT}/{self.DB_NAME}"
        )


class TestConfig(Config):
    """Testing configuration."""

    TESTING = True
    DB_NAME = os.environ.get("DB_NAME", "hotel_booking_test")
