"""Python Strategy Model

Table to store user-created Python strategy scripts with backtest results.
"""

import uuid
from typing import Any, Dict, Optional

from sqlalchemy import JSON, Column, DateTime, Float, Integer, String, Text
from sqlalchemy.sql import func

from .base import Base


class PythonStrategy(Base):
    """User-created Python strategy script with online editing and backtesting."""

    __tablename__ = "python_strategies"

    id = Column(
        String(100),
        primary_key=True,
        default=lambda: "pystrat-" + str(uuid.uuid4()),
    )
    name = Column(String(200), nullable=False, comment="Strategy display name")
    description = Column(Text, nullable=True, comment="Strategy description")
    code = Column(Text, nullable=False, comment="Python strategy source code")
    status = Column(
        String(50),
        nullable=False,
        default="draft",
        comment="Strategy status: draft, backtesting, completed, error",
    )

    # Backtest configuration
    backtest_config = Column(
        JSON,
        nullable=True,
        comment="Backtest parameters (symbols, date range, initial capital, etc.)",
    )

    # Backtest results
    backtest_result = Column(
        JSON,
        nullable=True,
        comment="Backtest result summary (returns, trades, metrics, etc.)",
    )
    backtest_error = Column(
        Text,
        nullable=True,
        comment="Error message if backtest failed",
    )

    created_at = Column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
    updated_at = Column(
        DateTime(timezone=True),
        server_default=func.now(),
        onupdate=func.now(),
        nullable=False,
    )

    def __repr__(self) -> str:
        return f"<PythonStrategy(id={self.id}, name='{self.name}', status='{self.status}')>"

    def to_dict(self) -> Dict[str, Any]:
        return {
            "id": str(self.id),
            "name": self.name,
            "description": self.description,
            "code": self.code,
            "status": self.status,
            "backtest_config": self.backtest_config,
            "backtest_result": self.backtest_result,
            "backtest_error": self.backtest_error,
            "created_at": self.created_at.isoformat() if self.created_at else None,
            "updated_at": self.updated_at.isoformat() if self.updated_at else None,
        }
