"""私有课堂的本地模型 Provider；拒绝把私有内容路由到远程主机。"""

from ipaddress import ip_address
from urllib.parse import urlparse

from agent.providers.base import OpenAICompatibleProvider


def _is_loopback(hostname: str | None) -> bool:
    if hostname == "localhost":
        return True
    if hostname is None:
        return False
    try:
        return ip_address(hostname).is_loopback
    except ValueError:
        return False


class LocalModelProvider(OpenAICompatibleProvider):
    def __init__(
        self,
        *,
        endpoint: str,
        model: str,
        timeout_seconds: float = 120.0,
    ) -> None:
        parsed = urlparse(endpoint)
        if parsed.scheme not in {"http", "https"} or not _is_loopback(parsed.hostname):
            raise ValueError("本地模型 endpoint 必须指向 localhost 或 loopback 地址。")
        super().__init__(
            endpoint=endpoint,
            model=model,
            api_key=None,
            timeout_seconds=timeout_seconds,
        )
