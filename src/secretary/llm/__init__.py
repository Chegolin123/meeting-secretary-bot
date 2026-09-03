"""LLM: постобработка транскриптов."""

from secretary.llm.deepseek import DeepSeekClient, DeepSeekError, MeetingSummary, parse_summary

__all__ = ["DeepSeekClient", "DeepSeekError", "MeetingSummary", "parse_summary"]