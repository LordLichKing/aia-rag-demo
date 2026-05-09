import logging
from typing import Optional

from app import get_settings

logger = logging.getLogger(__name__)


class RefusalHandler:
    def __init__(
        self,
        low_confidence_threshold: float = 0.3,
        refusal_message: Optional[str] = None,
    ):
        settings = get_settings()
        safety_cfg = settings.safety
        self.low_confidence_threshold = low_confidence_threshold
        self.refusal_message = refusal_message or safety_cfg.get(
            "refusal_message",
            "抱歉，我无法回答这个问题。请尝试联系相关部门获取更多信息。",
        )

    def get_no_context_refusal(self) -> str:
        return (
            "抱歉，根据现有知识库，我未能找到与您问题相关的信息。\n\n"
            "建议：\n"
            "- 请尝试换一种方式描述您的问题\n"
            "- 联系人力资源部门或相关部门获取更多信息\n"
            "- 查阅完整的员工手册或合规指南文档"
        )

    def get_low_confidence_refusal(self) -> str:
        return (
            "抱歉，我对该问题的回答信心较低，为避免提供不准确的信息，我建议：\n\n"
            "- 请联系相关部门确认具体细节\n"
            "- 查阅原始文档获取最准确的信息\n"
            "- 尝试更具体地描述您的问题"
        )

    def get_injection_refusal(self) -> str:
        return (
            "抱歉，您的问题无法被处理。请确保您的问题与内部知识库内容相关，"
            "并以正常方式提问。如需帮助，请联系IT支持部门。"
        )

    def get_out_of_scope_refusal(self) -> str:
        return (
            "抱歉，您的问题超出了内部知识库的范围。本系统仅支持回答关于"
            "员工手册、合规指南、技术规范和架构文档相关的问题。\n\n"
            "建议：请联系相关部门获取其他方面的信息。"
        )

    def get_error_refusal(self) -> str:
        return (
            "抱歉，系统暂时无法处理您的请求。请稍后重试或联系IT支持部门。"
        )

    def should_refuse(
        self,
        confidence: float,
        has_context: bool,
        is_injection: bool,
        is_out_of_scope: bool = False,
    ) -> tuple:
        if is_injection:
            return True, "prompt_injection", self.get_injection_refusal()
        if is_out_of_scope:
            return True, "out_of_scope", self.get_out_of_scope_refusal()
        if not has_context:
            return True, "no_context", self.get_no_context_refusal()
        if confidence < self.low_confidence_threshold:
            return True, "low_confidence", self.get_low_confidence_refusal()
        return False, None, None
