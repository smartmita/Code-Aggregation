import os
import sys
import json
import threading
import queue

# --- 核心逻辑 ---


def find_files(
    directory: str, extensions: list, ignore_items: set, log_queue: queue.Queue
) -> list:
    """
    【功能修改】查找指定目录下及其所有子目录中的所有指定后缀名的文件。
    忽略规则更新：
    1. 如果忽略项不含路径分隔符 (如 'venv'), 则忽略所有同名文件/文件夹。
    2. 如果忽略项包含路径分隔符 (如 'C:\\project\\data'), 则精确匹配该完整路径。
    """
    found_files_list = []
    log_queue.put(f"开始在 '{directory}' 中搜索...")

    extensions_lower = [ext.lower() for ext in extensions]

    # 将忽略项分为两类：纯名称 和 完整路径
    ignore_basenames = {
        item.lower() for item in ignore_items if os.path.sep not in item
    }
    ignore_full_paths = {
        os.path.abspath(item).lower() for item in ignore_items if os.path.sep in item
    }

    for root, dirs, files in os.walk(directory, topdown=True):
        # --- 过滤目录 ---
        # 1. 根据纯名称过滤
        dirs[:] = [d for d in dirs if d.lower() not in ignore_basenames]
        # 2. 根据完整路径过滤
        dirs[:] = [
            d
            for d in dirs
            if os.path.abspath(os.path.join(root, d)).lower() not in ignore_full_paths
        ]

        # --- 过滤文件 ---
        for file in files:
            # 1. 根据纯名称过滤
            if file.lower() in ignore_basenames:
                continue

            full_path = os.path.join(root, file)
            abs_path = os.path.abspath(full_path)

            # 2.根据完整路径过滤
            if abs_path.lower() in ignore_full_paths:
                continue

            # 检查文件后缀名是否匹配
            if any(file.lower().endswith(ext) for ext in extensions_lower):
                found_files_list.append(abs_path)
                log_queue.put(f"  -> 找到: {abs_path}")

    log_queue.put(f"搜索完成。共找到 {len(found_files_list)} 个文件。")
    return found_files_list

def generate_file_tree(root_dir: str, file_paths: list, log_queue: queue.Queue) -> str:
    """
    根据文件路径列表生成文件结构树状图。
    """
    log_queue.put("正在生成文件结构树...")
    tree = {}
    for path in file_paths:
        try:
            relative_path = os.path.relpath(path, root_dir)
            parts = relative_path.split(os.sep)
            current_level = tree
            for part in parts[:-1]:
                if part not in current_level:
                    current_level[part] = {}
                current_level = current_level[part]
            current_level[parts[-1]] = None
        except ValueError:
            parts = path.split(os.sep)
            current_level = tree
            for part in parts[:-1]:
                if part not in current_level:
                    current_level[part] = {}
                current_level = current_level[part]
            current_level[parts[-1]] = None

    def format_tree(node, prefix=""):
        lines = []
        items = sorted(node.items(), key=lambda x: x[1] is not None)
        pointers = ["├─── "] * (len(items) - 1) + ["└─── "]
        for pointer, (name, sub_node) in zip(pointers, items):
            is_dir = sub_node is not None
            icon = "📁 " if is_dir else "📄 "
            lines.append(f"{prefix}{pointer}{icon}{name}")
            if is_dir:
                extension = "│   " if pointer == "├─── " else "    "
                lines.extend(format_tree(sub_node, prefix + extension))
        return lines

    tree_lines = [f"{os.path.basename(root_dir)}"] + format_tree(tree)
    log_queue.put("文件结构树生成完毕。")
    return "\n".join(tree_lines)


def get_unique_filepath(
    directory: str, filename: str, extension: str, log_queue: queue.Queue
) -> str:
    """
    【新增功能】检查文件路径是否存在，如果存在，则在文件名后添加 (n) 直到找到一个不重复的路径。
    同时通过 log_queue 发出提示。
    """
    base_path = os.path.join(directory, f"{filename}{extension}")
    if not os.path.exists(base_path):
        return base_path

    counter = 1
    original_full_name = f"{filename}{extension}"

    while True:
        new_filename_with_ext = f"{filename} ({counter}){extension}"
        new_path = os.path.join(directory, new_filename_with_ext)
        if not os.path.exists(new_path):
            log_queue.put(f"提示: 文件 '{original_full_name}' 已存在。")
            log_queue.put(f"将自动重命名并保存为 -> '{new_filename_with_ext}'")
            return new_path
        counter += 1

def aggregate_code(
    root_dir: str,
    file_paths: list,
    output_filename: str,
    output_format: str,
    log_queue: queue.Queue,
    progress_queue: queue.Queue,
):
    """
    将多个代码文件的内容聚合到一个文件中，并在开头加入文件结构树。
    """
    total_files = len(file_paths)


    # 检查并创建输出目录
    output_dir = os.path.dirname(output_filename)
    if not os.path.exists(output_dir):
        try:
            os.makedirs(output_dir)
            log_queue.put(f"自动创建输出目录: {output_dir}")
        except Exception as e:
            log_queue.put(f"创建输出目录失败: {output_dir} - {e}")
            return False # 如果创建目录失败，则退出函数

    try:
        with open(output_filename, "w", encoding="utf-8") as output_file:
            log_queue.put(f"正在创建并写入文件: {output_filename}")

            output_file.write("=" * 80 + "\n")
            output_file.write(f"根目录: {root_dir}\n")
            output_file.write(f"共 {total_files} 个文件\n")
            output_file.write("=" * 80 + "\n\n")

            if file_paths:
                tree_structure = generate_file_tree(root_dir, file_paths, log_queue)
                output_file.write("文件结构树:\n")
                output_file.write(tree_structure)
                output_file.write("\n\n" + "=" * 80 + "\n\n")

            for i, file_path in enumerate(file_paths):
                log_queue.put(f"正在写入 ({i + 1}/{total_files}): {file_path}")
                progress_queue.put((i + 1) / total_files * 100)

                output_file.write("-" * 80 + "\n")
                output_file.write(f"文件路径: {file_path}\n")
                output_file.write("-" * 80 + "\n\n")

                try:
                    with open(
                        file_path, "r", encoding="utf-8", errors="ignore"
                    ) as input_file:
                        content = input_file.read()

                        if output_format == ".md":
                            lang = os.path.splitext(file_path)[1].lstrip(".")
                            output_file.write(f"```{lang}\n")
                            output_file.write(content)
                            output_file.write("\n```\n\n")
                        else:
                            output_file.write(content)
                            output_file.write("\n\n")

                except Exception as e:
                    error_message = f"!!! 读取文件时出错: {file_path} -> {e} !!!\n\n"
                    log_queue.put(error_message)
                    output_file.write(error_message)

            log_queue.put(
                f"所有代码内容已成功聚合到 '{os.path.basename(output_filename)}' 文件中。"
            )
    except IOError as e:
        log_queue.put(f"错误：无法写入文件 {output_filename}。-> {e}")
