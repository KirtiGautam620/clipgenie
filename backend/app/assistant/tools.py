"""What the assistant can do. Each shortcut on the home page is one of these.

A tool that is not built yet is still listed, with available=False and the plain reason, so the
page can show it as "Soon" and the assistant can say why instead of pretending.
"""

TOOLS = {
    "make_clips": {
        "title": "Make clips",
        "description": "Turn a long video into short vertical clips, edited automatically.",
        "available": True, "needs_confirmation": True,
        "example": "Turn my podcast into 5 Shorts",
    },
    "video_ideas": {
        "title": "Video ideas",
        "description": "Ideas for your next video, based on what you talk about in your own videos.",
        "available": True, "needs_confirmation": False,
        "example": "Give me ideas for my next video",
    },
    "get_more_views": {
        "title": "Get more views", "available": False,
        "reason": "This needs your YouTube channel's statistics, and connecting a channel isn't built yet.",
    },
    "channel_audit": {
        "title": "Channel audit", "available": False,
        "reason": "This needs your YouTube channel's statistics, and connecting a channel isn't built yet.",
    },
    "create_thumbnail": {
        "title": "Create thumbnail",
        "description": "A thumbnail from the best frames of one of your clips, with your title on it.",
        "available": True, "needs_confirmation": False,
        "example": "Create a thumbnail for my last video",
    },
    "write_copy": {
        "title": "Write titles",
        "description": "A title, description and hashtags for each clip, written from what is said in it.",
        "available": True, "needs_confirmation": False,
        "example": "Write titles and hashtags for my clips",
    },
    "find_broll": {
        "title": "Find B-roll", "available": False,
        "reason": "B-roll needs a source of stock footage, and none is connected yet.",
    },
    "ai_voiceover": {
        "title": "AI voiceover", "available": False,
        "reason": "A voiceover needs a speech model, and none is installed.",
    },
    "compose_video": {
        "title": "Compose video", "available": False,
        "reason": "Making a video from photos isn't available yet.",
    },
}

ORDER = ["get_more_views", "channel_audit", "create_thumbnail", "write_copy", "video_ideas", "make_clips",
         "find_broll", "ai_voiceover", "compose_video"]


def get(name: str) -> dict | None:
    tool = TOOLS.get(name)
    return {"name": name, **tool} if tool else None


def listing() -> list[dict]:
    """The shortcuts, in the order the home page shows them."""
    return [get(name) for name in ORDER]
