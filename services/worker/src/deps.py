"""Deps bundles the collaborators every step handler needs: gRPC clients,
object storage, and local admission limits. Built once in main.py."""

from __future__ import annotations

from dataclasses import dataclass

from clients.content_client import ContentClient
from clients.media_client import MediaClient
from clients.objectstore import ObjectStore
from limits import Limits


@dataclass
class Deps:
    media: MediaClient
    content: ContentClient
    objects: ObjectStore
    limits: Limits
    gemini_model: str
    tts_voice: str
