"""
跨模块共用的纯函数工具。

对应需求：FR-RPT-01 ~ FR-RPT-03 报表统计、FR-AI-02 智能助手个人数据查询

为什么单独成文件：这类按日期算整年数的计算看似简单，但闰年、月末等边界
处理不好就会长期存在「差一岁」的偏差，且极难被发现。
集中一处，才能保证报表的「工龄分布」与智能助手回答的「年假天数」
用的是同一套算法——两处各写一份，迟早出现
「报表说我工龄 9 年、助手说 10 年」这种自己跟自己对不上的情况。

@author 王坤尧
"""

from datetime import date


def years_since(start, today=None):
    """由起始日期算整年数（年龄与工龄共用）。返回 None 表示无从计算。

    用 (月, 日) 元组比较，而不是「天数 ÷ 365」：
    后者在闰年会有 1 天的误差，导致生日当天算出的年龄少 1 岁，
    而这类错误只在极少数记录上出现，最难被发现。
    """
    if not start:
        return None
    today = today or date.today()
    years = today.year - start.year
    if (today.month, today.day) < (start.month, start.day):
        years -= 1
    return years
