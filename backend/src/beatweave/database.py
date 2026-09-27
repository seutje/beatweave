from collections.abc import Iterator
from contextlib import contextmanager
from pathlib import Path

from alembic import command
from alembic.config import Config
from sqlalchemy import Engine, create_engine
from sqlalchemy.orm import Session, sessionmaker


class Database:
    def __init__(self, path: Path) -> None:
        self.path = path
        self.engine: Engine | None = None
        self._session_factory: sessionmaker[Session] | None = None

    def initialize(self) -> None:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self.engine = create_engine(f"sqlite:///{self.path.as_posix()}")
        self._session_factory = sessionmaker(self.engine, expire_on_commit=False)
        config = Config(str(Path(__file__).parents[2] / "alembic.ini"))
        config.set_main_option("sqlalchemy.url", f"sqlite:///{self.path.as_posix()}")
        command.upgrade(config, "head")

    @contextmanager
    def session(self) -> Iterator[Session]:
        if self._session_factory is None:
            raise RuntimeError("Database has not been initialized")
        session = self._session_factory()
        try:
            yield session
            session.commit()
        except Exception:
            session.rollback()
            raise
        finally:
            session.close()

    def close(self) -> None:
        if self.engine is not None:
            self.engine.dispose()
        self.engine = None
        self._session_factory = None
