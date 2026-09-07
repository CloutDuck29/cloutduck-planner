import re


def extract_homework(
    text: str | None,
) -> str | None:
    if not text:
        return None

    match = re.search(
        r"(?:^|\n)\s*ДЗ\s*:\s*(.*)",
        text,
        flags=re.IGNORECASE | re.DOTALL,
    )

    if not match:
        return None

    homework = match.group(1).strip()

    if not homework:
        return None

    if homework in {
        "-",
        "—",
        "–",
    }:
        return None

    return homework