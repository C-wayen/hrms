"""
公共查询模块数据模型。

本模块以查询与打印为主，唯一的表是人事变动通知单：

    NotificationDoc  人事变动通知单   FR-QRY-02

注意：FR-QRY-01「多维检索」不建表——它是对 Employee 表的复合条件查询，
无需额外的数据结构。

对应文档：HRMS/code_artifact.md（SRS V1.1）

@author 王坤尧
"""

from django.db import models

from apps.sysconf.models import Employee


class NotificationDoc(models.Model):
    """人事变动通知单。

    对应 FR-QRY-02「生成人事变动通知单，支持 PDF 导出或打印」。
    「套红」指公文红头格式，由模板（templates/pubquery/notification_pdf.html）
    负责呈现，本表只存正文数据。
    """

    class DocType(models.TextChoices):
        """通知单类型。"""

        TRANSFER = 'transfer', '调动通知'
        REGULAR = 'regular', '转正通知'
        REWARD = 'reward', '奖惩通知'
        RESIGN = 'resign', '离职通知'

    doc_no = models.CharField('通知单编号', max_length=30, unique=True)
    doc_type = models.CharField('通知单类型', max_length=20, choices=DocType.choices)
    title = models.CharField('标题', max_length=100)
    employee = models.ForeignKey(
        Employee,
        verbose_name='涉及员工',
        on_delete=models.PROTECT,
        related_name='notification_docs',
    )
    content = models.TextField('正文')
    issue_date = models.DateField('签发日期')
    issuer = models.ForeignKey(
        Employee, verbose_name='签发人',
        null=True, blank=True, on_delete=models.SET_NULL, related_name='+',
    )
    related_transfer = models.ForeignKey(
        'personnel.TransferRecord',
        verbose_name='关联调动记录',
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name='notification_docs',
        help_text='调动类通知单由调动记录自动带出前后岗位信息',
    )
    created_at = models.DateTimeField('创建时间', auto_now_add=True)

    class Meta:
        verbose_name = '人事通知单'
        verbose_name_plural = '人事通知单'
        ordering = ['-issue_date']
        indexes = [
            models.Index(fields=['doc_type', 'issue_date'], name='idx_doc_type_date'),
        ]

    def __str__(self):
        return f'{self.doc_no} {self.title}'
