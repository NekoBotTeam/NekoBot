"""安全计算器模块

替换不安全的 eval() 调用，提供安全的表达式计算功能
参考 AstrBot 的安全实践
"""

import ast
import operator
from typing import Any, Union
from loguru import logger


class SafeCalculator:
    """安全计算器

    使用 AST 解析和白名单机制，避免 eval() 的安全风险
    只支持基本的数学运算，不支持任意代码执行
    """

    # 支持的运算符映射
    OPERATORS = {
        ast.Add: operator.add,
        ast.Sub: operator.sub,
        ast.Mult: operator.mul,
        ast.Div: operator.truediv,
        ast.FloorDiv: operator.floordiv,
        ast.Mod: operator.mod,
        ast.Pow: operator.pow,
        ast.USub: operator.neg,
        ast.UAdd: operator.pos,
    }

    # 支持的函数（数学函数）
    FUNCTIONS = {
        "abs": abs,
        "round": round,
        "min": min,
        "max": max,
        "sum": sum,
        "pow": pow,
    }

    # 支持的常数
    CONSTANTS = {
        "pi": 3.141592653589793,
        "e": 2.718281828459045,
    }

    def __init__(self, allow_functions: bool = True, allow_constants: bool = True):
        """初始化安全计算器

        Args:
            allow_functions: 是否允许内置函数
            allow_constants: 是否允许数学常数
        """
        self.allow_functions = allow_functions
        self.allow_constants = allow_constants

    def evaluate(self, expression: str) -> Union[int, float]:
        """安全地计算数学表达式

        Args:
            expression: 数学表达式字符串

        Returns:
            计算结果

        Raises:
            ValueError: 表达式不合法或不安全
            TypeError: 类型错误
            ZeroDivisionError: 除以零
        """
        try:
            # 解析表达式为 AST
            node = ast.parse(expression, mode="eval")

            # 检查和计算
            return self._eval(node.body)

        except (ValueError, TypeError, ZeroDivisionError):
            raise
        except Exception as e:
            raise ValueError(f"表达式计算失败: {e}") from e

    def _eval(self, node: ast.AST) -> Any:
        """递归计算 AST 节点

        Args:
            node: AST 节点

        Returns:
            计算结果

        Raises:
            ValueError: 不支持的操作
        """
        # 数字常量
        if isinstance(node, ast.Constant):
            if isinstance(node.value, (int, float)):
                return node.value
            elif isinstance(node.value, str) and self.allow_constants:
                # 检查是否是常数
                if node.value in self.CONSTANTS:
                    return self.CONSTANTS[node.value]
            raise ValueError(f"不支持的常量: {node.value}")

        # 变量名（用于常数）
        if isinstance(node, ast.Name):
            if self.allow_constants and node.id in self.CONSTANTS:
                return self.CONSTANTS[node.id]
            raise ValueError(f"不支持的变量: {node.id}")

        # 二元运算
        if isinstance(node, ast.BinOp):
            left = self._eval(node.left)
            right = self._eval(node.right)

            op_type = type(node.op)
            if op_type in self.OPERATORS:
                return self.OPERATORS[op_type](left, right)
            else:
                raise ValueError(f"不支持的运算符: {op_type.__name__}")

        # 一元运算
        if isinstance(node, ast.UnaryOp):
            operand = self._eval(node.operand)

            op_type = type(node.op)
            if op_type in self.OPERATORS:
                return self.OPERATORS[op_type](operand)
            else:
                raise ValueError(f"不支持的一元运算符: {op_type.__name__}")

        # 函数调用
        if isinstance(node, ast.Call):
            if not self.allow_functions:
                raise ValueError("函数调用已被禁用")

            func_name = None
            if isinstance(node.func, ast.Name):
                func_name = node.func.id
            elif isinstance(node.func, ast.Attribute):
                # 不支持属性访问
                raise ValueError(f"不支持的方法调用: {ast.unparse(node.func)}")

            if func_name in self.FUNCTIONS:
                args = [self._eval(arg) for arg in node.args]
                return self.FUNCTIONS[func_name](*args)
            else:
                raise ValueError(f"不支持的函数: {func_name}")

        # 表达式列表（用于逗号分隔的表达式）
        if isinstance(node, ast.Tuple):
            return tuple(self._eval(elt) for elt in node.elts)

        # 括号分组（已自动处理，不需要特殊处理）

        raise ValueError(f"不支持的语法结构: {type(node).__name__}")

    def is_safe_expression(self, expression: str) -> bool:
        """检查表达式是否安全

        Args:
            expression: 要检查的表达式

        Returns:
            是否安全
        """
        try:
            self.evaluate(expression)
            return True
        except Exception:
            return False


class AdvancedSafeCalculator(SafeCalculator):
    """高级安全计算器

    支持更多数学函数和操作
    """

    def __init__(self):
        """初始化高级计算器"""
        super().__init__(allow_functions=True, allow_constants=True)

        # 添加更多数学函数
        try:
            import math
            self.FUNCTIONS.update({
                "sin": math.sin,
                "cos": math.cos,
                "tan": math.tan,
                "sqrt": math.sqrt,
                "log": math.log,
                "log10": math.log10,
                "exp": math.exp,
                "ceil": math.ceil,
                "floor": math.floor,
                "factorial": math.factorial,
            })
            self.CONSTANTS.update({
                "pi": math.pi,
                "e": math.e,
                "inf": float("inf"),
            })
            logger.debug("高级计算器已启用，支持 math 模块函数")
        except ImportError:
            logger.warning("math 模块不可用，使用基础功能")


def safe_calculate(expression: str, advanced: bool = False) -> str:
    """安全计算表达式的便捷函数

    Args:
        expression: 数学表达式
        advanced: 是否使用高级计算器

    Returns:
        计算结果的字符串表示

    Examples:
        >>> safe_calculate("2 + 3 * 4")
        '14'
        >>> safe_calculate("sin(pi/2)", advanced=True)
        '1.0'
    """
    try:
        calculator = AdvancedSafeCalculator() if advanced else SafeCalculator()
        result = calculator.evaluate(expression)

        # 格式化结果
        if isinstance(result, float):
            # 移除不必要的 .0
            if result.is_integer():
                return str(int(result))
            # 限制小数位数
            return f"{result:.10g}".rstrip("0").rstrip(".") if "." in f"{result:.10g}" else str(result)
        else:
            return str(result)

    except Exception as e:
        logger.error(f"安全计算失败: {e}")
        return f"计算失败: {e}"


__all__ = [
    "SafeCalculator",
    "AdvancedSafeCalculator",
    "safe_calculate",
]
