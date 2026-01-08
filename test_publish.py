# coding=utf-8
"""测试发布功能"""

import sys
import io
from pathlib import Path

# 设置标准输出编码为UTF-8
if sys.platform == 'win32':
    sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8')
    sys.stderr = io.TextIOWrapper(sys.stderr.buffer, encoding='utf-8')

# 添加项目根目录到路径
project_root = Path(__file__).parent
sys.path.insert(0, str(project_root))

from public.index import publish_content

def main():
    print("=" * 60)
    print("测试发布功能")
    print("=" * 60)
    print("\n")
    
    # 读取文章文件
    article_file = project_root / "output" / "articles" / "Vue3与Vue2响应式原理_20251216_095448.md"
    
    if not article_file.exists():
        print(f"[错误] 文章文件不存在: {article_file}")
        return
    
    # 读取文件内容
    with open(article_file, 'r', encoding='utf-8') as f:
        content_text = f.read()
    
    # 解析Markdown，提取标题和内容
    lines = content_text.split('\n')
    title = "前端Vue3与Vue2响应式区别和底层原理"
    content = ""
    
    # 跳过前面的元数据，找到实际内容
    start_idx = 0
    for i, line in enumerate(lines):
        if line.strip() == "---":
            start_idx = i + 1
            break
    
    if start_idx > 0:
        content = '\n'.join(lines[start_idx:]).strip()
    else:
        # 如果没有找到分隔符，使用整个内容
        content = content_text
    
    print(f"文章标题: {title}")
    print(f"文章长度: {len(content)} 字符")
    print("\n正在发布到Typecho平台...")
    print("=" * 60)
    
    # 发布文章
    result = publish_content(
        content={
            'title': title,
            'content': content
        },
        platform_ids=['typecho'],
        tags='Vue,前端,技术,响应式'
    )
    
    # 显示结果
    print("\n发布结果：")
    print("=" * 60)
    print(f"总计: {result['total']} 个平台")
    print(f"成功: {result['success_count']} 个")
    print(f"失败: {result['total'] - result['success_count']} 个")
    print("\n详细信息：")
    
    for r in result['results']:
        platform_name = r.get('platform_name', r.get('platform', '未知'))
        if r.get('success'):
            print(f"  [成功] {platform_name}: 发布成功")
            if r.get('url'):
                print(f"    文章链接: {r['url']}")
        else:
            print(f"  [失败] {platform_name}: 发布失败")
            if r.get('error'):
                print(f"    错误: {r['error']}")
    
    print("\n")


if __name__ == "__main__":
    main()






















