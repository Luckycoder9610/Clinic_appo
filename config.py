import os
from pathlib import Path
from dotenv import load_dotenv

BASE_DIR = Path(__file__).resolve().parent
load_dotenv(BASE_DIR / ".env")


def build_database_uri(db_type="mysql", user="root", password="", host="localhost", port="3306", db_name="clinic_db", force_sqlite=False):
    if force_sqlite or db_type == "sqlite":
        sqlite_path = BASE_DIR / "clinic.db"
        return f"sqlite:///{sqlite_path.as_posix()}"
    
    password_part = f":{password}" if password else ""
    return f"mysql+pymysql://{user}{password_part}@{host}:{port}/{db_name}?charset=utf8mb4"


class Config:
    SECRET_KEY = os.getenv("SECRET_KEY", "clinic-secret-key-change-in-production")
    
    # Cancellation policy defaults
    DEFAULT_CUTOFF_HOURS = float(os.getenv("CANCELLATION_CUTOFF_HOURS", 24))
    DEFAULT_LATE_FEE = float(os.getenv("LATE_CANCELLATION_FEE", 25.00))
    
    # Database config
    DB_TYPE = os.getenv("DB_TYPE", "mysql").lower()
    DB_USER = os.getenv("DB_USER", "root")
    DB_PASSWORD = os.getenv("DB_PASSWORD", "")
    DB_HOST = os.getenv("DB_HOST", "localhost")
    DB_PORT = os.getenv("DB_PORT", "3306")
    DB_NAME = os.getenv("DB_NAME", "clinic_db")
    
    SQLALCHEMY_DATABASE_URI = build_database_uri(
        db_type=DB_TYPE,
        user=DB_USER,
        password=DB_PASSWORD,
        host=DB_HOST,
        port=DB_PORT,
        db_name=DB_NAME,
    )
    SQLALCHEMY_TRACK_MODIFICATIONS = False
    SQLALCHEMY_ENGINE_OPTIONS = {
        "pool_recycle": 280,
        "pool_pre_ping": True,
    }

    @staticmethod
    def get_database_uri(force_sqlite=False):
        return build_database_uri(
            db_type=Config.DB_TYPE,
            user=Config.DB_USER,
            password=Config.DB_PASSWORD,
            host=Config.DB_HOST,
            port=Config.DB_PORT,
            db_name=Config.DB_NAME,
            force_sqlite=force_sqlite,
        )


class TestConfig(Config):
    TESTING = True
    DB_TYPE = "sqlite"
    SQLALCHEMY_DATABASE_URI = "sqlite:///:memory:"
    DEFAULT_CUTOFF_HOURS = 24.0
    DEFAULT_LATE_FEE = 25.00
    SQLALCHEMY_ENGINE_OPTIONS = {}
