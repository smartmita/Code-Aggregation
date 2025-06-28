import os
import sys
import json
import tkinter as tk
from tkinter import ttk, filedialog, messagebox, scrolledtext
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

            # 2. 根据完整路径过滤
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


# --- GUI 应用 v1.5 (自动重命名) ---
class CodeAggregatorApp:
    CONFIG_FILE = "code_aggregator_config.json"

    def __init__(self, root):
        self.root = root
        self.root.title("代码聚合工具 v1.5 (自动重命名)")
        self.root.geometry("800x780")
        self.root.minsize(700, 650)

        self.script_dir = self.get_script_directory()

        main_frame = ttk.Frame(root, padding="10")
        main_frame.pack(fill=tk.BOTH, expand=True)

        self.log_queue = queue.Queue()
        self.progress_queue = queue.Queue()

        self.create_widgets(main_frame)
        self.load_config()

        self.root.protocol("WM_DELETE_WINDOW", self.on_closing)
        self.process_log_queue()

    def get_script_directory(self):
        if getattr(sys, "frozen", False):
            application_path = os.path.dirname(sys.executable)
        else:
            application_path = os.path.dirname(os.path.abspath(__file__))
        return application_path

    def create_widgets(self, parent):
        # --- 1. 目标目录选择 ---
        dir_frame = ttk.LabelFrame(
            parent, text="1. 选择要提取代码的根目录", padding="10"
        )
        dir_frame.pack(fill=tk.X, padx=5, pady=5)

        self.dir_path = tk.StringVar()
        ttk.Entry(dir_frame, textvariable=self.dir_path).pack(
            side=tk.LEFT, fill=tk.X, expand=True, padx=(0, 5)
        )
        ttk.Button(dir_frame, text="浏览...", command=self.select_directory).pack(
            side=tk.LEFT
        )

        # --- 2. 提取文件类型 ---
        ext_frame = ttk.LabelFrame(parent, text="2. 选择要提取的文件类型", padding="10")
        ext_frame.pack(fill=tk.X, padx=5, pady=5)

        self.ext_vars = {}
        common_exts = [
            ".py",
            ".js",
            ".html",
            ".css",
            ".c",
            ".h",
            ".cpp",
            ".java",
            ".go",
            ".rs",
        ]

        ext_check_frame = ttk.Frame(ext_frame)
        ext_check_frame.pack(fill=tk.X)
        for i, ext in enumerate(common_exts):
            var = tk.BooleanVar(value=(ext == ".py"))
            self.ext_vars[ext] = var
            ttk.Checkbutton(ext_check_frame, text=ext, variable=var).pack(
                side=tk.LEFT, padx=5
            )

        ext_custom_frame = ttk.Frame(ext_frame, padding=(0, 5))
        ext_custom_frame.pack(fill=tk.X)
        ttk.Label(ext_custom_frame, text="其他类型 (用逗号分隔):").pack(
            side=tk.LEFT, padx=(0, 5)
        )
        self.custom_extensions = tk.StringVar()
        self.custom_extensions_entry = ttk.Entry(
            ext_custom_frame, textvariable=self.custom_extensions
        )
        self.custom_extensions_entry.pack(fill=tk.X, expand=True)
        self._setup_placeholder()

        # --- 3. 忽略文件夹/文件 ---
        ignore_frame = ttk.LabelFrame(
            parent,
            text="3. 设置要忽略的文件夹/文件 (支持按名称或完整路径忽略)",
            padding="10",
        )
        ignore_frame.pack(fill=tk.BOTH, expand=True, padx=5, pady=5)

        defaults_frame = ttk.Frame(ignore_frame)
        defaults_frame.pack(fill=tk.X)
        self.ignore_vars = {}
        common_ignores = [
            "venv",
            "__pycache__",
            ".git",
            ".vscode",
            "node_modules",
            "dist",
            "build",
        ]
        for item in common_ignores:
            var = tk.BooleanVar(value=True)
            self.ignore_vars[item] = var
            ttk.Checkbutton(defaults_frame, text=item, variable=var).pack(
                side=tk.LEFT, padx=5
            )

        custom_frame = ttk.Frame(ignore_frame, padding=(0, 10))
        custom_frame.pack(fill=tk.BOTH, expand=True)
        list_container = ttk.Frame(custom_frame)
        list_container.pack(side=tk.LEFT, fill=tk.BOTH, expand=True, padx=(0, 10))
        self.ignore_listbox = tk.Listbox(list_container, height=5)
        scrollbar = ttk.Scrollbar(
            list_container, orient=tk.VERTICAL, command=self.ignore_listbox.yview
        )
        self.ignore_listbox.config(yscrollcommand=scrollbar.set)
        scrollbar.pack(side=tk.RIGHT, fill=tk.Y)
        self.ignore_listbox.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)
        btn_frame = ttk.Frame(custom_frame)
        btn_frame.pack(side=tk.LEFT, fill=tk.Y)
        ttk.Button(btn_frame, text="添加文件夹", command=self.add_ignore_folder).pack(
            pady=2, fill=tk.X
        )
        ttk.Button(btn_frame, text="添加文件", command=self.add_ignore_file).pack(
            pady=2, fill=tk.X
        )
        ttk.Button(btn_frame, text="移除选中项", command=self.remove_ignore_item).pack(
            pady=2, fill=tk.X
        )

        # --- 4. 输出设置与配置 ---
        output_frame = ttk.LabelFrame(parent, text="4. 输出设置与配置", padding="10")
        output_frame.pack(fill=tk.X, padx=5, pady=5)

        output_dir_frame = ttk.Frame(output_frame)
        output_dir_frame.pack(fill=tk.X, pady=(0, 10))
        ttk.Label(output_dir_frame, text="输出目录:").pack(side=tk.LEFT, padx=(0, 5))
        self.output_dir_path = tk.StringVar()
        ttk.Entry(output_dir_frame, textvariable=self.output_dir_path).pack(
            side=tk.LEFT, fill=tk.X, expand=True, padx=(0, 5)
        )
        ttk.Button(
            output_dir_frame, text="浏览...", command=self.select_output_directory
        ).pack(side=tk.LEFT)

        output_file_frame = ttk.Frame(output_frame)
        output_file_frame.pack(fill=tk.X)
        ttk.Label(output_file_frame, text="文件名:").pack(side=tk.LEFT, padx=(0, 5))
        self.output_filename = tk.StringVar(value="code_summary")
        ttk.Entry(output_file_frame, textvariable=self.output_filename, width=30).pack(
            side=tk.LEFT
        )

        ttk.Label(output_file_frame, text="格式:").pack(side=tk.LEFT, padx=(15, 5))
        self.output_format = tk.StringVar(value=".md")
        ttk.OptionMenu(
            output_file_frame, self.output_format, ".md", ".md", ".txt"
        ).pack(side=tk.LEFT)

        save_btn_frame = ttk.Frame(output_frame)
        save_btn_frame.pack(fill=tk.X, pady=(10, 0))
        self.save_status_label = ttk.Label(save_btn_frame, text="")
        self.save_status_label.pack(side=tk.RIGHT, padx=(5, 0))
        self.save_button = ttk.Button(
            save_btn_frame, text="保存当前配置", command=self.save_config_manual
        )
        self.save_button.pack(side=tk.RIGHT)

        # --- 5. 执行与日志 ---
        action_frame = ttk.LabelFrame(parent, text="5. 执行与日志", padding="10")
        action_frame.pack(fill=tk.BOTH, expand=True, padx=5, pady=5)

        self.start_button = ttk.Button(
            action_frame, text="开始聚合", command=self.start_aggregation_thread
        )
        self.start_button.pack(pady=5)

        self.progress_bar = ttk.Progressbar(
            action_frame, orient="horizontal", mode="determinate"
        )
        self.progress_bar.pack(fill=tk.X, pady=5)

        self.log_area = scrolledtext.ScrolledText(
            action_frame, height=10, wrap=tk.WORD, state=tk.DISABLED
        )
        self.log_area.pack(fill=tk.BOTH, expand=True, pady=5)

    def _setup_placeholder(self):
        self.placeholder_text = "示例：.toml,.csv,.log"
        self.placeholder_color = "grey"
        self.default_fg_color = self.custom_extensions_entry.cget("foreground")
        self.custom_extensions_entry.bind("<FocusIn>", self._on_entry_focus_in)
        self.custom_extensions_entry.bind("<FocusOut>", self._on_entry_focus_out)
        self._on_entry_focus_out(None)

    def _on_entry_focus_in(self, event):
        if self.custom_extensions_entry.get() == self.placeholder_text:
            self.custom_extensions_entry.delete(0, "end")
            self.custom_extensions_entry.config(foreground=self.default_fg_color)

    def _on_entry_focus_out(self, event):
        if not self.custom_extensions_entry.get():
            self.custom_extensions_entry.insert(0, self.placeholder_text)
            self.custom_extensions_entry.config(foreground=self.placeholder_color)

    def select_directory(self):
        path = filedialog.askdirectory(initialdir=self.dir_path.get())
        if path:
            self.dir_path.set(path)

    def select_output_directory(self):
        path = filedialog.askdirectory(initialdir=self.output_dir_path.get())
        if path:
            self.output_dir_path.set(path)

    def add_ignore_folder(self):
        path = filedialog.askdirectory(title="选择要忽略的文件夹")
        if path:
            abs_path = os.path.abspath(path)
            self._add_to_ignore_list(abs_path)

    def add_ignore_file(self):
        path = filedialog.askopenfilename(title="选择要忽略的文件")
        if path:
            abs_path = os.path.abspath(path)
            self._add_to_ignore_list(abs_path)

    def _add_to_ignore_list(self, item_path):
        if item_path and item_path not in self.ignore_listbox.get(0, tk.END):
            self.ignore_listbox.insert(tk.END, item_path)

    def remove_ignore_item(self):
        selected_indices = self.ignore_listbox.curselection()
        for i in reversed(selected_indices):
            self.ignore_listbox.delete(i)

    def start_aggregation_thread(self):
        if not self.dir_path.get():
            messagebox.showerror("错误", "请先选择一个要提取的根目录！")
            return

        self.start_button.config(state=tk.DISABLED)
        self.progress_bar["value"] = 0
        self.log_area.config(state=tk.NORMAL)
        self.log_area.delete("1.0", tk.END)
        self.log_area.config(state=tk.DISABLED)

        thread = threading.Thread(target=self.run_aggregation_logic, daemon=True)
        thread.start()

    def run_aggregation_logic(self):
        try:
            # 1. 收集配置
            target_dir = self.dir_path.get()
            extensions = [ext for ext, var in self.ext_vars.items() if var.get()]
            custom_ext_str = self.custom_extensions.get()
            if custom_ext_str != self.placeholder_text:
                custom_exts = [
                    ext.strip() for ext in custom_ext_str.split(",") if ext.strip()
                ]
                extensions.extend(custom_exts)

            if not extensions:
                self.log_queue.put("错误: 未选择任何文件类型!")
                self.log_queue.put("FINISH_TASK")
                return

            ignored_items = {
                name for name, var in self.ignore_vars.items() if var.get()
            }
            custom_ignored = self.ignore_listbox.get(0, tk.END)
            ignored_items.update(custom_ignored)

            output_dir = self.output_dir_path.get()
            if not output_dir or not os.path.isdir(output_dir):
                self.log_queue.put(
                    f"警告: 输出目录 '{output_dir}' 无效。将使用程序所在目录。"
                )
                output_dir = self.script_dir
                self.root.after(0, lambda: self.output_dir_path.set(output_dir))

            # 【修改】调用新函数处理文件名冲突
            base_filename = self.output_filename.get()
            output_format = self.output_format.get()
            output_file_path = get_unique_filepath(
                output_dir, base_filename, output_format, self.log_queue
            )

            # 2. 执行文件查找和聚合
            found_files = find_files(
                target_dir, extensions, ignored_items, self.log_queue
            )

            if found_files:
                aggregate_code(
                    target_dir,
                    found_files,
                    output_file_path,
                    output_format,
                    self.log_queue,
                    self.progress_queue,
                )
                self.log_queue.put(f"SUCCESS:{output_file_path}")
            else:
                self.log_queue.put("未找到符合条件的文件。任务结束。")
        except Exception as e:
            self.log_queue.put(f"发生未预料的错误: {e}")
        finally:
            self.log_queue.put("FINISH_TASK")

    def process_log_queue(self):
        try:
            while not self.log_queue.empty():
                message = self.log_queue.get_nowait()
                if isinstance(message, str):
                    if message.startswith("SUCCESS:"):
                        output_file = message.split(":", 1)[1]
                        if messagebox.askyesno(
                            "完成",
                            f"代码已成功聚合!\n\n文件保存在:\n'{output_file}'\n\n是否立即打开该文件？",
                        ):
                            try:
                                os.startfile(os.path.abspath(output_file))
                            except Exception as e:
                                messagebox.showerror("错误", f"无法自动打开文件: {e}")
                    elif message == "FINISH_TASK":
                        self.start_button.config(state=tk.NORMAL)
                    else:
                        self.log_area.config(state=tk.NORMAL)
                        self.log_area.insert(tk.END, message + "\n")
                        self.log_area.see(tk.END)
                        self.log_area.config(state=tk.DISABLED)

            while not self.progress_queue.empty():
                self.progress_bar["value"] = self.progress_queue.get_nowait()

        except queue.Empty:
            pass
        finally:
            self.root.after(100, self.process_log_queue)

    def on_closing(self):
        if messagebox.askokcancel(
            "退出", "确定要退出吗？\n(当前配置将在退出时自动保存)"
        ):
            self.save_config()
            self.root.destroy()

    def save_config_manual(self):
        self.save_config()
        self.save_status_label.config(text="配置已保存!")
        self.root.after(2000, lambda: self.save_status_label.config(text=""))

    def save_config(self):
        custom_ext_val = self.custom_extensions.get()
        if custom_ext_val == self.placeholder_text:
            custom_ext_val = ""

        config = {
            "directory": self.dir_path.get(),
            "output_directory": self.output_dir_path.get(),
            "extensions_checked": {
                ext: var.get() for ext, var in self.ext_vars.items()
            },
            "extensions_custom": custom_ext_val,
            "ignore_defaults": {
                name: var.get() for name, var in self.ignore_vars.items()
            },
            "ignore_custom": list(self.ignore_listbox.get(0, tk.END)),
            "output_filename": self.output_filename.get(),
            "output_format": self.output_format.get(),
        }
        try:
            config_path = os.path.join(self.script_dir, self.CONFIG_FILE)
            with open(config_path, "w", encoding="utf-8") as f:
                json.dump(config, f, indent=4)
        except IOError as e:
            print(f"无法保存配置: {e}")

    def load_config(self):
        config_path = os.path.join(self.script_dir, self.CONFIG_FILE)
        if not os.path.exists(config_path):
            self.output_dir_path.set(self.script_dir)
            return
        try:
            with open(config_path, "r", encoding="utf-8") as f:
                config = json.load(f)

            self.dir_path.set(config.get("directory", ""))
            self.output_dir_path.set(config.get("output_directory", self.script_dir))

            if "extensions_checked" in config:
                for ext, value in config["extensions_checked"].items():
                    if ext in self.ext_vars:
                        self.ext_vars[ext].set(value)

            self.custom_extensions.set(config.get("extensions_custom", ""))
            self._on_entry_focus_out(None)

            if "ignore_defaults" in config:
                for name, value in config["ignore_defaults"].items():
                    if name in self.ignore_vars:
                        self.ignore_vars[name].set(value)

            if "ignore_custom" in config:
                self.ignore_listbox.delete(0, tk.END)
                for item in config["ignore_custom"]:
                    self.ignore_listbox.insert(tk.END, item)

            self.output_filename.set(config.get("output_filename", "code_summary"))
            self.output_format.set(config.get("output_format", ".md"))

        except (IOError, json.JSONDecodeError) as e:
            print(f"无法加载配置: {e}")
            self.output_dir_path.set(self.script_dir)


if __name__ == "__main__":
    root = tk.Tk()

    try:
        if sys.platform == "win32":
            style = ttk.Style(root)
            if "vista" in style.theme_names():
                style.theme_use("vista")
    except tk.TclError:
        print("未找到 'vista' 主题，将使用默认主题。")

    app = CodeAggregatorApp(root)
    root.mainloop()
