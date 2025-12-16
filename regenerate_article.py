# coding=utf-8
"""重新生成文章：测试生动性改进"""

import sys
import io
from pathlib import Path
from datetime import datetime

# 设置标准输出编码为UTF-8
if sys.platform == 'win32':
    sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8')
    sys.stderr = io.TextIOWrapper(sys.stderr.buffer, encoding='utf-8')

# 添加项目根目录到路径
project_root = Path(__file__).parent
sys.path.insert(0, str(project_root))

from create.index import generate_article_by_topic

def main():
    print("=" * 60)
    print("正在重新生成文章（加入生动性改进）：前端Vue3与Vue2响应式区别和底层原理")
    print("=" * 60)
    print("\n")
    
    # 生成文章
    result = generate_article_by_topic(
        topic="前端Vue3与Vue2响应式区别和底层原理",
        requirements="请详细讲解Vue2和Vue3的响应式原理、区别、优缺点、应用场景和代码示例。注意：每隔2-3个段落要插入有趣的举例或俏皮话，让内容生动有趣，适合小白阅读。",
        platform="技术博客",
        content_type="技术文章",
        word_count=3000,
        style="专业但生动"
    )
    
    if result['success']:
        print("\n[成功] 文章生成成功！\n")
        print("=" * 60)
        print("生成的文章内容：")
        print("=" * 60)
        print(result['content'])
        print("\n" + "=" * 60)
        
        # 保存到文件
        output_dir = project_root / "output" / "articles"
        output_dir.mkdir(parents=True, exist_ok=True)
        
        filename = f"Vue3与Vue2响应式原理_生动版_{datetime.now().strftime('%Y%m%d_%H%M%S')}.md"
        output_path = output_dir / filename
        
        with open(output_path, 'w', encoding='utf-8') as f:
            f.write("# 前端Vue3与Vue2响应式区别和底层原理\n\n")
            f.write(f"**生成时间**: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}\n\n")
            f.write(f"**平台**: 技术博客\n\n")
            f.write(f"**类型**: 技术文章（生动版）\n\n")
            f.write("---\n\n")
            f.write(result['content'])
        
        print(f"\n[文件] 文章已保存到: {output_path}")
        
        if result.get('usage'):
            print(f"\n[统计] Token使用情况: {result['usage']}")
    else:
        error_msg = result.get('error', '未知错误')
        print(f"\n[错误] 生成失败：{error_msg}")
        print("\n提示：请检查：")
        print("1. API Key是否正确配置在 config/config.yaml 中")
        print("2. 网络连接是否正常")
        print("3. API配额是否充足")
        print("4. 查看上面的详细错误信息")

if __name__ == "__main__":
    main()

