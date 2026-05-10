from dataclasses import dataclass, field


@dataclass(slots=True)
class SearchHit:
    chat_id: int
    title: str
    chat_type: str
    username: str | None = None
    link: str | None = None
    description: str | None = None
    is_forum: bool = False
    members_count: int | None = None
    relevance_score: float = 0.0
    matched_by: list[str] = field(default_factory=list)
    linked_chat_title: str | None = None
    linked_chat_link: str | None = None
    channel_status: str | None = None
