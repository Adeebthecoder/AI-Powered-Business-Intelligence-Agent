"""
json_parsing.py
---------------
The LLM is asked to reply in JSON, but this model cannot be forced to
(it has no response_format option). So the reply may have code fences or
extra sentences around the JSON. extract_json() digs the JSON out safely.

This file has no other code in it, so it is easy to test.
"""

import json
import re


def extract_json(text: str) -> dict | None:
    """
    Find the first JSON object in the model's reply.

    Handles the usual mess: ```json code fences, a sentence before or after
    the JSON, and braces inside strings. Returns None if nothing usable is found.
    """
    if not text:
        return None
    # 1. remove code fences such as ```json ... ```
    cleaned = re.sub(r"```[a-zA-Z]*", "", text).replace("```", "").strip()

    # 2. walk through the text and cut out the first balanced {...} block
    start = cleaned.find("{")
    while start != -1:
        depth, in_string, escaped = 0, False, False
        for position in range(start, len(cleaned)):
            char = cleaned[position]
            if in_string:
                if escaped:
                    escaped = False
                elif char == "\\":
                    escaped = True
                elif char == '"':
                    in_string = False
            elif char == '"':
                in_string = True
            elif char == "{":
                depth += 1
            elif char == "}":
                depth -= 1
                if depth == 0:
                    candidate = cleaned[start:position + 1]
                    try:
                        # strict=False lets a line break inside a string pass
                        parsed = json.loads(candidate, strict=False)
                        if isinstance(parsed, dict):
                            return parsed
                    except ValueError:
                        pass
                    break
        start = cleaned.find("{", start + 1)
    return None
