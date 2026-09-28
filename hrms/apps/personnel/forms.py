"""
人事管理模块表单。

关联需求：FR-PER-01 职工档案管理

设计说明：本表单只负责「档案」字段，**不含登录名与密码**。
账号开通与密码设置属于 FR-SYS-03 用户管理——让 HR 在填档案时
顺手设密码，是弱口令的主要来源。

@author 王坤尧
"""

from django import forms

from apps.sysconf.models import Employee

from .models import (
    Attendance,
    LeaveRequest,
    RegularizationApply,
    RewardPunish,
    SocialInsurance,
)

# 字段分组常量。定义为模块级而非类属性，因为嵌套的 Meta 类
# 无法访问外层类作用域，而 Meta.fields 又需要用到它们。
_BASIC_FIELDS = [
    'employee_no', 'real_name', 'gender', 'birth_date', 'id_card',
    'phone', 'education', 'political_status', 'graduate_school',
    'major', 'native_place', 'address',
]
_JOB_FIELDS = [
    'department', 'position', 'salary_level', 'employ_status',
    'hire_date', 'probation_end_date', 'regular_date', 'resign_date',
]

# 社保表单的分组常量（同样需为模块级，供嵌套 Meta 与模板共用）
_SI_BASIC_FIELDS = ['employee', 'period', 'insurance_base', 'remark']
_SI_PERSONAL_FIELDS = [
    'pension_personal', 'medical_personal',
    'unemployment_personal', 'housing_fund_personal',
]
_SI_COMPANY_FIELDS = [
    'pension_company', 'medical_company',
    'unemployment_company', 'housing_fund_company',
]


class EmployeeForm(forms.ModelForm):
    """职工档案新增 / 编辑表单。"""

    # 暴露给模板做分组渲染，避免模板里堆一长串 if 判断
    BASIC_FIELDS = _BASIC_FIELDS
    JOB_FIELDS = _JOB_FIELDS

    class Meta:
        model = Employee
        fields = _BASIC_FIELDS + _JOB_FIELDS
        widgets = {
            # 日期控件显式指定 %Y-%m-%d：
            # 中文 locale 下 Django 默认输出「2026年9月28日」，HTML5 的
            # <input type="date"> 不认这种格式，会显示为空
            'birth_date': forms.DateInput(format='%Y-%m-%d', attrs={'type': 'date'}),
            'hire_date': forms.DateInput(format='%Y-%m-%d', attrs={'type': 'date'}),
            'probation_end_date': forms.DateInput(format='%Y-%m-%d', attrs={'type': 'date'}),
            'regular_date': forms.DateInput(format='%Y-%m-%d', attrs={'type': 'date'}),
            'resign_date': forms.DateInput(format='%Y-%m-%d', attrs={'type': 'date'}),
            'address': forms.TextInput(),
        }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        # 统一为控件加上 Bootstrap 样式类：
        # Django 默认渲染的裸 <input> 没有样式，直接放进页面很难看
        for field in self.fields.values():
            widget = field.widget
            if isinstance(widget, (forms.Select, forms.SelectMultiple)):
                widget.attrs.setdefault('class', 'form-select')
            elif isinstance(widget, forms.CheckboxInput):
                widget.attrs.setdefault('class', 'form-check-input')
            else:
                widget.attrs.setdefault('class', 'form-control')

    def clean(self):
        """跨字段校验：日期的先后关系，以及「离职状态」与「离职日期」是否自洽。"""
        cleaned = super().clean()
        hire_date = cleaned.get('hire_date')
        resign_date = cleaned.get('resign_date')
        status = cleaned.get('employ_status')

        if hire_date and resign_date and resign_date < hire_date:
            self.add_error('resign_date', '离职日期不能早于入职日期。')

        if status == Employee.EmployStatus.RESIGNED and not resign_date:
            self.add_error('resign_date', '在职状态为「离职」时，必须填写离职日期。')

        if status != Employee.EmployStatus.RESIGNED and resign_date:
            self.add_error('employ_status', '已填写离职日期，在职状态应为「离职」。')

        return cleaned


class RegularizationApplyForm(forms.ModelForm):
    """转正申请表单（FR-PER-02）。

    只填「申请」部分：审批意见、审批人、审批时间由审批动作写入。
    放在同一张表单里会让申请人在提交时就能预设审批结果。
    """

    class Meta:
        model = RegularizationApply
        fields = [
            'employee', 'apply_date', 'original_status',
            'expect_regular_date', 'self_evaluation', 'department_opinion',
        ]
        widgets = {
            'apply_date': forms.DateInput(format='%Y-%m-%d', attrs={'type': 'date'}),
            'expect_regular_date': forms.DateInput(format='%Y-%m-%d', attrs={'type': 'date'}),
            'self_evaluation': forms.Textarea(attrs={'rows': 3}),
            'department_opinion': forms.Textarea(attrs={'rows': 3}),
        }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        # 只有「实习 / 试用」状态的员工才有转正一说，从源头限制可选范围
        self.fields['employee'].queryset = (
            Employee.objects
            .filter(
                is_deleted=False,
                employ_status__in=[
                    Employee.EmployStatus.INTERN,
                    Employee.EmployStatus.PROBATION,
                ],
            )
            .order_by('employee_no')
        )
        self._apply_bootstrap_classes()

    def _apply_bootstrap_classes(self):
        """统一为控件加上 Bootstrap 样式类，保证与档案表单观感一致。"""
        for field in self.fields.values():
            widget = field.widget
            if isinstance(widget, (forms.Select, forms.SelectMultiple)):
                widget.attrs.setdefault('class', 'form-select')
            elif isinstance(widget, forms.CheckboxInput):
                widget.attrs.setdefault('class', 'form-check-input')
            else:
                widget.attrs.setdefault('class', 'form-control')

    def clean_employee(self):
        employee = self.cleaned_data['employee']
        # 同一员工不允许存在多张待审批申请，否则审批通过时会重复转正
        if RegularizationApply.objects.filter(
            employee=employee, status=RegularizationApply.ApplyStatus.PENDING
        ).exists():
            raise forms.ValidationError('该员工已有待审批的转正申请，请先处理后再发起。')
        return employee


class RegularizationApproveForm(forms.Form):
    """转正审批表单：填写 HR 意见并选择通过或驳回。"""

    action = forms.ChoiceField(
        label='审批结果',
        choices=[('approve', '通过转正'), ('reject', '驳回申请')],
        widget=forms.RadioSelect,
        initial='approve',
    )
    hr_opinion = forms.CharField(
        label='HR 意见',
        required=False,
        widget=forms.Textarea(attrs={'rows': 3, 'class': 'form-control', 'placeholder': '可填写审批说明'}),
    )


class SocialInsuranceForm(forms.ModelForm):
    """社保缴纳记录表单（FR-PER-02）。

    personal_total / company_total 刻意**不出现在表单中**：
    它们由模型 save() 自动汇总。让人手工填「合计」迟早会和明细对不上。
    """

    # 供模板分组渲染。必须用**列表**而非逗号字符串：
    # 模板的 in 对字符串做的是子串匹配，字段名互为子串时会误判
    BASIC_FIELDS = _SI_BASIC_FIELDS
    PERSONAL_FIELDS = _SI_PERSONAL_FIELDS
    COMPANY_FIELDS = _SI_COMPANY_FIELDS

    class Meta:
        model = SocialInsurance
        fields = _SI_BASIC_FIELDS + _SI_PERSONAL_FIELDS + _SI_COMPANY_FIELDS
        widgets = {
            'period': forms.TextInput(attrs={'placeholder': '格式 YYYY-MM，如 2026-09'}),
        }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields['employee'].queryset = (
            Employee.objects.filter(is_deleted=False).order_by('employee_no')
        )
        for field in self.fields.values():
            widget = field.widget
            if isinstance(widget, (forms.Select, forms.SelectMultiple)):
                widget.attrs.setdefault('class', 'form-select')
            else:
                widget.attrs.setdefault('class', 'form-control')



def _apply_bootstrap(form):
    """给表单所有控件加上 Bootstrap 样式类。

    抽成函数而不是每个表单重复写：本项目有 6 个表单，
    这段循环重复六遍容易漏改。
    """
    for field in form.fields.values():
        widget = field.widget
        if isinstance(widget, (forms.Select, forms.SelectMultiple)):
            widget.attrs.setdefault('class', 'form-select')
        elif isinstance(widget, forms.CheckboxInput):
            widget.attrs.setdefault('class', 'form-check-input')
        else:
            widget.attrs.setdefault('class', 'form-control')


class AttendanceForm(forms.ModelForm):
    """考勤记录表单（FR-PER-03）。"""

    class Meta:
        model = Attendance
        fields = [
            'employee', 'work_date', 'status',
            'check_in', 'check_out', 'work_hours', 'remark',
        ]
        widgets = {
            'work_date': forms.DateInput(format='%Y-%m-%d', attrs={'type': 'date'}),
            'check_in': forms.TimeInput(format='%H:%M', attrs={'type': 'time'}),
            'check_out': forms.TimeInput(format='%H:%M', attrs={'type': 'time'}),
        }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields['employee'].queryset = (
            Employee.objects.filter(is_deleted=False).order_by('employee_no')
        )
        _apply_bootstrap(self)

    def clean(self):
        """校验打卡时间与工时的自洽性。"""
        cleaned = super().clean()
        check_in = cleaned.get('check_in')
        check_out = cleaned.get('check_out')
        if check_in and check_out and check_out <= check_in:
            self.add_error('check_out', '下班打卡时间必须晚于上班打卡时间。')
        return cleaned


class LeaveRequestForm(forms.ModelForm):
    """请假申请表（FR-PER-03、UC-05）。

    对应 SRS 6.4 活动图中的「表单校验通过？」判定节点。
    """

    class Meta:
        model = LeaveRequest
        fields = ['employee', 'leave_type', 'start_date', 'end_date', 'days', 'reason']
        widgets = {
            'start_date': forms.DateInput(format='%Y-%m-%d', attrs={'type': 'date'}),
            'end_date': forms.DateInput(format='%Y-%m-%d', attrs={'type': 'date'}),
            'reason': forms.Textarea(attrs={'rows': 3}),
        }

    def __init__(self, *args, user=None, **kwargs):
        super().__init__(*args, **kwargs)
        queryset = Employee.objects.filter(is_deleted=False).order_by('employee_no')
        # 非 HR 角色只能给自己提交：否则普通职工可以代别人请假
        if user is not None and not getattr(user, 'can_view_all', False):
            queryset = queryset.filter(pk=user.pk)
        self.fields['employee'].queryset = queryset
        _apply_bootstrap(self)

    def clean(self):
        """校验请假起止日期与天数（对应测试用例 TC-PER-03-01）。"""
        cleaned = super().clean()
        start = cleaned.get('start_date')
        end = cleaned.get('end_date')
        days = cleaned.get('days')

        if start and end and end < start:
            self.add_error('end_date', '结束日期不能早于开始日期。')

        if start and end and days and end >= start:
            natural_days = (end - start).days + 1
            if days > natural_days:
                self.add_error(
                    'days', f'请假天数不能超过起止日期覆盖的 {natural_days} 天。'
                )

        return cleaned


class LeaveApproveForm(forms.Form):
    """请假审批表单。"""

    action = forms.ChoiceField(
        label='审批结果',
        choices=[('approve', '通过'), ('reject', '驳回')],
        widget=forms.RadioSelect,
        initial='approve',
    )
    approve_opinion = forms.CharField(
        label='审批说明',
        required=False,
        widget=forms.Textarea(attrs={'rows': 3, 'class': 'form-control', 'placeholder': '可填写审批说明'}),
    )


class RewardPunishForm(forms.ModelForm):
    """奖罚登记表单（FR-PER-03）。"""

    class Meta:
        model = RewardPunish
        fields = ['employee', 'record_type', 'happen_date', 'title', 'amount', 'description']
        widgets = {
            'happen_date': forms.DateInput(format='%Y-%m-%d', attrs={'type': 'date'}),
            'description': forms.Textarea(attrs={'rows': 3}),
        }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields['employee'].queryset = (
            Employee.objects.filter(is_deleted=False).order_by('employee_no')
        )
        _apply_bootstrap(self)
