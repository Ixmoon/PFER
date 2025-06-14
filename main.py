# -*- coding: utf-8 -*-
"""
项目文件打包与重建工具

一个功能强大、界面优美的工具，用于将项目文件合并为单个文本，或从文本重建项目。
支持拖拽排序、自定义注释风格、文件类型选择、实时预览、文件类型图标和剪切板功能。
"""
import sys
import os
import re
import json
import logging
import fnmatch
from typing import List, Dict, Optional, Tuple
from dataclasses import dataclass, field

from PySide6.QtWidgets import (
	QApplication, QMainWindow, QWidget, QVBoxLayout, QHBoxLayout,
	QPushButton, QLineEdit, QTextEdit, QFileDialog, QLabel,
	QMessageBox, QStatusBar, QGroupBox, QSplitter, QProgressDialog,
	QTreeWidget, QTreeWidgetItem, QHeaderView, QDialog, QTableWidget,
	QTableWidgetItem, QDialogButtonBox, QAbstractItemView, QTabWidget,
	QListWidget, QListWidgetItem
)
from PySide6.QtGui import QIcon, QTextCursor, QFont
from PySide6.QtCore import Qt, QTimer, Signal, QThread, QByteArray

# 导入编译后的资源文件
try:
	import resources_rc
except ImportError:
	print("错误: 找不到资源文件 `resources_rc.py`。")
	print("请先根据代码注释中的说明，创建并编译 `resources.qrc` 文件。")
	sys.exit(1)


# --- 1. 辅助函数 ---
 
def get_resource_path(relative_path: str) -> str:
    """
    获取资源的绝对路径，兼容源码运行和PyInstaller打包两种情况。
    对于PyInstaller的单文件（--onefile）模式，它会查找.exe文件所在的目录。
    """
    if getattr(sys, 'frozen', False):
        # 打包后的路径
        base_path = os.path.dirname(sys.executable)
    else:
        # 源码运行的路径
        base_path = os.path.abspath(".")
    return os.path.join(base_path, relative_path)
 
 
# --- 2. 常量与核心数据结构 ---
 
@dataclass
class FileInfo:
	"""使用 dataclass 定义文件信息，保持数据清晰"""
	rel_path: str
	content: str
	language: str
	comment_symbol: str
	item_ref: Optional[QTreeWidgetItem] = field(default=None, repr=False) # 反向引用UI项

# 正则表达式
CODE_BLOCK_PATTERN = re.compile(r"```(\w*)\n(.*?)\n\s*```", re.DOTALL)
PATH_COMMENT_PATTERN = re.compile(r"^\s*(?:<!--\s*)?([#|//|;]+)?\s*(\S+)(?:\s*-->)?")
INVALID_PATH_CHARS_PATTERN = re.compile(r'[<>:"|?*]')

# 默认配置文件名
CONFIG_FILE_NAME = "config.json"

# 默认后缀映射表
DEFAULT_SUFFIX_MAP = {
	".py": {"language": "python", "comment": "#"},
	".js": {"language": "javascript", "comment": "//"},
	".ts": {"language": "typescript", "comment": "//"},
	".html": {"language": "html", "comment": "<!--"},
	".css": {"language": "css", "comment": "/*"},
	".scss": {"language": "scss", "comment": "//"},
	".json": {"language": "json", "comment": ""},
	".md": {"language": "markdown", "comment": ""},
	".java": {"language": "java", "comment": "//"},
	".cs": {"language": "csharp", "comment": "//"},
	".cpp": {"language": "cpp", "comment": "//"},
	".h": {"language": "cpp", "comment": "//"},
	".xml": {"language": "xml", "comment": "<!--"},
	".yaml": {"language": "yaml", "comment": "#"},
	".sh": {"language": "bash", "comment": "#"},
	".ini": {"language": "ini", "comment": ";"},
	".txt": {"language": "text", "comment": "#"},
}

# 图标路径映射
FILE_ICON_MAP = {
	'.py': ':/icons/python.svg',
	'.js': ':/icons/js.svg',
	'.html': ':/icons/html.svg',
	'.css': ':/icons/css.svg',
	'.json': ':/icons/json.svg',
	'.md': ':/icons/text.svg',
	'.xml': ':/icons/text.svg',
	'.txt': ':/icons/text.svg',
	'default': ':/icons/file-generic.svg'
}

# --- 2. 自定义控件 ---

class ProjectTreeWidget(QTreeWidget):
	"""支持拖放排序和美化样式的自定义树控件"""
	order_changed = Signal()

	def __init__(self, parent=None):
		super().__init__(parent)
		self.setDragDropMode(QAbstractItemView.DragDropMode.InternalMove)
		self.setSelectionMode(QAbstractItemView.SelectionMode.ExtendedSelection)
		self.setDropIndicatorShown(True)
		self.setDragEnabled(True)
		self.setAlternatingRowColors(True) # 增加可读性

	def dropEvent(self, event):
		"""重写拖放事件，在操作完成后发射信号"""
		super().dropEvent(event)
		if event.source() == self and event.dropAction() == Qt.DropAction.MoveAction:
			self.order_changed.emit()

class SuffixMapEditorDialog(QDialog):
	"""用于编辑后缀、语言和注释映射的对话框"""
	def __init__(self, current_map: dict, parent=None):
		super().__init__(parent)
		self.setWindowTitle("编辑后缀映射")
		self.setWindowIcon(QIcon(":/icons/edit.svg"))
		self.setMinimumSize(550, 450)
		self._edited_map = {k: v.copy() for k, v in current_map.items()}

		self.table_widget = QTableWidget(0, 3)
		self.table_widget.setHorizontalHeaderLabels(["后缀", "语言标识", "注释符号"])
		header = self.table_widget.horizontalHeader()
		header.setSectionResizeMode(0, QHeaderView.ResizeMode.Interactive)
		header.setSectionResizeMode(1, QHeaderView.ResizeMode.Stretch)
		header.setSectionResizeMode(2, QHeaderView.ResizeMode.Interactive)
		self.table_widget.setSortingEnabled(True)

		self.add_btn = QPushButton(QIcon(":/icons/edit.svg"), " 添加行")
		self.remove_btn = QPushButton(QIcon(":/icons/clear-all.svg"), " 删除选中行")
		self.button_box = QDialogButtonBox(QDialogButtonBox.StandardButton.Ok | QDialogButtonBox.StandardButton.Cancel)

		layout = QVBoxLayout(self)
		btn_layout = QHBoxLayout()
		btn_layout.addWidget(self.add_btn)
		btn_layout.addWidget(self.remove_btn)
		btn_layout.addStretch()
		layout.addLayout(btn_layout)
		layout.addWidget(self.table_widget)
		layout.addWidget(self.button_box)

		self._populate_table()
		self._connect_signals()

	def _connect_signals(self):
		self.add_btn.clicked.connect(self._add_row)
		self.remove_btn.clicked.connect(self._remove_row)
		self.button_box.accepted.connect(self._validate_and_accept)
		self.button_box.rejected.connect(self.reject)

	def _populate_table(self):
		self.table_widget.setSortingEnabled(False)
		for suffix, data in sorted(self._edited_map.items()):
			self._add_row(suffix, data.get('language', ''), data.get('comment', ''))
		self.table_widget.setSortingEnabled(True)

	def _add_row(self, suffix="", lang="", comment=""):
		row = self.table_widget.rowCount()
		self.table_widget.insertRow(row)
		self.table_widget.setItem(row, 0, QTableWidgetItem(suffix))
		self.table_widget.setItem(row, 1, QTableWidgetItem(lang))
		self.table_widget.setItem(row, 2, QTableWidgetItem(comment))

	def _remove_row(self):
		rows = sorted({index.row() for index in self.table_widget.selectedIndexes()}, reverse=True)
		for row in rows:
			self.table_widget.removeRow(row)

	def _validate_and_accept(self):
		new_map = {}
		for row in range(self.table_widget.rowCount()):
			suffix_item = self.table_widget.item(row, 0)
			lang_item = self.table_widget.item(row, 1)
			comment_item = self.table_widget.item(row, 2)
			
			suffix = suffix_item.text().strip() if suffix_item else ""
			lang = lang_item.text().strip() if lang_item else ""
			comment = comment_item.text().strip() if comment_item else ""

			if not suffix.startswith('.') or len(suffix) < 2:
				QMessageBox.warning(self, "验证错误", f"第 {row+1} 行: 后缀必须以 '.' 开头且至少包含一个字符。")
				return
			if not lang:
				QMessageBox.warning(self, "验证错误", f"第 {row+1} 行: 语言标识不能为空。")
				return
			if suffix in new_map:
				QMessageBox.warning(self, "验证错误", f"发现重复后缀 '{suffix}'。")
				return
			new_map[suffix] = {"language": lang, "comment": comment}
		
		self._edited_map = new_map
		self.accept()

	def get_edited_map(self) -> dict:
		return self._edited_map


class Worker(QThread):
	"""在后台执行耗时任务的通用工作线程"""
	finished = Signal(object)      # 任务完成时发射，携带结果
	error = Signal(str)          # 发生错误时发射，携带错误信息
	progress = Signal(int, str)  # 报告进度 (当前索引, 当前文件路径)

	def __init__(self, func, *args, **kwargs):
		super().__init__()
		self._func = func
		self._args = args
		self._kwargs = kwargs
		self.is_cancelled = False

	def run(self):
		"""执行任务"""
		try:
			# 将 self (worker instance) 传递给目标函数，以便它可以调用 progress.emit
			result = self._func(self, *self._args, **self._kwargs)
			if not self.is_cancelled:
				self.finished.emit(result)
		except Exception as e:
			logging.error(f"工作线程出错: {e}", exc_info=True)
			if not self.is_cancelled:
				self.error.emit(str(e))
	
	def cancel(self):
		"""请求取消任务"""
		self.is_cancelled = True


# --- 3. 主应用窗口 ---

class ProjectPackerTool(QMainWindow):
	"""主应用窗口类，整合了所有功能"""
	def __init__(self):
		super().__init__()

		self.file_data: List[FileInfo] = []
		self.config: Dict[str, any] = {}
		self.config_file_path = get_resource_path(CONFIG_FILE_NAME)
		self._block_signals = False
		self.worker: Optional[Worker] = None
		self.progress_dialog: Optional[QProgressDialog] = None
		
		self._load_config()
		self._init_ui()
		self._connect_signals()
		self._apply_styles()
		self._update_ui_from_config()
		self._update_button_states()

		self.setWindowTitle("项目文件打包与重建工具")
		self.setWindowIcon(QIcon(':/icons/app-icon.svg'))
		self.setGeometry(100, 100, 1500, 850)
		self.setStatusBar(QStatusBar())
		self.statusBar().showMessage("准备就绪。欢迎使用！")

	def _init_ui(self):
		central_widget = QWidget()
		self.setCentralWidget(central_widget)
		main_layout = QHBoxLayout(central_widget)
		main_layout.setContentsMargins(10, 10, 10, 10)
		main_layout.setSpacing(10)

		# 左侧: 控制面板
		left_panel = QWidget()
		left_panel.setFixedWidth(380)
		left_layout = QVBoxLayout(left_panel)
		left_layout.setSpacing(15)

		# Tab控件
		self.tabs = QTabWidget()
		pack_tab = QWidget()
		reconstruct_tab = QWidget()
		config_tab = QWidget()
		
		self.tabs.addTab(pack_tab, QIcon(":/icons/pack.svg"), "打包项目")
		self.tabs.addTab(reconstruct_tab, QIcon(":/icons/build.svg"), "重建项目")
		self.tabs.addTab(config_tab, QIcon(":/icons/config.svg"), "高级配置")

		self._create_pack_tab(pack_tab)
		self._create_reconstruct_tab(reconstruct_tab)
		self._create_config_tab(config_tab)
		
		left_layout.addWidget(self.tabs)
		
		# 中间和右侧
		self.center_and_right_splitter = QSplitter(Qt.Orientation.Horizontal)
		
		# 中间: 文件树
		tree_group = QGroupBox("项目文件 (可拖拽排序)")
		tree_layout = QVBoxLayout(tree_group)
		self.file_tree = ProjectTreeWidget()
		self.file_tree.setHeaderLabels(["文件路径", "语言"])
		self.file_tree.header().setSectionResizeMode(0, QHeaderView.ResizeMode.Stretch)
		self.file_tree.header().setSectionResizeMode(1, QHeaderView.ResizeMode.Interactive)
		self.file_tree.setColumnWidth(1, 100)
		tree_layout.addWidget(self.file_tree)
		
		# 右侧: 文本预览/编辑区
		text_group = QGroupBox("合并文本预览 / 输入")
		text_layout = QVBoxLayout(text_group)
		
		text_actions_layout = QHBoxLayout()
		self.copy_to_clipboard_btn = QPushButton(QIcon(":/icons/clipboard.svg"), " 复制")
		self.parse_text_btn = QPushButton(QIcon(":/icons/parse.svg"), " 解析")
		self.save_text_btn = QPushButton(QIcon(":/icons/save.svg"), " 保存")
		self.clear_all_btn = QPushButton(QIcon(":/icons/clear-all.svg"), " 清空")
		
		text_actions_layout.addStretch()
		text_actions_layout.addWidget(self.copy_to_clipboard_btn)
		text_actions_layout.addWidget(self.parse_text_btn)
		text_actions_layout.addWidget(self.save_text_btn)
		text_actions_layout.addWidget(self.clear_all_btn)

		self.text_area = QTextEdit()
		self.text_area.setLineWrapMode(QTextEdit.LineWrapMode.NoWrap)
		
		text_layout.addLayout(text_actions_layout)
		text_layout.addWidget(self.text_area)

		# 组装
		self.center_and_right_splitter.addWidget(tree_group)
		self.center_and_right_splitter.addWidget(text_group)
		self.center_and_right_splitter.setSizes([450, 650])

		main_layout.addWidget(left_panel)
		main_layout.addWidget(self.center_and_right_splitter)

	def _create_pack_tab(self, tab):
		layout = QVBoxLayout(tab)
		layout.setSpacing(10)
		layout.setContentsMargins(5, 15, 5, 5)

		# 1. 源目录
		layout.addWidget(QLabel("1. 选择项目源目录:"))
		source_layout = QHBoxLayout()
		self.source_dir_edit = QLineEdit()
		self.browse_source_btn = QPushButton(QIcon(":/icons/browse-folder.svg"), "")
		source_layout.addWidget(self.source_dir_edit)
		source_layout.addWidget(self.browse_source_btn)
		layout.addLayout(source_layout)

		# 2. 文件类型
		layout.addWidget(QLabel("2. 选择要打包的文件类型:"))
		self.suffix_checklist = QListWidget()
		self.suffix_checklist.setSpacing(2)
		layout.addWidget(self.suffix_checklist)
		
		checklist_btn_layout = QHBoxLayout()
		self.select_all_btn = QPushButton("全选")
		self.deselect_all_btn = QPushButton("全不选")
		checklist_btn_layout.addWidget(self.select_all_btn)
		checklist_btn_layout.addWidget(self.deselect_all_btn)
		layout.addLayout(checklist_btn_layout)

		# 3. 排除项
		layout.addWidget(QLabel("3. 排除项 (逗号分隔):"))
		self.exclude_edit = QLineEdit()
		layout.addWidget(self.exclude_edit)
		
		layout.addStretch()
		self.extract_btn = QPushButton(QIcon(":/icons/pack.svg"), " 开始打包")
		self.extract_btn.setObjectName("action_button")
		layout.addWidget(self.extract_btn)

	def _create_reconstruct_tab(self, tab):
		layout = QVBoxLayout(tab)
		layout.setSpacing(10)
		layout.setContentsMargins(5, 15, 5, 5)

		layout.addWidget(QLabel("1. 选择重建输出目录:"))
		output_layout = QHBoxLayout()
		self.output_dir_edit = QLineEdit(os.path.abspath("reconstructed_project"))
		self.browse_output_btn = QPushButton(QIcon(":/icons/browse-folder.svg"), "")
		output_layout.addWidget(self.output_dir_edit)
		output_layout.addWidget(self.browse_output_btn)
		layout.addLayout(output_layout)
		
		layout.addStretch()
		self.reconstruct_btn = QPushButton(QIcon(":/icons/build.svg"), " 开始重建")
		self.reconstruct_btn.setObjectName("action_button")
		layout.addWidget(self.reconstruct_btn)

	def _create_config_tab(self, tab):
		layout = QVBoxLayout(tab)
		layout.setSpacing(10)
		layout.setContentsMargins(5, 15, 5, 5)

		layout.addWidget(QLabel("后缀与语言/注释映射:"))
		self.suffix_map_display = QTextEdit()
		self.suffix_map_display.setReadOnly(True)
		self.suffix_map_display.setFont(QFont("Courier New", 10))
		layout.addWidget(self.suffix_map_display)
		
		config_btn_layout = QHBoxLayout()
		self.edit_map_btn = QPushButton(QIcon(":/icons/edit.svg"), " 编辑映射")
		self.reset_map_btn = QPushButton(QIcon(":/icons/reset.svg"), " 重置为默认")
		config_btn_layout.addWidget(self.edit_map_btn)
		config_btn_layout.addWidget(self.reset_map_btn)
		layout.addLayout(config_btn_layout)
		layout.addStretch()
		
	def _connect_signals(self):
		# 按钮
		self.browse_source_btn.clicked.connect(lambda: self._browse_directory(self.source_dir_edit, "选择项目源目录"))
		self.browse_output_btn.clicked.connect(lambda: self._browse_directory(self.output_dir_edit, "选择重建输出目录"))
		self.extract_btn.clicked.connect(self._run_extraction)
		self.reconstruct_btn.clicked.connect(self._run_reconstruction)
		self.edit_map_btn.clicked.connect(self._edit_suffix_map)
		self.reset_map_btn.clicked.connect(self._reset_suffix_map)
		self.parse_text_btn.clicked.connect(self._parse_text_to_tree)
		self.save_text_btn.clicked.connect(self._save_text_to_file)
		self.copy_to_clipboard_btn.clicked.connect(self._copy_text_to_clipboard)
		self.clear_all_btn.clicked.connect(self._clear_all)
		self.select_all_btn.clicked.connect(lambda: self._set_all_suffixes_checked(True))
		self.deselect_all_btn.clicked.connect(lambda: self._set_all_suffixes_checked(False))

		# 输入变化
		self.source_dir_edit.textChanged.connect(self._update_button_states)
		self.output_dir_edit.textChanged.connect(self._update_button_states)
		self.text_area.textChanged.connect(self._update_button_states)
		self.exclude_edit.textChanged.connect(self._trigger_save_config)
		self.suffix_checklist.itemChanged.connect(self._on_suffix_selection_changed)
		
		# 树视图
		self.file_tree.order_changed.connect(self._on_file_order_changed)
		self.file_tree.itemSelectionChanged.connect(self._highlight_text_for_selection)
		
		# 添加Tooltips
		self._add_tooltips()

	def _add_tooltips(self):
		self.source_dir_edit.setToolTip("选择或输入你的项目根文件夹路径。")
		self.browse_source_btn.setToolTip("浏览文件夹")
		self.suffix_checklist.setToolTip("勾选需要打包进结果的文件扩展名。")
		self.exclude_edit.setToolTip("输入要排除的文件或文件夹，用逗号或换行分隔。\n支持.gitignore风格的通配符，例如:\n.git/, build/, *.log, !important.log")
		self.extract_btn.setToolTip("从源目录中查找、读取并打包文件。")
		self.output_dir_edit.setToolTip("指定一个文件夹用于存放重建后的项目文件。")
		self.browse_output_btn.setToolTip("浏览文件夹")
		self.reconstruct_btn.setToolTip("从文件列表和预览文本中重建项目结构和文件。")
		self.file_tree.setToolTip("显示已打包的文件列表。\n你可以拖拽文件来调整它们在最终文本中的顺序。")
		self.text_area.setToolTip("这里显示合并后的文本，也可以将文本粘贴到此处进行解析。")
		self.copy_to_clipboard_btn.setToolTip("将预览区的所有内容复制到系统剪切板。")
		self.parse_text_btn.setToolTip("从预览区的文本中解析文件结构，更新左侧文件列表。")
		self.save_text_btn.setToolTip("将预览区的文本内容保存为一个.md或.txt文件。")
		self.clear_all_btn.setToolTip("清空文件列表和预览区的所有内容。")
		self.edit_map_btn.setToolTip("打开对话框，自定义文件后缀与编程语言、注释符号的映射关系。")
		self.reset_map_btn.setToolTip("将后缀映射恢复到程序内置的默认设置。")

	# --- 配置管理 (与原版相同) ---
	def _load_config(self):
		try:
			if os.path.exists(self.config_file_path):
				with open(self.config_file_path, 'r', encoding='utf-8') as f:
					self.config = json.load(f)
				if not all(k in self.config for k in ['suffix_map', 'exclude_patterns', 'selected_suffixes']):
					raise ValueError("Config file is missing required keys.")
			else:
				self._reset_config_to_defaults(save=False)
		except (json.JSONDecodeError, ValueError, TypeError) as e:
			logging.warning(f"加载或验证配置文件 '{self.config_file_path}' 失败: {e}. 重置为默认值。")
			self._reset_config_to_defaults(save=False)
		
	def _save_config(self):
		try:
			self.config['exclude_patterns'] = self.exclude_edit.text()
			self.config['selected_suffixes'] = self._get_selected_suffixes()
			self.config['window_geometry'] = self.saveGeometry().toBase64().data().decode('ascii')
			self.config['splitter_state'] = self.center_and_right_splitter.saveState().toBase64().data().decode('ascii')
			with open(self.config_file_path, 'w', encoding='utf-8') as f:
				json.dump(self.config, f, indent=4, ensure_ascii=False)
			logging.info("配置已保存。")
		except IOError as e:
			logging.error(f"保存配置失败: {e}")
			self.statusBar().showMessage("错误: 无法保存配置。", 3000)

	def _trigger_save_config(self):
		QTimer.singleShot(500, self._save_config)

	def _reset_config_to_defaults(self, save=True):
		self.config = {
			'suffix_map': DEFAULT_SUFFIX_MAP.copy(),
			'exclude_patterns': "*.log, *.tmp, build/, dist/, venv/, .git/, .vscode/, __pycache__/",
			'selected_suffixes': list(DEFAULT_SUFFIX_MAP.keys()),
			'window_geometry': None,
			'splitter_state': None
		}
		if save:
			self._save_config()
			self.statusBar().showMessage("配置已重置为默认值。", 2000)

	# --- UI 更新与同步 ---
	def _update_ui_from_config(self):
		self._block_signals = True
		self.exclude_edit.setText(self.config.get('exclude_patterns', ''))
		
		geometry_b64 = self.config.get('window_geometry')
		if geometry_b64:
			self.restoreGeometry(QByteArray.fromBase64(geometry_b64.encode('ascii')))
		
		splitter_state_b64 = self.config.get('splitter_state')
		if splitter_state_b64:
			self.center_and_right_splitter.restoreState(QByteArray.fromBase64(splitter_state_b64.encode('ascii')))
			
		self._update_suffix_map_display()
		self._update_suffix_checklist()
		self._block_signals = False

	def _update_data_from_ui(self):
		self._populate_tree_widget()
		self._regenerate_combined_text()
		self._update_button_states()

	def _update_suffix_map_display(self):
		display_text = [
			f"{suffix:<10} -> {data.get('language', 'N/A'):<15} (注释: {data.get('comment', '无')})"
			for suffix, data in sorted(self.config['suffix_map'].items())
		]
		self.suffix_map_display.setPlainText("\n".join(display_text))

	def _update_suffix_checklist(self):
		self.suffix_checklist.clear()
		all_suffixes = sorted(self.config['suffix_map'].keys())
		selected_suffixes = self.config.get('selected_suffixes', [])
		
		for suffix in all_suffixes:
			item = QListWidgetItem(suffix)
			item.setIcon(self._get_icon_for_file(suffix))
			item.setFlags(item.flags() | Qt.ItemFlag.ItemIsUserCheckable)
			item.setCheckState(Qt.CheckState.Checked if suffix in selected_suffixes else Qt.CheckState.Unchecked)
			self.suffix_checklist.addItem(item)
	
	# --- 核心逻辑 (多线程改造) ---
	def _run_extraction(self):
		if self.worker and self.worker.isRunning():
			QMessageBox.information(self, "任务正在进行", "已有任务在后台运行，请稍候。")
			return
		
		source_path = self.source_dir_edit.text().strip()
		if not os.path.isdir(source_path):
			QMessageBox.warning(self, "输入错误", "请选择一个有效的源目录。")
			return

		selected_suffixes = self._get_selected_suffixes()
		if not selected_suffixes:
			QMessageBox.warning(self, "输入错误", "请至少选择一种文件类型进行打包。")
			return

		exclude_patterns = self._parse_exclusions(self.exclude_edit.text())
		all_filepaths = self._gather_source_files(source_path, exclude_patterns)

		self._set_ui_for_task(True, "正在打包文件...", len(all_filepaths))
		
		self.worker = Worker(self._task_extraction, source_path, selected_suffixes, all_filepaths)
		self.worker.progress.connect(self._update_progress)
		self.worker.finished.connect(self._on_extraction_finished)
		self.worker.error.connect(self._on_task_error)
		self.worker.start()

	def _task_extraction(self, worker: Worker, source_path: str, selected_suffixes: List[str], all_filepaths: List[str]) -> Tuple[List[FileInfo], Dict]:
		new_file_data = []
		stats = {"extracted": 0, "skipped_type": 0, "error": 0}
		for i, fpath in enumerate(all_filepaths):
			if worker.is_cancelled: break
			worker.progress.emit(i, os.path.basename(fpath))

			_, suffix = os.path.splitext(fpath)
			if suffix.lower() not in selected_suffixes:
				stats["skipped_type"] += 1
				continue

			map_entry = self.config['suffix_map'].get(suffix.lower())
			if map_entry:
				try:
					with open(fpath, 'r', encoding='utf-8', errors='ignore') as f:
						content = f.read()
					rel_path = os.path.relpath(fpath, source_path).replace(os.sep, '/')
					new_file_data.append(FileInfo(
						rel_path=rel_path, content=content,
						language=map_entry.get('language', 'text'),
						comment_symbol=map_entry.get('comment', '#')
					))
					stats["extracted"] += 1
				except Exception as e:
					logging.error(f"无法读取文件 {fpath}: {e}")
					stats["error"] += 1
		return new_file_data, stats

	def _on_extraction_finished(self, result: Tuple[List[FileInfo], Dict]):
		self._set_ui_for_task(False)
		if not result: return # Canceled or Error

		new_file_data, stats = result
		self.file_data = new_file_data
		self._update_data_from_ui()
		
		summary = (f"打包完成!\n\n"
				   f"  - 已打包: {stats['extracted']} 个文件\n"
				   f"  - 因类型跳过: {stats['skipped_type']} 个文件\n"
				   f"  - 读取错误: {stats['error']} 个文件")
		QMessageBox.information(self, "打包摘要", summary)
		self.statusBar().showMessage(f"成功打包 {stats['extracted']} 个文件。", 5000)

	def _run_reconstruction(self):
		if self.worker and self.worker.isRunning():
			QMessageBox.information(self, "任务正在进行", "已有任务在后台运行，请稍候。")
			return
			
		output_path = self.output_dir_edit.text().strip()
		if not output_path or not self.file_data:
			QMessageBox.warning(self, "输入错误", "请选择一个输出目录，并确保文件树中有文件。")
			return

		if os.path.exists(output_path) and os.listdir(output_path):
			reply = QMessageBox.question(self, "确认覆盖", f"输出目录 '{output_path}' 非空，文件可能被覆盖。\n是否继续？",
										 QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No)
			if reply != QMessageBox.StandardButton.Yes: return

		self._set_ui_for_task(True, "正在重建项目...", len(self.file_data))
		
		self.worker = Worker(self._task_reconstruction, output_path, self.file_data)
		self.worker.progress.connect(self._update_progress)
		self.worker.finished.connect(self._on_reconstruction_finished)
		self.worker.error.connect(self._on_task_error)
		self.worker.start()

	def _task_reconstruction(self, worker: Worker, output_path: str, file_data: List[FileInfo]) -> Dict:
		stats = {"created": 0, "error": 0, "invalid_path": 0}
		for i, file_info in enumerate(file_data):
			if worker.is_cancelled: break
			worker.progress.emit(i, file_info.rel_path)

			if ".." in file_info.rel_path.split('/') or INVALID_PATH_CHARS_PATTERN.search(file_info.rel_path):
				logging.warning(f"检测到无效或不安全的路径，已跳过: {file_info.rel_path}")
				stats["invalid_path"] += 1
				continue
			
			try:
				full_path = os.path.join(output_path, file_info.rel_path)
				os.makedirs(os.path.dirname(full_path), exist_ok=True)
				with open(full_path, 'w', encoding='utf-8', newline='\n') as f:
					f.write(file_info.content)
				stats["created"] += 1
			except (IOError, OSError) as e:
				logging.error(f"无法写入文件 {file_info.rel_path}: {e}")
				stats["error"] += 1
		return stats

	def _on_reconstruction_finished(self, stats: Dict):
		self._set_ui_for_task(False)
		if not stats: return # Canceled or Error
		
		summary = (f"重建完成!\n\n"
				   f"  - 已创建: {stats['created']} 个文件\n"
				   f"  - 写入错误: {stats['error']} 个文件\n"
				   f"  - 无效路径跳过: {stats['invalid_path']} 个文件")
		QMessageBox.information(self, "重建摘要", summary)
		self.statusBar().showMessage(f"成功重建 {stats['created']} 个文件。", 5000)

	# --- 任务状态与UI管理 ---
	def _set_ui_for_task(self, is_running: bool, progress_title: str = "", max_value: int = 0):
		"""根据任务是否正在运行来启用/禁用UI控件"""
		self.extract_btn.setDisabled(is_running)
		self.reconstruct_btn.setDisabled(is_running)
		self.parse_text_btn.setDisabled(is_running)
		self.clear_all_btn.setDisabled(is_running)
		
		if is_running:
			self.progress_dialog = QProgressDialog(progress_title, "取消", 0, max_value, self)
			self.progress_dialog.setWindowModality(Qt.WindowModality.WindowModal)
			self.progress_dialog.canceled.connect(self._cancel_task)
			self.progress_dialog.show()
		elif self.progress_dialog:
			self.progress_dialog.close()
			self.progress_dialog = None
		
		self._update_button_states() # 重新评估其他按钮状态

	def _update_progress(self, value: int, label: str):
		if self.progress_dialog:
			self.progress_dialog.setValue(value)
			self.progress_dialog.setLabelText(f"处理中: {label}...")

	def _cancel_task(self):
		if self.worker:
			self.worker.cancel()
		self._set_ui_for_task(False)
		self.statusBar().showMessage("任务已取消。", 3000)

	def _on_task_error(self, error_message: str):
		self._set_ui_for_task(False)
		QMessageBox.critical(self, "任务出错", f"后台任务执行失败:\n{error_message}")
		self.statusBar().showMessage("任务执行出错。", 5000)
		
	def _parse_text_to_tree(self):
		full_content = self.text_area.toPlainText()
		if not full_content.strip():
			QMessageBox.warning(self, "无输入", "文本区域是空的。")
			return

		path_to_info_map: Dict[str, FileInfo] = {}
		
		for match in CODE_BLOCK_PATTERN.finditer(full_content):
			language = match.group(1)
			block_content = match.group(2).strip()
			
			first_line = block_content.split('\n', 1)[0]
			path_match = PATH_COMMENT_PATTERN.match(first_line)
			
			if path_match:
				comment_symbol = path_match.group(1) or ''
				rel_path = path_match.group(2).strip()
				content = block_content.split('\n', 1)[1] if '\n' in block_content else ''
				path_to_info_map[rel_path] = FileInfo(rel_path, content, language, comment_symbol)
			else:
				logging.warning(f"跳过语言为'{language}'的代码块，因缺少有效的路径注释。")

		self.file_data = list(path_to_info_map.values())
		self._update_data_from_ui()
		self.statusBar().showMessage(f"从文本中解析出 {len(self.file_data)} 个文件。", 3000)

	# --- 事件处理与槽函数 (与原版相同) ---
	def _on_file_order_changed(self):
		new_order_data = [self.file_tree.topLevelItem(i).data(0, Qt.ItemDataRole.UserRole)
						  for i in range(self.file_tree.topLevelItemCount())]
		self.file_data = [info for info in new_order_data if info]
		self._regenerate_combined_text()
		self.statusBar().showMessage("文件顺序已更新。", 1500)

	def _on_suffix_selection_changed(self):
		if not self._block_signals:
			self._trigger_save_config()

	def _clear_all(self):
		reply = QMessageBox.question(self, "确认清空", "确定要清空所有数据（文件列表和文本区）吗？\n此操作不可撤销。",
									 QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No, QMessageBox.StandardButton.No)
		if reply == QMessageBox.StandardButton.Yes:
			self.file_data = []
			self.text_area.clear()
			self._update_data_from_ui()
			self.statusBar().showMessage("已清空所有数据。", 2000)

	def _edit_suffix_map(self):
		dialog = SuffixMapEditorDialog(self.config['suffix_map'], self)
		if dialog.exec():
			self.config['suffix_map'] = dialog.get_edited_map()
			self._update_ui_from_config()
			self._save_config()
			self.statusBar().showMessage("后缀映射已更新。", 2000)

	def _reset_suffix_map(self):
		reply = QMessageBox.question(self, "确认重置", "确定要将后缀映射重置为默认值吗？",
									 QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No)
		if reply == QMessageBox.StandardButton.Yes:
			self._reset_config_to_defaults(save=True)
			self._update_ui_from_config()

	# --- UI 辅助方法 (重要修改) ---
	def _populate_tree_widget(self):
		"""根据 self.file_data 刷新文件树视图 (已更新)"""
		self.file_tree.clear()
		for file_info in self.file_data:
			# 增加了第二列“语言”
			item = QTreeWidgetItem([file_info.rel_path, file_info.language])
			item.setIcon(0, self._get_icon_for_file(file_info.rel_path))
			item.setData(0, Qt.ItemDataRole.UserRole, file_info)
			item.setToolTip(0, f"路径: {file_info.rel_path}\n语言: {file_info.language}")
			file_info.item_ref = item
			self.file_tree.addTopLevelItem(item)

	def _regenerate_combined_text(self):
		"""根据 self.file_data 生成合并后的文本 (与原版相同)"""
		blocks = []
		for file_info in self.file_data:
			if "<!--" in file_info.comment_symbol:
				comment_line = f"<!-- {file_info.rel_path} -->\n"
			elif file_info.comment_symbol:
				comment_line = f"{file_info.comment_symbol} {file_info.rel_path}\n"
			else:
				comment_line = ""

			block = (f"```{file_info.language}\n"
					 f"{comment_line}"
					 f"{file_info.content.strip()}\n"
					 "```\n")
			blocks.append(block)
		
		self.text_area.blockSignals(True)
		self.text_area.setPlainText("\n".join(blocks))
		self.text_area.blockSignals(False)
		self._update_button_states()

	def _update_button_states(self):
		is_source_valid = os.path.isdir(self.source_dir_edit.text())
		is_output_valid = bool(self.output_dir_edit.text())
		has_files_in_tree = bool(self.file_data)
		has_text = bool(self.text_area.toPlainText().strip())
		
		self.extract_btn.setEnabled(is_source_valid)
		self.reconstruct_btn.setEnabled(has_files_in_tree and is_output_valid)
		self.parse_text_btn.setEnabled(has_text)
		self.save_text_btn.setEnabled(has_text)
		self.copy_to_clipboard_btn.setEnabled(has_text)
		self.clear_all_btn.setEnabled(has_files_in_tree or has_text)

	def _highlight_text_for_selection(self):
		"""高亮显示选中文件对应的文本块 (与原版相同)"""
		selected_items = self.file_tree.selectedItems()
		if not selected_items: return
		
		file_info = selected_items[0].data(0, Qt.ItemDataRole.UserRole)
		if not file_info: return

		search_str = f"```{file_info.language}"
		doc = self.text_area.document()
		
		cursor = QTextCursor(doc)
		while True:
			cursor = doc.find(search_str, cursor)
			if cursor.isNull(): break

			check_cursor = QTextCursor(cursor)
			check_cursor.movePosition(QTextCursor.MoveOperation.NextBlock)
			line_text = check_cursor.block().text().strip()
			
			if file_info.rel_path in line_text:
				block_start_cursor = QTextCursor(cursor)
				block_start_cursor.movePosition(QTextCursor.MoveOperation.StartOfLine)
				
				block_end_cursor = doc.find("```", block_start_cursor)
				if not block_end_cursor.isNull():
					block_end_cursor.movePosition(QTextCursor.MoveOperation.EndOfLine)
					
					selection_cursor = QTextCursor(block_start_cursor)
					selection_cursor.setPosition(block_end_cursor.position(), QTextCursor.MoveMode.KeepAnchor)
					
					self.text_area.setTextCursor(selection_cursor)
					self.text_area.ensureCursorVisible()
				return

	def _get_icon_for_file(self, filename: str) -> QIcon:
		"""根据文件名后缀返回一个内嵌的资源图标 (已更新)"""
		ext = os.path.splitext(filename)[1].lower()
		icon_path = FILE_ICON_MAP.get(ext, FILE_ICON_MAP['default'])
		return QIcon(icon_path)

	# --- 通用辅助方法 (与原版相同, 细微调整) ---
	def _browse_directory(self, line_edit: QLineEdit, title: str):
		directory = QFileDialog.getExistingDirectory(self, title, line_edit.text())
		if directory:
			line_edit.setText(os.path.abspath(directory))
			
	def _save_text_to_file(self):
		path, _ = QFileDialog.getSaveFileName(self, "保存合并文本", "", "Markdown 文件 (*.md);;文本文件 (*.txt);;所有文件 (*)")
		if path:
			try:
				with open(path, 'w', encoding='utf-8', newline='\n') as f:
					f.write(self.text_area.toPlainText())
				self.statusBar().showMessage(f"文本已保存到 {os.path.basename(path)}", 3000)
			except IOError as e:
				QMessageBox.critical(self, "保存错误", f"无法保存文件:\n{e}")

	def _copy_text_to_clipboard(self):
		clipboard = QApplication.clipboard()
		clipboard.setText(self.text_area.toPlainText())
		self.statusBar().showMessage("已复制到剪切板。", 2000)

	def _get_selected_suffixes(self) -> List[str]:
		return [self.suffix_checklist.item(i).text() for i in range(self.suffix_checklist.count()) if self.suffix_checklist.item(i).checkState() == Qt.CheckState.Checked]
	
	def _set_all_suffixes_checked(self, checked: bool):
		self._block_signals = True
		state = Qt.CheckState.Checked if checked else Qt.CheckState.Unchecked
		for i in range(self.suffix_checklist.count()):
			self.suffix_checklist.item(i).setCheckState(state)
		self._block_signals = False
		self._on_suffix_selection_changed()

	def _parse_exclusions(self, exclude_str: str) -> List[str]:
		"""解析排除字符串为模式列表，忽略空行和注释。"""
		patterns = []
		# 支持逗号和换行符作为分隔符
		delimiters = re.compile(r'[,\n]')
		for line in delimiters.split(exclude_str):
			line = line.strip()
			if line and not line.startswith('#'):
				patterns.append(line)
		return patterns

	def _gather_source_files(self, root_dir: str, exclude_patterns: List[str]) -> List[str]:
		"""搜集源文件，使用 .gitignore 风格的排除规则。"""
		filepaths = []
		for root, dirs, files in os.walk(root_dir, topdown=True):
			# 必须先处理目录，这样可以避免进入被排除的目录
			dirs[:] = [d for d in dirs if not self._is_excluded(os.path.join(root, d), root_dir, exclude_patterns)]
			for name in files:
				fpath = os.path.join(root, name)
				if not self._is_excluded(fpath, root_dir, exclude_patterns):
					filepaths.append(fpath)
		return filepaths

	def _is_excluded(self, path: str, root: str, patterns: List[str]) -> bool:
		"""
		检查路径是否匹配 .gitignore 风格的模式。
		- 后匹配的规则会覆盖先匹配的规则。
		- `!` 前缀表示否定匹配。
		- `/` 后缀表示只匹配目录。
		"""
		rel_path = os.path.relpath(path, root).replace(os.sep, '/')
		is_dir = os.path.isdir(path)
		
		excluded = False
		for pattern in patterns:
			negate = pattern.startswith('!')
			if negate:
				pattern = pattern[1:]

			# 规范化模式：移除尾部斜杠，但记录下来
			is_dir_pattern = pattern.endswith('/')
			if is_dir_pattern:
				pattern = pattern.rstrip('/')

			# 如果是目录模式，但当前路径不是目录，则跳过
			if is_dir_pattern and not is_dir:
				continue

			# 检查匹配
			match = False
			# 模式不含斜杠，匹配任意层级的基本名称
			if '/' not in pattern:
				if fnmatch.fnmatch(os.path.basename(rel_path), pattern):
					match = True
			# 模式包含斜杠，从根开始匹配
			else:
				if fnmatch.fnmatch(rel_path, pattern):
					match = True
			
			if match:
				excluded = not negate
				
		return excluded

	def closeEvent(self, event):
		if self.worker and self.worker.isRunning():
			reply = QMessageBox.question(self, "确认退出", "有任务正在后台运行，确定要强制退出吗？",
										 QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No, QMessageBox.StandardButton.No)
			if reply == QMessageBox.StandardButton.Yes:
				self.worker.cancel()
				self.worker.wait(500) # 等待最多500ms让线程结束
			else:
				event.ignore()
				return
		
		self._save_config()
		super().closeEvent(event)

	# --- 界面样式 (全新设计) ---
	def _apply_styles(self):
		"""从外部文件加载并应用QSS样式表"""
		try:
			style_path = get_resource_path('style.qss')
			with open(style_path, 'r', encoding='utf-8') as f:
				style_sheet = f.read()
			self.setStyleSheet(style_sheet)
		except FileNotFoundError:
			logging.error("样式文件 'style.qss' 未找到。请确保它与主程序在同一目录下。")
			# 提供一个基础的回退样式
			self.setStyleSheet("QMainWindow { background-color: #2c313c; color: white; }")
		except Exception as e:
			logging.error(f"加载样式文件失败: {e}")

# --- 4. 应用程序入口点 ---
if __name__ == "__main__":
	logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
	
	app = QApplication(sys.argv)
	
	window = ProjectPackerTool()
	window.show()
	
	sys.exit(app.exec())