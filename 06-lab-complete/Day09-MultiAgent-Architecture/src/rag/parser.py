from __future__ import annotations

import re


def parse_policy_markdown(markdown_text: str) -> list[dict]:
    """Parse markdown into chunks by H2 + H3 structure.

    Each chunk contains the full H2 context, the H3 subsection, and all content
    under that H3 heading — suitable for embedding into a vector store.
    """
    chunks: list[dict] = []
    current_h2 = ""
    current_h3 = ""
    content_lines: list[str] = []

    def flush() -> None:
        if current_h3 and content_lines:
            text = "\n".join(content_lines).strip()
            if text:
                citation = f"{current_h2} > {current_h3}"
                rendered_text = f"## {current_h2}\n### {current_h3}\n\n{text}"
                chunks.append({
                    "section_h2": current_h2,
                    "section_h3": current_h3,
                    "citation": citation,
                    "rendered_text": rendered_text,
                })

    for line in markdown_text.splitlines():
        h2_match = re.match(r"^##\s+(.+)", line)
        h3_match = re.match(r"^###\s+(.+)", line)

        if h2_match:
            flush()
            current_h2 = h2_match.group(1).strip()
            current_h3 = ""
            content_lines = []
        elif h3_match:
            flush()
            current_h3 = h3_match.group(1).strip()
            content_lines = []
        else:
            if current_h3:
                content_lines.append(line)

    flush()
    return chunks
