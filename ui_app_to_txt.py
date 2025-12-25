import os
import re

def read_file_with_header(file_path, base_dir):
    """读取文件内容并添加文件路径头信息"""
    relative_path = os.path.relpath(file_path, base_dir)
    with open(file_path, 'r', encoding='utf-8') as f:
        content = f.read()
    
    # 添加文件头信息
    header = f"# File: {relative_path}\n"
    header += "# " + "=" * 50 + "\n"
    
    return header + content + "\n\n" + "=" * 60 + "\n\n"

def main():
    # 目标文件夹路径
    target_dir = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'ui', 'app')
    
    # 输出文件路径
    output_file = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'py_to_txt_output', 'ui_app_code.txt')
    
    # 查找ui/app文件夹中的所有.py文件
    python_files = []
    for file in os.listdir(target_dir):
        if file.endswith('.py'):
            python_files.append(os.path.join(target_dir, file))
    
    # 按文件名排序，确保顺序一致
    python_files.sort()
    
    # 读取所有文件内容
    all_content = ""
    total_lines = 0
    
    for file_path in python_files:
        print(f'读取文件: {os.path.basename(file_path)}')
        file_content = read_file_with_header(file_path, os.path.dirname(os.path.abspath(__file__)))
        all_content += file_content
        total_lines += file_content.count('\n') + 1
    
    # 保存到txt文件
    with open(output_file, 'w', encoding='utf-8') as f:
        # 添加总头信息
        f.write(f"# UI/App Folder Code Collection\n")
        f.write(f"# Total Files: {len(python_files)}\n")
        f.write(f"# Total Lines: {total_lines}\n")
        f.write("# " + "=" * 50 + "\n\n")
        f.write(all_content)
    
    print(f'\nUI/App文件夹代码输出完成！')
    print(f'输出文件: {output_file}')
    print(f'包含文件数: {len(python_files)}')
    print(f'总代码行数: {total_lines}')
    
    # 显示文件列表
    print(f'\n包含的文件:')
    for file_path in python_files:
        relative_path = os.path.relpath(file_path, os.path.dirname(os.path.abspath(__file__)))
        print(f'  - {relative_path}')

if __name__ == '__main__':
    main()