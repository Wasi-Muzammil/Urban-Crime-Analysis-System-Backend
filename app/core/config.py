from dotenv import load_dotenv
import os

load_dotenv()

# Database
DB_HOST     = os.getenv("DB_HOST", "localhost")
DB_PORT     = int(os.getenv("DB_PORT", 3306))
DB_USER     = os.getenv("DB_USER", "root")
DB_PASSWORD = os.getenv("DB_PASSWORD", "")
DB_NAME     = os.getenv("DB_NAME", "urban_crime_db")

# JWT
SECRET_KEY         = os.getenv("SECRET_KEY", "change-this-in-production")
ALGORITHM          = "HS256"
JWT_EXPIRE_MINUTES = 60 * 24  # 1 day

# Google OAuth
GOOGLE_CLIENT_ID     = os.getenv("GOOGLE_CLIENT_ID")
GOOGLE_CLIENT_SECRET = os.getenv("GOOGLE_CLIENT_SECRET")
GOOGLE_REDIRECT_URI  = os.getenv("GOOGLE_REDIRECT_URI")

# App
FRONTEND_URL = os.getenv("FRONTEND_URL", "http://localhost:3000")
