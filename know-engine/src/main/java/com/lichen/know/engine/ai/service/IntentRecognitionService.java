package com.lichen.know.engine.ai.service;

import com.lichen.know.engine.ai.model.IntentRecognitionResult;
import dev.langchain4j.service.SystemMessage;
import dev.langchain4j.service.UserMessage;

/**
 * 意图识别服务
 *
 * @author Hollis
 */
public interface IntentRecognitionService {

    @SystemMessage(fromResource = "prompts/intent-recognition-new-prompt.txt")
    IntentRecognitionResult chat(@UserMessage String userMessage);
}
