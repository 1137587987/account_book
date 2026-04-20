import json
import lark_oapi as lark
from lark_oapi.api.im.v1 import CreateMessageRequest, CreateMessageRequestBody

from app.config import settings

_client: lark.Client | None = None


def get_feishu_client() -> lark.Client:
    global _client
    if _client is None:
        _client = (
            lark.Client.builder()
            .app_id(settings.FEISHU_APP_ID)
            .app_secret(settings.FEISHU_APP_SECRET)
            .build()
        )
    return _client


async def send_text(open_id: str, text: str) -> None:
    client = get_feishu_client()
    request = (
        CreateMessageRequest.builder()
        .receive_id_type("open_id")
        .request_body(
            CreateMessageRequestBody.builder()
            .receive_id(open_id)
            .msg_type("text")
            .content(json.dumps({"text": text}))
            .build()
        )
        .build()
    )
    await client.im.v1.message.acreate(request)
