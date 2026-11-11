"""嵌入式设备登记。"""

from datetime import datetime

from sqlalchemy import BigInteger, DateTime, String
from sqlalchemy.orm import Mapped, mapped_column

from app.models.base import Base


class DeviceRegistration(Base):
    __tablename__ = "device_registration"

    device_id: Mapped[str] = mapped_column(String(64), primary_key=True)
    secret_digest: Mapped[str] = mapped_column(String(64), nullable=False)
    verification_code: Mapped[str] = mapped_column(String(8), nullable=False)
    requested_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    approved_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    approved_by: Mapped[int | None] = mapped_column(BigInteger)
