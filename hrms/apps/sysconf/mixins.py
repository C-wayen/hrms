"""
视图层通用工具。

对应需求：FR-SYS-01 权限控制、FR-SYS-02 基础数据、FR-SYS-03 用户与菜单管理

为什么放在 sysconf 而不是各模块自己留一份：sysconf 是所有业务模块的依赖底座
（Employee 在此），共用件放这里，依赖方向才是单向的（各模块 → sysconf）；
反过来让基础模块去 import 薪酬模块取一个 mixin，就成反向依赖了。

@author 王坤尧
"""


class FormPageMixin:
    """为新增 / 编辑表单页补齐统一的页面上下文。

    把这三个键抽出来的原因：各模块的新增与编辑视图有几十处都要传它们，
    任何一处写漏，模板就会渲染出一个没有标题、取消按钮指向错误页面的表单。
    """

    page_title = ''
    form_hint = ''
    cancel_url = ''

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context['page_title'] = self.page_title
        context['form_hint'] = self.form_hint
        context['cancel_url'] = self.cancel_url
        return context
