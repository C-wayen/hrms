"""
薪酬管理模块表单。

关联需求：FR-SAL-01 薪酬体系配置、FR-SAL-02 工资核算、FR-SAL-03 加班与水电登记

设计说明：三类登记记录（加班 / 水电 / 产量）的「所属薪酬周期」一律由业务日期
（加班日期、生产日期）自动推导，不交给用户手填。原因：手填的周期一旦与日期
不一致，工资就会落到错误的月份，而这种错误在列表页上完全看不出来，
只有等到员工发现工资条不对才会暴露。

@author 王坤尧
"""

import re

from django import forms

from apps.sysconf.models import Department

from .models import (
    OvertimeRecord,
    PieceworkRecord,
    SalaryLevel,
    SalaryStandard,
    UtilityFeeRecord,
)

# 薪酬周期统一为 'YYYY-MM'，与 SalaryRecord.salary_period 的 max_length=7 约束一致
PERIOD_RE = re.compile(r'^\d{4}-(0[1-9]|1[0-2])$')


class MonthInput(forms.TextInput):
    """HTML5 月份选择器。

    用它而不是两个下拉框的原因：salary_period 本身就是 'YYYY-MM' 字符串，
    原生 <input type="month"> 提交的值格式恰好一致，无需任何转换代码。
    """

    input_type = 'month'


def validate_period(value: str) -> None:
    """校验薪酬周期格式。

    在表单层拦住非法值，而不是留给数据库按 max_length 截断——
    截断后的 '2026-9' 会静默匹配不到任何记录，症状是「工资全是 0」。
    """
    if value and not PERIOD_RE.match(value):
        raise forms.ValidationError('薪酬周期格式应为 YYYY-MM，例如 2026-09。')


def _apply_bootstrap(form) -> None:
    """统一为控件加上 Bootstrap 样式类，保证与其它模块观感一致。"""
    for field in form.fields.values():
        widget = field.widget
        if isinstance(widget, (forms.Select, forms.SelectMultiple)):
            widget.attrs.setdefault('class', 'form-select')
        elif isinstance(widget, forms.CheckboxInput):
            widget.attrs.setdefault('class', 'form-check-input')
        else:
            widget.attrs.setdefault('class', 'form-control')


# =============================================================================
# 一、薪酬体系（FR-SAL-01）
# =============================================================================


class SalaryLevelForm(forms.ModelForm):
    """薪酬级别表单（FR-SAL-01）。"""

    class Meta:
        model = SalaryLevel
        fields = ['code', 'name', 'base_salary', 'post_allowance', 'is_active', 'remark']


class SalaryStandardForm(forms.ModelForm):
    """薪酬标准表单（FR-SAL-01、FR-SYS-02）。

    标准按生效日期版本化，因此新增一条即代表「从某日起改用新标准」，
    不做覆盖式编辑——覆盖后历史工资就再也算不出来了。
    """

    class Meta:
        model = SalaryStandard
        fields = [
            'effective_date',
            'overtime_workday_rate',
            'overtime_weekend_rate',
            'overtime_holiday_rate',
            'monthly_work_hours',
            'water_price',
            'electricity_price',
            'social_insurance_ratio',
            'is_active',
        ]
        widgets = {
            'effective_date': forms.DateInput(format='%Y-%m-%d', attrs={'type': 'date'}),
        }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        _apply_bootstrap(self)

    def clean_social_insurance_ratio(self):
        """把「百分数写法」挡在门外。"""
        ratio = self.cleaned_data.get('social_insurance_ratio') or 0
        # 写成 10.5 这种百分数几乎必然导致社保扣款算成十倍，
        # 且症状是「工资变成负数」，排查起来很绕，因此在入口直接拦住
        if ratio > 1:
            raise forms.ValidationError('请填小数形式的比例：10.5% 应填 0.105。')
        if ratio < 0:
            raise forms.ValidationError('比例不能为负数。')
        return ratio

    def clean_monthly_work_hours(self):
        """月标准工时必须为正，否则折算加班时薪时会除零。"""
        hours = self.cleaned_data.get('monthly_work_hours') or 0
        if hours <= 0:
            raise forms.ValidationError('月标准工时必须大于 0，否则无法折算加班时薪。')
        return hours


# =============================================================================
# 二、津贴与扣减项登记（FR-SAL-03、FR-SAL-02）
# =============================================================================


class OvertimeRecordForm(forms.ModelForm):
    """加班登记表单（FR-SAL-03）。"""

    class Meta:
        model = OvertimeRecord
        fields = ['employee', 'overtime_date', 'overtime_type', 'hours', 'reason']
        widgets = {
            'overtime_date': forms.DateInput(format='%Y-%m-%d', attrs={'type': 'date'}),
        }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        _apply_bootstrap(self)
        # 只列出未删除、且配置了薪酬级别的在职员工：没有级别的员工算不出加班时薪
        self.fields['employee'].queryset = self.fields['employee'].queryset.filter(
            is_deleted=False, salary_level__isnull=False
        ).select_related('department')

    def clean_hours(self):
        hours = self.cleaned_data.get('hours') or 0
        if hours <= 0:
            raise forms.ValidationError('加班时长必须大于 0。')
        # 单日加班超过 24 小时显然是录入错误，提前拦截避免污染工资
        if hours > 24:
            raise forms.ValidationError('单条加班时长不应超过 24 小时。')
        return hours

    def save(self, commit=True):
        """保存前由加班日期推导所属薪酬周期，保证两者永远一致。"""
        instance = super().save(commit=False)
        instance.salary_period = self.cleaned_data['overtime_date'].strftime('%Y-%m')
        if commit:
            instance.save()
        return instance


class UtilityFeeRecordForm(forms.ModelForm):
    """水电费扣费登记表单（FR-SAL-03）。"""

    class Meta:
        model = UtilityFeeRecord
        fields = [
            'employee', 'salary_period',
            'water_usage', 'water_fee', 'electricity_usage', 'electricity_fee',
            'remark',
        ]
        widgets = {
            'salary_period': MonthInput(),
        }
        help_texts = {
            'water_fee': '留空则按「用水量 × 薪酬标准中的水费单价」自动计算',
            'electricity_fee': '留空则按「用电量 × 薪酬标准中的电费单价」自动计算',
        }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        _apply_bootstrap(self)
        self.fields['employee'].queryset = self.fields['employee'].queryset.filter(
            is_deleted=False
        ).select_related('department')

    def clean_salary_period(self):
        period = (self.cleaned_data.get('salary_period') or '').strip()
        validate_period(period)
        return period

    def clean(self):
        """抄表数与金额至少填一项，否则这条记录对工资毫无影响。"""
        cleaned = super().clean()
        if not cleaned.get('water_usage') and not cleaned.get('water_fee') \
                and not cleaned.get('electricity_usage') and not cleaned.get('electricity_fee'):
            raise forms.ValidationError('用水、用电的抄表数与金额不能全为空。')
        return cleaned

    def save(self, commit=True):
        """未填金额时按薪酬标准单价自动算出，避免手工算错。"""
        instance = super().save(commit=False)
        standard = SalaryStandard.get_for_period(instance.salary_period)
        if standard:
            if not instance.water_fee and instance.water_usage:
                instance.water_fee = instance.water_usage * standard.water_price
            if not instance.electricity_fee and instance.electricity_usage:
                instance.electricity_fee = instance.electricity_usage * standard.electricity_price
        if commit:
            instance.save()
        return instance


class PieceworkRecordForm(forms.ModelForm):
    """计件 / 计时产量登记表单（FR-SAL-02）。"""

    class Meta:
        model = PieceworkRecord
        fields = [
            'employee', 'work_date', 'work_mode', 'product_name',
            'quantity', 'unit_price', 'hours', 'hourly_rate', 'remark',
        ]
        widgets = {
            'work_date': forms.DateInput(format='%Y-%m-%d', attrs={'type': 'date'}),
        }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        _apply_bootstrap(self)
        self.fields['employee'].queryset = self.fields['employee'].queryset.filter(
            is_deleted=False
        ).select_related('department')

    def clean(self):
        """按计薪方式校验必填项。

        模型上 quantity / hours 都有 default=0，所以数据库不会报错，
        但只填了「计件」的字段却选了「计时」，金额会静默算成 0，
        员工当月工资因此少一块。必须在表单层拦住。
        """
        cleaned = super().clean()
        work_mode = cleaned.get('work_mode')
        if work_mode == PieceworkRecord.WorkMode.PIECEWORK:
            if not cleaned.get('quantity') or not cleaned.get('unit_price'):
                raise forms.ValidationError('计件方式必须填写「数量」与「单价」。')
        elif work_mode == PieceworkRecord.WorkMode.TIMEWORK:
            if not cleaned.get('hours') or not cleaned.get('hourly_rate'):
                raise forms.ValidationError('计时方式必须填写「工时」与「时薪」。')
        return cleaned

    def save(self, commit=True):
        """保存前由生产日期推导所属薪酬周期，保证两者永远一致。"""
        instance = super().save(commit=False)
        instance.salary_period = self.cleaned_data['work_date'].strftime('%Y-%m')
        if commit:
            instance.save()
        return instance


# =============================================================================
# 三、工资核算（FR-SAL-02）
# =============================================================================


class SalaryCalculateForm(forms.Form):
    """工资核算参数表单（FR-SAL-02）。"""

    salary_period = forms.CharField(
        label='薪酬周期',
        widget=MonthInput(),
        help_text='要核算哪个月的工资',
    )
    department = forms.ModelChoiceField(
        label='核算范围',
        queryset=Department.objects.all(),
        required=False,
        empty_label='全体员工',
        widget=forms.Select(),
        help_text='留空表示核算全体员工；也可只核算某个部门',
    )

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        _apply_bootstrap(self)

    def clean_salary_period(self):
        period = (self.cleaned_data.get('salary_period') or '').strip()
        validate_period(period)
        return period
