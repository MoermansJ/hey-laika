"""SQLAlchemy models for the Bittle AI Companion."""
from datetime import datetime, timezone

from sqlalchemy import ForeignKey, String, Text, create_engine
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column, sessionmaker

from app.config import Config


def utcnow() -> datetime:
    return datetime.now(timezone.utc)


def iso_utc(moment: datetime | None) -> str | None:
    """ISO-8601 with an explicit offset. SQLite hands naive datetimes back
    for the UTC values written by utcnow(); without the offset a browser
    would read them as local time."""
    if moment is None:
        return None
    if moment.tzinfo is None:
        moment = moment.replace(tzinfo=timezone.utc)
    return moment.isoformat()


class Base(DeclarativeBase):
    pass


class Setting(Base):
    __tablename__ = "settings"

    key: Mapped[str] = mapped_column(String(64), primary_key=True)
    value: Mapped[str] = mapped_column(Text, default="{}")


class Robot(Base):
    __tablename__ = "robots"

    id: Mapped[int] = mapped_column(primary_key=True)
    name: Mapped[str] = mapped_column(String(64), default="Bittle")
    robot_type: Mapped[str] = mapped_column(String(64), default="bittle_x_v2")
    created_at: Mapped[datetime] = mapped_column(default=utcnow)


class Personality(Base):
    __tablename__ = "personalities"

    id: Mapped[int] = mapped_column(primary_key=True)
    robot_id: Mapped[int] = mapped_column(ForeignKey("robots.id"))
    energy: Mapped[float] = mapped_column(default=100.0)
    happiness: Mapped[float] = mapped_column(default=50.0)
    boredom: Mapped[float] = mapped_column(default=0.0)
    curiosity: Mapped[float] = mapped_column(default=50.0)
    mood: Mapped[str] = mapped_column(String(32), default="neutral")
    updated_at: Mapped[datetime] = mapped_column(default=utcnow, onupdate=utcnow)


class Interaction(Base):
    __tablename__ = "interactions"

    id: Mapped[int] = mapped_column(primary_key=True)
    robot_id: Mapped[int] = mapped_column(ForeignKey("robots.id"))
    interaction_type: Mapped[str] = mapped_column(String(32))  # pet, play, talk, feed
    created_at: Mapped[datetime] = mapped_column(default=utcnow)


class BehaviorLog(Base):
    __tablename__ = "behavior_logs"

    id: Mapped[int] = mapped_column(primary_key=True)
    robot_id: Mapped[int] = mapped_column(ForeignKey("robots.id"))
    behavior: Mapped[str] = mapped_column(String(64))
    reason: Mapped[str] = mapped_column(Text, default="")
    source: Mapped[str] = mapped_column(String(16), default="mock")  # claude | mock | manual
    created_at: Mapped[datetime] = mapped_column(default=utcnow)


class ConversationMessage(Base):
    __tablename__ = "conversation_messages"

    id: Mapped[int] = mapped_column(primary_key=True)
    robot_id: Mapped[int] = mapped_column(ForeignKey("robots.id"))
    role: Mapped[str] = mapped_column(String(16))  # user | assistant
    content: Mapped[str] = mapped_column(Text)
    created_at: Mapped[datetime] = mapped_column(default=utcnow)


class ChoreographyEntry(Base):
    __tablename__ = "choreography_library"

    id: Mapped[int] = mapped_column(primary_key=True)
    robot_type: Mapped[str] = mapped_column(String(64), default="bittle_x_v2")
    name: Mapped[str] = mapped_column(String(64))
    command_sequence: Mapped[str] = mapped_column(Text)  # JSON-encoded frames


class SystemConfiguration(Base):
    __tablename__ = "system_configuration"

    id: Mapped[int] = mapped_column(primary_key=True)
    key: Mapped[str] = mapped_column(String(64), unique=True)
    value: Mapped[str] = mapped_column(Text)


_IS_SQLITE = Config.sqlalchemy_url().startswith("sqlite")
# ~9 threads write this file (arbiter run log, metrics flush, sniffer, power
# tracker, request threads). A 30 s busy timeout plus WAL keeps readers
# from tripping over writers with "database is locked".
engine = create_engine(
    Config.sqlalchemy_url(),
    connect_args={"check_same_thread": False, "timeout": 30} if _IS_SQLITE else {})
SessionLocal = sessionmaker(bind=engine, expire_on_commit=False)

if _IS_SQLITE:
    from sqlalchemy import event

    @event.listens_for(engine, "connect")
    def _sqlite_pragmas(dbapi_connection, _record):
        cursor = dbapi_connection.cursor()
        cursor.execute("PRAGMA journal_mode=WAL")
        cursor.execute("PRAGMA busy_timeout=30000")
        cursor.close()


def init_db() -> None:
    """Create tables and ensure a default robot + personality row exist."""
    Base.metadata.create_all(engine)
    with SessionLocal() as session:
        robot = session.query(Robot).first()
        if robot is None:
            robot = Robot(name="Bittle")
            session.add(robot)
            session.flush()
            session.add(Personality(robot_id=robot.id))
            session.commit()
