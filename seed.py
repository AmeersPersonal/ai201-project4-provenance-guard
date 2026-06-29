"""
Fill the audit log with a few sample decisions and one appeal so GET /log has
something to show (the rubric wants at least 3 entries and an appeal). Safe to
re-run, it just adds more rows.

    python seed.py
"""

import os
import sys

# Pull tool from src/ and db from src/db/.
_SRC = os.path.join(os.path.dirname(os.path.abspath(__file__)), "src")
sys.path.insert(0, _SRC)
sys.path.insert(0, os.path.join(_SRC, "db"))

from dotenv import load_dotenv

import db
import tool

load_dotenv()

SAMPLES = [
    {
        "content_type": "text",
        "content": (
            "The rain came sideways today. I forgot my umbrella again, of "
            "course. My neighbor laughed at me from her porch. We stood under "
            "the awning and talked about nothing in particular, like her cat, "
            "the price of eggs, whether the late bus would ever show. It never "
            "did. I walked home soaked through and, strangely, happy."
        ),
    },
    {
        # Deliberately stuffed with AI tells, this is the one we expect to flag.
        "content_type": "text",
        "content": (
            "In today's fast-paced world, it is important to note that "
            "artificial intelligence plays a crucial role in modern society. "
            "Furthermore, this technology represents a testament to human "
            "ingenuity. Moreover, we must delve into the rich tapestry of "
            "innovation that underscores the ever-evolving landscape. It is a "
            "multifaceted and nuanced topic that elevates our understanding "
            "and fosters a seamless, robust future."
        ),
    },
    {
        "content_type": "text",
        "content": (
            "Morning light. The kettle clicks off and steam curls upward in "
            "the cold kitchen. I write three lines, cross out two, and decide "
            "the third can stay until tomorrow when I will probably hate it."
        ),
    },
    {
        "content_type": "metadata",
        "content": (
            '{"title": "Sunset over harbor", "generator": "Midjourney v6", '
            '"created": "2024-01-01T00:00:00Z", "author": "anon_user"}'
        ),
    },
    {
        # Repetitive, uniform, cliche-heavy: clears the bar for a confident AI call.
        "content_type": "text",
        "content": (
            "It is important to note that artificial intelligence is robust. "
            "It is important to note that artificial intelligence is seamless. "
            "Furthermore, artificial intelligence is robust. Furthermore, "
            "artificial intelligence is seamless. Moreover, artificial "
            "intelligence is robust. Moreover, artificial intelligence is "
            "seamless."
        ),
    },
]


def main():
    db.init_db()
    inserted = []
    for sample in SAMPLES:
        verdict = tool.run_pipeline(sample["content"], sample["content_type"])
        content_id = db.insert_decision(
            content_type=sample["content_type"],
            excerpt=sample["content"][:280],
            result=verdict["result"],
            ai_probability=verdict["ai_probability"],
            confidence=verdict["confidence"],
            signals=verdict["signals"],
            label=verdict["label"],
        )
        inserted.append((content_id, verdict))
        print(
            f"[seed] {content_id}  {sample['content_type']:<17} "
            f"{verdict['result']:<6} p_ai={verdict['ai_probability']:.3f} "
            f"conf={verdict['confidence']:.3f}"
        )

    # Appeal the buzzword paragraph (sample #2) so the log shows an appeal too.
    appeal_target = inserted[1][0]
    appeal_id = db.insert_appeal(
        content_id=appeal_target,
        reasoning=(
            "I wrote this myself for a satire piece that parodies corporate AI "
            "buzzwords. Please re-review, the style is intentional and not "
            "machine-generated."
        ),
    )
    print(f"[seed] appeal {appeal_id} filed against {appeal_target} "
          f"-> status now 'under_review'")


if __name__ == "__main__":
    main()
