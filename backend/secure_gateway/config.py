from __future__ import annotations
from pathlib import Path

CA_SERVICE_URL = "http://127.0.0.1:8011"
CORE_SYSTEM_URL = "http://127.0.0.1:8000"

JWT_SECRET = "CHANGE_ME_IN_PROD__use_env_var"
JWT_ALG = "HS256"
JWT_TTL_SECONDS = 3 * 60 * 60  # 3 hours

INITIAL_TRUST_SCORE = 90.0
TRUST_WINDOW_SECONDS = 5 * 60
TRUST_MIN = 0.0
TRUST_MAX = 100.0

ACTIVE_THRESHOLD = 70.0
RESTRICTED_THRESHOLD = 40.0

STRICT_CORE_AUTH = False

BASE_DIR = Path(__file__).resolve().parent
ROOT_CA_CACHE_PATH = BASE_DIR / "root_ca_cert.pem"
DB_PATH = BASE_DIR / "gateway.db"