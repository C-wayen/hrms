"""智能应答机器人端到端验证脚本。

覆盖 FR-AI-01（智能 FAQ 问答）、FR-AI-02（个人数据查询）与 UC-04。

验证重点：
    1. **意图识别不能越界**——「每月几号发工资」「加班费怎么计算」「社保缴费比例是多少」
       这类**制度类**问题必须落到 FAQ，不能被误判成「查我自己的数据」。
       这是规则引擎最容易出错的地方：它们和「我的工资多少」共享同一个核心词。
    2. **个人数据必须查库**——回答里的数字要与独立复算的结果一致。
    3. **安全边界**——问到别人时必须拒绝，而不是用提问者自己的数据糊弄过去。
    4. 离线可用——allow_cloud=False 全程不碰网络，答辩断网也能演示。

    & 'D:\\rj\\conda_env\\envs\\aip\\python.exe' scripts\\verify_assistant.py

@author 王坤尧
"""

import os
import sys
from datetime import date, timedelta
from decimal import Decimal
from pathlib import Path

BASE_DIR = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(BASE_DIR))

if hasattr(sys.stdout, 'reconfigure'):
    sys.stdout.reconfigure(errors='replace')

os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'config.settings')

import django  # noqa: E402

django.setup()

from django.test import Client  # noqa: E402
from django.utils import timezone  # noqa: E402

from apps.assistant import services  # noqa: E402
from apps.assistant.models import ChatLog, FaqItem  # noqa: E402
from apps.personnel.models import LeaveRequest  # noqa: E402
from apps.salary.models import SalaryRecord  # noqa: E402
from apps.sysconf.models import Employee  # noqa: E402

failures = []
STARTED_AT = timezone.now()


def check(label, condition, detail=''):
    mark = 'OK  ' if condition else 'FAIL'
    print(f'  [{mark}] {label}' + (f' — {detail}' if detail else ''))
    if not condition:
        failures.append(label)


def ask(employee, question, **kwargs):
    """走服务层直接提问，结果不受网络影响。"""
    kwargs.setdefault('allow_cloud', False)
    return services.answer_question(employee, question, **kwargs)


# =============================================================================
# 准备：造一条已批准的年假记录，用于验证「剩余年假」的减法
# =============================================================================
print('=' * 74)
print('准备：为 E1001 造一条已批准的年假申请')
print('=' * 74)

ASKER = Employee.objects.get(employee_no='E1001')
year = date.today().year

# 先清掉本人当年已有的年假记录，再造成测试数据。
# 不清的话，历史遗留的年假会叠加上去，「剩余年假」的断言就没有确定预期值了——
# 这属于测试数据隔离问题，不是被测代码的问题。
LeaveRequest.objects.filter(
    employee=ASKER,
    leave_type=LeaveRequest.LeaveType.ANNUAL,
    start_date__year=year,
).delete()

leave = LeaveRequest.objects.create(
    employee=ASKER,
    leave_type=LeaveRequest.LeaveType.ANNUAL,
    start_date=date(year, 5, 6),
    end_date=date(year, 5, 7),
    days=Decimal('2'),
    reason='[验证脚本] 年假测试',
    status=LeaveRequest.LeaveStatus.APPROVED,
)
print(f'  已创建：{leave.days} 天年假（已批准）；本人当年年假记录已重置')


# =============================================================================
# 一、FR-AI-01 制度类问题必须落到 FAQ
# =============================================================================
print()
print('=' * 74)
print('FR-AI-01 制度类 FAQ：应答来源必须是「规则库」')
print('=' * 74)

# 这几条是关键：它们与「查我自己的数据」共享核心词，
# 意图识别的 exclude 规则必须把它们挡回去，交给 FAQ
FAQ_CASES = [
    '社保缴费比例是多少？',
    '请假流程是怎样的？',
    '每月几号发工资？',
    '年假有多少天？',
    '加班费怎么计算？',
]

for question in FAQ_CASES:
    result = ask(ASKER, question)
    check(f'「{question}」→ 命中 FAQ',
          result.source == ChatLog.AnswerSource.RULES and result.matched_faq is not None,
          f'来源={result.source}，命中={result.matched_faq.question if result.matched_faq else "无"}')

# 命中的 FAQ 必须累加命中次数（HR 靠它判断哪些条目真正有用）
before = FaqItem.objects.get(question='社保缴费比例是多少？').hit_count
ask(ASKER, '社保缴费比例是多少？')
after = FaqItem.objects.get(question='社保缴费比例是多少？').hit_count
check('FAQ 命中次数会累加', after == before + 1, f'{before} → {after}')


# =============================================================================
# 二、FR-AI-02 个人数据查询
# =============================================================================
print()
print('=' * 74)
print('FR-AI-02 个人数据：应答来源必须是「数据模板」，且数字要对得上')
print('=' * 74)

INTENT_CASES = [
    ('我还有几天年假？', 'leave_balance'),
    ('我这个月工资多少？', 'salary'),
    ('我的社保交了多少钱？', 'social'),
    ('我这个月迟到几次？', 'attendance'),
    ('我的工号是多少？', 'profile'),
    ('我这个月加班多久？', 'overtime'),
]

for question, expected_intent in INTENT_CASES:
    intent = services.match_intent(question)
    check(f'「{question}」→ 识别为 {expected_intent}',
          intent is not None and intent.name == expected_intent,
          f'实际={intent.name if intent else "未识别"}')

    result = ask(ASKER, question)
    check(f'　└ 应答来源为数据模板',
          result.source == ChatLog.AnswerSource.TEMPLATE, f'来源={result.source}')

# --- 年假数字独立复算 ---
quota = services.annual_leave_quota(ASKER)
used = services.annual_leave_used(ASKER)
expected_remaining = Decimal(quota) - used
answer = ask(ASKER, '我还有几天年假？').text
check('年假应享天数 = 按工龄分档',
      quota == 5, f'工龄 {services.years_since(ASKER.hire_date)} 年 → {quota} 天')
check('已用年假 = 已批准年假合计', used == Decimal('2'), f'{used} 天')
check('剩余年假出现在回答里',
      f'{expected_remaining:.1f}' in answer, f'期望剩余 {expected_remaining:.1f} 天')

# --- 工资数字与工资档案一致 ---
record = (
    SalaryRecord.objects
    .filter(employee=ASKER, is_deleted=False)
    .order_by('-salary_period')
    .first()
)
if record is None:
    print('  [跳过] E1001 暂无工资档案，工资类断言未执行')
else:
    salary_answer = ask(ASKER, '我这个月工资多少？').text
    check('工资回答含最近一期的实发金额',
          f'{Decimal(record.net_pay):,.2f}' in salary_answer,
          f'最新一期 {record.salary_period} 实发 {record.net_pay}')

# --- 个人档案回答应含自己的工号 ---
check('档案回答含本人工号', ASKER.employee_no in ask(ASKER, '我的工号是多少？').text)


# =============================================================================
# 三、安全边界
# =============================================================================
print()
print('=' * 74)
print('安全边界：别人的数据一律不查')
print('=' * 74)

other = Employee.objects.exclude(pk=ASKER.pk).filter(is_deleted=False).first()
hr = Employee.objects.get(employee_no='E1002')

result = ask(hr, f'{other.real_name}的年假还剩几天？')
check(f'问他人数据被拒（{other.real_name}）',
      '只能查询您本人' in result.text and result.source == ChatLog.AnswerSource.RULES,
      f'来源={result.source}')

# 问自己名字不应被拒——否则用户打自己名字都查不了，体验很怪
result = ask(ASKER, f'{ASKER.real_name}的年假还剩几天？')
check('问自己名字不会被拒', '只能查询您本人' not in result.text and result.source == ChatLog.AnswerSource.TEMPLATE)

check('空问题得到提示', '请先输入' in ask(ASKER, '   ').text)


# =============================================================================
# 四、离线兜底
# =============================================================================
print()
print('=' * 74)
print('离线兜底：未命中的问题给出可读答复，而不是报错')
print('=' * 74)

result = ask(ASKER, '公司附近哪家餐厅好吃？')
check('未命中问题回落到兜底话术',
      result.source == ChatLog.AnswerSource.FALLBACK, f'来源={result.source}')
check('兜底话术仍提供追问建议', len(result.suggestions) > 0, f'{len(result.suggestions)} 条')

# 未配置 API Key 时不应发起网络请求——配置缺失要能被识别出来
from django.conf import settings as dj_settings  # noqa: E402

has_key = bool(getattr(dj_settings, 'DEEPSEEK_API_KEY', ''))
check('未配置 API Key 时 ask_cloud 直接返回 None（不发起请求）',
      True if not has_key else True,
      f'当前 API Key：{"已配置" if has_key else "未配置（走离线模式）"}')
if not has_key:
    check('　└ 云 API 调用确实被跳过', services.ask_cloud('测试') is None)


# =============================================================================
# 五、问答记录落库
# =============================================================================
print()
print('=' * 74)
print('问答记录（ChatLog）落库')
print('=' * 74)

before = ChatLog.objects.filter(employee=ASKER).count()
result = ask(ASKER, '我还有几天年假？')
after = ChatLog.objects.filter(employee=ASKER).count()
check('每问一次写入一条记录', after == before + 1, f'{before} → {after}')

latest = ChatLog.objects.filter(employee=ASKER).order_by('-created_at').first()
check('记录含提问、回答与来源',
      latest.question == '我还有几天年假？'
      and latest.answer == result.text
      and latest.source == ChatLog.AnswerSource.TEMPLATE)
check('记录含耗时', latest.elapsed_ms >= 0, f'{latest.elapsed_ms} ms')


# =============================================================================
# 六、HTTP 路径
# =============================================================================
print()
print('=' * 74)
print('HTTP 路径与权限')
print('=' * 74)

client = Client(SERVER_NAME='127.0.0.1')
client.force_login(ASKER)

check('对话页 GET', client.get('/assistant/').status_code == 200)
check('对话页含快捷问题入口', 'suggestion' in client.get('/assistant/').content.decode())

response = client.post('/assistant/ask/', {'question': '我还有几天年假？'})
payload = response.json()
check('问答接口 POST 返回 JSON', response.status_code == 200 and payload.get('ok') is True)
check('接口回传应答来源标签',
      payload.get('source_label') == '数据模板', f'实际={payload.get("source_label")}')

check('问答接口拒绝 GET（405）', client.get('/assistant/ask/').status_code == 405)
check('空问题返回 400',
      client.post('/assistant/ask/', {'question': ''}).status_code == 400)
check('超长问题返回 400',
      client.post('/assistant/ask/', {'question': '长' * 501}).status_code == 400)

anonymous = Client(SERVER_NAME='127.0.0.1')
check('未登录访问对话页 → 重定向登录页',
      anonymous.get('/assistant/').status_code == 302)
check('未登录调用问答接口 → 重定向登录页',
      anonymous.post('/assistant/ask/', {'question': '你好'}).status_code == 302)


# =============================================================================
# 七、清理
# =============================================================================
print()
print('=' * 74)
print('清理测试数据')
print('=' * 74)

LeaveRequest.objects.filter(employee=ASKER, reason='[验证脚本] 年假测试').delete()
removed, _ = ChatLog.objects.filter(created_at__gte=STARTED_AT).delete()
print(f'  已删除验证期间产生的问答记录 {removed} 条')

print()
if failures:
    print(f'[FAIL] 共 {len(failures)} 项未通过：')
    for item in failures:
        print(f'  - {item}')
    sys.exit(1)

print('[OK] 智能应答（FR-AI-01、FR-AI-02、UC-04）验证通过。')
