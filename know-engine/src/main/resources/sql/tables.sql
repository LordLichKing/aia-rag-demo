CREATE database if NOT EXISTS `know_engine` default character set utf8mb4 collate utf8mb4_unicode_ci;
use `know_engine`;

SET NAMES utf8mb4;

-- 知识文档表
CREATE TABLE `knowledge_document` (
    `doc_id`        BIGINT        NOT NULL AUTO_INCREMENT COMMENT '文档ID',
    `doc_title`     VARCHAR(1024) NOT NULL COMMENT '文档标题',
    `upload_user`   VARCHAR(255)  NULL     COMMENT '上传用户',
    `doc_url`       VARCHAR(2048) NULL     COMMENT '文档URL',
    `converted_doc_url` VARCHAR(2048) NULL  COMMENT '转换后的文档URL',
    `expire_date`   DATE          NULL     COMMENT '文档失效日期',
    `status`        VARCHAR(32)   NOT NULL COMMENT '状态：INIT, UPLOADED, CONVERTING, CONVERTED, CHUNKED, VECTOR_STORED',
    `accessible_by` VARCHAR(1024) NULL     COMMENT '可见范围',
    `description`   VARCHAR(512)  NULL     COMMENT '文档描述',
    `knowledge_base_type` VARCHAR(32) NULL COMMENT '知识库类型：DOCUMENT_SEARCH, DATA_QUERY',
    `extension`     TEXT          NULL     COMMENT '扩展字段，保存JSON字符串',
    `created_at`    DATETIME      NOT NULL DEFAULT CURRENT_TIMESTAMP COMMENT '创建时间',
    `updated_at`    DATETIME      NOT NULL DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP COMMENT '修改时间',
    `lock_version` INT           NOT NULL DEFAULT 0 COMMENT '乐观锁版本号',
    `deleted`       TINYINT      NOT NULL DEFAULT 0 COMMENT '是否删除：0-未删除，1-已删除',
    PRIMARY KEY (`doc_id`),
    -- 为状态字段添加索引，优化定时任务扫表性能
    INDEX `idx_status` (`status`),
    -- 复合索引：状态+文档ID，优化分页查询性能
    INDEX `idx_status_doc_id` (`status`, `doc_id`),
    -- 创建时间索引，优化按时间排序查询
    INDEX `idx_created_at` (`created_at`)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci COMMENT = '知识文档表';

-- 知识片段表
CREATE TABLE `knowledge_segment` (
    `id`          BIGINT       NOT NULL AUTO_INCREMENT COMMENT '片段ID',
    `text`        LONGTEXT     NOT NULL COMMENT '文本内容',
    `chunk_id`    VARCHAR(255) NULL     COMMENT '分片ID',
    `metadata`    VARCHAR(2048) NULL     COMMENT '元数据',
    `document_id` BIGINT       NOT NULL COMMENT '所属文档ID',
    `chunk_order` INT       NOT NULL COMMENT '顺序',
    `embedding_id` VARCHAR(255) NULL     COMMENT '嵌入ID',
    `status` VARCHAR(255) NULL     COMMENT '状态：STORED, VECTOR_STORED',
    `skip_embedding` INT NULL     COMMENT '是否跳过嵌入生成',
    `created_at`  DATETIME     NOT NULL DEFAULT CURRENT_TIMESTAMP COMMENT '创建时间',
    `updated_at`  DATETIME     NOT NULL DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP COMMENT '修改时间',
    `lock_version`  INT          NOT NULL DEFAULT 0 COMMENT '乐观锁版本号',
    `deleted`       TINYINT      NOT NULL DEFAULT 0 COMMENT '是否删除：0-未删除，1-已删除',
    PRIMARY KEY (`id`),
    -- 文档ID索引
    INDEX `idx_document_id` (`document_id`),
    -- 复合索引：文档ID+顺序，优化按文档查询并排序
    INDEX `idx_document_id_chunk_order` (`document_id`, `chunk_order`),
    -- 复合索引：文档ID+状态+跳过嵌入，优化向量化补偿任务查询
    INDEX `idx_document_status_skip` (`document_id`, `status`, `skip_embedding`),
    -- 状态索引，优化按状态查询
    INDEX `idx_status` (`status`)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci COMMENT = '知识片段表';

-- 表元数据表（存储动态创建的表的元数据信息）
CREATE TABLE `table_meta` (
    `id`           BIGINT       NOT NULL AUTO_INCREMENT COMMENT '主键ID',
    `table_name`   VARCHAR(128) NOT NULL COMMENT '表名',
    `description`  VARCHAR(512) NULL     COMMENT '表描述',
    `create_sql`   TEXT         NULL     COMMENT '建表语句',
    `columns_info` TEXT         NULL     COMMENT '字段信息（JSON格式）',
    `created_at`   DATETIME     NOT NULL DEFAULT CURRENT_TIMESTAMP COMMENT '创建时间',
    `updated_at`   DATETIME     NOT NULL DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP COMMENT '修改时间',
    `lock_version` INT          NOT NULL DEFAULT 0 COMMENT '乐观锁版本号',
    `deleted`      TINYINT      NOT NULL DEFAULT 0 COMMENT '是否删除：0-未删除，1-已删除',
    PRIMARY KEY (`id`),
    -- 表名唯一索引
    UNIQUE INDEX `uk_table_name` (`table_name`),
    -- 创建时间索引
    INDEX `idx_created_at` (`created_at`)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci COMMENT = '表元数据表';

-- AI对话会话表
CREATE TABLE `chat_conversation` (
    `id`              BIGINT      NOT NULL AUTO_INCREMENT COMMENT '主键ID',
    `conversation_id` VARCHAR(64) NOT NULL COMMENT '会话唯一标识',
    `user_id`         VARCHAR(64) NOT NULL COMMENT '用户ID',
    `title`           VARCHAR(512) NULL    COMMENT '会话标题',
    `created_at`   DATETIME     NOT NULL DEFAULT CURRENT_TIMESTAMP COMMENT '创建时间',
    `updated_at`   DATETIME     NOT NULL DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP COMMENT '修改时间',
    `lock_version` INT          NOT NULL DEFAULT 0 COMMENT '乐观锁版本号',
    `deleted`      TINYINT      NOT NULL DEFAULT 0 COMMENT '是否删除：0-未删除，1-已删除',
    `status`          VARCHAR(32) NOT NULL DEFAULT 'active' COMMENT '状态',
    PRIMARY KEY (`id`),
    UNIQUE KEY `uk_conversation_id` (`conversation_id`)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci COMMENT = 'AI对话会话表';

-- AI对话消息表
CREATE TABLE `chat_message` (
    `id`               BIGINT       NOT NULL AUTO_INCREMENT COMMENT '主键ID',
    `message_id`       VARCHAR(64)  NOT NULL COMMENT '消息唯一标识',
    `conversation_id`  VARCHAR(64)  NOT NULL COMMENT '所属会话ID',
    `type`             VARCHAR(32)  NOT NULL COMMENT '角色：USER/ASSISTANT',
    `content`          LONGTEXT     NULL     COMMENT '消息内容',
    `transform_content` LONGTEXT    NULL     COMMENT '改写后的内容',
    `token_count`      INT          NULL     COMMENT 'Token数量',
    `model_name`       VARCHAR(128) NULL     COMMENT '使用的模型名称',
    `rag_references`   JSON         NULL     COMMENT 'RAG引用内容JSON数组，包含document_id、document_title、chunk_id、chunk_content、similarity_score、retrieval_source等字段',
    `created_at`   DATETIME     NOT NULL DEFAULT CURRENT_TIMESTAMP COMMENT '创建时间',
    `updated_at`   DATETIME     NOT NULL DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP COMMENT '修改时间',
    `lock_version` INT          NOT NULL DEFAULT 0 COMMENT '乐观锁版本号',
    `deleted`      TINYINT      NOT NULL DEFAULT 0 COMMENT '是否删除：0-未删除，1-已删除',
    `metadata`         JSON         NULL     COMMENT '扩展元数据JSON格式',
    PRIMARY KEY (`id`),
    UNIQUE KEY `uk_message_id` (`message_id`),
    INDEX `idx_conversation_id` (`conversation_id`),
    INDEX `idx_create_time` (`created_at`)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci COMMENT = 'AI对话消息表';


CREATE database if NOT EXISTS `xxl_job` default character set utf8mb4 collate utf8mb4_unicode_ci;
use `xxl_job`;

SET NAMES utf8mb4;

## —————————————————————— job group and registry ——————————————————

CREATE TABLE `xxl_job_group`
(
    `id`           int(11)     NOT NULL AUTO_INCREMENT,
    `app_name`     varchar(64) NOT NULL COMMENT '执行器AppName',
    `title`        varchar(64) NOT NULL COMMENT '执行器名称',
    `address_type` tinyint(4)  NOT NULL DEFAULT '0' COMMENT '执行器地址类型：0=自动注册、1=手动录入',
    `address_list` text COMMENT '执行器地址列表，多地址逗号分隔',
    `update_time`  datetime             DEFAULT NULL,
    PRIMARY KEY (`id`)
) ENGINE = InnoDB
  DEFAULT CHARSET = utf8mb4;

CREATE TABLE `xxl_job_registry`
(
    `id`                bigint(20)   NOT NULL AUTO_INCREMENT,
    `registry_group`    varchar(50)  NOT NULL,
    `registry_key`      varchar(255) NOT NULL,
    `registry_value`    varchar(255) NOT NULL,
    `update_time`       datetime DEFAULT NULL,
    PRIMARY KEY (`id`),
    UNIQUE KEY `i_g_k_v` (`registry_group`, `registry_key`, `registry_value`) USING BTREE
) ENGINE = InnoDB
  DEFAULT CHARSET = utf8mb4;

## —————————————————————— job info ——————————————————

CREATE TABLE `xxl_job_info`
(
    `id`                        int(11)      NOT NULL AUTO_INCREMENT,
    `job_group`                 int(11)      NOT NULL COMMENT '执行器主键ID',
    `job_desc`                  varchar(255) NOT NULL,
    `add_time`                  datetime              DEFAULT NULL,
    `update_time`               datetime              DEFAULT NULL,
    `author`                    varchar(64)           DEFAULT NULL COMMENT '作者',
    `alarm_email`               varchar(255)          DEFAULT NULL COMMENT '报警邮件',
    `schedule_type`             varchar(50)  NOT NULL DEFAULT 'NONE' COMMENT '调度类型',
    `schedule_conf`             varchar(128)          DEFAULT NULL COMMENT '调度配置，值含义取决于调度类型',
    `misfire_strategy`          varchar(50)  NOT NULL DEFAULT 'DO_NOTHING' COMMENT '调度过期策略',
    `executor_route_strategy`   varchar(50)           DEFAULT NULL COMMENT '执行器路由策略',
    `executor_handler`          varchar(255)          DEFAULT NULL COMMENT '任务handler',
    `executor_param`            text                  DEFAULT NULL COMMENT '任务参数',
    `executor_block_strategy`   varchar(50)           DEFAULT NULL COMMENT '阻塞处理策略',
    `executor_timeout`          int(11)      NOT NULL DEFAULT '0' COMMENT '任务执行超时时间，单位秒',
    `executor_fail_retry_count` int(11)      NOT NULL DEFAULT '0' COMMENT '失败重试次数',
    `glue_type`                 varchar(50)  NOT NULL COMMENT 'GLUE类型',
    `glue_source`               mediumtext COMMENT 'GLUE源代码',
    `glue_remark`               varchar(128)          DEFAULT NULL COMMENT 'GLUE备注',
    `glue_updatetime`           datetime              DEFAULT NULL COMMENT 'GLUE更新时间',
    `child_jobid`               varchar(255)          DEFAULT NULL COMMENT '子任务ID，多个逗号分隔',
    `trigger_status`            tinyint(4)   NOT NULL DEFAULT '0' COMMENT '调度状态：0-停止，1-运行',
    `trigger_last_time`         bigint(13)   NOT NULL DEFAULT '0' COMMENT '上次调度时间',
    `trigger_next_time`         bigint(13)   NOT NULL DEFAULT '0' COMMENT '下次调度时间',
    PRIMARY KEY (`id`)
) ENGINE = InnoDB
  DEFAULT CHARSET = utf8mb4;

CREATE TABLE `xxl_job_logglue`
(
    `id`          int(11)      NOT NULL AUTO_INCREMENT,
    `job_id`      int(11)      NOT NULL COMMENT '任务，主键ID',
    `glue_type`   varchar(50) DEFAULT NULL COMMENT 'GLUE类型',
    `glue_source` mediumtext COMMENT 'GLUE源代码',
    `glue_remark` varchar(128) NOT NULL COMMENT 'GLUE备注',
    `add_time`    datetime    DEFAULT NULL,
    `update_time` datetime    DEFAULT NULL,
    PRIMARY KEY (`id`)
) ENGINE = InnoDB
  DEFAULT CHARSET = utf8mb4;

## —————————————————————— job log and report ——————————————————

CREATE TABLE `xxl_job_log`
(
    `id`                        bigint(20)          NOT NULL AUTO_INCREMENT,
    `job_group`                 int(11)             NOT NULL COMMENT '执行器主键ID',
    `job_id`                    int(11)             NOT NULL COMMENT '任务，主键ID',
    `executor_address`          varchar(255)        DEFAULT NULL COMMENT '执行器地址，本次执行的地址',
    `executor_handler`          varchar(255)        DEFAULT NULL COMMENT '任务handler',
    `executor_param`            text                DEFAULT NULL COMMENT '任务参数',
    `executor_sharding_param`   varchar(20)         DEFAULT NULL COMMENT '任务分片参数，格式如 1/2',
    `executor_fail_retry_count` int(11)             NOT NULL DEFAULT '0' COMMENT '失败重试次数',
    `trigger_time`              datetime            DEFAULT NULL COMMENT '调度-时间',
    `trigger_code`              int(11)             NOT NULL COMMENT '调度-结果',
    `trigger_msg`               text                COMMENT '调度-日志',
    `handle_time`               datetime            DEFAULT NULL COMMENT '执行-时间',
    `handle_code`               int(11)             NOT NULL COMMENT '执行-状态',
    `handle_msg`                text                COMMENT '执行-日志',
    `alarm_status`              tinyint(4)          NOT NULL DEFAULT '0' COMMENT '告警状态：0-默认、1-无需告警、2-告警成功、3-告警失败',
    PRIMARY KEY (`id`),
    KEY `I_trigger_time` (`trigger_time`),
    KEY `I_handle_code` (`handle_code`),
    KEY `I_jobgroup` (`job_group`),
    KEY `I_jobid` (`job_id`)
) ENGINE = InnoDB
  DEFAULT CHARSET = utf8mb4;

CREATE TABLE `xxl_job_log_report`
(
    `id`            int(11) NOT NULL AUTO_INCREMENT,
    `trigger_day`   datetime         DEFAULT NULL COMMENT '调度-时间',
    `running_count` int(11) NOT NULL DEFAULT '0' COMMENT '运行中-日志数量',
    `suc_count`     int(11) NOT NULL DEFAULT '0' COMMENT '执行成功-日志数量',
    `fail_count`    int(11) NOT NULL DEFAULT '0' COMMENT '执行失败-日志数量',
    `update_time`   datetime         DEFAULT NULL,
    PRIMARY KEY (`id`),
    UNIQUE KEY `i_trigger_day` (`trigger_day`) USING BTREE
) ENGINE = InnoDB
  DEFAULT CHARSET = utf8mb4;

## —————————————————————— lock ——————————————————

CREATE TABLE `xxl_job_lock`
(
    `lock_name` varchar(50) NOT NULL COMMENT '锁名称',
    PRIMARY KEY (`lock_name`)
) ENGINE = InnoDB
  DEFAULT CHARSET = utf8mb4;

## —————————————————————— user ——————————————————

CREATE TABLE `xxl_job_user`
(
    `id`         int(11)     NOT NULL AUTO_INCREMENT,
    `username`   varchar(50) NOT NULL COMMENT '账号',
    `password`   varchar(100) NOT NULL COMMENT '密码加密信息',
    `token`      varchar(100) DEFAULT NULL COMMENT '登录token',
    `role`       tinyint(4)  NOT NULL COMMENT '角色：0-普通用户、1-管理员',
    `permission` varchar(255) DEFAULT NULL COMMENT '权限：执行器ID列表，多个逗号分割',
    PRIMARY KEY (`id`),
    UNIQUE KEY `i_username` (`username`) USING BTREE
) ENGINE = InnoDB
  DEFAULT CHARSET = utf8mb4;


## —————————————————————— for default data ——————————————————

INSERT INTO `xxl_job_group`(`id`, `app_name`, `title`, `address_type`, `address_list`, `update_time`)
    VALUES (1, 'xxl-job-executor-sample', '通用执行器Sample', 0, NULL, now()),
           (2, 'xxl-job-executor-sample-ai', 'AI执行器Sample', 0, NULL, now());

INSERT INTO `xxl_job_info`(`id`, `job_group`, `job_desc`, `add_time`, `update_time`, `author`, `alarm_email`,
                           `schedule_type`, `schedule_conf`, `misfire_strategy`, `executor_route_strategy`,
                           `executor_handler`, `executor_param`, `executor_block_strategy`, `executor_timeout`,
                           `executor_fail_retry_count`, `glue_type`, `glue_source`, `glue_remark`, `glue_updatetime`,
                           `child_jobid`)
VALUES (1, 1, '示例任务01', now(), now(), 'XXL', '', 'CRON', '0 0 0 * * ? *',
        'DO_NOTHING', 'FIRST', 'demoJobHandler', '', 'SERIAL_EXECUTION', 0, 0, 'BEAN', '', 'GLUE代码初始化',
        now(), ''),
       (2, 2, 'Ollama示例任务', now(), now(), 'XXL', '', 'NONE', '',
        'DO_NOTHING', 'FIRST', 'ollamaJobHandler', '{
    "input": "Java实现二叉树层序遍历",
    "prompt": "你是一个研发工程师，擅长解决技术类问题。",
    "model": "qwen3.5:2b"
}', 'SERIAL_EXECUTION', 0, 0, 'BEAN', '', 'GLUE代码初始化',
        now(), ''),
       (3, 2, 'Dify示例任务', now(), now(), 'XXL', '', 'NONE', '',
        'DO_NOTHING', 'FIRST', 'difyWorkflowJobHandler', '{
    "inputs":{
        "input":"查询班级各学科前三名"
    },
    "user": "xxl-job",
    "baseUrl": "http://localhost/v1",
    "apiKey": "app-OUVgNUOQRIMokfmuJvBJoUTN"
}', 'SERIAL_EXECUTION', 0, 0, 'BEAN', '', 'GLUE代码初始化',
        now(), ''),
       (4, 2, 'OpenClaw示例任务', now(), now(), 'XXL', '', 'NONE', '',
        'DO_NOTHING', 'FIRST', 'openClawJobHandler', '{
    "input": "查看下上海今天得天气，给出出游建议",
    "prompt": "你是一个出游助手，擅长做旅游规划"
}', 'SERIAL_EXECUTION', 0, 0, 'BEAN', '', 'GLUE代码初始化',
        now(), '');

INSERT INTO `xxl_job_user`(`id`, `username`, `password`, `role`, `permission`)
VALUES (1, 'admin', '8d969eef6ecad3c29a3a629280e686cf0c3f5d5a86aff3ca12020c923adc6c92', 1, NULL);

INSERT INTO `xxl_job_lock` (`lock_name`)
VALUES ('schedule_lock');

commit;
