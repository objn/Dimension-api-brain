import uvicorn
import locale
import sys
import os

os.environ['PYTHONUTF8'] = '1'
try:
    locale.setlocale(locale.LC_ALL, 'en_US.UTF-8')
except:
    try:
        locale.setlocale(locale.LC_ALL, '')
    except:
        pass

from src.config import settings

if __name__ == "__main__":
    is_development = settings.environment.lower() == "development"

    print(f"Starting server in {settings.environment.upper()} mode")
    print(f"Auto-reload: {'enabled' if is_development else 'disabled'}")
    print(f"Server: http://{settings.host}:{settings.port}")

    uvicorn.run(
        "src.main:app",
        host=settings.host,
        port=settings.port,
        reload=is_development,
        log_level="info"
    )
