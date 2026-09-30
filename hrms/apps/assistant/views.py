"""
智能应答机器人视图。

对应需求：FR-AI-01 智能 FAQ 问答、FR-AI-02 个人数据查询
对应用例：UC-04 AI 机器人问答

页面与接口分离：界面用模板渲染骨架，问答走 JSON 接口异步完成，
这样每条回答可以就地追加，不必整页刷新，也便于把「应答来源」一并显示出来。

应答逻辑全部在 services.py，本文件只做参数校验与响应封装。

@author 王坤尧
"""

from django.contrib.auth.decorators import login_required
from django.http import JsonResponse
from django.shortcuts import render
from django.views.decorators.http import require_POST

from .models import ChatLog, FaqItem
from .services import DEFAULT_SUGGESTIONS, answer_question

# 单条提问的长度上限：既是防滥用，也避免超长文本拖慢云 API 请求
MAX_QUESTION_LENGTH = 500


@login_required
def chat(request):
    """智能助手对话界面（FR-AI-01、FR-AI-02）。

    不加权限校验：该菜单对全部角色可见，且问答内容按登录用户隔离
    （个人数据只回答本人的），不存在越权读取的入口。
    """
    return render(request, 'assistant/chat.html', {
        'page_title': '智能助手',
        'suggestions': DEFAULT_SUGGESTIONS,
        'faq_count': FaqItem.objects.filter(is_active=True).count(),
    })


@login_required
@require_POST
def ask(request):
    """问答接口。

    只接受 POST：问答会产生 ChatLog 记录，用 GET 会被浏览器预取或
    被收藏夹意外触发，凭空多出一堆「问题为空」的记录。
    """
    question = (request.POST.get('question') or '').strip()
    if not question:
        return JsonResponse({'ok': False, 'error': '请输入问题。'}, status=400)
    if len(question) > MAX_QUESTION_LENGTH:
        return JsonResponse(
            {'ok': False, 'error': f'问题太长了，请控制在 {MAX_QUESTION_LENGTH} 字以内。'},
            status=400,
        )

    result = answer_question(request.user, question)

    return JsonResponse({
        'ok': True,
        'answer': result.text,
        'source': result.source,
        # 把来源标签一并回传：答辩时能一眼看出这次是规则命中、
        # 数据模板还是云 API，不必去翻数据库
        'source_label': ChatLog.AnswerSource(result.source).label,
        'suggestions': result.suggestions,
        'elapsed_ms': result.elapsed_ms,
    })
