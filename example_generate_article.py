# coding=utf-8
"""
示例：使用创作模块生成文章
"""

import sys
from pathlib import Path

# 添加项目根目录到路径
project_root = Path(__file__).parent
sys.path.insert(0, str(project_root))

from create.index import generate_article_by_topic


def main():
    """生成关于Vue3与Vue2响应式区别和底层原理的文章"""
    
    print("=" * 60)
    print("📝 生成技术文章示例")
    print("=" * 60)
    print("\n")
    
    # 生成文章
    result = generate_article_by_topic(
        topic="前端Vue3与Vue2响应式区别和底层原理",
        requirements="""
请详细讲解：
1. Vue2的响应式原理（Object.defineProperty）
2. Vue3的响应式原理（Proxy）
3. 两者的区别和优缺点对比
4. 实际应用场景的选择建议
5. 代码示例和性能对比
""",
        platform="技术博客",
        content_type="技术文章",
        word_count=3000,
        style="专业"
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
        filename = f"Vue3与Vue2响应式原理_{datetime.now().strftime('%Y%m%d_%H%M%S')}.md"
        output_path = output_dir / filename
        
        with open(output_path, 'w', encoding='utf-8') as f:
            f.write("# 前端Vue3与Vue2响应式区别和底层原理\n\n")
            f.write(f"**生成时间**: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}\n\n")
            f.write("---\n\n")
            f.write(result['content'])
        
        print(f"\n📄 文章已保存到: {output_path}")
        
        if result.get('usage'):
            print(f"\n📊 Token使用情况: {result['usage']}")
    else:
        print(f"\n❌ 生成失败：{result.get('error', '未知错误')}")


if __name__ == "__main__":
    main()

