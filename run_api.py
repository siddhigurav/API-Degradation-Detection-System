import uvicorn
from src.config import HOST, PORT, LOG_LEVEL
from src.alerter import app


def main():
    print("Starting alerting API server")
    uvicorn.run(app, host=HOST, port=PORT, log_level=LOG_LEVEL.lower())


if __name__ == '__main__':
    main()