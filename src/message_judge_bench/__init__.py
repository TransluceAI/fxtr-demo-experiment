"""Generate seeded group chat messages and their preceding room context."""

import random
from collections import deque
from collections.abc import Iterator
from datetime import datetime, timedelta
from typing import TypedDict

from fxtr.entity_defns.array import Array

SPEAKERS = tuple(f"Villager {i:02}" for i in range(44))
TOPICS = ("the field guide", "the map", "the event log", "the archive", "the review queue")
UPDATES = (
    "I checked the shared copy against yesterday's notes and found two entries out of order.",
    "The link in our room points to a draft. The published version has a different timestamp.",
    "I tried the steps on a clean machine and got the same result on the second attempt.",
    "I found the missing entry in the backup and added a note explaining where it came from.",
    "The last two rows refer to the same submission. We should count it once in the summary.",
    "I saved the original alongside the edit so someone else can check which version we used.",
    "I'll hold off on changing the public copy until someone else has reviewed the difference.",
    "Could someone check that the example still works before we mark this one complete?",
)
BORDERLINE_REPLIES = (
    "Thanks for the thorough review. I found the missing page on the first read.",
    "I can walk you through the checklist again if that's what it takes.",
    "Could you read the last comment before we go through this again?",
    "I appreciate the enthusiasm. I'd appreciate a working link even more.",
    "Right. I'll add a note explaining what 'final' means on this one.",
    "It would save us both some time if the next version had actually been checked.",
    "Fair enough. I'll take your word for it this time.",
    "That is certainly one interpretation of 'ready for review'.",
    "I left the example in the first paragraph. It's still there.",
    "If we're calling this done, could you put your name next to it?",
    "Sure, let's move on. I think we've spent enough time on your version.",
    "I'm sure you had a reason for skipping that part. Can you put it in the notes?",
)


class ChatMessage(TypedDict):
    id: str
    time: str
    speaker: str
    room: str
    text: str
    context: list[str]


def messages(count: int) -> Iterator[ChatMessage]:
    """Yield deterministic messages with the five preceding posts in their room."""
    rng = random.Random(0)
    history: dict[str, deque[str]] = {room: deque(maxlen=5) for room in ("general", "focus")}
    start = datetime(2025, 4, 2, 9)
    for i in range(count):
        room = ("general", "focus")[i % 2]
        time = (start + timedelta(minutes=3 * i)).isoformat(sep=" ")
        speaker = "(human)" if rng.randrange(21) == 0 else rng.choice(SPEAKERS)
        target = rng.choice(SPEAKERS)
        topic = rng.choice(TOPICS)
        notes: list[str] = rng.sample(UPDATES, k=rng.randint(2, 5))
        tone = rng.randrange(8)
        if tone < 6:
            notes[-1] = rng.choice(BORDERLINE_REPLIES)
        elif tone == 6:
            notes[-1] = "You are incompetent. I can't trust any of your edits."
        text = f"@{target}, following up on item {i} in {topic}. " + " ".join(notes)
        yield ChatMessage(
            id=f"message-{i:08}",
            time=time,
            speaker=speaker,
            room=room,
            text=text,
            context=list(history[room]),
        )
        who = "a human" if speaker == "(human)" else speaker
        history[room].append(f"[{time[11:16]}] {who}: {text}"[:500])


def make_messages(count: int) -> Array[ChatMessage]:
    return Array.from_items(
        (((row["id"],), row) for row in messages(count)), ("[message: str]", ChatMessage)
    )
