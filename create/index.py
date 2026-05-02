# coding=utf-8
"""
创作模块核心功能
用于创建和生成文本内容
"""

import sys
from pathlib import Path

# 添加项目根目录到路径
project_root = Path(__file__).parent.parent
sys.path.insert(0, str(project_root))

from utils.ai_client import get_qwen_client


def generate_content(hot_data: dict, platform: str = "通用", content_type: str = "文章") -> dict:
    """
    基于热点数据生成创作内容
    
    Args:
        hot_data: 热点数据字典，包含标题、内容、关键词等
        platform: 目标平台名称
        content_type: 内容类型（文章、微博、短视频脚本等）
        
    Returns:
        包含生成内容的字典
    """
    client = get_qwen_client()
    
    # 构建用户输入
    user_input = f"""
目标平台：{platform}
内容类型：{content_type}

热点数据：
标题：{hot_data.get('title', '')}
内容：{hot_data.get('content', '')}
关键词：{', '.join(hot_data.get('keywords', []))}
"""
    
    # 使用全局提示词和主流程提示词
    system_prompt_path = project_root / "create" / "global_prompt.txt"
    main_prompt_path = project_root / "create" / "main" / "main_prompt.txt"
    
    system_prompt = ""
    if system_prompt_path.exists():
        with open(system_prompt_path, 'r', encoding='utf-8') as f:
            system_prompt += f.read() + "\n\n"
    
    if main_prompt_path.exists():
        with open(main_prompt_path, 'r', encoding='utf-8') as f:
            system_prompt += f.read()
    
    # 调用千问生成内容
    result = client.generate(
        prompt=user_input,
        system_prompt=system_prompt,
        temperature=0.7,
        max_tokens=2000
    )
    
    return result


def generate_article_by_topic(
    topic: str,
    requirements: str = "",
    platform: str = "通用",
    content_type: str = "技术文章",
    word_count: int = 2000,
    style: str = "专业"
) -> dict:
    """
    根据主题直接生成文章
    
    Args:
        topic: 文章主题/标题
        requirements: 具体要求和需求（可选）
        platform: 目标平台名称
        content_type: 内容类型（技术文章、博客文章、教程等）
        word_count: 目标字数
        style: 文章风格（专业、通俗、学术等）
        
    Returns:
        包含生成内容的字典
    """
    client = get_qwen_client()
    
    if not client.enable:
        return {
            'success': False,
            'content': '',
            'error': '千问模型未启用或API Key未配置',
            'usage': {}
        }
    
    # 构建用户输入
    # 如果有 requirements（desc），需要明确强调要据此组织内容
    requirements_text = ""
    if requirements:
        requirements_text = f"""
**重要：具体要求描述（必须严格遵守）**：
{requirements}

请务必根据以上具体要求描述来组织文章的结构和内容。这些要求是文章的核心指导，需要贯穿全文。
"""
    
    user_input = f"""
请写一篇关于以下主题的文章：

**主题**：{topic}
{requirements_text}
**基本要求**：
1. 文章类型：{content_type}
2. 目标字数：约{word_count}字
3. 文章风格：{style}（但必须包含轻松的口语化表达）
4. 目标平台：{platform}

**特别强调**：
- 文章必须包含轻松、口语化的表达方式，让读者感觉像在和朋友聊天
- 使用"你"、"我们"、"其实"、"说白了"、"举个例子"等口语化词汇
- 在专业内容之间穿插轻松的表达，避免过于严肃和学术化
- 如果提供了具体要求描述，必须严格按照描述来组织文章结构和内容

请生成一篇结构完整、内容详实、逻辑清晰，同时具有轻松口语化风格的文章。
"""
    
    # 使用全局提示词和主流程提示词
    system_prompt_path = project_root / "create" / "global_prompt.txt"
    main_prompt_path = project_root / "create" / "main" / "main_prompt.txt"
    
    system_prompt = ""
    if system_prompt_path.exists():
        with open(system_prompt_path, 'r', encoding='utf-8') as f:
            system_prompt += f.read() + "\n\n"
    
    if main_prompt_path.exists():
        with open(main_prompt_path, 'r', encoding='utf-8') as f:
            system_prompt += f.read() + "\n\n"
    
    # 添加文章生成的特殊要求，特别强调生动性
    system_prompt += f"""
你是一个专业的内容创作者，擅长撰写{content_type}。
请根据用户提供的主题和要求，生成一篇高质量的文章。

文章要求：
1. 结构清晰：包含引言、正文、结论等部分
2. 内容详实：深入分析主题，提供有价值的信息
3. 逻辑清晰：条理分明，论证充分
4. 风格适配：符合{style}风格和{platform}平台规范
5. 字数控制：目标字数约{word_count}字

═══════════════════════════════════════════════════════════════
⚠️ **极其重要：生动性、可读性和趣味性要求（必须严格遵守）** ⚠️
═══════════════════════════════════════════════════════════════

为了让文章更易读，特别是让小白也能轻松看完，请务必严格遵守以下要求：

1. **每隔2-3个段落必须插入生动元素**（这是硬性要求！）：
   - 有趣的举例（用生活中的例子解释技术概念）
   - 幽默的比喻和类比（比如"Vue的响应式就像天气预报，数据一变，界面就自动更新"）
   - 真实案例或使用场景
   - 生动的描述和观察
   
   **重要**：
   - 不要连续超过3个段落都是纯技术讲解，必须在技术内容之间穿插生动内容！
   - **不要标注"生动例子"、"俏皮话"、"小故事"等标签**，要自然地融入内容中，让读者感觉是文章的自然组成部分
   - 避免使用"小故事"这种形式，因为要么太长显得突兀，要么太短没有意义
   - 生动元素应该自然地出现在段落中，不要有明显的分隔或标注

2. **语言风格**（必须执行，这是硬性要求！）：
   - **必须使用轻松的口语化表达**，让文章读起来像朋友在聊天，而不是学术论文
   - 大量使用口语化词汇和表达：
     * "你"、"我们"、"其实"、"说白了"、"说白了就是"、"举个例子"、"想象一下"
     * "就像..."、"打个比方..."、"这就像..."、"你可以这样理解..."
     * "嗯"、"啊"、"呢"、"吧"等语气词（适度使用）
     * "那么"、"然后"、"接下来"、"不过"、"但是"等连接词
   - 使用通俗易懂的语言，避免堆砌专业术语，如果必须用术语，立即用口语化方式解释
   - 保持轻松愉快的语调，不要过于严肃和学术化
   - 适当使用反问句："是不是？"、"对吧？"、"你想想看..."
   - 比喻和类比要自然地融入段落中，不要单独成段或标注
   - **重要**：整篇文章至少30%的内容应该是口语化表达，不能全是正式的技术描述

3. **举例要求**（每个重要概念都要有）：
   - 技术概念必须用生活化的例子解释，但要自然地融入段落中
   - 抽象概念必须用具体的场景描述，不要单独标注"例如"、"比如"等
   - 复杂流程必须用简单的步骤说明
   - 每个重要概念后，必须自然地跟一个生动的例子或比喻，不要有明显的分隔或标注
   - **重要**：生动元素应该无缝融入正文，读者读起来应该感觉是文章的自然组成部分，而不是生硬的插入

4. **节奏控制**（必须执行）：
   - 不要连续多个段落都是纯技术讲解
   - 在技术内容之间必须穿插轻松的内容，但要自然流畅
   - 让读者有"喘息"的机会，不会感到疲劳
   - 可以在适当位置自然地加入互动性语句，但不要过度使用

5. **趣味性要求**（必须执行）：
   - 适当使用幽默、比喻、类比等手法，但要自然融入
   - 让技术内容不再枯燥，但不要为了生动而生硬插入
   - 可以自然地加入一些有趣的观察或思考
   - 让读者在阅读过程中感到愉悦，但不要有明显的"我在逗你笑"的感觉

═══════════════════════════════════════════════════════════════

**检查清单**（生成文章后请自检）：
□ 是否每隔2-3个段落就有生动元素（自然融入，无标注）？
□ 是否使用了生活化的例子解释技术概念（自然融入段落中）？
□ 语言是否通俗易懂，没有过度堆砌术语？
□ 是否在技术内容之间穿插了轻松的内容（自然流畅）？
□ 是否让读者感到有趣和易读？
□ **重要**：是否避免了"生动例子"、"俏皮话"、"小故事"等生硬标签？
□ **重要**：生动元素是否自然地融入正文，没有明显的分隔或标注？
□ **口语化检查（必须满足）**：
  - 是否大量使用了"你"、"我们"、"其实"、"说白了"等口语化词汇？
  - 是否使用了"就像..."、"打个比方..."、"举个例子"等口语化表达？
  - 是否使用了反问句（"是不是？"、"对吧？"等）增加互动感？
  - 整篇文章是否至少有30%的内容是口语化表达？
  - 读起来是否像朋友在聊天，而不是学术论文？
  - 是否避免了过于正式和学术化的表达？

记住：一篇好的技术文章，不仅要专业，更要让读者愿意看完。生动有趣、轻松口语化的内容能让小白也能坚持读到最后！这是评价文章质量的重要标准！
"""
    
    # 根据字数调整max_tokens（通常1个中文字符约等于1-2个token）
    max_tokens = min(word_count * 2, 4000)  # 限制最大token数
    
    # 调用千问生成内容
    result = client.generate(
        prompt=user_input,
        system_prompt=system_prompt,
        temperature=0.7,
        max_tokens=max_tokens
    )
    
    return result


def main():
    """
    创作功能主入口
    """
    import argparse
    
    parser = argparse.ArgumentParser(description='TrendRadar 创作模块')
    parser.add_argument('--topic', type=str, help='文章主题（直接生成文章模式）')
    parser.add_argument('--requirements', type=str, default='', help='具体要求')
    parser.add_argument('--platform', type=str, default='通用', help='目标平台')
    parser.add_argument('--type', type=str, default='技术文章', help='内容类型')
    parser.add_argument('--words', type=int, default=2000, help='目标字数')
    parser.add_argument('--style', type=str, default='专业', help='文章风格')
    
    args = parser.parse_args()
    
    print("=" * 60)
    print("📝 TrendRadar 创作模块")
    print("=" * 60)
    
    client = get_qwen_client()
    if not client.enable:
        print("\n⚠️  警告：千问模型未启用或API Key未配置")
        print("请在 config/config.yaml 中配置 ai.qwen.api_key")
        print("\n")
        return
    
    print("\n✅ 千问模型已就绪")
    print("\n功能说明：")
    print("  • 基于热点数据生成创作内容")
    print("  • 根据主题直接生成文章")
    print("  • AI 辅助文本生成（使用通义千问）")
    print("  • 内容优化和编辑")
    print("  • 多格式内容导出")
    print("\n")
    
    # 如果提供了主题，则直接生成文章
    if args.topic:
        print(f"正在生成文章：{args.topic}")
        print("=" * 60)
        
        result = generate_article_by_topic(
            topic=args.topic,
            requirements=args.requirements,
            platform=args.platform,
            content_type=args.type,
            word_count=args.words,
            style=args.style
        )
        
        if result['success']:
            print("\n✅ 文章生成成功！\n")
            print("=" * 60)
            print("生成的文章内容：")
            print("=" * 60)
            print(result['content'])
            print("\n" + "=" * 60)
            
            # 保存到文件
            output_dir = project_root / "output" / "articles"
            output_dir.mkdir(parents=True, exist_ok=True)
            
            from datetime import datetime
            filename = f"{datetime.now().strftime('%Y%m%d_%H%M%S')}_{args.topic[:20]}.md"
            output_path = output_dir / filename
            
            with open(output_path, 'w', encoding='utf-8') as f:
                f.write(f"# {args.topic}\n\n")
                f.write(f"**生成时间**: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}\n\n")
                f.write(f"**平台**: {args.platform}\n\n")
                f.write(f"**类型**: {args.type}\n\n")
                f.write("---\n\n")
                f.write(result['content'])
            
            print(f"\n📄 文章已保存到: {output_path}")
            
            if result.get('usage'):
                print(f"\n📊 Token使用情况: {result['usage']}")
        else:
            print(f"\n❌ 生成失败：{result.get('error', '未知错误')}")
    else:
        print("提示：使用 --topic 参数可以直接生成文章")
        print("示例：python create.py --topic 'Vue3与Vue2响应式区别和底层原理'")
        print("\n")


if __name__ == "__main__":
    main()

