"""Closed provider registry; no client-controlled endpoints or scopes."""

PROVIDERS = {
    "gmail": {
        "id": "gmail",
        "name": "Gmail",
        "summary": "让邮件里的安排和线索，有迹可循。",
        "transport": "oauth",
        "platforms": ["web", "ios"],
        "permissions": ["读取最近收件箱及后续变化", "不发送、修改或删除邮件"],
        "scope": "https://www.googleapis.com/auth/gmail.readonly",
        "authorize": "https://accounts.google.com/o/oauth2/v2/auth",
        "token": "https://oauth2.googleapis.com/token",
        "api": "https://gmail.googleapis.com/gmail/v1/users/me",
    },
    "dida": {
        "id": "dida",
        "name": "滴答清单",
        "summary": "把清单里的待办，带进日常对话。",
        "transport": "oauth",
        "platforms": ["web", "ios"],
        "permissions": ["读取项目和任务", "不修改或完成外部任务"],
        "scope": "tasks:read",
        "authorize": "https://dida365.com/oauth/authorize",
        "token": "https://dida365.com/oauth/token",
        "api": "https://api.dida365.com/open/v1",
    },
    "apple_calendar": {
        "id": "apple_calendar",
        "name": "Apple 日历",
        "summary": "知道你的安排，留出合适的空隙。",
        "transport": "device",
        "platforms": ["ios"],
        "permissions": ["只读你选择的日历，过去 7 天至未来 30 天", "不读取参与者、备注或位置"],
    },
    "apple_health": {
        "id": "apple_health",
        "name": "Apple 健康",
        "summary": "从步数与活动量，了解生活的节奏。",
        "transport": "device",
        "platforms": ["ios"],
        "permissions": [
            "最近 7 天的每日步数与活动能量",
            "确认后上传至 Hymio，供个人助手和配置的 AI 模型使用",
        ],
    },
}


class ConnectorError(Exception):
    def __init__(self, code, status=400):
        self.code, self.status = code, status
        super().__init__(code)
