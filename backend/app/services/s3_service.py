"""
Сервис для работы с S3 (TimeWeb Object Storage).
Используем синхронный boto3 + asyncio.to_thread для асинхронного интерфейса.
"""
import logging
import asyncio
from typing import Optional
import boto3
from botocore.exceptions import ClientError

from app.config import (
    S3_ENDPOINT_URL,
    S3_ACCESS_KEY,
    S3_SECRET_KEY,
    S3_BUCKET_NAME,
    S3_REGION,
)

logger = logging.getLogger(__name__)


class S3Service:
    """Сервис для работы с S3 с асинхронным интерфейсом."""
    
    def __init__(self):
        # Синхронный клиент — создаём один раз
        self.client = boto3.client(
            's3',
            endpoint_url=S3_ENDPOINT_URL,
            aws_access_key_id=S3_ACCESS_KEY,
            aws_secret_access_key=S3_SECRET_KEY,
            region_name=S3_REGION,
        )
        self.bucket = S3_BUCKET_NAME
    
    async def upload_file(
        self,
        file_path: str,
        s3_key: str,
        content_type: Optional[str] = None,
    ) -> str:
        """Загрузить файл в S3 (асинхронно через to_thread)."""
        try:
            extra_args = {}
            if content_type:
                extra_args['ContentType'] = content_type
            
            # Оборачиваем синхронный вызов в asyncio
            await asyncio.to_thread(
                self.client.upload_file,
                Filename=file_path,
                Bucket=self.bucket,
                Key=s3_key,
                ExtraArgs=extra_args,
            )
            
            logger.info(f"✅ Файл загружен в S3: {s3_key}")
            return s3_key
            
        except ClientError as e:
            logger.error(f"❌ Ошибка загрузки в S3: {e}")
            raise
        except Exception as e:
            logger.error(f"❌ Неожиданная ошибка S3: {e}")
            raise
    
    async def get_presigned_url(
        self,
        s3_key: str,
        expiration: int = 3600,
    ) -> str:
        """Получить временную ссылку для скачивания."""
        try:
            # generate_presigned_url — быстрая операция, можно без to_thread
            url = self.client.generate_presigned_url(
                'get_object',
                Params={'Bucket': self.bucket, 'Key': s3_key},
                ExpiresIn=expiration,
            )
            return url
        except Exception as e:
            logger.error(f"❌ Ошибка генерации presigned URL: {e}")
            raise
    
    async def delete_file(self, s3_key: str) -> bool:
        """Удалить файл из S3."""
        try:
            await asyncio.to_thread(
                self.client.delete_object,
                Bucket=self.bucket,
                Key=s3_key,
            )
            logger.info(f"✅ Файл удалён из S3: {s3_key}")
            return True
        except Exception as e:
            logger.error(f"❌ Ошибка удаления из S3: {e}")
            return False
    
    async def file_exists(self, s3_key: str) -> bool:
        """Проверить существование файла."""
        try:
            await asyncio.to_thread(
                self.client.head_object,
                Bucket=self.bucket,
                Key=s3_key,
            )
            return True
        except ClientError:
            return False
        except Exception as e:
            logger.error(f"❌ Ошибка проверки файла: {e}")
            return False


# Глобальный экземпляр
s3_service = S3Service()