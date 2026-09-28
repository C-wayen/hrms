"""
菜单相关的自定义模板标签。

@author 王坤尧
"""

from django import template
from django.urls import NoReverseMatch, reverse

register = template.Library()


@register.simple_tag
def menu_url(name):
    """安全解析菜单路由名；路由尚未实现时返回 '#'。

    必要性：导航菜单是数据库驱动的配置数据，允许先配菜单、后实现页面。
    若模板里直接用 {% url %}，遇到未实现的路由会抛 NoReverseMatch，
    导致「改一条菜单配置就让全站 500」。这里兜底为 '#'，把配置错误
    降级为「点了没反应」，而不是整站崩溃。
    """
    if not name:
        return '#'
    try:
        return reverse(name)
    except NoReverseMatch:
        return '#'
