"""
培训管理模块表单。

关联需求：FR-TRN-01 课程与方案管理、FR-TRN-02 专项培训

@author 王坤尧
"""

from django import forms

from .models import Course, TrainingPlan, TrainingRecord


def _apply_bootstrap(form):
    """统一为控件加上 Bootstrap 样式类，保证与人事模块观感一致。"""
    for field in form.fields.values():
        widget = field.widget
        if isinstance(widget, (forms.Select, forms.SelectMultiple)):
            widget.attrs.setdefault('class', 'form-select')
        elif isinstance(widget, forms.CheckboxInput):
            widget.attrs.setdefault('class', 'form-check-input')
        else:
            widget.attrs.setdefault('class', 'form-control')


class CourseForm(forms.ModelForm):
    """培训课程表单（FR-TRN-01）。"""

    class Meta:
        model = Course
        fields = [
            'code', 'name', 'course_type', 'instructor',
            'duration_hours', 'description', 'is_active',
        ]
        widgets = {
            'description': forms.Textarea(attrs={'rows': 3}),
        }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        _apply_bootstrap(self)


class TrainingPlanForm(forms.ModelForm):
    """培训计划表单（FR-TRN-01）。"""

    class Meta:
        model = TrainingPlan
        fields = [
            'name', 'course', 'start_date', 'end_date', 'location',
            'target_departments', 'planned_headcount', 'status',
            'organizer', 'remark',
        ]
        widgets = {
            'start_date': forms.DateInput(format='%Y-%m-%d', attrs={'type': 'date'}),
            'end_date': forms.DateInput(format='%Y-%m-%d', attrs={'type': 'date'}),
        }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        _apply_bootstrap(self)
        # 多选部门给个合适的高度，否则浏览器默认只露一行
        self.fields['target_departments'].widget.attrs['size'] = 6

    def clean(self):
        """校验培训起止日期的先后关系。"""
        cleaned = super().clean()
        start = cleaned.get('start_date')
        end = cleaned.get('end_date')
        if start and end and end < start:
            self.add_error('end_date', '结束日期不能早于开始日期。')
        return cleaned


class TrainingRecordForm(forms.ModelForm):
    """培训记录与成绩表单（FR-TRN-02）。"""

    class Meta:
        model = TrainingRecord
        fields = ['plan', 'employee', 'attend_status', 'score', 'certificate_no', 'remark']

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        _apply_bootstrap(self)

    def clean(self):
        """校验考核状态与成绩的自洽性。

        没有这条校验，就会出现「考核通过但没有成绩」的记录，
        让 FR-TRN-02「成绩登记」名存实亡。
        """
        cleaned = super().clean()
        status = cleaned.get('attend_status')
        score = cleaned.get('score')
        graded = (
            TrainingRecord.AttendStatus.PASSED,
            TrainingRecord.AttendStatus.FAILED,
        )
        if status in graded and score is None:
            self.add_error('score', '状态为「考核通过 / 考核未通过」时必须填写成绩。')
        return cleaned
