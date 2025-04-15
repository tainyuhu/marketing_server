from linebot.v3.messaging import Configuration, ApiClient, MessagingApi, PushMessageRequest, TextMessage
from django.conf import settings

class LineBotApi:
    def __init__(self):
        config = Configuration(access_token=settings.LINE_CHANNEL_ACCESS_TOKEN)
        self.client = ApiClient(configuration=config)
        self.api = MessagingApi(api_client=self.client)

    def push_message(self, line_user_id, message):
        try:
            body = PushMessageRequest(
                to=line_user_id,
                messages=[TextMessage(text=message)]
            )

            self.api.push_message(push_message_request=body)
            return True
        except Exception as e:
            print(f"[ERROR] LINE 推播錯誤: {e}")
            return False
