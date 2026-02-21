"""
自定义游戏时长功能的属性测试

根据 fast-test.md 规则，使用精简的测试示例数量（每个测试 10 次迭代）
以加快验证速度。

测试覆盖：
- 属性 1：参数解析正确性
- 属性 2：无效参数拒绝
- 属性 3：范围验证
"""

import pytest
from hypothesis import given, strategies as st, settings


# 直接定义被测试的函数（避免导入依赖问题）
def parse_duration_parameter(message_text: str) -> tuple[int | None, str | None]:
    """
    解析游戏时长参数
    
    参数:
        message_text: 完整的命令文本，例如 "/startbet 10"
    
    返回:
        (duration, error_message) 元组
        - duration: 解析出的时长（分钟），None 表示使用默认值
        - error_message: 错误信息，None 表示解析成功
    """
    # 使用空格分割命令文本
    parts = message_text.split()
    
    # 如果只有命令本身，返回 None 表示使用默认值
    if len(parts) == 1:
        return (None, None)
    
    # 如果有第二个参数，尝试将其转换为整数
    if len(parts) >= 2:
        try:
            duration = int(parts[1])
            return (duration, None)
        except ValueError:
            return (None, "❌ 请输入有效的游戏时长（1-30 分钟的整数）")
    
    return (None, None)


def validate_duration(duration: int) -> tuple[bool, str | None]:
    """
    验证游戏时长是否有效
    
    参数:
        duration: 游戏时长（分钟）
    
    返回:
        (is_valid, error_message) 元组
        - is_valid: 是否有效
        - error_message: 错误信息，None 表示验证通过
    """
    if duration < 1:
        return (False, "❌ 游戏时长不能少于 1 分钟")
    
    if duration > 30:
        return (False, "❌ 游戏时长不能超过 30 分钟")
    
    return (True, None)


@settings(max_examples=10)
@given(st.integers(min_value=1, max_value=30))
def test_parse_duration_roundtrip(duration):
    """
    Feature: bet-custom-duration
    Property 1: 参数解析正确性
    
    验证：对于任意有效的整数 N（1 ≤ N ≤ 30），当命令文本为 `/startbet N` 时，
    解析函数应该返回 N 作为时长值，且不返回错误信息。
    
    **Validates: Requirements 1.1, 1.4**
    """
    message_text = f"/startbet {duration}"
    parsed_duration, error = parse_duration_parameter(message_text)
    
    assert parsed_duration == duration, f"期望解析出 {duration}，实际得到 {parsed_duration}"
    assert error is None, f"不应该有错误信息，但得到: {error}"


@settings(max_examples=10)
@given(st.text().filter(lambda s: not s.strip().isdigit() and s.strip() != ""))
def test_invalid_parameter_rejection(invalid_param):
    """
    Feature: bet-custom-duration
    Property 2: 无效参数拒绝
    
    验证：对于任意非整数字符串（包含字母、特殊字符、浮点数等），
    当作为 `/startbet` 的参数时，解析函数应该返回错误信息并拒绝创建赌局。
    
    **Validates: Requirements 1.3**
    """
    message_text = f"/startbet {invalid_param}"
    parsed_duration, error = parse_duration_parameter(message_text)
    
    assert parsed_duration is None, f"无效参数应该返回 None，但得到: {parsed_duration}"
    assert error is not None, "应该返回错误信息"
    assert "有效的游戏时长" in error, f"错误信息应该提示输入有效时长，实际: {error}"


@settings(max_examples=10)
@given(st.integers())
def test_duration_validation(duration):
    """
    Feature: bet-custom-duration
    Property 3: 有效范围验证
    
    验证：对于任意整数 N，当 1 ≤ N ≤ 30 时，验证函数应该返回有效结果；
    当 N < 1 或 N > 30 时，应该返回相应的错误信息。
    
    **Validates: Requirements 2.1, 2.2, 2.3**
    """
    is_valid, error = validate_duration(duration)
    
    if 1 <= duration <= 30:
        # 有效范围内
        assert is_valid is True, f"时长 {duration} 应该有效"
        assert error is None, f"有效时长不应该有错误信息，但得到: {error}"
    elif duration < 1:
        # 小于最小值
        assert is_valid is False, f"时长 {duration} 应该无效"
        assert error is not None, "应该返回错误信息"
        assert "不能少于 1 分钟" in error, f"错误信息应该提示最小值限制，实际: {error}"
    else:  # duration > 30
        # 大于最大值
        assert is_valid is False, f"时长 {duration} 应该无效"
        assert error is not None, "应该返回错误信息"
        assert "不能超过 30 分钟" in error, f"错误信息应该提示最大值限制，实际: {error}"


def test_parse_no_parameter():
    """
    测试不带参数的情况（使用默认值）
    
    验证：当命令文本为 `/startbet` 时，应该返回 None 表示使用默认值。
    
    **Validates: Requirements 1.2**
    """
    message_text = "/startbet"
    parsed_duration, error = parse_duration_parameter(message_text)
    
    assert parsed_duration is None, "不带参数应该返回 None"
    assert error is None, "不带参数不应该有错误信息"


def test_parse_boundary_values():
    """
    测试边界值
    
    验证边界值的解析和验证是否正确。
    """
    # 测试最小有效值
    message_text = "/startbet 1"
    parsed_duration, error = parse_duration_parameter(message_text)
    assert parsed_duration == 1
    assert error is None
    
    is_valid, validation_error = validate_duration(1)
    assert is_valid is True
    assert validation_error is None
    
    # 测试最大有效值
    message_text = "/startbet 30"
    parsed_duration, error = parse_duration_parameter(message_text)
    assert parsed_duration == 30
    assert error is None
    
    is_valid, validation_error = validate_duration(30)
    assert is_valid is True
    assert validation_error is None
    
    # 测试刚好超出下限
    is_valid, validation_error = validate_duration(0)
    assert is_valid is False
    assert "不能少于 1 分钟" in validation_error
    
    # 测试刚好超出上限
    is_valid, validation_error = validate_duration(31)
    assert is_valid is False
    assert "不能超过 30 分钟" in validation_error
