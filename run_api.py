import uvicorn
from src.config import settings
from src.alerter import app


def main():
    print("Starting alerting API server")
    uvicorn.run(app, host=settings.HOST, port=settings.PORT, log_level=settings.LOG_LEVEL.lower())


if __name__ == '__main__':
    main()