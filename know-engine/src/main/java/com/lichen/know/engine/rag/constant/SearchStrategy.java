package com.lichen.know.engine.rag.constant;

public enum SearchStrategy {
    VECTOR,
    HYBRID,
    HYBRID_RERANK;

    public static SearchStrategy fromString(String strategy) {
        return SearchStrategy.valueOf(strategy.toUpperCase());
    }
}
