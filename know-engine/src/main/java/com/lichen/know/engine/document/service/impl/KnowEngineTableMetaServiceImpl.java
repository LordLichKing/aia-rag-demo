package com.lichen.know.engine.document.service.impl;

import com.lichen.know.engine.document.entity.TableMeta;
import com.lichen.know.engine.document.mapper.TableMetaMapper;
import com.lichen.know.engine.document.service.KnowEngineTableMetaService;
import com.baomidou.mybatisplus.extension.service.impl.ServiceImpl;
import org.springframework.stereotype.Service;

/**
 * 知识片段表 Service 实现类
 */
@Service
public class KnowEngineTableMetaServiceImpl extends ServiceImpl<TableMetaMapper, TableMeta> implements KnowEngineTableMetaService {
}
