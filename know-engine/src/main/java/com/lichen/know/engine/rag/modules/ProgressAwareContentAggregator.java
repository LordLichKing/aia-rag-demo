package com.lichen.know.engine.rag.modules;

import com.lichen.know.engine.chat.entity.ChatMessage;
import com.lichen.know.engine.chat.service.ChatMessageService;
import com.alibaba.fastjson2.JSON;
import dev.langchain4j.rag.content.Content;
import dev.langchain4j.rag.content.aggregator.ContentAggregator;
import dev.langchain4j.rag.query.Query;
import lombok.extern.slf4j.Slf4j;
import org.springframework.util.CollectionUtils;

import java.util.Collection;
import java.util.List;
import java.util.Map;
import java.util.function.Consumer;
import java.util.stream.Collectors;

import static com.lichen.know.engine.rag.constant.MetadataKeyConstant.*;
import static dev.langchain4j.rag.content.ContentMetadata.RERANKED_SCORE;

/**
 * 带进度通知的内容聚合器
 * <p>
 * 在委托执行 {@link ContentAggregator#aggregate(Map)} 前后发送进度通知，
 * 用于流式返回前端当前处理阶段，减少用户等待焦虑。
 * <p>
 * 进度通知顺序：
 * <ol>
 *   <li>聚合前：{@code [PROGRESS]:正在排序筛选结果...}</li>
 *   <li>聚合后：{@code [PROGRESS]:正在生成回答...}（聚合完成后即将进入LLM生成阶段）</li>
 * </ol>
 *
 * @see ContentAggregator
 */
@Slf4j
public class ProgressAwareContentAggregator implements ContentAggregator {

    private final ContentAggregator delegate;
    private final Consumer<String> progressCallback;
    private final String chatMessageId;
    private final ChatMessageService chatMessageService;


    public ProgressAwareContentAggregator(ContentAggregator delegate, Consumer<String> progressCallback, String chatMessageId, ChatMessageService chatMessageService) {
        this.chatMessageService = chatMessageService;
        this.delegate = delegate;
        this.chatMessageId = chatMessageId;
        this.progressCallback = progressCallback;
    }

    @Override
    public List<Content> aggregate(Map<Query, Collection<List<Content>>> queryToContents) {
        // 发送进度：开始重排序/聚合
        if (progressCallback != null) {
            progressCallback.accept("[PROGRESS]:正在排序筛选结果...");
            System.out.println("[PROGRESS]:正在排序筛选结果...");
        }

        log.info("queryToContents = {}", queryToContents);

        List<Content> results = delegate.aggregate(queryToContents);

        try {
            List<ChatMessage.RagReference> ragReferences = results.stream()
                    .collect(Collectors.toMap(
                            content -> content.textSegment().metadata().getInteger(DOC_ID),
                            content -> content,
                            (existing, replacement) -> existing
                    )).values().stream().map(content -> {
                        ChatMessage.RagReference reference = new ChatMessage.RagReference();
                        reference.setDocumentId(content.textSegment().metadata().getInteger(DOC_ID) + "");
                        reference.setChunkId(content.textSegment().metadata().getString(CHUNK_ID));
                        reference.setUrl(content.textSegment().metadata().getString(URL));
                        reference.setDocumentTitle(content.textSegment().metadata().getString(FILE_NAME));
                        reference.setChunkContent(content.textSegment().text());
                        reference.setRerankScore((double) content.metadata().get(RERANKED_SCORE));
                        return reference;
                    }).collect(Collectors.toList());

            if (!CollectionUtils.isEmpty(ragReferences) && chatMessageService != null && chatMessageId != null) {
                chatMessageService.updateRagReferences(chatMessageId, ragReferences);
            }

            if (progressCallback != null) {
                progressCallback.accept("[REFERENCE]:" + JSON.toJSONString(ragReferences));
                System.out.println("[REFERENCE]:" + JSON.toJSONString(ragReferences));
            }
        } catch (Exception e) {
            log.warn("RAG引用信息回写失败: assistantMsgId={}", chatMessageId, e);
        }


        // 发送进度：聚合完成，即将进入LLM生成
        if (progressCallback != null) {
            progressCallback.accept("[PROGRESS]:正在生成回答...");
            System.out.println("[PROGRESS]:正在生成回答...");
        }

        return results;
    }
}
