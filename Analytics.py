"""Small, dependency-light transformations for the Flipkart review dashboard."""

from __future__ import annotations

import pandas as pd
import re
from collections import Counter


EXPECTED_COLUMNS = ("ReviewID", "ProductName", "Price_INR", "Rating", "ReviewTitle", "ReviewText")


def prepare_reviews(frame: pd.DataFrame) -> pd.DataFrame:
    """Normalize workbook columns and add a rating-based sentiment label."""
    if frame is None or frame.empty:
        return pd.DataFrame(columns=[*EXPECTED_COLUMNS, "Sentiment"])

    result = frame.copy()
    result.columns = [str(column).strip() for column in result.columns]
    # Accept common capitalization variants without hiding genuinely missing data.
    lookup = {column.casefold(): column for column in result.columns}
    rename = {
        lookup[name.casefold()]: name
        for name in EXPECTED_COLUMNS
        if name.casefold() in lookup
    }
    result = result.rename(columns=rename)
    for column in EXPECTED_COLUMNS:
        if column not in result:
            result[column] = pd.NA

    result["Rating"] = pd.to_numeric(result["Rating"], errors="coerce")
    result["Price_INR"] = pd.to_numeric(result["Price_INR"], errors="coerce")
    result = result.dropna(subset=["Rating"])
    result = result[result["Rating"].between(1, 5)].copy()
    result["Sentiment"] = result["Rating"].map(
        lambda rating: "Positive" if rating >= 4 else ("Mixed" if rating == 3 else "Negative")
    )
    for column in ("ReviewID", "ProductName", "ReviewTitle", "ReviewText"):
        result[column] = result[column].fillna("").astype(str)
    return result.reset_index(drop=True)


def summarize_reviews(reviews: pd.DataFrame) -> dict[str, float | int]:
    """Return the dashboard metrics for the selected review rows."""
    if reviews is None or reviews.empty:
        return {"count": 0, "average_rating": 0.0, "positive_pct": 0.0, "attention_count": 0}
    ratings = pd.to_numeric(reviews["Rating"], errors="coerce").dropna()
    count = len(ratings)
    return {
        "count": count,
        "average_rating": float(ratings.mean()) if count else 0.0,
        "positive_pct": float((ratings.ge(4).mean() * 100)) if count else 0.0,
        "attention_count": int(ratings.le(2).sum()),
    }
_STOP_WORDS = {
    "about", "after", "again", "also", "are", "been", "being", "but", "can",
    "could", "did", "does", "dont", "each", "for", "from", "good", "have",
    "here", "into", "just", "like", "made", "more", "most", "much", "only",
    "other", "our", "product", "really", "some", "than", "that", "them", "then",
    "there", "they", "this", "too", "very", "was", "were", "what", "when", "with",
    "would", "your", "you", "its", "the", "and", "not", "but", "are", "is", "it",
    "to", "of", "in", "on", "at", "as", "an", "a", "i", "my", "we", "ok",
}


def analyze_product(reviews: pd.DataFrame) -> dict:
    """Build a transparent per-product analysis from review ratings and text."""
    metrics = summarize_reviews(reviews)
    if reviews is None or reviews.empty:
        return {**metrics, "rating_counts": pd.Series(dtype=int), "themes": [], "positive_examples": [], "negative_examples": []}

    rating_counts = reviews["Rating"].value_counts().reindex([1, 2, 3, 4, 5], fill_value=0)
    text = (reviews["ReviewTitle"].fillna("").astype(str) + " " + reviews["ReviewText"].fillna("").astype(str))
    words = Counter(
        word for value in text for word in re.findall(r"[a-zA-Z]{3,}", value.casefold())
        if word not in _STOP_WORDS
    )
    positive = reviews[reviews["Rating"] >= 4]
    negative = reviews[reviews["Rating"] <= 2]

    def examples(frame: pd.DataFrame) -> list[str]:
        result = []
        for _, row in frame.head(3).iterrows():
            title = str(row.get("ReviewTitle", "")).strip()
            body = str(row.get("ReviewText", "")).strip()
            excerpt = " — ".join(part for part in (title, body) if part)
            if excerpt:
                result.append(excerpt[:280])
        return result

    return {
        **metrics,
        "rating_counts": rating_counts,
        "themes": words.most_common(8),
        "positive_examples": examples(positive),
        "negative_examples": examples(negative),
    }

def build_product_roadmap(reviews: pd.DataFrame) -> dict[str, list[dict[str, str]]]:
    """Turn product feedback into evidence-linked actions grouped by urgency."""
    roadmap: dict[str, list[dict[str, str]]] = {
        "High priority – Immediate improvements": [],
        "Medium priority – Improvements in the near future": [],
        "Low priority – Future enhancements": [],
    }
    if reviews is None or reviews.empty:
        roadmap["Medium priority – Improvements in the near future"].append({
            "action": "Collect more customer feedback before planning changes.",
            "evidence": "There are no reviews for this product yet.",
        })
        return roadmap

    negative = reviews[reviews["Rating"] <= 2]
    positive = reviews[reviews["Rating"] >= 4]
    total = len(reviews)
    avg = float(pd.to_numeric(reviews["Rating"], errors="coerce").mean())

    # Use negative review terms as concrete candidate problem areas. The evidence
    # review snippet below keeps the recommendations grounded and inspectable.
    theme_counts: Counter[str] = Counter()
    theme_evidence: dict[str, str] = {}
    issue_terms = {
        "quality": "Inspect materials and quality checks",
        "broken": "Review product durability and transit protection",
        "damage": "Review product durability and transit protection",
        "delivery": "Investigate delivery and packaging issues",
        "pack": "Review packaging and delivery handling",
        "battery": "Investigate battery life and charging performance",
        "sound": "Review audio performance and tuning",
        "size": "Check sizing guidance and product dimensions",
        "fit": "Review fit and sizing guidance",
        "leak": "Check seals and leak prevention",
        "work": "Investigate reported functionality problems",
        "poor": "Investigate the most common causes of dissatisfaction",
        "waste": "Investigate reported usability or value concerns",
        "weak": "Review structural strength and durability",
        "return": "Review support and returns experience",
    }
    for _, row in negative.iterrows():
        snippet = " ".join(str(row.get(column, "")) for column in ("ReviewTitle", "ReviewText")).strip()
        words = set(re.findall(r"[a-zA-Z]{3,}", snippet.casefold()))
        for term, action in issue_terms.items():
            if term in words:
                theme_counts[action] += 1
                theme_evidence.setdefault(action, snippet[:220])

    if not negative.empty:
        for action, count in theme_counts.most_common(3):
            roadmap["High priority – Immediate improvements"].append({
                "action": action + ".",
                "evidence": f"Mentioned in {count} of {len(negative)} low-rated reviews. Example: “{theme_evidence[action]}”",
            })
        if not roadmap["High priority – Immediate improvements"]:
            example = str(negative.iloc[0].get("ReviewTitle", "") or negative.iloc[0].get("ReviewText", ""))[:220]
            roadmap["High priority – Immediate improvements"].append({
                "action": "Review low-rated feedback and resolve the recurring customer pain points.",
                "evidence": f"{len(negative)} of {total} reviews are rated 1–2 stars. Example: “{example}”",
            })
    else:
        roadmap["High priority – Immediate improvements"].append({
            "action": "No urgent issue is signaled by low ratings; keep monitoring new feedback.",
            "evidence": f"No 1–2 star reviews among {total} reviews.",
        })

    if avg < 4.0:
        roadmap["Medium priority – Improvements in the near future"].append({
            "action": "Prioritize the most frequent improvement themes and check whether changes lift ratings.",
            "evidence": f"Average rating is {avg:.1f}/5 across {total} reviews.",
        })
    elif not positive.empty:
        roadmap["Medium priority – Improvements in the near future"].append({
            "action": "Use positive feedback to identify strengths to preserve while addressing lower-rated cases.",
            "evidence": f"{len(positive)} of {total} reviews are rated 4–5 stars.",
        })

    roadmap["Low priority – Future enhancements"].append({
        "action": "Track ratings and recurring themes over time, then validate future enhancements with customers.",
        "evidence": f"Use the current {total} reviews as a baseline (average {avg:.1f}/5).",
    })
    return roadmap
