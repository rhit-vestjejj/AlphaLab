"""SQLite-backed experiment tracking."""

from __future__ import annotations

import json
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path

from sqlalchemy import DateTime, Integer, String, Text, create_engine, select
from sqlalchemy.orm import DeclarativeBase, Mapped, Session, mapped_column, sessionmaker

from alphalab.core.utils.errors import ExperimentStoreError


class Base(DeclarativeBase):
    """SQLAlchemy declarative base."""


class ExperimentORM(Base):
    """ORM model for stored experiments."""

    __tablename__ = "experiments"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    experiment_id: Mapped[str] = mapped_column(String(128), unique=True, index=True, nullable=False)
    timestamp: Mapped[datetime] = mapped_column(DateTime(timezone=True), index=True, nullable=False)
    strategy_name: Mapped[str] = mapped_column(String(255), nullable=False)
    config_yaml: Mapped[str] = mapped_column(Text, nullable=False)
    metrics_json: Mapped[str] = mapped_column(Text, nullable=False)
    artifact_paths_json: Mapped[str] = mapped_column(Text, nullable=False)
    tags_json: Mapped[str] = mapped_column(Text, nullable=False)


@dataclass(frozen=True)
class ExperimentRecord:
    """Read-model for experiment records."""

    experiment_id: str
    timestamp: datetime
    strategy_name: str
    config_yaml: str
    metrics: dict[str, float]
    artifact_paths: list[str]
    tags: list[str]


def _normalize_tags(tags: list[str] | None) -> list[str]:
    """Normalize tags to deterministic sorted unique list."""
    if not tags:
        return []
    normalized = sorted({tag.strip() for tag in tags if tag.strip()})
    return normalized


def _to_record(row: ExperimentORM) -> ExperimentRecord:
    """Convert ORM row to read-model."""
    row_timestamp = row.timestamp
    if row_timestamp.tzinfo is None:
        row_timestamp = row_timestamp.replace(tzinfo=UTC)

    return ExperimentRecord(
        experiment_id=row.experiment_id,
        timestamp=row_timestamp,
        strategy_name=row.strategy_name,
        config_yaml=row.config_yaml,
        metrics=dict(json.loads(row.metrics_json)),
        artifact_paths=list(json.loads(row.artifact_paths_json)),
        tags=list(json.loads(row.tags_json)),
    )


class ExperimentStore:
    """Store and query experiments in a local SQLite database."""

    def __init__(self, db_path: Path) -> None:
        """
        Initialize the experiment store.

        Args:
            db_path: SQLite database file path.
        """
        resolved_path = db_path.expanduser().resolve()
        resolved_path.parent.mkdir(parents=True, exist_ok=True)

        self.db_path = resolved_path
        self._engine = create_engine(f"sqlite+pysqlite:///{self.db_path}", future=True)
        self._session_factory = sessionmaker(
            bind=self._engine, class_=Session, expire_on_commit=False
        )
        try:
            Base.metadata.create_all(self._engine)
        except Exception as exc:
            raise ExperimentStoreError(
                f"Failed to initialize experiment store at {self.db_path}: {exc}"
            ) from exc

    def _session(self) -> Session:
        """Create a new database session."""
        return self._session_factory()

    def next_experiment_id(self, prefix: str = "exp") -> str:
        """
        Generate the next unique experiment id.

        Args:
            prefix: Identifier prefix.

        Returns:
            Unique experiment id string.
        """
        base = f"{prefix}_{datetime.now(tz=UTC).strftime('%Y%m%dT%H%M%S%fZ')}"
        candidate = base
        suffix = 1
        while self.get_experiment(candidate) is not None:
            candidate = f"{base}_{suffix:02d}"
            suffix += 1
        return candidate

    def create_experiment(
        self,
        experiment_id: str,
        strategy_name: str,
        config_yaml: str,
        metrics: dict[str, float],
        artifact_paths: list[str],
        tags: list[str] | None = None,
    ) -> ExperimentRecord:
        """
        Persist a new experiment record.

        Args:
            experiment_id: Unique experiment id.
            strategy_name: Strategy name.
            config_yaml: Serialized run config.
            metrics: Backtest metrics payload.
            artifact_paths: Artifact file paths.
            tags: Optional tags.

        Returns:
            Persisted experiment record.
        """
        normalized_tags = _normalize_tags(tags)
        normalized_artifacts = sorted({str(path) for path in artifact_paths})

        row = ExperimentORM(
            experiment_id=experiment_id,
            timestamp=datetime.now(tz=UTC),
            strategy_name=strategy_name,
            config_yaml=config_yaml,
            metrics_json=json.dumps(metrics, sort_keys=True),
            artifact_paths_json=json.dumps(normalized_artifacts, sort_keys=True),
            tags_json=json.dumps(normalized_tags, sort_keys=True),
        )

        with self._session() as session:
            try:
                session.add(row)
                session.commit()
                session.refresh(row)
                return _to_record(row)
            except Exception as exc:
                session.rollback()
                raise ExperimentStoreError(
                    f"Failed to create experiment '{experiment_id}' in {self.db_path}: {exc}"
                ) from exc

    def get_experiment(self, experiment_id: str) -> ExperimentRecord | None:
        """
        Fetch one experiment by id.

        Args:
            experiment_id: Experiment identifier.

        Returns:
            Experiment record or ``None``.
        """
        with self._session() as session:
            try:
                stmt = select(ExperimentORM).where(ExperimentORM.experiment_id == experiment_id)
                row = session.execute(stmt).scalar_one_or_none()
                return _to_record(row) if row is not None else None
            except Exception as exc:
                raise ExperimentStoreError(
                    f"Failed to load experiment '{experiment_id}' from {self.db_path}: {exc}"
                ) from exc

    def list_experiments(self, limit: int = 100) -> list[ExperimentRecord]:
        """
        List stored experiments in reverse chronological order.

        Args:
            limit: Maximum number of rows.

        Returns:
            Experiment records.
        """
        safe_limit = max(1, limit)
        with self._session() as session:
            try:
                stmt = (
                    select(ExperimentORM)
                    .order_by(ExperimentORM.timestamp.desc(), ExperimentORM.id.desc())
                    .limit(safe_limit)
                )
                rows = session.execute(stmt).scalars().all()
                return [_to_record(row) for row in rows]
            except Exception as exc:
                raise ExperimentStoreError(
                    f"Failed to list experiments from {self.db_path}: {exc}"
                ) from exc

    def append_artifacts(self, experiment_id: str, artifact_paths: list[str]) -> ExperimentRecord:
        """
        Append artifact paths to an existing experiment.

        Args:
            experiment_id: Experiment identifier.
            artifact_paths: Artifact paths to merge.

        Returns:
            Updated experiment record.

        Raises:
            ExperimentStoreError: If experiment id does not exist or update fails.
        """
        with self._session() as session:
            try:
                stmt = select(ExperimentORM).where(ExperimentORM.experiment_id == experiment_id)
                row = session.execute(stmt).scalar_one_or_none()
                if row is None:
                    raise ExperimentStoreError(f"Experiment '{experiment_id}' not found.")

                existing = list(json.loads(row.artifact_paths_json))
                merged = sorted({*existing, *(str(path) for path in artifact_paths)})
                row.artifact_paths_json = json.dumps(merged, sort_keys=True)
                session.commit()
                session.refresh(row)
                return _to_record(row)
            except ExperimentStoreError:
                session.rollback()
                raise
            except Exception as exc:
                session.rollback()
                raise ExperimentStoreError(
                    f"Failed to append artifacts for experiment '{experiment_id}': {exc}"
                ) from exc
