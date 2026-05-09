import logging
from typing import List


logger = logging.getLogger(__name__)


def estimate_faithfulness(answer: str, context: str) -> float:
    if not answer or not context:
        return 0.0

    answer_sents = _split_sentences(answer)
    if not answer_sents:
        return 0.0

    supported = 0
    context_lower = context.lower()
    context_words = set(_tokenize(context_lower))

    for sent in answer_sents:
        sent_words = _tokenize(sent.lower())
        if not sent_words:
            continue

        overlap = sum(1 for w in sent_words if w in context_words)
        ratio = overlap / len(sent_words) if sent_words else 0

        if ratio >= 0.5:
            supported += 1
        elif _has_semantic_match(sent, context_lower):
            supported += 1

    return round(supported / len(answer_sents), 4)


def estimate_context_relevance(question: str, context: str) -> float:
    if not question or not context:
        return 0.0

    question_words = set(_tokenize(question.lower()))
    if not question_words:
        return 0.0

    context_sents = _split_sentences(context)
    if not context_sents:
        return 0.0

    relevant = 0
    for sent in context_sents:
        sent_words = set(_tokenize(sent.lower()))
        overlap = len(question_words & sent_words)
        if overlap >= max(1, len(question_words) * 0.3):
            relevant += 1

    return round(relevant / len(context_sents), 4)


def _split_sentences(text: str) -> List[str]:
    import re
    sentences = re.split(r'[。！？.!?\n]', text)
    return [s.strip() for s in sentences if len(s.strip()) > 5]


def _tokenize(text: str) -> List[str]:
    tokens = []
    current = []
    for ch in text:
        if '\u4e00' <= ch <= '\u9fff':
            if current:
                tokens.append("".join(current))
                current = []
            tokens.append(ch)
        elif ch.isalnum():
            current.append(ch)
        else:
            if current:
                tokens.append("".join(current))
                current = []
    if current:
        tokens.append("".join(current))
    return tokens


def _has_semantic_match(sentence: str, context: str) -> bool:
    s_words = set(_tokenize(sentence.lower()))
    c_words = set(_tokenize(context))
    if not s_words:
        return False
    overlap = len(s_words & c_words)
    return overlap >= len(s_words) * 0.6
