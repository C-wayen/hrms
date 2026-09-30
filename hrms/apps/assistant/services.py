"""
HR 智能应答服务。

对应需求：FR-AI-01 智能 FAQ 问答、FR-AI-02 个人数据查询
对应用例：UC-04 AI 机器人问答

================================================================================
应答策略：三级降级，保证离线可用
================================================================================

    ① 个人数据意图  关键词打分识别意图 → 直接用 ORM 查**提问者本人**的数据
    ② 制度类 FAQ    关键词命中 FaqItem → 返回维护好的标准答案
    ③ 云 API 兜底   前两级都没命中且 AI_PROVIDER=cloud 时转 DeepSeek；
                    超时或异常则回落为「离线兜底」话术并提示

为什么把规则放在最前面，而不是先问模型：

    1. **涉及工资、社保、身份证这类个人数据，答案必须来自数据库。**
       模型能把一个凭空编出来的金额写得非常像样，而看的人无从分辨真伪——
       在 HR 系统里这种错误比「答不上来」严重得多。
    2. 答辩现场可能没有外网，规则模式必须能独立工作（SRS D-04 要求
       「支持离线规则模式与云 API 增强」）。
    3. 规则命中是毫秒级且零成本，没必要为「每月几号发工资」这种问题去调 API。

个人数据的边界：只回答**提问者本人**的数据。问题里若出现其他同事的姓名，
一律拒绝并说明原因，而不是猜他想查谁。

@author 王坤尧
"""

import json
import logging
import time
import urllib.error
import urllib.request
from dataclasses import dataclass, field
from datetime import date, timedelta
from decimal import Decimal

from django.conf import settings
from django.db.models import Count, F, Sum

from apps.personnel.models import Attendance, LeaveRequest, SocialInsurance
from apps.salary.models import OvertimeRecord, SalaryRecord
from apps.sysconf.models import Employee
from apps.sysconf.utils import years_since

from .models import ChatLog, FaqItem

logger = logging.getLogger(__name__)

DEEPSEEK_ENDPOINT = 'https://api.deepseek.com/chat/completions'

# 「个人信号」词：出现这些词，才认为用户在问**自己的数据**而不只是在问制度。
# 这道闸门不能省：「年假有多少天」和「我还有几天年假」共享核心词「年假」，
# 区别恰恰在于一个在问规则、一个在问我的余额；少了它，
# 制度类问题会被拿去查个人数据，答非所问。
PERSONAL_SIGNAL_WORDS = (
    '我', '本人', '自己', '咱',
    # 这类词只能指向本人状态，出现即说明是在问「我的」情况
    '还剩', '剩余', '还有', '余额', '没用',
)

# 法定年假分档：(累计工龄下限, 天数)。
# 与 FAQ 里写给员工看的口径完全一致——机器人说的和制度写的必须是同一套，
# 否则员工拿着两个数字来问 HR，谁都说不清哪个对。
ANNUAL_LEAVE_TIERS = ((20, 15), (10, 10), (1, 5))

# 每次回答附带的追问建议，降低「不知道该问什么」的冷启动门槛
DEFAULT_SUGGESTIONS = [
    '我还有几天年假？',
    '我这个月工资多少？',
    '社保缴费比例是多少？',
    '请假流程是怎样的？',
    '我的社保交了多少钱？',
]

SYSTEM_PROMPT = (
    '你是「人力资源管理系统」的在线助手，面向公司员工回答人事制度类问题。\n'
    '回答要求：\n'
    '1. 用简体中文，简洁分点，控制在 200 字以内；\n'
    '2. 只回答人事、考勤、薪酬、培训、社保相关的问题，其它领域礼貌说明无法回答；\n'
    '3. 不确定或系统里没有的信息，直接说「这个问题我暂时答不上来，建议咨询 HR」，'
    '**绝不允许编造**具体数字、比例或日期；\n'
    '4. 不要透露任何员工的具体个人数据（工资、身份证、社保账号等）。'
)


@dataclass
class Answer:
    """一次应答的结果。"""

    text: str
    source: str = ChatLog.AnswerSource.RULES
    matched_faq: FaqItem | None = None
    suggestions: list = field(default_factory=list)
    elapsed_ms: int = 0


# =============================================================================
# 一、通用工具
# =============================================================================


def _money(value) -> str:
    """把金额格式化成两位小数字符串；无值显示「—」。"""
    if value is None:
        return '—'
    return f'{Decimal(value):,.2f}'


def _this_month() -> str:
    """本月薪酬周期 'YYYY-MM'。"""
    return date.today().strftime('%Y-%m')


def _last_month() -> str:
    """上月薪酬周期 'YYYY-MM'。"""
    today = date.today()
    return (today.replace(day=1) - timedelta(days=1)).strftime('%Y-%m')


def _mentions_other_employee(question: str, employee) -> str | None:
    """问题里是否提到别的同事。返回提到的姓名，没有则 None。

    这是明确的安全边界：同事之间不该通过机器人互相看到工资、社保这类信息。
    与其猜测他想查谁，不如直接说明「只能查本人」。
    """
    others = (
        Employee.objects
        .filter(is_deleted=False)
        .exclude(pk=employee.pk)
        .values_list('real_name', flat=True)
    )
    for name in others:
        if name and name in question:
            return name
    return None


# =============================================================================
# 二、年假核算（FR-AI-02「剩余年假」的数据来源）
# =============================================================================


def annual_leave_quota(employee, year: int | None = None) -> int:
    """员工当年的法定年假天数。

    规则：累计工作满 1 年不满 10 年 5 天；满 10 年不满 20 年 10 天；满 20 年 15 天。
    入职当年按剩余日历天数折算（不足 1 天不计）。
    """
    year = year or date.today().year
    service_years = years_since(employee.hire_date) or 0

    quota = 0
    for threshold, days in ANNUAL_LEAVE_TIERS:
        if service_years >= threshold:
            quota = days
            break
    if quota == 0:
        return 0

    # 入职当年折算：按入职日到年末的剩余天数比例
    if employee.hire_date and employee.hire_date.year == year:
        remaining_days = (date(year, 12, 31) - employee.hire_date).days + 1
        return int(quota * remaining_days / 365)
    return quota


def annual_leave_used(employee, year: int | None = None) -> Decimal:
    """当年已批准的年假天数。"""
    year = year or date.today().year
    total = (
        LeaveRequest.objects
        .filter(
            employee=employee,
            leave_type=LeaveRequest.LeaveType.ANNUAL,
            status=LeaveRequest.LeaveStatus.APPROVED,
            start_date__year=year,
            is_deleted=False,
        )
        .aggregate(total=Sum('days'))['total']
    )
    return total or Decimal('0')


# =============================================================================
# 三、各意图的处理函数
# =============================================================================


def _answer_leave_balance(employee, question: str) -> str:
    """剩余年假（FR-AI-02）。"""
    year = date.today().year
    quota = annual_leave_quota(employee, year)
    used = annual_leave_used(employee, year)

    if quota == 0:
        return (
            f'您目前的累计工作年限为 {years_since(employee.hire_date) or 0} 年，'
            '按《职工带薪年休假条例》，累计工作不满 1 年不享受带薪年休假。'
        )

    remaining = Decimal(quota) - used
    return (
        f'您 {year} 年的年假情况：\n'
        f'· 应享 {quota} 天（按累计工龄核定）\n'
        f'· 已使用 {used:.1f} 天\n'
        f'· 剩余 {remaining:.1f} 天'
    )


def _answer_salary(employee, question: str) -> str:
    """工资查询（FR-AI-02「本月应发工资」）。"""
    period = _last_month() if any(w in question for w in ('上月', '上个月')) else _this_month()
    record = SalaryRecord.objects.filter(
        employee=employee, salary_period=period, is_deleted=False
    ).first()

    prefix = ''
    if record is None:
        # 本月工资通常还没核算，回落到最近一期，并说清楚这是哪一期——
        # 直接报一个旧数字而不说明，会让人以为这就是本月的工资
        record = (
            SalaryRecord.objects
            .filter(employee=employee, is_deleted=False)
            .order_by('-salary_period')
            .first()
        )
        if record is None:
            return '系统里还没有您的工资档案。工资由 HR 核算后生成，请稍后再试。'
        prefix = f'{period} 的工资尚未核算，以下是最近一期：\n'

    status = '已发放' if record.pay_status == SalaryRecord.PayStatus.PAID else '待发放'
    return (
        f'{prefix}【{record.salary_period} 工资条】（{status}）\n'
        f'· 基本工资：{_money(record.base_salary)}\n'
        f'· 计件/计时：{_money(record.piecework_amount)}\n'
        f'· 加班费：{_money(record.overtime_amount)}\n'
        f'· 奖罚净额：{_money(record.reward_punish_amount)}\n'
        f'· 水电扣费：-{_money(record.utility_deduction)}\n'
        f'· 社保自负：-{_money(record.social_deduction)}\n'
        f'· 实发工资：{_money(record.net_pay)} 元'
    )


def _answer_profile(employee, question: str) -> str:
    """本人档案信息。"""
    return (
        f'您的档案信息：\n'
        f'· 工号：{employee.employee_no}\n'
        f'· 姓名：{employee.real_name}\n'
        f'· 部门：{employee.department.name if employee.department else "—"}\n'
        f'· 岗位：{employee.position.name if employee.position else "—"}\n'
        f'· 在职状态：{employee.get_employ_status_display()}\n'
        f'· 入职日期：{employee.hire_date or "—"}\n'
        f'· 工龄：{years_since(employee.hire_date) or 0} 年'
    )


def _answer_social(employee, question: str) -> str:
    """本人社保缴纳情况。"""
    record = (
        SocialInsurance.objects
        .filter(employee=employee)
        .order_by('-period')
        .first()
    )
    if record is None:
        return '系统里还没有您的社保缴费记录，请联系 HR 确认参保情况。'

    return (
        f'您 {record.period} 的社保缴费情况：\n'
        f'· 缴费基数：{_money(record.insurance_base)}\n'
        f'· 个人承担合计：{_money(record.personal_total)}\n'
        f'· 单位承担合计：{_money(record.company_total)}\n'
        f'（其中个人部分会在当月工资中代扣）'
    )


def _answer_attendance(employee, question: str) -> str:
    """本月考勤概况。"""
    today = date.today()
    rows = (
        Attendance.objects
        .filter(employee=employee, work_date__year=today.year, work_date__month=today.month)
        .values('status')
        .annotate(count=Count('id'))
    )
    labels = dict(Attendance.AttendanceStatus.choices)
    found = {row['status']: row['count'] for row in rows}

    if not found:
        return f'您在 {today.year} 年 {today.month} 月暂无考勤记录。'

    lines = [f'您 {today.year} 年 {today.month} 月的考勤：']
    # 按考勤状态枚举顺序输出，保证每次回答的条目顺序一致
    for value, label in Attendance.AttendanceStatus.choices:
        if value in found:
            lines.append(f'· {label}：{found[value]} 天')
    return '\n'.join(lines)


def _answer_leave_records(employee, question: str) -> str:
    """本人今年的请假记录汇总。"""
    year = date.today().year
    records = LeaveRequest.objects.filter(
        employee=employee, start_date__year=year, is_deleted=False
    )
    if not records.exists():
        return f'您 {year} 年还没有请假记录。'

    approved = records.filter(status=LeaveRequest.LeaveStatus.APPROVED)
    pending = records.filter(status=LeaveRequest.LeaveStatus.PENDING)
    total_days = approved.aggregate(total=Sum('days'))['total'] or Decimal('0')

    return (
        f'您 {year} 年的请假情况：\n'
        f'· 申请总数：{records.count()} 次\n'
        f'· 已批准：{approved.count()} 次，合计 {total_days:.1f} 天\n'
        f'· 待审批：{pending.count()} 次'
    )


def _answer_overtime(employee, question: str) -> str:
    """本月加班时长。"""
    period = _this_month()
    rows = OvertimeRecord.objects.filter(
        employee=employee, salary_period=period, is_deleted=False
    )
    total = rows.aggregate(total=Sum('hours'))['total'] or Decimal('0')

    if not rows.exists():
        return f'您在 {period} 没有加班记录。'

    labels = dict(OvertimeRecord.OvertimeType.choices)
    found = {}
    for row in rows:
        found[row.overtime_type] = found.get(row.overtime_type, Decimal('0')) + row.hours

    lines = [f'您 {period} 的加班情况（合计 {total:.1f} 小时）：']
    for value, label in OvertimeRecord.OvertimeType.choices:
        if value in found:
            lines.append(f'· {label}：{found[value]:.1f} 小时')
    return '\n'.join(lines)


# =============================================================================
# 四、意图识别
# =============================================================================


@dataclass(frozen=True)
class Intent:
    """一个意图的匹配规则。

    required：必须命中其中之一，否则不认为是这个意图。
    optional：命中一个加 1 分，用于在多个候选之间排序。
    exclude：命中任一即**直接排除**——这些词意味着用户在问「制度规定」，
             而不是「我的数据」，应当交给 FAQ 去答。
    """

    name: str
    required: tuple
    handler: object
    optional: tuple = ()
    exclude: tuple = ()


INTENTS = (
    Intent(
        name='leave_balance',
        required=('年假', '调休', '假期余额'),
        optional=('还剩', '剩余', '还有', '几天', '多少天', '余额', '没用'),
        exclude=('怎么算', '规定', '制度', '条例', '多少天假期'),
        handler=_answer_leave_balance,
    ),
    Intent(
        name='salary',
        required=('工资', '薪资', '薪水', '收入', '到手'),
        optional=('多少', '发了', '应发', '实发', '明细', '这个月', '上月'),
        exclude=('几号', '哪天', '怎么算', '公式', '为什么', '什么时候发'),
        handler=_answer_salary,
    ),
    Intent(
        name='social',
        required=('社保', '五险', '公积金'),
        optional=('交了', '扣了', '多少', '基数', '明细'),
        exclude=('比例', '标准', '怎么算', '规定', '怎么查', '怎么交'),
        handler=_answer_social,
    ),
    Intent(
        name='attendance',
        required=('考勤', '迟到', '早退', '旷工', '打卡'),
        optional=('几次', '几天', '记录', '这个月', '本月'),
        exclude=('规定', '制度', '怎么'),
        handler=_answer_attendance,
    ),
    Intent(
        name='leave_records',
        required=('请假记录', '请过', '请假情况', '请假次数'),
        optional=('几次', '几天', '今年', '汇总'),
        exclude=('流程', '怎么', '如何', '规定', '制度'),
        handler=_answer_leave_records,
    ),
    Intent(
        name='overtime',
        required=('加班',),
        optional=('多久', '几小时', '多少小时', '时长', '这个月', '本月'),
        exclude=('怎么算', '计算', '标准', '倍率', '规定', '制度', '为什么'),
        handler=_answer_overtime,
    ),
    Intent(
        name='profile',
        required=('档案', '部门', '岗位', '工号', '入职'),
        optional=('我', '级别', '职位', '什么时候'),
        exclude=('如何', '怎么', '哪里', '流程', '在哪'),
        handler=_answer_profile,
    ),
)


def match_intent(question: str):
    """按关键词打分识别意图，返回得分最高的 Intent；都不匹配返回 None。

    打分而不是「命中即返回」：多个意图可能共享高频词（如「这个月」），
    命中更多辅助词的意图更接近用户真正想问的。

    前置闸门：必须出现「个人信号」词。理由见 PERSONAL_SIGNAL_WORDS 的注释——
    这条闸门决定了「年假有多少天」会落到 FAQ，而不是被拿去查个人年假。
    """
    if not any(word in question for word in PERSONAL_SIGNAL_WORDS):
        return None

    is_first_person = any(word in question for word in ('我', '本人', '自己', '咱'))
    best, best_score = None, 0

    for intent in INTENTS:
        if any(word in question for word in intent.exclude):
            continue
        if not any(word in question for word in intent.required):
            continue

        score = 1 + sum(1 for word in intent.optional if word in question)
        # 明确的第一人称再补一分：「我的工资」比「工资还剩多少」更确切
        if is_first_person:
            score += 1
        if score > best_score:
            best, best_score = intent, score

    return best


# =============================================================================
# 五、FAQ 匹配（FR-AI-01）
# =============================================================================


def match_faq(question: str):
    """按关键词命中 FAQ，返回 (条目, 命中词数)。都不命中返回 (None, 0)。"""
    best, best_score = None, 0
    for item in FaqItem.objects.filter(is_active=True):
        score = sum(1 for word in item.keyword_list() if word and word in question)
        if score > best_score:
            best, best_score = item, score
    return best, best_score


# =============================================================================
# 六、云 API（可选增强）
# =============================================================================


def ask_cloud(question: str) -> str | None:
    """向 DeepSeek 提问；任何失败都返回 None，由调用方回落。

    用标准库 urllib 而不是 requests：本项目依赖只有 Django / PyMySQL / dotenv，
    为一个可选增强功能引入新依赖不划算（答辩环境还得额外装包）。

    只传问题、不传任何个人数据：涉及个人数据的问题在第①级就已被规则吃掉，
    不该有个人数据流向外部 API。
    """
    api_key = getattr(settings, 'DEEPSEEK_API_KEY', '') or ''
    if not api_key:
        logger.info('未配置 DEEPSEEK_API_KEY，跳过云 API')
        return None

    payload = {
        'model': getattr(settings, 'DEEPSEEK_MODEL', 'deepseek-chat'),
        'messages': [
            {'role': 'system', 'content': SYSTEM_PROMPT},
            {'role': 'user', 'content': question},
        ],
        'temperature': 0.3,
        'max_tokens': 600,
    }
    request = urllib.request.Request(
        DEEPSEEK_ENDPOINT,
        data=json.dumps(payload).encode('utf-8'),
        headers={
            'Content-Type': 'application/json',
            'Authorization': f'Bearer {api_key}',
        },
    )

    timeout = getattr(settings, 'AI_REQUEST_TIMEOUT', 8)
    try:
        with urllib.request.urlopen(request, timeout=timeout) as response:
            body = json.loads(response.read().decode('utf-8'))
        content = body['choices'][0]['message']['content'].strip()
        return content or None
    except Exception as exc:  # noqa: BLE001 —— 网络层异常种类多，一律视为不可用
        logger.warning('云 API 不可用，回落规则模式：%s', exc)
        return None


# =============================================================================
# 七、主入口
# =============================================================================


def answer_question(employee, question: str, *, allow_cloud: bool = None) -> Answer:
    """应答主流程：三级降级 + 落库问答记录。

    allow_cloud 为 None 时按 settings.AI_PROVIDER 决定；
    验证脚本与离线演示可显式传 False，保证结果不受网络影响。
    """
    started = time.monotonic()
    question = (question or '').strip()

    if not question:
        return Answer(text='请先输入您想问的问题。', suggestions=DEFAULT_SUGGESTIONS)

    # ---- 第 0 步：安全边界，先于一切匹配 ----
    # 放在最前面，是因为「张伟的年假还剩几天」同样会命中年假意图，
    # 若先匹配意图，就会用提问者自己的数据去回答一个关于别人的问题
    mentioned = _mentions_other_employee(question, employee)
    if mentioned:
        return _finish(
            employee, question, started,
            Answer(
                text=(
                    f'抱歉，我只能查询您本人的数据，无法查看「{mentioned}」的信息。\n'
                    '涉及他人薪酬、考勤等信息请通过 HR 走正式流程。'
                ),
                suggestions=DEFAULT_SUGGESTIONS,
            ),
        )

    # ---- 第 1 步：个人数据意图（答案必须来自数据库）----
    intent = match_intent(question)
    if intent is not None:
        text = intent.handler(employee, question)
        return _finish(
            employee, question, started,
            Answer(text=text, source=ChatLog.AnswerSource.TEMPLATE),
        )

    # ---- 第 2 步：制度类 FAQ ----
    faq, score = match_faq(question)
    if faq is not None and score > 0:
        FaqItem.objects.filter(pk=faq.pk).update(hit_count=F('hit_count') + 1)
        return _finish(
            employee, question, started,
            Answer(text=faq.answer, source=ChatLog.AnswerSource.RULES, matched_faq=faq),
        )

    # ---- 第 3 步：云 API 兜底 ----
    if allow_cloud is None:
        allow_cloud = getattr(settings, 'AI_PROVIDER', 'rules') == 'cloud'
    if allow_cloud:
        text = ask_cloud(question)
        if text:
            return _finish(
                employee, question, started,
                Answer(text=text, source=ChatLog.AnswerSource.CLOUD),
            )

    # ---- 兜底话术 ----
    return _finish(
        employee, question, started,
        Answer(
            text=(
                '这个问题我暂时答不上来。\n'
                '您可以换个说法，或者试试下面这些我比较擅长的问题；'
                '也可以直接联系 HR 咨询。'
            ),
            source=ChatLog.AnswerSource.FALLBACK,
            suggestions=DEFAULT_SUGGESTIONS,
        ),
    )


def _finish(employee, question: str, started: float, result: Answer) -> Answer:
    """补齐建议与耗时、写入问答记录，再返回结果。

    落库放在这里而不是每个分支里各写一遍：少一处遗漏，就少一条查不到的记录。
    """
    if not result.suggestions:
        result.suggestions = DEFAULT_SUGGESTIONS
    result.elapsed_ms = int((time.monotonic() - started) * 1000)

    try:
        ChatLog.objects.create(
            employee=employee,
            question=question,
            answer=result.text,
            source=result.source,
            matched_faq=result.matched_faq,
            elapsed_ms=result.elapsed_ms,
        )
    except Exception as exc:  # noqa: BLE001
        # 记录失败不应让用户看不到答案——对话本身才是主任务
        logger.warning('问答记录写入失败：%s', exc)

    return result
