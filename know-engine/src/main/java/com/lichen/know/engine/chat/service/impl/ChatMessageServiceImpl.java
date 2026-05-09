package com.lichen.know.engine.chat.service.impl;

import com.lichen.know.engine.chat.constant.ChatMessageType;
import com.lichen.know.engine.chat.entity.ChatMessage;
import com.lichen.know.engine.chat.mapper.ChatMessageMapper;
import com.lichen.know.engine.chat.service.ChatMessageService;
import com.baomidou.mybatisplus.core.conditions.query.LambdaQueryWrapper;
import com.baomidou.mybatisplus.extension.plugins.pagination.Page;
import com.baomidou.mybatisplus.extension.service.impl.ServiceImpl;
import org.springframework.stereotype.Service;

import java.time.LocalDateTime;
import java.util.List;
import java.util.UUID;

/**
 * AI对话消息表 Service 实现类
 */
@Service
public class ChatMessageServiceImpl extends ServiceImpl<ChatMessageMapper, ChatMessage> implements ChatMessageService {

    @Override
    public List<ChatMessage> getMessagesByConversationId(String conversationId) {
        return this.list(new LambdaQueryWrapper<ChatMessage>()
                .eq(ChatMessage::getConversationId, conversationId)
                .orderByAsc(ChatMessage::getCreatedAt));
    }

    @Override
    public ChatMessage getByMessageId(String messageId) {
        return this.getOne(new LambdaQueryWrapper<ChatMessage>()
                .eq(ChatMessage::getMessageId, messageId));
    }

    @Override
    public String saveUserMessage(String conversationId, String content) {
        String messageId = UUID.randomUUID().toString().replace("-", "");

        ChatMessage message = new ChatMessage();
        message.setMessageId(messageId);
        message.setConversationId(conversationId);
        message.setType(ChatMessageType.USER);
        message.setContent(content);
        message.setCreatedAt(LocalDateTime.now());

        this.save(message);
        return messageId;
    }

    @Override
    public void updateTransformContent(String messageId, String transformContent) {
        ChatMessage update = new ChatMessage();
        update.setTransformContent(transformContent);
        this.update(update, new LambdaQueryWrapper<ChatMessage>()
                .eq(ChatMessage::getMessageId, messageId));
    }

    @Override
    public void updateRagReferences(String messageId, List<ChatMessage.RagReference> ragReferences) {
        ChatMessage update = new ChatMessage();
        update.setRagReferences(ragReferences);
        this.update(update, new LambdaQueryWrapper<ChatMessage>()
                .eq(ChatMessage::getMessageId, messageId));
    }

    @Override
    public void updateContent(String messageId, String content) {
        ChatMessage update = new ChatMessage();
        update.setContent(content);
        this.update(update, new LambdaQueryWrapper<ChatMessage>()
                .eq(ChatMessage::getMessageId, messageId));
    }

    @Override
    public String saveAssistantMessage(String conversationId) {
        String messageId = UUID.randomUUID().toString().replace("-", "");

        ChatMessage message = new ChatMessage();
        message.setMessageId(messageId);
        message.setConversationId(conversationId);
        message.setType(ChatMessageType.ASSISTANT);
        message.setCreatedAt(LocalDateTime.now());

        this.save(message);
        return messageId;
    }

    @Override
    public boolean deleteMessagesByConversationId(String conversationId) {
        return this.remove(new LambdaQueryWrapper<ChatMessage>()
                .eq(ChatMessage::getConversationId, conversationId));
    }

    @Override
    public List<ChatMessage> getRecentMessages(String conversationId, int limit) {
        Page<ChatMessage> page = this.page(
                new Page<>(1, limit),
                new LambdaQueryWrapper<ChatMessage>()
                        .eq(ChatMessage::getConversationId, conversationId)
                        .orderByDesc(ChatMessage::getCreatedAt)
        );

        // 返回列表需要反转，使其按时间正序排列
        List<ChatMessage> records = page.getRecords();
        java.util.Collections.reverse(records);
        return records;
    }
}
