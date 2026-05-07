"""生命周期钩子注册方法模块

包含钩子注册、注销和清除相关方法。

此模块作为 facade，组合 DecoratorMixin 和 UnregisterMixin。
"""

from src.lifecycle_hooks._decorator import DecoratorMixin
from src.lifecycle_hooks._unregister import UnregisterMixin


class RegistrationMixin(DecoratorMixin, UnregisterMixin):
    """钩子注册方法 mixin

    组合装饰器模式和注销功能。
    """
    pass


__all__ = ["DecoratorMixin", "RegistrationMixin", "UnregisterMixin"]