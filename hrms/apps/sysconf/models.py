"""
系统设置与安全模块数据模型。

本模块承载 HRMS 的账号体系与基础数据，是所有其他模块的依赖底座：

    Employee    员工 —— 既是登录账号（继承 AbstractUser），也是人事档案
    Department  部门 —— 自关联成树，对应 FR-SYS-02 组织机构树形管理
    Position    岗位 —— 员工职位的字典来源
    DataDict    数据字典 —— 政治面貌、学历等枚举值的统一存放处
    Menu        导航菜单 —— 按角色控制可见性，对应 FR-SYS-03

设计决策（2026-09-28 与项目负责人确认）：

1. **账号与员工合一**：本项目所有员工都需要登录系统，既不存在「非员工的账号」，
   也不存在「无账号的员工」，因此不拆表。Employee 继承 AbstractUser，即 SRS 5.1
   所述的「Employee 继承 User」，类图无需修改。
2. **角色即 Django 内置 Group**：通过 Group 关联 Permission 实现 RBAC
   （系统管理员 / HR 专员·经理 / 普通职工 即三个 Group），无需自建 Role 表，
   Django Admin 可直接管理。
3. **软删除范围**：员工使用 `is_deleted` 标记（离职档案需长期保留供追溯），
   部门、岗位、字典等基础数据直接物理删除。

对应文档：HRMS/code_artifact.md（SRS V1.1）

@author 王坤尧
"""

from datetime import date

from django.contrib.auth.models import AbstractUser, Group
from django.core.validators import RegexValidator
from django.db import models


# =============================================================================
# 一、基础数据（FR-SYS-02）
# =============================================================================


class Department(models.Model):
    """部门（组织机构节点）。

    通过 parent 自关联构成树形结构，层级不设上限（实际业务一般 3~4 层）。
    对应 FR-SYS-02「组织机构树形管理」。
    """

    name = models.CharField('部门名称', max_length=50)
    code = models.CharField('部门编码', max_length=20, unique=True)
    parent = models.ForeignKey(
        'self',
        verbose_name='上级部门',
        null=True,
        blank=True,
        # PROTECT：部门下若仍有子部门或员工，禁止删除，避免产生游离数据
        on_delete=models.PROTECT,
        related_name='children',
    )
    leader = models.ForeignKey(
        'Employee',
        verbose_name='部门负责人',
        null=True,
        blank=True,
        # SET_NULL：负责人离职后部门仍需保留，只是暂时空缺
        on_delete=models.SET_NULL,
        related_name='led_departments',
    )
    sort_order = models.PositiveIntegerField('排序号', default=0)
    is_active = models.BooleanField('是否启用', default=True)
    created_at = models.DateTimeField('创建时间', auto_now_add=True)
    updated_at = models.DateTimeField('更新时间', auto_now=True)

    class Meta:
        verbose_name = '部门'
        verbose_name_plural = '部门'
        ordering = ['sort_order', 'code']

    def __str__(self):
        return self.name

    def get_full_path(self) -> str:
        """返回「总公司 / 技术部 / 后端组」形式的完整路径，供下拉框展示。

        guard 用于防御脏数据造成的环路，最多向上追溯 20 层。
        """
        names, node, guard = [], self, 0
        while node is not None and guard < 20:
            names.append(node.name)
            node = node.parent
            guard += 1
        return ' / '.join(reversed(names))


class Position(models.Model):
    """岗位（职位）。

    对应 FR-SYS-02 的岗位级别字典；员工通过外键关联到具体岗位。
    """

    name = models.CharField('岗位名称', max_length=50)
    code = models.CharField('岗位编码', max_length=20, unique=True)
    level = models.CharField('岗位级别', max_length=20, blank=True)
    description = models.CharField('岗位说明', max_length=200, blank=True)
    is_active = models.BooleanField('是否启用', default=True)
    created_at = models.DateTimeField('创建时间', auto_now_add=True)

    class Meta:
        verbose_name = '岗位'
        verbose_name_plural = '岗位'
        ordering = ['code']

    def __str__(self):
        return self.name


class DataDict(models.Model):
    """数据字典。

    以「类型 + 键 + 值」的单表结构统一存放各类枚举项（政治面貌、婚姻状况、
    请假类型、奖罚类型、证书类别等），避免为每种枚举单独建表。

    对应 FR-SYS-02「数据字典（政治面貌、岗位级别等）」。
    """

    dict_type = models.CharField('字典类型', max_length=50)
    dict_key = models.CharField('字典键', max_length=50)
    dict_value = models.CharField('字典值', max_length=100)
    sort_order = models.PositiveIntegerField('排序号', default=0)
    is_active = models.BooleanField('是否启用', default=True)
    remark = models.CharField('备注', max_length=200, blank=True)
    created_at = models.DateTimeField('创建时间', auto_now_add=True)

    class Meta:
        verbose_name = '数据字典'
        verbose_name_plural = '数据字典'
        # 同一字典类型下键必须唯一，防止出现两个「01」
        unique_together = [('dict_type', 'dict_key')]
        ordering = ['dict_type', 'sort_order']

    def __str__(self):
        return f'{self.dict_type}:{self.dict_value}'


# =============================================================================
# 二、导航菜单（FR-SYS-03）
# =============================================================================


class Menu(models.Model):
    """导航菜单项。

    侧边栏按当前登录员工的角色（Group）动态渲染：只显示 visible_roles
    中包含该员工任一角色的菜单项。对应 FR-SYS-03「用户与菜单管理」。
    """

    title = models.CharField('菜单名称', max_length=50)
    url_name = models.CharField('路由名', max_length=100, blank=True)
    parent = models.ForeignKey(
        'self',
        verbose_name='上级菜单',
        null=True,
        blank=True,
        # CASCADE：菜单属于纯配置数据，删除父菜单时子菜单一并删除
        on_delete=models.CASCADE,
        related_name='children',
    )
    icon = models.CharField('图标类名', max_length=50, blank=True)
    sort_order = models.PositiveIntegerField('排序号', default=0)
    visible_roles = models.ManyToManyField(
        Group,
        verbose_name='可见角色',
        blank=True,
        related_name='menus',
    )
    is_active = models.BooleanField('是否启用', default=True)

    class Meta:
        verbose_name = '导航菜单'
        verbose_name_plural = '导航菜单'
        ordering = ['sort_order']

    def __str__(self):
        return self.title


# =============================================================================
# 三、员工（既是登录账号，也是人事档案）
# =============================================================================


class Employee(AbstractUser):
    """员工账号兼人事档案。

    继承 AbstractUser 后自动获得以下认证字段：
        password / is_active / is_staff / is_superuser /
        date_joined / last_login / groups / user_permissions

    对应 FR-PER-01「职工档案管理」与 FR-SYS-01「权限控制」。

    注意：AbstractUser 自带的 first_name / last_name 在中文场景无意义，
    统一改用 real_name 字段，代码中请勿使用这两个字段。
    """

    class Gender(models.TextChoices):
        """性别。用枚举而非魔法字符，便于 FR-RPT-01 性别比例直接分组统计。"""

        MALE = 'M', '男'
        FEMALE = 'F', '女'

    class Education(models.TextChoices):
        """学历。用于 FR-RPT-01 学历构成统计。"""

        BELOW_COLLEGE = 'below_college', '大专以下'
        COLLEGE = 'college', '大专'
        BACHELOR = 'bachelor', '本科'
        MASTER = 'master', '硕士'
        DOCTOR = 'doctor', '博士'

    class EmployStatus(models.TextChoices):
        """在职状态。离职员工业绩与工资记录需保留，故用状态标记而非删除。"""

        INTERN = 'intern', '实习'
        PROBATION = 'probation', '试用'
        REGULAR = 'regular', '正式'
        RESIGNED = 'resigned', '离职'

    # --- 账号字段（覆盖 AbstractUser 默认定义，放宽长度限制）---
    username = models.CharField('登录名', max_length=50, unique=True)

    # --- 档案基本字段 ---
    employee_no = models.CharField('工号', max_length=20, unique=True)
    real_name = models.CharField('姓名', max_length=30)
    gender = models.CharField('性别', max_length=1, choices=Gender.choices)
    birth_date = models.DateField(
        '出生日期',
        null=True,
        blank=True,
        help_text='用于生日提醒（FR-PER-04）与年龄段统计（FR-RPT-01）',
    )
    id_card = models.CharField(
        '身份证号',
        max_length=18,
        unique=True,
        validators=[RegexValidator(r'^\d{17}[\dXx]$', '身份证号格式不正确（应为 18 位）')],
    )
    phone = models.CharField(
        '手机号',
        max_length=11,
        blank=True,
        validators=[RegexValidator(r'^1[3-9]\d{9}$', '手机号格式不正确')],
    )
    education = models.CharField(
        '学历', max_length=20, choices=Education.choices, blank=True
    )
    political_status = models.CharField(
        '政治面貌', max_length=20, blank=True, help_text='取值来自数据字典'
    )
    graduate_school = models.CharField(
        '毕业院校', max_length=100, blank=True, help_text='正式员工与实习生均需填写'
    )
    major = models.CharField('所学专业', max_length=50, blank=True)
    native_place = models.CharField('籍贯', max_length=50, blank=True)
    address = models.CharField('现住址', max_length=200, blank=True)

    # --- 任职信息 ---
    department = models.ForeignKey(
        Department,
        verbose_name='所属部门',
        null=True,
        blank=True,
        on_delete=models.PROTECT,
        related_name='employees',
    )
    position = models.ForeignKey(
        Position,
        verbose_name='岗位',
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name='employees',
    )
    salary_level = models.ForeignKey(
        'salary.SalaryLevel',
        verbose_name='薪酬级别',
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name='employees',
        help_text='对应 FR-SAL-01 薪酬体系配置',
    )
    employ_status = models.CharField(
        '在职状态',
        max_length=20,
        choices=EmployStatus.choices,
        default=EmployStatus.REGULAR,
    )
    hire_date = models.DateField('入职日期', null=True, blank=True)
    probation_end_date = models.DateField(
        '实习/试用期结束日期',
        null=True,
        blank=True,
        help_text='到期未转正应触发提醒，避免实习生长期停留在实习状态（FR-PER-02）',
    )
    regular_date = models.DateField(
        '转正日期',
        null=True,
        blank=True,
        help_text='转正审批通过时写入，报表可按转正时间统计（FR-PER-02、FR-RPT-03）',
    )
    resign_date = models.DateField('离职日期', null=True, blank=True)

    # --- 软删除标记 ---
    is_deleted = models.BooleanField(
        '是否已删除',
        default=False,
        help_text='离职或误录入的档案置为 True，保留历史以便追溯，不做物理删除',
    )

    # --- 审计字段 ---
    created_at = models.DateTimeField('创建时间', auto_now_add=True)
    updated_at = models.DateTimeField('更新时间', auto_now=True)

    # createsuperuser 命令会依次询问以下字段（AbstractUser 默认只问 email）
    REQUIRED_FIELDS = ['real_name', 'employee_no', 'id_card', 'gender']

    class Meta:
        verbose_name = '员工'
        verbose_name_plural = '员工'
        ordering = ['employee_no']
        indexes = [
            # 员工列表「按部门筛选 + 按工号排序」是最高频查询（FR-PER-01）
            models.Index(fields=['department', 'employee_no'], name='idx_emp_dept_no'),
            # 在职状态用于人员流动统计（FR-RPT-03）
            models.Index(fields=['employ_status'], name='idx_emp_status'),
        ]

    def __str__(self):
        return f'{self.real_name}（{self.employee_no}）'

    def save(self, *args, **kwargs):
        """保存前把 username 与工号同步（工号即账号）。

        为什么需要同步：Django 的 authenticate() 依据 USERNAME_FIELD（本模型仍为
        username）查找用户，而业务上只承认工号。把工号写进 username，员工直接
        用工号就能登录，不必再记一个登录名。

        为什么是「始终覆盖」而不是「为空时才填」：只要允许两者不同，就会出现
        「登录名 zhangwei、工号 E1001」两套标识各自被改、最终对不上。

        注：若调用方传入了不含 username 的 update_fields（如登录时更新
        last_login），这里的赋值只影响内存，不会写库，也不会造成冲突。
        """
        if self.employee_no:
            self.username = self.employee_no
        super().save(*args, **kwargs)

    @property
    def age(self):
        """由出生日期实时推算周岁。

        不落库存储：年龄每天都在变，存字段会立刻过期；
        报表统计时按需分组即可（FR-RPT-01 年龄段分布）。
        """
        if not self.birth_date:
            return None
        today = date.today()
        # 今年生日是否已过；没过则减 1 岁
        birthday_passed = (today.month, today.day) >= (
            self.birth_date.month,
            self.birth_date.day,
        )
        return today.year - self.birth_date.year - (0 if birthday_passed else 1)

    @property
    def service_years(self):
        """司龄（年），用于 FR-RPT-01 工龄统计与年假推算（FR-AI-02）。"""
        if not self.hire_date:
            return None
        end = self.resign_date or date.today()
        return round((end - self.hire_date).days / 365.25, 1)

    @property
    def role_names(self) -> list:
        """当前员工所属的角色名列表，供侧边栏菜单渲染与权限判断使用。"""
        return list(self.groups.values_list('name', flat=True))

    # 可查看「全员」业务数据的角色。
    # 为什么不用权限（Permission）而用角色名：Django 的权限是**模型级**的，
    # 无法表达「普通职工只能看自己的请假」这类**行级**规则。
    # 行级规则只能在视图层按数据范围过滤，这里集中定义「谁能看全量」。
    DATA_SCOPE_ROLES = ('系统管理员', 'HR 专员/经理')

    @property
    def can_view_all(self) -> bool:
        """当前用户是否可查看全员数据（请假、考勤、奖罚等）。

        列表视图据此决定数据范围：
            可看全量 -> 不加过滤
            只能看自己 -> 过滤为 employee=self
        """
        if self.is_superuser:
            return True
        return self.groups.filter(name__in=self.DATA_SCOPE_ROLES).exists()
