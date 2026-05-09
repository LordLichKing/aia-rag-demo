package com.lichen.know.engine.chat.entity;

import com.lichen.know.engine.ai.model.IntentRecognitionResult;

public record ChatParam(String userId, String conversationId, String messageId,String content,
                        IntentRecognitionResult intentRecognitionResult) {
}
