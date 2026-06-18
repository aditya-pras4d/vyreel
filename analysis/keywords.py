"""
Single source of truth for topic keyword matching, shared by topic_detector
and competitor_gap (previously each had its own map, which drifted apart).

Matching rules:
- Word boundaries are enforced, so "rag" no longer matches inside "storage"
  or "llm" inside "fullmetal".
- Spaces/hyphens/dots inside a keyword match an optional separator, so
  "chat gpt" matches "chatgpt", "chat-gpt", "chat gpt" and "chat.gpt".
- A trailing '*' means prefix-match: "fine tun*" matches "fine-tuning",
  "finetuned", etc.
"""
import re

TOPIC_KEYWORDS: dict[str, list[str]] = {
    "ChatGPT": ["chat gpt"],
    "GPT-4": ["gpt 4"],
    "Claude AI": ["claude"],
    "Gemini AI": ["gemini"],
    "Llama": ["llama"],
    "Sora": ["sora"],
    "OpenAI": ["open ai"],
    "Anthropic": ["anthropic"],
    "Google DeepMind": ["deepmind"],
    "Midjourney": ["mid journey"],
    "Stable Diffusion": ["stable diffusion"],
    "AI Agents": ["ai agent*", "agentic"],
    "RAG": ["rag", "retrieval augmented"],
    "Fine-tuning": ["fine tun*"],
    "Prompt Engineering": ["prompt engineer*"],
    "LLMs": ["llm", "llms", "large language model*"],
    "AI Video": ["ai video", "text to video"],
    "AI Image Generation": ["ai image*", "text to image", "image generation"],
    "AI Automation": ["ai automat*", "automation"],
    "No-code AI": ["no code"],
    "Vibe Coding": ["vibe cod*"],
    "Cursor IDE": ["cursor"],
    "GitHub Copilot": ["copilot"],
    "Devin AI": ["devin"],
    "Sam Altman": ["sam altman"],
    "Elon Musk / xAI": ["elon musk"],
    "Grok / xAI": ["grok", "xai", "x ai"],
    "Perplexity AI": ["perplexity"],
    "Mistral": ["mistral"],
    "Hugging Face": ["hugging face"],
}


def _keyword_pattern(kw: str) -> str:
    prefix = kw.endswith("*")
    if prefix:
        kw = kw[:-1]
    parts = [re.escape(p) for p in re.split(r"[\s\-.]+", kw) if p]
    pattern = r"[\s\-.]?".join(parts)
    return rf"\b{pattern}" + ("" if prefix else r"\b")


_COMPILED: dict[str, re.Pattern] = {
    topic: re.compile("|".join(_keyword_pattern(kw) for kw in kws))
    for topic, kws in TOPIC_KEYWORDS.items()
}


def extract_topics(text: str) -> list[str]:
    """All topics mentioned in the text."""
    text_lower = (text or "").lower()
    return [topic for topic, pattern in _COMPILED.items() if pattern.search(text_lower)]


def topic_in_text(topic: str, text: str) -> bool:
    pattern = _COMPILED.get(topic)
    if pattern is None:
        pattern = re.compile(_keyword_pattern(topic.lower()))
    return bool(pattern.search((text or "").lower()))
