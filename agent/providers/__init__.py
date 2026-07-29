"""模型 Provider 与隐私路由。"""

from agent.providers.base import ModelProvider
from backend.app.schemas.task import PrivacyMode


class ProviderNotConfiguredError(RuntimeError):
    pass


class ProviderRouter:
    def __init__(
        self,
        *,
        local: ModelProvider | None = None,
        cloud: ModelProvider | None = None,
    ) -> None:
        self._providers = {PrivacyMode.LOCAL: local, PrivacyMode.CLOUD: cloud}

    def select(self, privacy_mode: PrivacyMode) -> ModelProvider:
        provider = self._providers[privacy_mode]
        if provider is None:
            raise ProviderNotConfiguredError(
                f"privacy_mode={privacy_mode} 对应的模型 Provider 尚未配置。"
            )
        return provider
