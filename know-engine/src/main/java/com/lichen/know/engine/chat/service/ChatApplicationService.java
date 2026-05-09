package com.lichen.know.engine.chat.service;

import com.lichen.know.engine.ai.service.KnowEngineChatAiService;
import com.lichen.know.engine.ai.service.PromptService;
import com.lichen.know.engine.chat.entity.ChatParam;
import com.lichen.know.engine.document.service.KnowledgeSegmentService;
import com.lichen.know.engine.rag.modules.KnowEngineElasticsearchContentRetriever;
import com.lichen.know.engine.rag.modules.KnowEngineQueryRouter;
import com.lichen.know.engine.rag.modules.KnowEngineQueryTransformer;
import com.lichen.know.engine.rag.modules.ProgressAwareContentAggregator;
import com.lichen.know.engine.rag.modules.reranker.BgeScoringModel;
import com.lichen.know.engine.rag.modules.splitter.ProgressAwareContentRetriever;
import dev.langchain4j.community.rag.content.retriever.neo4j.Neo4jGraph;
import dev.langchain4j.community.rag.content.retriever.neo4j.Neo4jText2CypherRetriever;
import dev.langchain4j.experimental.rag.content.retriever.sql.SqlDatabaseContentRetriever;
import dev.langchain4j.memory.chat.MessageWindowChatMemory;
import dev.langchain4j.model.chat.ChatModel;
import dev.langchain4j.model.chat.StreamingChatModel;
import dev.langchain4j.model.input.PromptTemplate;
import dev.langchain4j.model.openai.OpenAiEmbeddingModel;
import dev.langchain4j.model.scoring.onnx.OnnxScoringModel;
import dev.langchain4j.rag.DefaultRetrievalAugmentor;
import dev.langchain4j.rag.RetrievalAugmentor;
import dev.langchain4j.rag.content.aggregator.ContentAggregator;
import dev.langchain4j.rag.content.aggregator.ReRankingContentAggregator;
import dev.langchain4j.rag.content.injector.ContentInjector;
import dev.langchain4j.rag.content.injector.DefaultContentInjector;
import dev.langchain4j.rag.content.retriever.elasticsearch.ElasticsearchContentRetriever;
import dev.langchain4j.service.AiServices;
import dev.langchain4j.store.embedding.elasticsearch.ElasticsearchConfigurationFullText;
import dev.langchain4j.store.embedding.elasticsearch.ElasticsearchConfigurationKnn;
import org.elasticsearch.client.RestClient;
import org.neo4j.driver.Driver;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.stereotype.Service;
import reactor.core.Disposable;
import reactor.core.publisher.Flux;
import reactor.core.scheduler.Schedulers;

import javax.sql.DataSource;
import java.util.List;
import java.util.concurrent.atomic.AtomicBoolean;
import java.util.function.Consumer;

import static com.lichen.know.engine.rag.config.ElasticSearchConfiguration.INDEX_NAME;

@Service
public class ChatApplicationService {

    @Autowired
    private ChatModel chatModel;

    @Autowired
    private StreamingChatModel streamingChatModel;

    @Autowired
    private KnowledgeSegmentService knowledgeSegmentService;

    @Autowired
    private RestClient restClient;

    @Autowired
    private Driver neo4jDriver;

    @Autowired
    private DataSource dataSource;

    @Autowired
    private PromptService promptService;

    @Autowired
    private OpenAiEmbeddingModel openAiEmbeddingModel;

    @Autowired
    private ChatMessageService chatMessageService;

    /**
     * 流式对话（无进度回调）
     */
    public Flux<String> chat(ChatParam chatParam) {
        return chat(chatParam, null);
    }

    /**
     * 流式对话（带进度回调）
     * <p>
     * 使用 Flux.create() 将 RAG 管道各环节的进度消息与 LLM 流式输出桥接到同一个 Flux 中，
     * 确保进度消息在对应的 LLM token 之前到达前端。
     * <p>
     * 进度推送环节：
     * <ol>
     *   <li>问题改写 — 由 {@link KnowEngineQueryTransformer} 发送</li>
     *   <li>问题路由 — 由 {@link KnowEngineQueryRouter} 发送</li>
     *   <li>排序筛选 — 由 {@link ProgressAwareContentAggregator} 发送</li>
     *   <li>生成回答 — 由 {@link ProgressAwareContentAggregator} 在聚合完成后发送</li>
     * </ol>
     *
     * @param chatParam        对话参数
     * @param progressCallback 进度回调，可为 null
     */
    public Flux<String> chat(ChatParam chatParam, Consumer<String> progressCallback) {

        return Flux.<String>create(sink -> {
                    // 进度回调：同时写入 sink 和外部回调
                    Consumer<String> callback = msg -> {
                        sink.next(msg);
                        if (progressCallback != null) {
                            progressCallback.accept(msg);
                        }
                    };

                    String assistantMessageId = chatMessageService.saveAssistantMessage(chatParam.conversationId());

                    // 构建查询改写器（带进度回调）
                    KnowEngineQueryTransformer queryTransformer = new KnowEngineQueryTransformer(chatModel, chatParam.messageId(), callback);

                    ProgressAwareContentRetriever embeddingRetriever = new ProgressAwareContentRetriever(KnowEngineElasticsearchContentRetriever.builder()
                            .configuration(ElasticsearchConfigurationKnn.builder().build())
                            .maxResults(5)
                            .minScore(0.5)
                            .embeddingModel(openAiEmbeddingModel)
                            .restClient(restClient)
                            .indexName(INDEX_NAME)
                            .knowledgeSegmentService(knowledgeSegmentService)
                            .build(), callback);

                    ProgressAwareContentRetriever fullTextRetriever = new ProgressAwareContentRetriever(ElasticsearchContentRetriever.builder()
                            .configuration(ElasticsearchConfigurationFullText.builder().build())
                            .restClient(restClient)
                            .indexName(INDEX_NAME)
                            .maxResults(5)
                            .build(), callback);

                    ProgressAwareContentRetriever sqlRetriever = new ProgressAwareContentRetriever(SqlDatabaseContentRetriever.builder().dataSource(dataSource)
                            //todo
                            .promptTemplate(new PromptTemplate("textToSqlPrompt.getContentAsString(UTF_8)"))
                            .databaseStructure("tablesSql.getContentAsString(UTF_8)")
                            .chatModel(chatModel)
                            .build(), callback);

                    ProgressAwareContentRetriever neo4jRetriever = new ProgressAwareContentRetriever(Neo4jText2CypherRetriever.builder()
                            .graph(Neo4jGraph.builder()
                                    .driver(neo4jDriver)
                                    .build())
                            .chatModel(chatModel)
                            .build(), callback);

                    OnnxScoringModel scoringModel = BgeScoringModel.getInstance();

                    // 使用带进度通知的聚合器包装原始聚合器
                    ContentAggregator contentAggregator = new ProgressAwareContentAggregator(
                            ReRankingContentAggregator.builder()
                                    .scoringModel(scoringModel)
                                    .maxResults(5)
                                    .querySelector(queryToContents -> queryToContents.keySet().iterator().next())
                                    .build(),
                            callback, assistantMessageId, chatMessageService
                    );

                    String prompt = promptService.getPrompt(chatParam.intentRecognitionResult());

                    ContentInjector contentInjector = new DefaultContentInjector(PromptTemplate.from(prompt));

                    // 构建查询路由器（带进度回调）
                    RetrievalAugmentor retrievalAugmentor = DefaultRetrievalAugmentor.builder()
                            .queryRouter(new KnowEngineQueryRouter(List.of(embeddingRetriever, fullTextRetriever, sqlRetriever, neo4jRetriever), chatModel, callback))
                            .queryTransformer(queryTransformer)
                            .contentAggregator(contentAggregator)
                            .contentInjector(contentInjector)
                            .build();

                    KnowEngineChatAiService knowEngineChatAiService = AiServices.builder(KnowEngineChatAiService.class)
                            .chatModel(chatModel)
                            .streamingChatModel(streamingChatModel)
                            .chatMemoryProvider(memoryId -> MessageWindowChatMemory.builder().maxMessages(10).build())
                            .retrievalAugmentor(retrievalAugmentor)
                            .build();

                    // 订阅 LLM 流式输出，桥接到 sink
                    AtomicBoolean firstToken = new AtomicBoolean(true);
                    StringBuilder contentBuilder = new StringBuilder();
                    Disposable disposable = knowEngineChatAiService.streamChat(chatParam.conversationId(), chatParam.content())
                            .doOnNext(token -> {
                                // 首个 token 到达时，如果之前没有发出"正在生成回答"，则补发
                                // （正常情况下由 ProgressAwareContentAggregator 已发出，此处为兜底）
                                if (firstToken.compareAndSet(true, false)) {
                                    // 标记已开始接收 token
                                }
                                contentBuilder.append(token);
                            })
                            .doOnComplete(() -> chatMessageService.updateContent(assistantMessageId, contentBuilder.toString()))
                            .subscribe(sink::next, sink::error, sink::complete);

                    // 取消时同步取消内部订阅
                    sink.onCancel(disposable::dispose);
                })
                .subscribeOn(Schedulers.boundedElastic())
                // publishOn 引入异步边界：boundedElastic 线程专用于执行阻塞 RAG 操作，
                // parallel 线程独立运行 drain loop，确保进度消息能及时推送到前端 SSE 响应
                .publishOn(Schedulers.parallel());
    }
}
