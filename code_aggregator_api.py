import argparse
import json
import os
import queue
import sys
from typing import Any

# 导入核心函数
from utils import (
    aggregate_code,
    find_files,
    generate_file_tree,
    get_unique_filepath,
)


class CodeAggregatorAPI:
    """代码聚合工具的API接口类
    提供简洁的编程接口，无需GUI即可使用所有核心功能。
    """

    def __init__(self):
        self.default_extensions = [".py"]
        self.default_ignore_items = {
            "venv",
            "__pycache__",
            ".git",
            ".vscode",
            "node_modules",
            "dist",
            "build",
            ".pytest_cache",
        }
        self.config_file = "code_aggregator_config.json"

    def aggregate_directory(
        self,
        directory: str,
        output_file: str = None,
        extensions: list[str] = None,
        ignore_items: set[str] = None,
        output_format: str = ".md",
        auto_rename: bool = True,
        verbose: bool = True,
    ) -> str | None:
        """聚合指定目录中的代码文件

        Args:
            directory: 要扫描的根目录
            output_file: 输出文件路径（如果为None，则在当前目录生成）
            extensions: 要包含的文件扩展名列表
            ignore_items: 要忽略的文件/文件夹名称或路径
            output_format: 输出格式（.md 或 .txt）
            auto_rename: 如果文件已存在，是否自动重命名
            verbose: 是否输出详细日志

        Returns:
            成功时返回输出文件路径，失败时返回None
        """
        # 参数处理
        if extensions is None:
            extensions = self.default_extensions.copy()

        if ignore_items is None:
            ignore_items = self.default_ignore_items.copy()

        if output_file is None:
            output_file = os.path.join(os.getcwd(), f"code_summary{output_format}")

        # 确保目录存在
        if not os.path.isdir(directory):
            if verbose:
                print(f"错误：目录不存在 - {directory}")
            return None

        # 创建日志队列
        log_queue = queue.Queue()
        progress_queue = queue.Queue()

        try:
            # 查找文件
            found_files = find_files(directory, extensions, ignore_items, log_queue)

            # 输出日志
            if verbose:
                self._print_queue_messages(log_queue)

            if not found_files:
                if verbose:
                    print("未找到符合条件的文件")
                return None

            # 处理输出文件路径
            if auto_rename:
                output_dir = os.path.dirname(output_file) or os.getcwd()
                output_filename = os.path.splitext(os.path.basename(output_file))[0]
                output_ext = os.path.splitext(output_file)[1] or output_format

                final_output_path = get_unique_filepath(
                    output_dir, output_filename, output_ext, log_queue
                )

                if verbose:
                    self._print_queue_messages(log_queue)
            else:
                final_output_path = output_file

            # 聚合代码
            aggregate_code(
                directory,
                found_files,
                final_output_path,
                output_format,
                log_queue,
                progress_queue,
            )

            # 输出最终日志
            if verbose:
                self._print_queue_messages(log_queue)
                print(f"\n✨ 聚合完成！文件已保存到: {final_output_path}")

            return final_output_path

        except Exception as e:
            if verbose:
                print(f"发生错误: {e}")
            return None

    def generate_tree_only(
        self,
        directory: str,
        extensions: list[str] = None,
        ignore_items: set[str] = None,
    ) -> str | None:
        """仅生成文件结构树，不聚合代码内容

        Args:
            directory: 要扫描的根目录
            extensions: 要包含的文件扩展名列表
            ignore_items: 要忽略的文件/文件夹名称或路径

        Returns:
            文件结构树字符串，失败时返回None
        """
        if extensions is None:
            extensions = self.default_extensions.copy()

        if ignore_items is None:
            ignore_items = self.default_ignore_items.copy()

        log_queue = queue.Queue()

        try:
            found_files = find_files(directory, extensions, ignore_items, log_queue)
            if found_files:
                return generate_file_tree(directory, found_files, log_queue)
            return None
        except Exception:
            return None

    def save_config(self, config: dict[str, Any], config_path: str = None) -> bool:
        """保存配置到文件

        Args:
            config: 配置字典
            config_path: 配置文件路径（可选）

        Returns:
            保存成功返回True，否则返回False
        """
        if config_path is None:
            config_path = self.config_file

        try:
            with open(config_path, "w", encoding="utf-8") as f:
                json.dump(config, f, indent=4, ensure_ascii=False)
            return True
        except Exception:
            return False

    def load_config(self, config_path: str = None) -> dict[str, Any] | None:
        """从文件加载配置

        Args:
            config_path: 配置文件路径（可选）

        Returns:
            配置字典，失败时返回None
        """
        if config_path is None:
            config_path = self.config_file

        if not os.path.exists(config_path):
            return None

        try:
            with open(config_path, encoding="utf-8") as f:
                return json.load(f)
        except Exception:
            return None

    def _print_queue_messages(self, log_queue: queue.Queue):
        """打印队列中的所有消息"""
        while not log_queue.empty():
            try:
                message = log_queue.get_nowait()
                print(message)
            except queue.Empty:
                break


def main():
    """命令行接口入口"""
    parser = argparse.ArgumentParser(
        description="代码聚合工具 - 命令行接口",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
使用示例:
  python code_aggregator_api.py /path/to/project
  python code_aggregator_api.py /path/to/project --ext .py,.js,.html
  python code_aggregator_api.py /path/to/project --output ./result.md
  python code_aggregator_api.py /path/to/project --tree-only
        """,
    )

    parser.add_argument("directory", help="要扫描的根目录路径")

    parser.add_argument(
        "--output", "-o", help="输出文件路径（默认：当前目录下的code_summary.md）"
    )

    parser.add_argument(
        "--ext",
        "--extensions",
        help="要包含的文件扩展名，用逗号分隔（默认：.py）",
        default=".py",
    )

    parser.add_argument(
        "--ignore",
        help="要忽略的文件/文件夹名称，用逗号分隔",
        default="venv,__pycache__,.git,.vscode,node_modules,dist,build",
    )

    parser.add_argument(
        "--format", choices=[".md", ".txt"], default=".md", help="输出格式（默认：.md）"
    )

    parser.add_argument(
        "--no-auto-rename",
        action="store_true",
        help="如果输出文件已存在，不自动重命名而是覆盖",
    )

    parser.add_argument(
        "--tree-only",
        action="store_true",
        help="仅生成并打印文件结构树，不聚合代码内容",
    )

    parser.add_argument(
        "--quiet", "-q", action="store_true", help="安静模式，不输出详细日志"
    )

    args = parser.parse_args()

    # 解析参数
    directory = os.path.abspath(args.directory)
    extensions = [ext.strip() for ext in args.ext.split(",") if ext.strip()]
    ignore_items = {item.strip() for item in args.ignore.split(",") if item.strip()}

    # 创建API实例
    api = CodeAggregatorAPI()

    if args.tree_only:
        # 仅生成文件结构树
        tree = api.generate_tree_only(directory, extensions, ignore_items)
        if tree:
            print(tree)
            return 0
        else:
            print("生成文件结构树失败")
            return 1
    else:
        # 聚合代码
        result = api.aggregate_directory(
            directory=directory,
            output_file=args.output,
            extensions=extensions,
            ignore_items=ignore_items,
            output_format=args.format,
            auto_rename=not args.no_auto_rename,
            verbose=not args.quiet,
        )

        if result:
            return 0
        else:
            return 1


if __name__ == "__main__":
    sys.exit(main())
