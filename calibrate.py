"""
Checks that the confidence scores actually mean something. Two claims:

1. Separation: known-AI text should score higher in ai_probability than
   known-human text. If the scores were noise the two averages would overlap.
2. Monotonic confidence: confidence should climb as the probability moves away
   from 0.5, so a 0.51 call is reported much less confidently than a 0.95 one.

Both hold offline (heuristics only). With a GROQ_API_KEY the LLM signal pushes
the clear cases further toward the edges. The output here is what the README's
confidence section quotes.

    python calibrate.py
"""

import os
import statistics
import sys

_SRC = os.path.join(os.path.dirname(os.path.abspath(__file__)), "src")
sys.path.insert(0, _SRC)

from dotenv import load_dotenv

import tool

load_dotenv()

KNOWN_HUMAN = [
    "The rain came sideways today and I forgot my umbrella again, of course. "
    "My neighbor laughed. We talked about nothing. The bus never came. I "
    "walked home soaked and, strangely, happy about the whole stupid morning.",
    "Grandma kept buttons in a tin that smelled of peppermint. She'd let me "
    "sort them for hours. Blue ones. The cracked one. That single gold button "
    "nobody ever found a use for. I still have the tin. The buttons too.",
    "Honestly? The concert was too loud and my feet hurt by the second song. "
    "But then they played the one I love and I forgot all of it. Funny how "
    "that works.",
]

KNOWN_AI = [
    "In today's fast-paced world, it is important to note that artificial "
    "intelligence plays a crucial role. Furthermore, this represents a "
    "testament to innovation. Moreover, we must delve into the rich tapestry "
    "of progress that underscores our multifaceted future.",
    "Sustainability is a multifaceted and nuanced topic that plays a vital "
    "role in modern society. It is important to note that we must foster "
    "robust, seamless solutions. Furthermore, these initiatives elevate "
    "communities and underscore an ever-evolving commitment to progress.",
    "Embarking on a journey of self-improvement is a testament to personal "
    "growth. Moreover, it is important to leverage cutting-edge strategies. "
    "Furthermore, this multifaceted approach fosters a seamless and robust "
    "transformation that elevates one's potential.",
]


def _run(group):
    return [tool.run_pipeline(text, "text") for text in group]


def _variant(label):
    if "AI-generated" in label:
        return "AI"
    if "human-written" in label:
        return "HUMAN"
    return "UNCERTAIN"


def _summary(label, rows):
    probs = [r["ai_probability"] for r in rows]
    print(f"\n=== {label} (n={len(rows)}) ===")
    for r in rows:
        print(f"  {r['result']:<6} p_ai={r['ai_probability']:.3f} "
              f"conf={r['confidence']:.3f}  -> {_variant(r['label'])}")
    return statistics.mean(probs)


def main():
    human_rows = _run(KNOWN_HUMAN)
    ai_rows = _run(KNOWN_AI)
    h_p = _summary("KNOWN HUMAN", human_rows)
    a_p = _summary("KNOWN AI", ai_rows)

    print("\n=== CLAIM 1: SEPARATION ===")
    print(f"  human mean p_ai = {h_p:.3f}")
    print(f"  ai    mean p_ai = {a_p:.3f}")
    print(f"  separation = {a_p - h_p:+.3f}   "
          f"({'PASS' if a_p - h_p > 0.2 else 'FAIL'}: want clearly positive)")

    print("\n=== CLAIM 2: MONOTONIC CONFIDENCE ===")
    print("  ensemble p_ai -> confidence (signals held unanimous):")
    prev = -1.0
    monotonic = True
    for p in (0.50, 0.55, 0.60, 0.70, 0.80, 0.95):
        c = tool._compute_confidence(p, [p, p, p])
        flag = "" if c >= prev else "  <-- DROP"
        if c < prev:
            monotonic = False
        print(f"    p_ai={p:.2f} -> confidence={c:.3f}{flag}")
        prev = c
    print(f"  {'PASS' if monotonic else 'FAIL'}: confidence rises with "
          f"distance from the 0.5 boundary "
          f"(0.51 is reported far less confidently than 0.95).")


if __name__ == "__main__":
    main()
