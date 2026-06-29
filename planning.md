# Provenance Guard, planning

## What I'm building

A backend a writing/art platform can call to ask "was this made by a person or by
AI?" and get an answer that's honest about uncertainty. It needs to classify a
submission, score how confident it is, hand back a reader-facing label, let
creators appeal, rate limit the submit endpoint, and log every decision.

The design rule I kept coming back to: don't force a binary. A borderline call
should look borderline to the reader, and a writer flagged by mistake should have
a way to contest it. On a writing platform, calling a human's work AI is the
worse error, so the labels and confidence both lean cautious.

## Architecture

```
        POST /submit        POST /appeal        GET /log     GET /
            |                    |                  |          |
            v                    v                  v          v
   +-------------------------------------------------------------+
   |                 Flask app  (src/main.py)                    |
   |   validates input, rate limits /submit, returns JSON        |
   +-------------------------------------------------------------+
            |                    |                  |
            v                    |                  |
   +---------------------------+ |                  |
   | pipeline (src/tool.py)    | |                  |
   |   llm_judge  (Groq)       | |                  |
   |   burstiness              | |                  |
   |   lexical_diversity       | |                  |
   |   ai_cliche               | |                  |
   |   metadata_signature  *   | |                  |
   |     |                     | |                  |
   |   weighted blend -> p_ai  | |                  |
   |   confidence + label      | |                  |
   +---------------------------+ |                  |
            |                    |                  |
            v                    v                  v
   +-------------------------------------------------------------+
   |              SQLite  (src/db/db.py)                         |
   |   decisions (verdict + signal scores + status)             |
   |   appeals   (reasoning, linked to a decision)              |
   +-------------------------------------------------------------+

   * metadata_signature only runs for content_type = "metadata".
```

Submission flow: text comes in to `/submit`, the pipeline runs each signal, the
scores get blended into `ai_probability`, that plus signal agreement gives a
confidence, confidence picks one of three labels, the whole thing is written to
the `decisions` table, and the verdict comes back as JSON.

Appeal flow: a `content_id` and a reason come in to `/appeal`, the reason is
saved to the `appeals` table and linked to the decision, the decision's status
becomes `under_review`, and the updated record comes back.

## The signals, and what each one misses

Each signal returns 0 (looks human) to 1 (looks AI), or nothing if there's too
little text. Using four different angles means a piece has to look AI in more than
one way before the blended score gets confident.

- `llm_judge` (weight 0.50): a Groq model reads the text and estimates how likely
  it's AI. It's the only signal that understands meaning, so it carries the most
  weight. Blind spots: it costs an API call, it can be fooled by AI text that's
  been edited by hand, and it's dropped completely when there's no key.
- `burstiness` (0.20): variation in sentence length. People mix long and short
  sentences; AI evens out. Blind spot: a human writing short, uniform sentences
  reads as AI.
- `lexical_diversity` (0.15): type-token ratio, how repetitive the vocabulary is.
  Blind spot: very sensitive to length and generally noisy, so it's the weakest
  one and gets a low weight.
- `ai_cliche` (0.15): how many known LLM phrases show up, plus em-dash density.
  Blind spot: a human parodying that style trips it, and a careful AI writer who
  avoids the phrases slips past.
- `metadata_signature`: only for the metadata content type. Looks for generator
  tags and zeroed timestamps in a JSON blob.

## Uncertainty and the score

`ai_probability` is a weighted average of whatever signals were available
(weights renormalized). Result is AI at 0.5 or above, else Human.

Confidence is the more useful number. It blends how far the probability sits from
0.5 with how much the signals agree:

```
boundary_term = 2 * abs(p_ai - 0.5)
agreement     = clamp(1 - 2 * stdev(signal_scores))
confidence    = clamp(0.5 * boundary_term + 0.5 * agreement)
```

So 0.6 to the system means "leaning AI, but not by much, and/or the signals
aren't unanimous, so don't trust it too far." Anything at 0.70 confidence or
above gets a confident label; below that is uncertain.

## The three labels

Picked by confidence (see `build_label` in `src/tool.py`). Exact wording is in
the README. In short:

- confident AI: "Likely AI-generated... automated guess, not proof, and the
  creator can appeal."
- confident human: "Likely human-written... automated guess, not proof."
- under 0.70: "Origin unclear... treat the result as inconclusive."

## Storage

- `decisions`: content_id, content_type, excerpt, result, ai_probability,
  confidence, signals (JSON), label, status (classified or under_review),
  created_at.
- `appeals`: id, content_id, reasoning, created_at.

## API surface

- `POST /submit` -> classify, save, return verdict + confidence + label + the
  per-signal scores. Rate limited.
- `POST /appeal` -> log the reason, set status to under_review, return the record.
- `GET /log` -> all decisions with their appeals.
- `GET /` -> what the service is.

## Edge cases I expect to handle badly

- Short, plain human writing with even sentence lengths. `burstiness` reads the
  uniformity as AI, and with no key there's no semantic signal to overrule it, so
  honest human prose can end up "uncertain." This actually showed up in testing.
- Human text that quotes or parodies corporate AI-speak. The `ai_cliche`
  signal counts the buzzwords and leans AI even though a person wrote it. The
  seeded buzzword sample is exactly this case, which is why it's the one with an
  appeal filed against it.
- Lightly edited AI output. Once someone varies the sentence lengths and strips
  the stock phrases, the statistics signals go quiet and it rides almost entirely
  on `llm_judge`.

## Stretch features

- Ensemble: four signals with written-down weights and a renormalized weighted
  average (done).
- Multi-modal: a second content type. `/submit` branches on `content_type` to
  handle `metadata` (and `image_description`) on top of plain text (done).

## Stack

Flask, Flask-Limiter, Groq, python-dotenv, and SQLite from the standard library.
SQLite keeps the audit log on disk with no extra setup. Keeping the LLM as one
signal among several (rather than the whole system) is what makes the detection
multi-signal and lets it degrade gracefully when there's no key.
