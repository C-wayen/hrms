"""
公共查询模块表单。

关联需求：FR-QRY-02 通知套红与打印

@author 王坤尧
"""

from django import forms

from apps.sysconf.models import Employee

from .models import NotificationDoc


class NotificationDocForm(forms.ModelForm):
    """人事变动通知单表单（FR-QRY-02）。

    「套红」是公文红头格式，由打印模板负责呈现，本表单只管正文数据。
    """

    class Meta:
        model = NotificationDoc
        fields = [
            'doc_no', 'doc_type', 'title', 'employee',
            'content', 'issue_date', 'issuer', 'related_transfer',
        ]
        widgets = {
            'issue_date': forms.DateInput(format='%Y-%m-%d', attrs={'type': 'date'}),
            'content': forms.Textarea(attrs={'rows': 6}),
        }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)

        self.fields['employee'].queryset = (
            Employee.objects.filter(is_deleted=False).order_by('employee_no')
        )
        # 签发人默认为当前用户（在视图中赋值），此处允许留空
        self.fields['issuer'].queryset = (
            Employee.objects.filter(is_deleted=False).order_by('employee_no')
        )

        for field in self.fields.values():
            widget = field.widget
            if isinstance(widget, (forms.Select, forms.SelectMultiple)):
                widget.attrs.setdefault('class', 'form-select')
            elif isinstance(widget, forms.CheckboxInput):
                widget.attrs.setdefault('class', 'form-check-input')
            else:
                widget.attrs.setdefault('class', 'form-control')
