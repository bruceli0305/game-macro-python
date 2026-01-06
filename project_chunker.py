import os
import re

def find_python_files(directory):
    """查找目录下所有.py文件，排除.venv文件夹"""
    python_files = []
    for root, dirs, files in os.walk(directory):
        # 排除.venv文件夹
        if '.venv' in root:
            continue
        for file in files:
            if file.endswith('.py'):
                python_files.append(os.path.join(root, file))
    return python_files

def read_file_with_header(file_path, base_dir):
    """读取文件内容并添加文件路径头信息"""
    relative_path = os.path.relpath(file_path, base_dir)
    with open(file_path, 'r', encoding='utf-8') as f:
        content = f.read()
    
    # 添加文件头信息
    header = f"# File: {relative_path}\n"
    header += "# " + "=" * 50 + "\n"
    
    return header + content + "\n\n" + "=" * 60 + "\n\n"

def chunk_content_by_functions(content, max_lines=2000):
    """按函数分割内容，确保每个分块约2000行，且函数完整"""
    lines = content.split('\n')
    chunks = []
    current_chunk = []
    current_line_count = 0
    
    # 查找函数定义的位置
    function_starts = []
    for i, line in enumerate(lines):
        if re.match(r'^\s*(?:def|class)\s+\w+\s*\(', line):
            function_starts.append(i)
    
    # 如果没有函数定义，直接按行分割
    if not function_starts:
        for i in range(0, len(lines), max_lines):
            chunk_lines = lines[i:i+max_lines]
            chunks.append('\n'.join(chunk_lines))
        return chunks
    
    # 按函数分割
    i = 0
    while i < len(lines):
        # 如果当前块接近最大行数，且下一个函数在当前块内，则结束当前块
        if current_line_count >= max_lines * 0.8:
            # 查找下一个函数开始位置
            next_func_start = None
            for func_start in function_starts:
                if func_start > i:
                    next_func_start = func_start
                    break
            
            # 如果下一个函数在当前块内，结束当前块
            if next_func_start and next_func_start - i < max_lines * 0.2:
                chunks.append('\n'.join(current_chunk))
                current_chunk = []
                current_line_count = 0
        
        # 添加当前行到块中
        current_chunk.append(lines[i])
        current_line_count += 1
        i += 1
        
        # 如果当前块达到最大行数，结束当前块
        if current_line_count >= max_lines:
            chunks.append('\n'.join(current_chunk))
            current_chunk = []
            current_line_count = 0
    
    # 添加最后一个块
    if current_chunk:
        chunks.append('\n'.join(current_chunk))
    
    return chunks

def main():
    # 获取当前目录
    current_dir = os.path.dirname(os.path.abspath(__file__))
    # 设置目标目录为 rotation_editor
    # target_dir = os.path.join(current_dir, 'rotation_editor')
    target_dir = current_dir
    # 查找所有.py文件
    python_files = find_python_files(target_dir)
    
    # 输出文件夹
    output_dir = os.path.join(current_dir, 'py_to_txt_output')
    
    # 读取所有文件内容
    all_content = ""
    for file_path in python_files:
        print(f'读取文件: {file_path}')
        file_content = read_file_with_header(file_path, target_dir)
        all_content += file_content
    
    # 按函数分割整个项目内容
    chunks = chunk_content_by_functions(all_content, max_lines=2000)
    
    # 保存每个分块
    for i, chunk in enumerate(chunks):
        output_file = os.path.join(output_dir, f'project_chunk_{i+1:02d}.txt')
        
        with open(output_file, 'w', encoding='utf-8') as f:
            # 添加分块头信息
            f.write(f"# Project Chunk {i+1}")
            f.write(f"# Total Lines: {chunk.count(chr(10)) + 1}\n")
            f.write("# " + "=" * 50 + "\n\n")
            f.write(chunk)
        
        print(f'保存分块 {i+1}/{len(chunks)} 到 {output_file}')
    
    print(f'\n项目切块完成！共生成 {len(chunks)} 个文件')
    print(f'总代码行数: {all_content.count(chr(10)) + 1}')

if __name__ == '__main__':
    main()