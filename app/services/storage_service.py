from datetime import timedelta
from io import BytesIO
from urllib.parse import urlsplit, urlunsplit
from uuid import uuid4

from minio import Minio
from minio.error import S3Error

from app.core.config import get_settings

settings = get_settings()


class StorageService:
    """Файлы задач хранятся в MinIO, в базе остаются только метаданные."""

    def __init__(self) -> None:
        self.client = Minio(
            settings.minio_endpoint,
            access_key=settings.minio_access_key,
            secret_key=settings.minio_secret_key,
            secure=settings.minio_secure,
        )
        self.bucket = settings.minio_bucket

    def ensure_bucket(self) -> None:
        """Bucket создается при первом обращении, чтобы локальный запуск не требовал ручной настройки MinIO."""
        if not self.client.bucket_exists(self.bucket):
            self.client.make_bucket(self.bucket)

    def upload_bytes(self, *, filename: str, data: bytes, content_type: str | None) -> str:
        """Object key формируется отдельно от имени файла, чтобы избежать конфликтов одинаковых имен."""
        self.ensure_bucket()
        object_key = f"attachments/{uuid4().hex}/{filename}"
        self.client.put_object(
            self.bucket,
            object_key,
            BytesIO(data),
            length=len(data),
            content_type=content_type or "application/octet-stream",
        )
        return object_key

    def get_presigned_download_url(self, object_key: str) -> str:
        """Ссылка выдается временно, прямой доступ к bucket не открывается."""
        self.ensure_bucket()
        url = self.client.presigned_get_object(self.bucket, object_key, expires=timedelta(minutes=15))
        if settings.minio_public_endpoint:
            parsed = urlsplit(url)
            url = urlunsplit((parsed.scheme, settings.minio_public_endpoint, parsed.path, parsed.query, parsed.fragment))
        return url

    def delete_object(self, object_key: str) -> None:
        """Удаление файла выполняется в хранилище, метаданные удаляются отдельно в БД."""
        try:
            self.client.remove_object(self.bucket, object_key)
        except S3Error:
            pass


def get_storage_service() -> StorageService:
    return StorageService()
