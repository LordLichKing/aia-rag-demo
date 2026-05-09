package com.lichen.know.engine.chat.entity;

import com.lichen.know.engine.chat.constant.ChatConversationStatus;
import com.lichen.know.engine.document.entity.BaseEntity;
import com.baomidou.mybatisplus.annotation.IdType;
import com.baomidou.mybatisplus.annotation.TableId;
import com.baomidou.mybatisplus.annotation.TableName;
import lombok.Data;

/**
 * AI对话会话表
 */
@Data
@TableName("chat_conversation")
public class ChatConversation extends BaseEntity {

    /**
     * 主键ID
     */
    @TableId(value = "id", type = IdType.AUTO)
    private Long id;

    /**
     * 会话唯一标识
     */
    private String conversationId;

    /**
     * 用户ID
     */
    private String userId;

    /**
     * 会话标题
     */
    private String title;

    /**
     * 状态
     */
    private ChatConversationStatus status;
}
