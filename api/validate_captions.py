import pysrt

#validate captions (check from grammar, punctuations etc.)
def validate_caption_quality(srt_path: str, max_words: int = 6, min_gap: float = 0.05):
    """Validate caption density, readability, and timing overlaps."""
    subs = pysrt.open(srt_path)
    issues = []

    for i, sub in enumerate(subs):
        word_count = len(sub.text.split())
        if word_count > max_words:
            issues.append(f"[{i+1}] Too many words ({word_count})")

        if i < len(subs) - 1:
            gap = (subs[i + 1].start.ordinal - sub.end.ordinal) / 1000
            if gap < min_gap:
                issues.append(f"[{i+1}] Short/overlap gap ({gap:.2f}s)")

    if issues:
        print("Validation issues found:")
        for issue in issues:
            print("  ", issue)
        score = max(0, 100 - len(issues) * 5)
    else:
        print("Captions validated successfully.")
        score = 100

    return score
