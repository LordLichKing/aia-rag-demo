package com.lichen.know.engine.document.controller;

import com.lichen.know.engine.document.entity.DocumentSplitParam;
import com.lichen.know.engine.document.entity.DocumentUploadParam;
import com.lichen.know.engine.document.entity.KnowledgeDocument;
import com.lichen.know.engine.document.service.DocumentProcessService;
import com.lichen.know.engine.document.service.KnowledgeDocumentService;
import com.lichen.know.engine.document.service.impl.PdfProcessServiceImpl;
import com.baomidou.mybatisplus.core.conditions.query.QueryWrapper;
import com.baomidou.mybatisplus.extension.plugins.pagination.Page;
import dev.langchain4j.data.embedding.Embedding;
import dev.langchain4j.data.segment.TextSegment;
import dev.langchain4j.model.openai.OpenAiEmbeddingModel;
import dev.langchain4j.store.embedding.EmbeddingMatch;
import dev.langchain4j.store.embedding.EmbeddingSearchRequest;
import dev.langchain4j.store.embedding.EmbeddingSearchResult;
import dev.langchain4j.store.embedding.elasticsearch.ElasticsearchEmbeddingStore;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.web.bind.annotation.*;
import org.springframework.web.multipart.MultipartFile;

import java.io.IOException;
import java.util.List;

/**
 * 知识文档表 Controller
 */
@RestController
@RequestMapping("/api/document")
public class KnowledgeDocumentController {

    @Autowired
    private KnowledgeDocumentService knowledgeDocumentService;

    @Autowired
    private DocumentProcessService documentProcessService;

    @Autowired
    private PdfProcessServiceImpl fileProcessService;

    /**
     * 文件上传接口
     *
     * @param file         上传的文件
     * @param uploadUser   上传用户
     * @param accessibleBy 可见范围（可选）
     * @return 保存后的文档记录
     */
    @PostMapping("/upload")
    public KnowledgeDocument uploadFile(
            @RequestParam("file") MultipartFile file,
            @RequestParam("uploadUser") String uploadUser,
            @RequestParam("title") String title,
            @RequestParam(value = "tableName", required = false) String tableName,
            @RequestParam("description") String description,
            @RequestParam("knowledgeBaseType") String knowledgeBaseType,
            @RequestParam(value = "accessibleBy", required = false) String accessibleBy) throws IOException {
        return documentProcessService.upload(new DocumentUploadParam(file, uploadUser, title, accessibleBy, description, knowledgeBaseType, tableName));
    }

    /**
     * 对文档进行切分
     * 注意：此方法为手动触发切分接口，正常流程由事件驱动自动执行
     *
     * @param documentId 文档ID
     * @return 切分后的片段数量
     */
    @PostMapping("/split/{documentId}")
    public Integer splitDocument(@PathVariable Long documentId,
                                 @RequestParam("splitType") String splitType,
                                 @RequestParam("chunkSize") Integer chunkSize,
                                 @RequestParam(value = "overlap", required = false) Integer overlap,
                                 @RequestParam(value = "regex", required = false) String regex,
                                 @RequestParam(value = "titleLevel", required = false) Integer titleLevel,
                                 @RequestParam(value = "separator", required = false) String separator
    ) {
        KnowledgeDocument document = knowledgeDocumentService.getById(documentId);
        return documentProcessService.split(document, new DocumentSplitParam(splitType, chunkSize, overlap, titleLevel, separator, regex));
    }

    /**
     * 向量化并存储
     * 注意：此方法为手动触发向量化接口，正常流程由事件驱动自动执行
     *
     * @param docId 文档ID
     * @return 结果
     */
    @PostMapping("/embedding")
    public String embedding(Long docId) {
        KnowledgeDocument document = knowledgeDocumentService.getById(docId);
        return documentProcessService.embedAndStore(document) ? "success" : "failed";
    }

    /**
     * 分页查询
     */
    @GetMapping("/page")
    public Page<KnowledgeDocument> page(
            @RequestParam(defaultValue = "1") Integer current,
            @RequestParam(defaultValue = "10") Integer size) {
        return knowledgeDocumentService.page(new Page<>(current, size));
    }

    /**
     * 根据ID查询
     */
    @GetMapping("/{id:\\d+}")
    public KnowledgeDocument getById(@PathVariable Long id) {
        return knowledgeDocumentService.getById(id);
    }

    /**
     * 根据状态查询列表
     */
    @GetMapping("/list-by-status")
    public List<KnowledgeDocument> listByStatus(@RequestParam String status) {
        QueryWrapper<KnowledgeDocument> wrapper = new QueryWrapper<>();
        wrapper.eq("status", status);
        return knowledgeDocumentService.list(wrapper);
    }

    /**
     * 获取图片描述
     * 用于测试
     *
     * @param url 图片URL
     * @return 图片描述
     */
    @GetMapping("/image-desc")
    public String getImageDesc(String url) {
        return fileProcessService.generateImageDescription(url);
    }

    @Autowired
    private OpenAiEmbeddingModel openAiEmbeddingModel;

    @Autowired
    private ElasticsearchEmbeddingStore embeddingStore;

    /**
     * 根据查询问题返回相关文档
     * <p>
     * 主要用于测试
     *
     * @param query
     * @return
     */
    @GetMapping("/askDocument")
    public String askDocument(String query) {
        Embedding queryEmbedding = openAiEmbeddingModel.embed(query).content();

        EmbeddingSearchResult<TextSegment> relevant = embeddingStore.search(
                EmbeddingSearchRequest.builder()
                        .queryEmbedding(queryEmbedding)
                        .minScore(0.7)
                        .build());

        if (relevant.matches().size() > 0) {
            EmbeddingMatch<TextSegment> embeddingMatch = relevant.matches().get(0);

            System.out.println(embeddingMatch.score());
            System.out.println(embeddingMatch.embedded().text());

            return embeddingMatch.embedded().text();
        } else {
            return "No relevant documents found.";
        }
    }
}
