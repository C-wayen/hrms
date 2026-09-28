"""
智能应答机器人模块数据模型。

    FaqItem    FAQ 知识库          FR-AI-01
    ChatLog    问答交互记录        FR-AI-01、FR-AI-02

应答策略（对应 SRS 3.1 的服务端渲染架构）：

    1. 制度类 FAQ 提问   → 关键词命中 FaqItem，直接返回答案，不调模型
    2. 个人数据类提问    → 意图槽位识别 + SQL 模板直接查库（如「我还有几天年假」）
    3. 上述未命中        → 当 AI_PROVIDER=cloud 时转 DeepSeek；
                          请求超时或异常则回落规则模式，并提示「当前为离线问答」

因此答辩演示无需联网，也不会因 API 故障而翻车。

对应文档：HRMS/code_artifact.md（SRS V1.1）

@author 王坤尧
"""

from django.db import models

from apps.sysconf.models import Employee


class FaqItem(models.Model):
    """FAQ 知识库条目。

    对应 FR-AI-01「员工可向机器人询问社保缴费比例、请假流程、薪酬发放日等问题」。
    keywords 用逗号分隔的触发词做匹配，兼顾命中率与可维护性——
    HR 在后台改关键词就能调整应答效果，不需要改代码。
    """

    question = models.CharField('标准问题', max_length=200)
    answer = models.TextField('标准答案')
    keywords = models.CharField(
        '触发关键词', max_length=200,
        help_text='多个关键词用英文逗号分隔，命中任一即视为匹配',
    )
    category = models.CharField('分类', max_length=50, blank=True)
    sort_order = models.PositiveIntegerField('排序号', default=0)
    hit_count = models.PositiveIntegerField('命中次数', default=0)
    is_active = models.BooleanField('是否启用', default=True)
    created_at = models.DateTimeField('创建时间', auto_now_add=True)
    updated_at = models.DateTimeField('更新时间', auto_now=True)

    class Meta:
        verbose_name = 'FAQ 知识库'
        verbose_name_plural = 'FAQ 知识库'
        ordering = ['category', 'sort_order']

    def __str__(self):
        return self.question

    def keyword_list(self) -> list:
        """返回拆分后的关键词列表，供匹配逻辑使用。"""
        return [k.strip() for k in self.keywords.split(',') if k.strip()]


class ChatLog(models.Model):
    """问答交互记录。

    对应 FR-AI-01 / FR-AI-02。记录 source 字段用于统计各应答路径的占比，
    也便于排查「为什么这次答得不对」。
    """

    class AnswerSource(models.TextChoices):
        """应答来源。"""

        RULES = 'rules', '规则库'
        TEMPLATE = 'template', '数据模板'
        CLOUD = 'cloud', '云 API'
        FALLBACK = 'fallback', '离线兜底'

    employee = models.ForeignKey(
        Employee,
        verbose_name='提问人',
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name='chat_logs',
    )
    question = models.TextField('提问内容')
    answer = models.TextField('回答内容')
    source = models.CharField(
        '应答来源', max_length=20, choices=AnswerSource.choices, default=AnswerSource.RULES
    )
    matched_faq = models.ForeignKey(
        FaqItem,
        verbose_name='命中的 FAQ',
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name='chat_logs',
    )
    elapsed_ms = models.PositiveIntegerField('耗时(毫秒)', default=0)
    created_at = models.DateTimeField('创建时间', auto_now_add=True)

    class Meta:
        verbose_name = '问答记录'
        verbose_name_plural = '问答记录'
        ordering = ['-created_at']
        indexes = [
            models.Index(fields=['employee', 'created_at'], name='idx_chat_emp_time'),
        ]

    def __str__(self):
        return f'{self.employee} 提问：{self.question[:20]}'
