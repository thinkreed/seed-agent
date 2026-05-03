"""
ask_user_types.py 单元测试

测试：
- QuestionOption: 选项定义
- Question: 问题定义
- UserResponse: 用户响应
- AskUserRequest: 请求结构
- AskUserResult: 结果结构
- AskUserState: 状态管理
"""

import sys
import unittest
from pathlib import Path

# 添加项目根目录到 Python 路径
project_root = Path(__file__).parent.parent
sys.path.insert(0, str(project_root))
sys.path.insert(0, str(project_root / "src"))

from tools.ask_user_types import (
    QuestionOption,
    Question,
    QuestionType,
    UserResponse,
    AskUserRequest,
    AskUserResult,
    AskUserState,
    get_ask_user_state,
    reset_ask_user_state,
)


class TestQuestionOption(unittest.TestCase):
    """测试 QuestionOption"""

    def test_basic_option(self):
        """基本选项"""
        opt = QuestionOption(label="Yes")
        self.assertEqual(opt.label, "Yes")
        self.assertEqual(opt.value, "Yes")  # 默认等于 label
        self.assertIsNone(opt.description)

    def test_option_with_value(self):
        """带值的选项"""
        opt = QuestionOption(label="确认", value="confirm")
        self.assertEqual(opt.label, "确认")
        self.assertEqual(opt.value, "confirm")

    def test_option_with_description(self):
        """带描述的选项"""
        opt = QuestionOption(label="Yes", description="Proceed with action")
        self.assertEqual(opt.description, "Proceed with action")

    def test_to_dict(self):
        """转换为字典"""
        opt = QuestionOption(label="Yes", value="yes", description="Confirm")
        d = opt.to_dict()

        self.assertEqual(d["label"], "Yes")
        self.assertEqual(d["value"], "yes")
        self.assertEqual(d["description"], "Confirm")


class TestQuestion(unittest.TestCase):
    """测试 Question"""

    def test_basic_question(self):
        """基本问题"""
        q = Question(
            question="Continue?",
            header="Confirm",
            options=[QuestionOption(label="Yes"), QuestionOption(label="No")]
        )

        self.assertEqual(q.question, "Continue?")
        self.assertEqual(q.header, "Confirm")
        self.assertEqual(len(q.options), 2)
        self.assertEqual(q.question_type, QuestionType.SINGLE_SELECT)

    def test_header_truncated(self):
        """header 自动截断"""
        q = Question(
            question="Test",
            header="This is a very long header that should be truncated",
            options=[QuestionOption(label="Yes"), QuestionOption(label="No")]
        )

        self.assertEqual(len(q.header), 30)

    def test_multi_select_sets_type(self):
        """多选设置类型"""
        q = Question(
            question="Select files",
            header="Files",
            options=[
                QuestionOption(label="File A"),
                QuestionOption(label="File B")
            ],
            multi_select=True
        )

        self.assertEqual(q.question_type, QuestionType.MULTI_SELECT)

    def test_confirmation_auto_options(self):
        """确认类型自动设置选项"""
        q = Question(
            question="Are you sure?",
            header="Confirm",
            question_type=QuestionType.CONFIRMATION
        )

        self.assertEqual(len(q.options), 2)
        self.assertEqual(q.options[0].value, "yes")
        self.assertEqual(q.options[1].value, "no")

    def test_to_dict(self):
        """转换为字典"""
        q = Question(
            question="Test?",
            header="Test",
            options=[QuestionOption(label="Yes"), QuestionOption(label="No")]
        )
        d = q.to_dict()

        self.assertEqual(d["question"], "Test?")
        self.assertEqual(d["header"], "Test")
        self.assertEqual(d["options"], [{"label": "Yes", "value": "Yes"}, {"label": "No", "value": "No"}])


class TestUserResponse(unittest.TestCase):
    """测试 UserResponse"""

    def test_basic_response(self):
        """基本响应"""
        resp = UserResponse(question_id="0", selected=["Yes"])
        self.assertEqual(resp.question_id, "0")
        self.assertEqual(resp.selected, ["Yes"])
        self.assertIsNone(resp.custom_input)

    def test_response_with_custom(self):
        """带自定义输入"""
        resp = UserResponse(question_id="0", selected=["custom"], custom_input="My custom text")
        self.assertEqual(resp.custom_input, "My custom text")

    def test_to_dict(self):
        """转换为字典"""
        resp = UserResponse(question_id="0", selected=["Yes"], custom_input="test")
        d = resp.to_dict()

        self.assertEqual(d["question_id"], "0")
        self.assertEqual(d["selected"], ["Yes"])
        self.assertEqual(d["custom_input"], "test")


class TestAskUserRequest(unittest.TestCase):
    """测试 AskUserRequest"""

    def test_basic_request(self):
        """基本请求"""
        q = Question(
            question="Test?",
            header="Test",
            options=[QuestionOption(label="Yes"), QuestionOption(label="No")]
        )
        req = AskUserRequest(questions=[q], session_id="test_session")

        self.assertEqual(len(req.questions), 1)
        self.assertEqual(req.session_id, "test_session")
        self.assertTrue(req.request_id)  # 自动生成

    def test_from_simple(self):
        """从简单参数创建"""
        req = AskUserRequest.from_simple(
            question="Continue?",
            options=["Yes", "No"],
            header="Confirm",
            session_id="test"
        )

        self.assertEqual(len(req.questions), 1)
        self.assertEqual(req.questions[0].question, "Continue?")
        self.assertEqual(len(req.questions[0].options), 2)

    def test_to_dict(self):
        """转换为字典"""
        req = AskUserRequest.from_simple(question="Test?", session_id="test")
        d = req.to_dict()

        self.assertEqual(d["session_id"], "test")
        self.assertEqual(len(d["questions"]), 1)


class TestAskUserResult(unittest.TestCase):
    """测试 AskUserResult"""

    def test_basic_result(self):
        """基本结果"""
        resp = UserResponse(question_id="0", selected=["Yes"])
        result = AskUserResult(request_id="abc123", responses=[resp])

        self.assertEqual(result.request_id, "abc123")
        self.assertEqual(len(result.responses), 1)
        self.assertFalse(result.cancelled)
        self.assertFalse(result.timeout)

    def test_cancelled_result(self):
        """取消结果"""
        result = AskUserResult.cancelled_result("abc123")

        self.assertTrue(result.cancelled)
        self.assertEqual(result.request_id, "abc123")

    def test_timeout_result(self):
        """超时结果"""
        result = AskUserResult.timeout_result("abc123")

        self.assertTrue(result.timeout)
        self.assertEqual(result.request_id, "abc123")

    def test_get_selected_values(self):
        """获取选中值"""
        resp1 = UserResponse(question_id="0", selected=["Yes"])
        resp2 = UserResponse(question_id="1", selected=["Option A", "Option B"])
        result = AskUserResult(request_id="test", responses=[resp1, resp2])

        values = result.get_selected_values()
        self.assertEqual(values, ["Yes", "Option A", "Option B"])

    def test_get_first_selected(self):
        """获取第一个选中值"""
        result = AskUserResult(
            request_id="test",
            responses=[UserResponse(question_id="0", selected=["Yes"])]
        )

        self.assertEqual(result.get_first_selected(), "Yes")


class TestAskUserState(unittest.TestCase):
    """测试 AskUserState"""

    def test_initial_state(self):
        """初始状态"""
        state = AskUserState()
        self.assertIsNone(state.pending_request)
        self.assertIsNone(state.response)
        self.assertFalse(state.is_waiting())

    def test_set_request(self):
        """设置请求"""
        state = AskUserState()
        req = AskUserRequest.from_simple(question="Test?")
        state.set_request(req)

        self.assertEqual(state.pending_request, req)
        self.assertTrue(state.is_waiting())

    def test_inject_response(self):
        """注入响应"""
        state = AskUserState()
        req = AskUserRequest.from_simple(question="Test?")
        state.set_request(req)

        result = AskUserResult(request_id=req.request_id, responses=[])
        state.inject_response(result)

        self.assertEqual(state.response, result)
        self.assertIsNone(state.pending_request)
        self.assertFalse(state.is_waiting())

    def test_clear(self):
        """清理状态"""
        state = AskUserState()
        req = AskUserRequest.from_simple(question="Test?")
        state.set_request(req)
        state.clear()

        self.assertIsNone(state.pending_request)
        self.assertIsNone(state.response)

    def test_global_state(self):
        """全局状态"""
        reset_ask_user_state()
        state = get_ask_user_state()

        self.assertIsInstance(state, AskUserState)
        self.assertFalse(state.is_waiting())


if __name__ == '__main__':
    unittest.main()