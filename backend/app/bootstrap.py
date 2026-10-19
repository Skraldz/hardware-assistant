"""Create database tables if they do not exist yet.

Kept separate from app.main so importing the FastAPI app (e.g. in tests) never
touches the real database. Run explicitly before starting the API.
"""

from app import models  # noqa: F401  registers models on Base.metadata
from app.db import Base, engine


def main() -> None:
    Base.metadata.create_all(bind=engine)


if __name__ == "__main__":
    main()
