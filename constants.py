# -*- coding: utf-8 -*-
"""常量定义"""

import re
import os

# --- 正则表达式 ---
# 匹配代码块，例如 ```python ... ```
CODE_BLOCK_PATTERN = re.compile(r"```(\w+)\n(.*?)\n\s*```", re.DOTALL)
# 匹配代码块内首行的文件路径注释，例如 # src/main.py
FIRST_LINE_PATH_COMMENT_PATTERN = re.compile(r"^\s*#\s*(\S+)")
# 匹配路径中的非法字符
INVALID_PATH_CHARS_PATTERN = re.compile(r'[<>:"|?*]')

# --- 默认后缀映射 ---
# 文件后缀到代码块语言标识符的映射
DEFAULT_SUFFIX_MAP = {
	".py": "python",
	".js": "javascript",
	".html": "html",
	".css": "css",
	".md": "markdown",
	".json": "json",
	".xml": "xml",
	".yaml": "yaml",
	".sh": "bash",
	".txt": "text"
	# 可根据需要添加更多映射
}

# --- 配置文件 ---
# 保存和加载后缀映射等设置的文件名
CONFIG_FILE_NAME = "buildGUi_config.json"
# 配置文件相对于主脚本的路径
CONFIG_FILE_PATH = os.path.join(os.path.dirname(__file__), CONFIG_FILE_NAME) if '__file__' in locals() else CONFIG_FILE_NAME


# --- 默认值 ---
DEFAULT_OUTPUT_DIR = os.path.abspath("reconstructed_project")

# --- UI 相关 ---
# 默认窗口大小
DEFAULT_WINDOW_WIDTH = 900
DEFAULT_WINDOW_HEIGHT = 900
# 分割器初始比例
DEFAULT_SPLITTER_SIZES_H = [600, 300]
DEFAULT_SPLITTER_SIZES_V_TOP = [150, 400, 150]

# --- 日志格式 ---
LOG_FORMAT_CONSOLE = '%(asctime)s - %(levelname)s - %(message)s'
LOG_FORMAT_GUI = '%(asctime)s - %(levelname)s - %(message)s'
LOG_DATE_FORMAT_GUI = '%H:%M:%S'