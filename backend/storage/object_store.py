"""storage/object_store.py —— 对象存储抽象（P0 基础设施，P2 生图/上传统一入口）。

设计要点：
- 抽象基类 ObjectStore：put/get/delete/url 四方法，上层（生图落盘、上传托管）只依赖此接口，
  切换 local ↔ s3 ↔ oss 时业务代码零改动（契约见 build_object_store）。
- LocalStore：沿用当前本地磁盘行为（data/generated、data/uploads + 静态托管），dev 默认。
- S3Store / OSSStore：S3 兼容 / 阿里云 OSS 实现，懒加载 SDK（未安装不 import 报错），
  返回 CDN_URL 或对象存储访问域名。
- 默认命名空间（namespace）映射到现有目录与 URL 前缀，保证 LocalStore 与现状一致：
  - "generated" → data/generated，URL 前缀 /generated
  - "uploads"   → data/uploads，  URL 前缀 /uploads
"""
from __future__ import annotations

import logging
from abc import ABC, abstractmethod
from pathlib import Path

from backend.config import settings

logger = logging.getLogger('object_store')
_NAMESPACES = {'generated': ('generated', '/generated'), 'uploads': ('uploads', '/uploads')}

class ObjectStore(ABC):
    """对象存储抽象。key 为相对路径（如 plan_P001.png / shops/S001/cover.jpg）。"""

    @abstractmethod
    def put(self, key: str, data: bytes, *, namespace: str='uploads') -> str:
        """写入对象，返回可访问 URL。"""

    @abstractmethod
    def get(self, key: str, *, namespace: str='uploads') -> bytes | None:
        """读取对象，不存在返回 None。"""

    @abstractmethod
    def delete(self, key: str, *, namespace: str='uploads') -> None:
        """删除对象（不存在静默忽略）。"""

    @abstractmethod
    def url(self, key: str, *, namespace: str='uploads') -> str:
        """返回对象的访问 URL（不保证已存在）。"""

class LocalStore(ObjectStore):
    """本地磁盘实现，沿用现有静态托管约定。

    每个 namespace 直接映射到配置目录（generated_dir / upload_dir），
    与改造前的「settings.generated_dir / 文件名」行为完全一致；
    目录在请求时按需解析，支持测试中对 settings 的 monkeypatch 即时生效。
    """

    def _base(self, namespace: str) -> Path:
        if namespace == 'uploads':
            return Path(getattr(settings, 'upload_dir', 'data/uploads'))
        return Path(settings.generated_dir)

    def _path(self, key: str, namespace: str) -> Path:
        return self._base(namespace) / key

    def put(self, key: str, data: bytes, *, namespace: str='uploads') -> str:
        path = self._path(key, namespace)
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(data)
        return self.url(key, namespace=namespace)

    def get(self, key: str, *, namespace: str='uploads') -> bytes | None:
        path = self._path(key, namespace)
        return path.read_bytes() if path.exists() else None

    def delete(self, key: str, *, namespace: str='uploads') -> None:
        path = self._path(key, namespace)
        if path.exists():
            try:
                path.unlink()
            except OSError as exc:
                logger.warning('删除本地对象失败 %s: %s', path, exc)

    def url(self, key: str, *, namespace: str='uploads') -> str:
        _, prefix = _NAMESPACES.get(namespace, (namespace, f'/{namespace}'))
        return f'{prefix}/{key}'

class S3Store(ObjectStore):
    """S3 兼容对象存储（AWS S3 / 腾讯云 COS / MinIO 等）。

    SDK 懒加载：仅在实际使用时 import boto3，未安装不影响模块导入与 local 模式。
    """

    def __init__(self) -> None:
        if not settings.storage_bucket:
            raise ValueError('storage_bucket 未配置，无法使用 S3Store')
        import boto3
        self.bucket = settings.storage_bucket
        self.cdn_base = settings.storage_cdn_base.rstrip('/') if settings.storage_cdn_base else ''
        self.client = boto3.client('s3', endpoint_url=settings.storage_endpoint or None, region_name=settings.storage_region or None, aws_access_key_id=settings.storage_access_key or None, aws_secret_access_key=settings.storage_secret_key or None)

    def _obj(self, key: str, namespace: str) -> str:
        return f'{namespace}/{key}'

    def put(self, key: str, data: bytes, *, namespace: str='uploads') -> str:
        self.client.put_object(Bucket=self.bucket, Key=self._obj(key, namespace), Body=data)
        return self.url(key, namespace=namespace)

    def get(self, key: str, *, namespace: str='uploads') -> bytes | None:
        from botocore.exceptions import ClientError
        try:
            resp = self.client.get_object(Bucket=self.bucket, Key=self._obj(key, namespace))
            return resp['Body'].read()
        except ClientError:
            return None

    def delete(self, key: str, *, namespace: str='uploads') -> None:
        self.client.delete_object(Bucket=self.bucket, Key=self._obj(key, namespace))

    def url(self, key: str, *, namespace: str='uploads') -> str:
        if self.cdn_base:
            return f'{self.cdn_base}/{namespace}/{key}'
        return f'{settings.storage_endpoint}/{self.bucket}/{namespace}/{key}'

class OSSStore(ObjectStore):
    """阿里云 OSS 实现（SDK 懒加载，未安装不影响模块导入）。"""

    def __init__(self) -> None:
        if not settings.storage_bucket:
            raise ValueError('storage_bucket 未配置，无法使用 OSSStore')
        import oss2
        self.bucket_name = settings.storage_bucket
        self.cdn_base = settings.storage_cdn_base.rstrip('/') if settings.storage_cdn_base else ''
        auth = oss2.Auth(settings.storage_access_key, settings.storage_secret_key)
        self.bucket = oss2.Bucket(auth, settings.storage_endpoint or 'https://oss-cn-hangzhou.aliyuncs.com', self.bucket_name)

    def _obj(self, key: str, namespace: str) -> str:
        return f'{namespace}/{key}'

    def put(self, key: str, data: bytes, *, namespace: str='uploads') -> str:
        self.bucket.put_object(self._obj(key, namespace), data)
        return self.url(key, namespace=namespace)

    def get(self, key: str, *, namespace: str='uploads') -> bytes | None:
        import oss2
        try:
            return self.bucket.get_object(self._obj(key, namespace)).read()
        except oss2.exceptions.NoSuchKey:
            return None

    def delete(self, key: str, *, namespace: str='uploads') -> None:
        self.bucket.delete_object(self._obj(key, namespace))

    def url(self, key: str, *, namespace: str='uploads') -> str:
        if self.cdn_base:
            return f'{self.cdn_base}/{namespace}/{key}'
        return f'https://{self.bucket_name}.{settings.storage_endpoint}/{namespace}/{key}'

def build_object_store() -> ObjectStore:
    """按 storage_backend 装配存储后端；默认 local（dev/test 零配置）。"""
    backend = (settings.storage_backend or 'local').lower()
    if backend == 's3':
        logger.info('对象存储装配: S3Store -> %s', settings.storage_bucket)
        return S3Store()
    if backend == 'oss':
        logger.info('对象存储装配: OSSStore -> %s', settings.storage_bucket)
        return OSSStore()
    logger.info('对象存储装配: LocalStore（dev 默认）')
    return LocalStore()
_store: ObjectStore | None = None

def get_object_store() -> ObjectStore:
    """获取对象存储单例。"""
    global _store
    if _store is None:
        _store = build_object_store()
    return _store

def save_generated(key: str, data: bytes) -> str:
    """生图产物落盘，返回可访问 URL（namespace=generated）。"""
    return get_object_store().put(key, data, namespace='generated')

def save_upload(key: str, data: bytes) -> str:
    """商家上传图片落盘，返回可访问 URL（namespace=uploads）。"""
    return get_object_store().put(key, data, namespace='uploads')

def read_generated(key: str) -> bytes | None:
    """读取生图产物（namespace=generated），不存在返回 None。"""
    return get_object_store().get(key, namespace='generated')

def read_upload(key: str) -> bytes | None:
    """读取上传图片（namespace=uploads），不存在返回 None。"""
    return get_object_store().get(key, namespace='uploads')
