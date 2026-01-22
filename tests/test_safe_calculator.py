"""安全计算器单元测试

测试安全计算器的功能和安全特性
"""

import pytest
from packages.provider.safe_calculator import (
    SafeCalculator,
    AdvancedSafeCalculator,
    safe_calculate,
)


class TestSafeCalculator:
    """安全计算器测试"""

    @pytest.fixture
    def calculator(self):
        return SafeCalculator()

    def test_basic_arithmetic(self, calculator):
        """测试基本算术运算"""
        assert calculator.evaluate("1 + 2") == 3
        assert calculator.evaluate("5 - 3") == 2
        assert calculator.evaluate("2 * 3") == 6
        assert calculator.evaluate("10 / 2") == 5
        assert calculator.evaluate("7 // 2") == 3
        assert calculator.evaluate("7 % 3") == 1
        assert calculator.evaluate("2 ** 3") == 8

    def test_operator_precedence(self, calculator):
        """测试运算符优先级"""
        assert calculator.evaluate("1 + 2 * 3") == 7
        assert calculator.evaluate("(1 + 2) * 3") == 9
        assert calculator.evaluate("2 ** 3 * 4") == 32

    def test_unary_operators(self, calculator):
        """测试一元运算符"""
        assert calculator.evaluate("-5") == -5
        assert calculator.evaluate("+5") == 5
        assert calculator.evaluate("--5") == 5
        assert calculator.evaluate("-(2 + 3)") == -5

    def test_complex_expressions(self, calculator):
        """测试复杂表达式"""
        assert calculator.evaluate("(1 + 2) * (3 - 1)") == 6
        assert calculator.evaluate("((2 + 3) * 4) - 10") == 10
        assert calculator.evaluate("10 - (2 + 3) * 2") == 0

    def test_float_division(self, calculator):
        """测试浮点除法"""
        result = calculator.evaluate("7 / 2")
        assert result == 3.5

        result = calculator.evaluate("1 / 3")
        assert abs(result - 0.333333) < 0.001

    def test_security_code_execution(self, calculator):
        """测试防止代码执行"""
        # 这些应该被拒绝
        with pytest.raises(ValueError, match="不支持的"):
            calculator.evaluate("__import__('os').system('ls')")

        with pytest.raises(ValueError, match="不支持的"):
            calculator.evaluate("print('hello')")

        with pytest.raises(ValueError, match="不支持的"):
            calculator.evaluate("exec('1+1')")

    def test_security_import_attempts(self, calculator):
        """测试防止导入尝试"""
        with pytest.raises(ValueError):
            calculator.evaluate("import os")

        with pytest.raises(ValueError):
            calculator.evaluate("from math import sqrt")

    def test_security_function_calls(self, calculator):
        """测试未授权的函数调用"""
        with pytest.raises(ValueError):
            calculator.evaluate("eval('1+1')")

        with pytest.raises(ValueError):
            calculator.evaluate("open('/etc/passwd')")

    def test_built_in_functions_disabled(self, calculator):
        """测试内置函数默认禁用"""
        with pytest.raises(ValueError):
            calculator.evaluate("abs(-5)")

        with pytest.raises(ValueError):
            calculator.evaluate("max(1, 2, 3)")

    def test_constants_disabled(self, calculator):
        """测试常数默认禁用"""
        with pytest.raises(ValueError):
            calculator.evaluate("pi")

        with pytest.raises(ValueError):
            calculator.evaluate("e")

    def test_error_handling(self, calculator):
        """测试错误处理"""
        # 语法错误
        with pytest.raises(ValueError):
            calculator.evaluate("1 + ")

        # 除以零
        with pytest.raises(ZeroDivisionError):
            calculator.evaluate("1 / 0")

        # 未定义的变量
        with pytest.raises(ValueError):
            calculator.evaluate("undefined_var + 1")

    def test_empty_expression(self, calculator):
        """测试空表达式"""
        with pytest.raises(ValueError):
            calculator.evaluate("")

    def test_is_safe_expression(self, calculator):
        """测试安全表达式检查"""
        assert calculator.is_safe_expression("1 + 2") is True
        assert calculator.is_safe_expression("2 * 3") is True
        assert calculator.is_safe_expression("__import__('os')") is False
        assert calculator.is_safe_expression("print('test')") is False


class TestAdvancedSafeCalculator:
    """高级安全计算器测试"""

    @pytest.fixture
    def calculator(self):
        try:
            return AdvancedSafeCalculator()
        except Exception:
            pytest.skip("math module not available")

    def test_math_constants(self, calculator):
        """测试数学常数"""
        import math
        result = calculator.evaluate("pi")
        assert abs(result - math.pi) < 0.001

        result = calculator.evaluate("e")
        assert abs(result - math.e) < 0.001

    def test_math_functions(self, calculator):
        """测试数学函数"""
        # 三角函数
        result = calculator.evaluate("sin(pi/2)")
        assert abs(result - 1.0) < 0.001

        result = calculator.evaluate("cos(0)")
        assert abs(result - 1.0) < 0.001

        # 其他函数
        result = calculator.evaluate("sqrt(16)")
        assert result == 4

        result = calculator.evaluate("abs(-5)")
        assert result == 5

        result = calculator.evaluate("round(3.7)")
        assert result == 4

    def test_complex_math_expressions(self, calculator):
        """测试复杂数学表达式"""
        result = calculator.evaluate("sin(pi/2) + cos(0)")
        assert abs(result - 2.0) < 0.001

        result = calculator.evaluate("sqrt(16) * 2")
        assert result == 8

    def test_security_advanced(self, calculator):
        """测试高级模式仍然安全"""
        with pytest.raises(ValueError):
            calculator.evaluate("__import__('os')")

        with pytest.raises(ValueError):
            calculator.evaluate("eval('1+1')")


class TestSafeCalculateFunction:
    """便捷函数测试"""

    def test_basic_calculation(self):
        """测试基本计算"""
        assert safe_calculate("1 + 2") == "3"
        assert safe_calculate("2 * 3") == "6"
        assert safe_calculate("10 / 2") == "5"

    def test_advanced_calculation(self):
        """测试高级计算"""
        result = safe_calculate("sin(pi/2)", advanced=True)
        assert "1.0" in result or "1" in result

    def test_error_handling(self):
        """测试错误处理"""
        result = safe_calculate("1 / 0")
        assert "失败" in result or "error" in result.lower()

        result = safe_calculate("print('test')")
        assert "失败" in result or "error" in result.lower()

    def test_float_formatting(self):
        """测试浮点数格式化"""
        # 整数结果不应有小数点
        result = safe_calculate("5.0")
        assert result == "5"

        # 小数应该保留
        result = safe_calculate("3.14159")
        assert "3.14" in result

    def test_complex_expression_formatting(self):
        """测试复杂表达式格式化"""
        result = safe_calculate("(1 + 2) * 3")
        assert result == "9"

        result = safe_calculate("10 / 3")
        # 应该有合理的精度
        assert "3.33" in result or "3.3" in result


class TestSecurityEdgeCases:
    """安全边界情况测试"""

    @pytest.fixture
    def calculator(self):
        return SafeCalculator()

    def test_string_injection(self, calculator):
        """测试字符串注入攻击"""
        with pytest.raises(ValueError):
            calculator.evaluate("''.__class__")

        with pytest.raises(ValueError):
            calculator.evaluate("''['__class__']")

    def test_attribute_access(self, calculator):
        """测试属性访问"""
        with pytest.raises(ValueError):
            calculator.evaluate("(1).__class__")

        with pytest.raises(ValueError):
            calculator.evaluate("(1).real")

    def test_subscript_access(self, calculator):
        """测试下标访问"""
        with pytest.raises(ValueError):
            calculator.evaluate("[1, 2, 3][0]")

        with pytest.raises(ValueError):
            calculator.evaluate("'hello'[0]")

    def test_lambda_expressions(self, calculator):
        """测试 lambda 表达式"""
        with pytest.raises(ValueError):
            calculator.evaluate("lambda x: x + 1")

    def test_list_comprehension(self, calculator):
        """测试列表推导式"""
        with pytest.raises(ValueError):
            calculator.evaluate("[x for x in range(10)]")

    def test_dict_comprehension(self, calculator):
        """测试字典推导式"""
        with pytest.raises(ValueError):
            calculator.evaluate("{x: x for x in range(3)}")

    def test_ternary_operator(self, calculator):
        """测试三元运算符"""
        with pytest.raises(ValueError):
            calculator.evaluate("1 if True else 0")

    def test_walrus_operator(self, calculator):
        """测试海象运算符"""
        # Python 3.8+
        with pytest.raises(ValueError):
            calculator.evaluate("(x := 5) + 1")


class TestPerformance:
    """性能测试"""

    def test_simple_performance(self):
        """测试简单表达式性能"""
        import time
        calculator = SafeCalculator()

        start = time.time()
        for _ in range(1000):
            calculator.evaluate("1 + 2 * 3")
        elapsed = time.time() - start

        # 1000 次计算应该在合理时间内完成
        assert elapsed < 1.0

    def test_complex_expression_performance(self):
        """测试复杂表达式性能"""
        import time
        calculator = SafeCalculator()

        expression = "((1 + 2) * 3 - 4) / 2 + 5 ** 2 - 10"

        start = time.time()
        for _ in range(1000):
            calculator.evaluate(expression)
        elapsed = time.time() - start

        assert elapsed < 2.0
