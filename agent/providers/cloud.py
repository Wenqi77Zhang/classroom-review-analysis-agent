"""公开课堂的云模型 Provider；凭据只能由后端配置传入。"""

from urllib.parse import urlparse

from agent.providers.base import OpenAICompatibleProvider


class CloudModelProvider(OpenAICompatibleProvider):
    def __init__(
        self,
        *,
        endpoint: str,
        model: str,
        api_key: str,
        timeout_seconds: float = 60.0,
    ) -> None:
        parsed = urlparse(endpoint)
        if parsed.scheme != "https" or not parsed.hostname:
            raise ValueError("云模型 endpoint 必须是有效的 HTTPS 地址。")
        if not api_key:
            raise ValueError("云模型 api_key 不能为空，且不得从前端请求读取。")
        super().__init__(
            endpoint=endpoint,
            model=model,
            api_key=api_key,
            timeout_seconds=timeout_seconds,
        )
