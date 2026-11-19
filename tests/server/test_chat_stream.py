"""SSE 流的内容过滤：只有模型自己说的话能进助手气泡。"""
import unittest

from langchain_core.messages import AIMessage, AIMessageChunk, HumanMessage, SystemMessage, ToolMessage

from src.server.routes.chat import _is_internal_tool, visible_text_content


class VisibleTextTests(unittest.TestCase):
    def test_ai_chunk_is_streamed(self):
        self.assertEqual(visible_text_content(AIMessageChunk(content="已生成柱状图")), "已生成柱状图")

    def test_ai_message_is_streamed(self):
        self.assertEqual(visible_text_content(AIMessage(content="完成")), "完成")

    def test_rubric_feedback_is_not_streamed(self):
        # rubric middleware 把评审意见作为 human 消息注入，它不能出现在助手气泡里
        feedback = HumanMessage(
            content="Address every failing criterion without regressing any criterion that already passes"
        )
        self.assertEqual(visible_text_content(feedback), "")

    def test_system_and_tool_messages_are_not_streamed(self):
        self.assertEqual(visible_text_content(SystemMessage(content="你是采购助手")), "")
        self.assertEqual(visible_text_content(ToolMessage(content="{\"code\":0}", tool_call_id="t1")), "")

    def test_blank_and_non_text_content_is_not_streamed(self):
        self.assertEqual(visible_text_content(AIMessageChunk(content="   ")), "")
        self.assertEqual(visible_text_content(AIMessageChunk(content=[{"type": "text", "text": "x"}])), "")


class InternalToolTests(unittest.TestCase):
    def test_grader_tool_is_internal(self):
        self.assertTrue(_is_internal_tool((), "GraderResponse"))

    def test_grader_namespace_is_internal(self):
        self.assertTrue(_is_internal_tool(("tools:rubric_grader",), "some_tool"))

    def test_business_tool_is_visible(self):
        self.assertFalse(_is_internal_tool((), "supplier_page"))


if __name__ == "__main__":
    unittest.main()
