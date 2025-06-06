# -*- coding: utf-8 -*-
"""项目文件提取与重建 GUI"""

import sys
import logging
import os
from typing import Dict, List, Set, Optional, Any # 导入类型提示

from PySide6.QtWidgets import (
	QApplication, QMainWindow, QWidget, QVBoxLayout, QHBoxLayout,
	QPushButton, QLineEdit, QTextEdit, QFileDialog, QLabel,
	QMessageBox, QStatusBar, QGroupBox, QSplitter, QProgressDialog,
	QDialog, QTableWidget, QTableWidgetItem, QDialogButtonBox, QHeaderView,
	QCheckBox, QScrollArea
)
from PySide6.QtGui import QIcon, QDesktopServices, QPalette, QColor
from PySide6.QtCore import Qt, QUrl, QTimer # 引入 QTimer 用于延迟保存配置

# 导入新模块
try:
	from . import constants
	from .config_manager import ConfigManager
	from .file_processor import ProjectReconstructor, combine_files, parse_exclusions
except ImportError:
	# 在直接运行脚本时回退
	import constants
	from config_manager import ConfigManager
	from file_processor import ProjectReconstructor, combine_files, parse_exclusions

# --- 日志设置 ---
log = logging.getLogger(__name__)
# 日志级别将在 main 函数中设置

# --- 自定义日志处理器 ---
class QTextEditLogHandler(logging.Handler):
	"""一个将日志记录写入 QTextEdit 小部件的处理器类。"""
	def __init__(self, text_edit_widget):
		super().__init__()
		self.widget = text_edit_widget
		# 设置一个简洁的日志格式 (使用常量)
		self.setFormatter(logging.Formatter(constants.LOG_FORMAT_GUI, datefmt=constants.LOG_DATE_FORMAT_GUI))

	def emit(self, record):
		"""将格式化后的日志消息追加到 QTextEdit。"""
		try:
			msg = self.format(record)
			# 确保在 UI 线程中更新小部件
			self.widget.append(msg)
			# 自动滚动到底部
			cursor = self.widget.textCursor()
			cursor.movePosition(cursor.MoveOperation.End)
			self.widget.setTextCursor(cursor)
		except Exception:
			self.handleError(record)


# --- 后缀映射编辑器对话框 (保持不变) ---
class SuffixMapEditorDialog(QDialog):
	"""用于使用表格编辑后缀到语言映射的对话框。"""
	def __init__(self, current_map: dict, parent=None):
		super().__init__(parent)
		self.setWindowTitle("编辑后缀映射")
		self.setMinimumSize(450, 400) # 设置合理的最小尺寸

		self._edited_map = current_map.copy() # 操作副本

		# --- 控件 ---
		self.table_widget = QTableWidget()
		self.table_widget.setColumnCount(2)
		self.table_widget.setHorizontalHeaderLabels(["后缀 (例如 .py)", "语言 (例如 python)"])
		# 设置列宽调整模式
		self.table_widget.horizontalHeader().setSectionResizeMode(0, QHeaderView.ResizeMode.Interactive) # 后缀列可交互调整
		self.table_widget.horizontalHeader().setSectionResizeMode(1, QHeaderView.ResizeMode.Stretch) # 语言列拉伸填充
		self.table_widget.setAlternatingRowColors(True) # 启用交替行颜色
		self.table_widget.setSortingEnabled(True) # 允许按列排序

		self.add_row_btn = QPushButton("添加行")
		self.remove_row_btn = QPushButton("删除选中行")

		# 标准对话框按钮 (确定/取消)
		self.button_box = QDialogButtonBox(QDialogButtonBox.StandardButton.Ok | QDialogButtonBox.StandardButton.Cancel)
		self.button_box.button(QDialogButtonBox.StandardButton.Ok).setText("确定")
		self.button_box.button(QDialogButtonBox.StandardButton.Cancel).setText("取消")


		# --- 布局 ---
		button_layout = QHBoxLayout()
		button_layout.addWidget(self.add_row_btn)
		button_layout.addWidget(self.remove_row_btn)
		button_layout.addStretch(1)

		main_layout = QVBoxLayout(self)
		main_layout.addLayout(button_layout)
		main_layout.addWidget(self.table_widget)
		main_layout.addWidget(self.button_box)

		# --- 填充表格 ---
		self._populate_table()

		# --- 连接信号与槽 ---
		self.add_row_btn.clicked.connect(self._add_row)
		self.remove_row_btn.clicked.connect(self._remove_row)
		self.button_box.accepted.connect(self._validate_and_accept) # 连接确定按钮到验证逻辑
		self.button_box.rejected.connect(self.reject) # 连接取消按钮
		self.table_widget.itemSelectionChanged.connect(self._update_remove_button_state) # 选择变化时更新按钮状态

		self._update_remove_button_state() # 设置初始状态

	def _update_remove_button_state(self):
		"""根据是否有选中行来启用/禁用删除按钮。"""
		has_selection = bool(self.table_widget.selectedIndexes())
		self.remove_row_btn.setEnabled(has_selection)

	def _populate_table(self):
		"""用当前的映射数据填充表格。"""
		self.table_widget.setRowCount(0) # 清空现有行
		self.table_widget.setSortingEnabled(False) # 填充时禁用排序以提高效率
		# 按后缀排序以获得一致的顺序
		for suffix, language in sorted(self._edited_map.items()):
			row_position = self.table_widget.rowCount()
			self.table_widget.insertRow(row_position)
			self.table_widget.setItem(row_position, 0, QTableWidgetItem(suffix))
			self.table_widget.setItem(row_position, 1, QTableWidgetItem(language))
		self.table_widget.setSortingEnabled(True) # 重新启用排序
		self._update_remove_button_state() # 更新按钮状态

	def _add_row(self):
		"""向表格添加一个新的空行。"""
		row_position = self.table_widget.rowCount()
		self.table_widget.insertRow(row_position)
		# 可选：选中新行以便立即编辑
		self.table_widget.setCurrentCell(row_position, 0)
		self._update_remove_button_state() # 更新按钮状态

	def _remove_row(self):
		"""删除当前选中的行。"""
		# 获取所有选中单元格的行号，去重并降序排序
		selected_rows = sorted(list(set(index.row() for index in self.table_widget.selectedIndexes())), reverse=True)
		if not selected_rows:
			self._show_warning("删除行", "请先选择要删除的行。")
			return
		for row in selected_rows:
			self.table_widget.removeRow(row)
		self._update_remove_button_state() # 更新按钮状态

	def _validate_and_accept(self):
		"""在接受对话框前验证表格内容。"""
		new_map = {}
		valid = True
		duplicates = set()
		for row in range(self.table_widget.rowCount()):
			suffix_item = self.table_widget.item(row, 0)
			lang_item = self.table_widget.item(row, 1)

			suffix = suffix_item.text().strip() if suffix_item else ""
			lang = lang_item.text().strip() if lang_item else ""

			# 静默跳过完全空的行
			if not suffix and not lang: continue

			error_msg = ""
			if not suffix or not suffix.startswith('.'):
				error_msg = f"第 {row+1} 行: 后缀必须以 '.' 开头且不能为空。"
				valid = False
			elif not lang:
				error_msg = f"第 {row+1} 行: 后缀 '{suffix}' 对应的语言不能为空。"
				valid = False
			elif suffix in new_map:
				error_msg = f"第 {row+1} 行: 发现重复后缀 '{suffix}'。请移除重复项。"
				valid = False
				duplicates.add(suffix) # 标记重复项

			if not valid:
				self._show_critical("验证错误", error_msg)
				# 将焦点设置到有问题的单元格
				self.table_widget.setCurrentCell(row, 0 if "后缀" in error_msg else 1)
				return # 停止验证

			new_map[suffix] = lang

		if valid:
			self._edited_map = new_map # 存储验证后的映射
			self.accept() # 接受对话框

	def get_edited_map(self) -> dict:
		"""在对话框被接受后返回验证过的映射。"""
		return self._edited_map

	# --- 辅助方法：显示消息框 ---
	def _show_warning(self, title: str, text: str):
		"""显示警告消息框。"""
		QMessageBox.warning(self, title, text)

	def _show_critical(self, title: str, text: str):
		"""显示严重错误消息框。"""
		QMessageBox.critical(self, title, text)


# --- 主应用程序窗口 ---
class ModernProjectManagerApp(QMainWindow):
	"""使用 PySide6 的现代化 GUI 应用程序。"""
	def __init__(self):
		super().__init__()
		self.setWindowTitle("项目文件提取与重建")
		# 使用常量设置窗口大小
		self.setGeometry(100, 100, constants.DEFAULT_WINDOW_WIDTH, constants.DEFAULT_WINDOW_HEIGHT)

		# --- 配置管理 ---
		self.config_manager = ConfigManager()
		self._load_initial_config() # 加载初始配置

		self._suffix_checkboxes: Dict[str, QCheckBox] = {} # 存储后缀复选框

		# --- UI 创建与设置 ---
		self._create_widgets() # 首先创建控件
		self._create_layouts() # 然后在布局中排列它们
		self._update_suffix_checkboxes() # 根据加载的配置更新复选框
		self._update_parsed_exclusions_display() # 根据加载的配置更新排除项预览
		self._setup_statusbar()
		self._setup_gui_logging()
		self._connect_signals()
		self._apply_styles() # 最后应用样式
		self._update_button_states() # 设置初始按钮状态

		# --- 延迟保存配置的计时器 ---
		self._save_config_timer = QTimer(self)
		self._save_config_timer.setSingleShot(True)
		self._save_config_timer.setInterval(1000) # 延迟1秒保存
		self._save_config_timer.timeout.connect(self._save_current_config)

	def _load_initial_config(self):
		"""加载初始配置并存储在实例变量中。"""
		log.debug("加载初始配置...")
		config = self.config_manager.load_config()
		self._current_suffix_map: Dict[str, str] = config['suffix_map']
		# selected_suffixes 可能为 None，在 _update_suffix_checkboxes 中处理
		self._selected_suffixes_on_load: Optional[List[str]] = config['selected_suffixes']
		self._loaded_exclude_patterns: str = config['exclude_patterns']
		log.debug(f"初始后缀映射: {len(self._current_suffix_map)} 项")
		log.debug(f"初始选中后缀: {self._selected_suffixes_on_load}")
		log.debug(f"初始排除模式: '{self._loaded_exclude_patterns}'")

	def _create_widgets(self):
		"""创建所有必需的控件和分组框。"""
		self.central_widget = QWidget()
		self.setCentralWidget(self.central_widget)

		# --- 分组框 (卡片式) ---
		self.output_groupbox = QGroupBox("输出设置")
		self.source_groupbox = QGroupBox("源设置")
		self.reconstruct_groupbox = QGroupBox("重建")
		self.log_groupbox = QGroupBox("日志")

		# --- 输出控件 ---
		self.output_dir_label = QLabel("输出目录:")
		self.output_dir_entry = QLineEdit()
		# 使用常量设置默认输出目录
		self.output_dir_entry.setText(constants.DEFAULT_OUTPUT_DIR)
		self.browse_output_btn = QPushButton("浏览...")
		self.browse_output_btn.setObjectName("browse_output_btn")
		self.browse_output_btn.setIcon(QIcon.fromTheme("folder-open", QIcon(":/qt-project.org/styles/commonstyle/images/diropen.png")))
		self.open_output_dir_btn = QPushButton("打开")
		self.open_output_dir_btn.setObjectName("open_output_dir_btn")
		self.open_output_dir_btn.setToolTip("在文件浏览器中打开输出目录")
		self.open_output_dir_btn.setIcon(QIcon.fromTheme("folder", QIcon(":/qt-project.org/styles/commonstyle/images/folder.png")))

		# --- 源控件 ---
		self.source_dir_label = QLabel("项目源目录:")
		self.source_dir_entry = QLineEdit()
		self.browse_source_btn = QPushButton("浏览...")
		self.browse_source_btn.setObjectName("browse_source_btn")
		self.browse_source_btn.setIcon(QIcon.fromTheme("folder-open", QIcon(":/qt-project.org/styles/commonstyle/images/diropen.png")))

		# --- 后缀选择控件 ---
		self.suffix_checkboxes_widget = QWidget()
		self.suffix_checkboxes_layout = QVBoxLayout(self.suffix_checkboxes_widget)
		self.suffix_checkboxes_layout.setContentsMargins(5, 5, 5, 5)
		self.suffix_checkboxes_layout.setSpacing(6)
		self.suffix_scroll_area = QScrollArea()
		self.suffix_scroll_area.setWidgetResizable(True)
		self.suffix_scroll_area.setWidget(self.suffix_checkboxes_widget)
		self.suffix_scroll_area.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
		self.suffix_scroll_area.setMinimumHeight(120)
		self.select_all_suffixes_btn = QPushButton("全选")
		self.select_all_suffixes_btn.setObjectName("select_all_suffixes_btn")
		self.deselect_all_suffixes_btn = QPushButton("全不选")
		self.deselect_all_suffixes_btn.setObjectName("deselect_all_suffixes_btn")
		self.edit_suffix_map_btn = QPushButton("编辑映射...")
		self.edit_suffix_map_btn.setObjectName("edit_suffix_map_btn")
		self.reset_suffix_map_btn = QPushButton("重置映射")
		self.reset_suffix_map_btn.setToolTip("将后缀映射重置为默认值")
		self.reset_suffix_map_btn.setObjectName("reset_suffix_map_btn")
		self.reset_suffix_map_btn.setIcon(QIcon.fromTheme("edit-undo", QIcon(":/qt-project.org/styles/commonstyle/images/undo.png")))

		# --- 排除项控件 ---
		self.exclude_label = QLabel("排除文件/后缀 (逗号分隔):")
		self.exclude_entry = QLineEdit()
		self.exclude_entry.setPlaceholderText("例如: test.py, *.log, build/, .git")
		# 设置加载的排除项文本
		self.exclude_entry.setText(self._loaded_exclude_patterns)
		self.parsed_exclusions_label = QLabel("当前生效的排除规则:")
		self.parsed_exclusions_display = QTextEdit()
		self.parsed_exclusions_display.setReadOnly(True)
		self.parsed_exclusions_display.setObjectName("parsed_exclusions_display")

		# --- 重建控件 ---
		self.text_area_label = QLabel("合并后的文本 / 输入:")
		self.text_area = QTextEdit()
		self.text_area.setObjectName("text_area")

		# --- 文本区域操作按钮 ---
		self.clear_text_btn = QPushButton("清空")
		self.clear_text_btn.setIcon(QIcon.fromTheme("edit-clear", QIcon(":/qt-project.org/styles/commonstyle/images/standardbutton-clear-16.png")))
		self.load_text_btn = QPushButton("加载...")
		self.load_text_btn.setToolTip("从文件加载文本")
		self.load_text_btn.setIcon(QIcon.fromTheme("document-open", QIcon(":/qt-project.org/styles/commonstyle/images/fileopen.png")))
		self.save_text_btn = QPushButton("保存...")
		self.save_text_btn.setToolTip("将文本保存到文件")
		self.save_text_btn.setIcon(QIcon.fromTheme("document-save", QIcon(":/qt-project.org/styles/commonstyle/images/filesave.png")))

		# --- 日志控件 ---
		self.log_text = QTextEdit()
		self.log_text.setObjectName("log_text")
		self.log_text.setReadOnly(True)

		# --- 分割器 ---
		self.main_splitter_h = QSplitter(Qt.Orientation.Horizontal)
		self.top_splitter_v = QSplitter(Qt.Orientation.Vertical)

		# --- 主要操作按钮 ---
		self.combine_btn = QPushButton("合并文件")
		self.combine_btn.setIcon(QIcon.fromTheme("list-add", QIcon(":/qt-project.org/styles/commonstyle/images/add-16.png")))
		self.combine_btn.setObjectName("combine_btn")
		self.reconstruct_btn = QPushButton("重建项目")
		self.reconstruct_btn.setIcon(QIcon.fromTheme("system-run", QIcon(":/qt-project.org/styles/commonstyle/images/refresh-16.png")))
		self.reconstruct_btn.setObjectName("reconstruct_btn")

	def _create_layouts(self):
		"""使用嵌套分割器和分组框排列控件。"""
		# 中央控件的主垂直布局
		main_layout = QVBoxLayout(self.central_widget)
		main_layout.setContentsMargins(15, 15, 15, 15)
		main_layout.setSpacing(12)

		# --- 输出卡片布局 ---
		output_layout = QVBoxLayout(self.output_groupbox)
		output_layout.addWidget(self.output_dir_label)
		output_layout.addWidget(self.output_dir_entry)
		output_button_layout = QHBoxLayout()
		output_button_layout.addWidget(self.browse_output_btn)
		output_button_layout.addWidget(self.open_output_dir_btn)
		output_button_layout.addStretch(1)
		output_layout.addLayout(output_button_layout)

		# --- 源设置卡片布局 ---
		source_layout = QVBoxLayout(self.source_groupbox)
		source_layout.addWidget(self.source_dir_label)
		source_layout.addWidget(self.source_dir_entry)
		source_layout.addWidget(self.browse_source_btn)

		# --- 后缀选择与排除项预览 (水平布局) ---
		suffix_exclude_preview_layout = QHBoxLayout()

		# 左侧: 后缀选择
		suffix_selection_area_layout = QVBoxLayout()
		suffix_selection_area_layout.addWidget(QLabel("选择要合并的文件后缀:"))
		suffix_selection_area_layout.addWidget(self.suffix_scroll_area, 1)
		suffix_exclude_preview_layout.addLayout(suffix_selection_area_layout, 1)

		# 右侧: 排除项预览
		exclude_preview_area_layout = QVBoxLayout()
		exclude_preview_area_layout.addWidget(self.parsed_exclusions_label)
		exclude_preview_area_layout.addWidget(self.parsed_exclusions_display)
		suffix_exclude_preview_layout.addLayout(exclude_preview_area_layout, 1)

		source_layout.addLayout(suffix_exclude_preview_layout)

		# --- 排除项输入 ---
		source_layout.addWidget(self.exclude_label)
		source_layout.addWidget(self.exclude_entry)

		# --- 映射与选择操作按钮 (合并为一行) ---
		map_select_button_layout = QHBoxLayout()
		map_select_button_layout.addWidget(self.select_all_suffixes_btn)
		map_select_button_layout.addWidget(self.deselect_all_suffixes_btn)
		map_select_button_layout.addSpacing(20)
		map_select_button_layout.addWidget(self.edit_suffix_map_btn)
		map_select_button_layout.addWidget(self.reset_suffix_map_btn)
		map_select_button_layout.addStretch(1)
		source_layout.addLayout(map_select_button_layout)

		source_layout.addStretch(1)

		# --- 重建卡片布局 ---
		reconstruct_layout = QVBoxLayout(self.reconstruct_groupbox)
		text_area_actions_layout = QHBoxLayout()
		text_area_actions_layout.addWidget(self.text_area_label)
		text_area_actions_layout.addStretch(1)
		text_area_actions_layout.addWidget(self.load_text_btn)
		text_area_actions_layout.addWidget(self.save_text_btn)
		text_area_actions_layout.addWidget(self.clear_text_btn)
		text_area_actions_layout.setSpacing(8)
		reconstruct_layout.addLayout(text_area_actions_layout)
		reconstruct_layout.addWidget(self.text_area, 1)

		# --- 日志卡片布局 ---
		log_layout = QVBoxLayout(self.log_groupbox)
		log_layout.addWidget(self.log_text, 1)

		# --- 组装分割器 ---
		self.top_splitter_v.addWidget(self.output_groupbox)
		self.top_splitter_v.addWidget(self.source_groupbox)
		self.top_splitter_v.addWidget(self.log_groupbox)
		# 使用常量设置分割器初始尺寸
		self.top_splitter_v.setSizes(constants.DEFAULT_SPLITTER_SIZES_V_TOP)

		self.main_splitter_h.addWidget(self.top_splitter_v)
		self.main_splitter_h.addWidget(self.reconstruct_groupbox)
		# 使用常量设置分割器初始尺寸
		self.main_splitter_h.setSizes(constants.DEFAULT_SPLITTER_SIZES_H)

		# --- 操作按钮布局 (底部) ---
		action_buttons_layout = QHBoxLayout()
		action_buttons_layout.addStretch(1)
		action_buttons_layout.addWidget(self.combine_btn)
		action_buttons_layout.addWidget(self.reconstruct_btn)
		action_buttons_layout.setSpacing(15)

		# --- 将分割器和操作按钮添加到主布局 ---
		main_layout.addWidget(self.main_splitter_h, 1)
		main_layout.addLayout(action_buttons_layout)

	def _setup_statusbar(self):
		"""设置状态栏。"""
		self.status_bar = QStatusBar()
		self.setStatusBar(self.status_bar)
		self.status_bar.showMessage("准备就绪。")

	def _setup_gui_logging(self):
		"""设置 GUI 日志记录器。"""
		gui_log_handler = QTextEditLogHandler(self.log_text)
		# Handler 内部已设置 Formatter
		log.addHandler(gui_log_handler)
		log.info("GUI 日志记录已初始化。")

	def _connect_signals(self):
		"""连接所有信号与槽。"""
		# 目录浏览和操作按钮
		self.browse_source_btn.clicked.connect(self._browse_source_dir)
		self.browse_output_btn.clicked.connect(self._browse_output_dir)
		self.open_output_dir_btn.clicked.connect(self._open_output_directory)
		self.combine_btn.clicked.connect(self._combine_files)
		self.reconstruct_btn.clicked.connect(self._reconstruct_project)

		# 文本区域操作按钮
		self.clear_text_btn.clicked.connect(self._clear_text_area)
		self.load_text_btn.clicked.connect(self._load_text_from_file)
		self.save_text_btn.clicked.connect(self._save_text_to_file)

		# 后缀选择与映射按钮
		self.select_all_suffixes_btn.clicked.connect(lambda: self._select_all_suffixes(True))
		self.deselect_all_suffixes_btn.clicked.connect(lambda: self._select_all_suffixes(False))
		self.reset_suffix_map_btn.clicked.connect(self._reset_suffix_map_to_defaults)
		self.edit_suffix_map_btn.clicked.connect(self._open_suffix_map_editor)

		# 排除项输入框
		self.exclude_entry.textChanged.connect(self._update_parsed_exclusions_display)
		# 连接到触发延迟保存
		self.exclude_entry.textChanged.connect(self._trigger_save_config)

		# 连接输入变化到按钮状态更新
		self.source_dir_entry.textChanged.connect(self._update_button_states)
		self.output_dir_entry.textChanged.connect(self._update_button_states)
		self.text_area.textChanged.connect(self._update_button_states)

		# 后缀复选框的 stateChanged 信号在 _update_suffix_checkboxes 中连接到 _trigger_save_config

	# --- 辅助方法 ---
	def _update_button_states(self):
		"""根据输入更新按钮的启用状态。"""
		source_dir_valid = os.path.isdir(self.source_dir_entry.text().strip())
		output_dir_valid = bool(self.output_dir_entry.text().strip())
		text_area_has_content = bool(self.text_area.toPlainText().strip())

		self.combine_btn.setEnabled(source_dir_valid)
		self.reconstruct_btn.setEnabled(text_area_has_content and output_dir_valid)
		self.save_text_btn.setEnabled(text_area_has_content)
		self.clear_text_btn.setEnabled(text_area_has_content)

		output_dir_exists = os.path.isdir(self.output_dir_entry.text().strip())
		self.open_output_dir_btn.setEnabled(output_dir_exists)

	def _clear_layout(self, layout):
		"""辅助函数：清空布局中的所有项目。"""
		if layout is not None:
			while layout.count():
				item = layout.takeAt(0)
				widget = item.widget()
				if widget is not None:
					widget.setParent(None)
					widget.deleteLater()
				else:
					sub_layout = item.layout()
					if sub_layout is not None:
						self._clear_layout(sub_layout)

	def _update_suffix_checkboxes(self):
		"""根据当前的后缀映射创建或更新复选框，并根据加载的配置设置状态。"""
		self._clear_layout(self.suffix_checkboxes_layout)
		self._suffix_checkboxes.clear()

		# 确定哪些后缀应该被选中
		# 如果从配置加载了列表，则使用它；否则默认全选当前映射中的后缀
		suffixes_to_select = set(self._selected_suffixes_on_load) if self._selected_suffixes_on_load is not None else set(self._current_suffix_map.keys())
		log.debug(f"将选中的后缀: {suffixes_to_select}")

		if not self._current_suffix_map:
			no_map_label = QLabel("未定义后缀映射。\n请点击“编辑映射...”添加。")
			no_map_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
			no_map_label.setStyleSheet("color: #aaaaaa; padding: 10px;")
			self.suffix_checkboxes_layout.addWidget(no_map_label)
			log.warning("后缀映射为空，无法创建复选框。")
			return

		log.debug(f"正在为 {len(self._current_suffix_map)} 个后缀创建复选框...")
		# 按后缀排序创建复选框
		for suffix in sorted(self._current_suffix_map.keys()):
			checkbox = QCheckBox(suffix)
			checkbox.setChecked(suffix in suffixes_to_select)
			# 连接状态变化到触发延迟保存
			checkbox.stateChanged.connect(self._trigger_save_config)
			checkbox.setToolTip(f"包含/排除后缀为 '{suffix}' 的文件")
			self.suffix_checkboxes_layout.addWidget(checkbox)
			self._suffix_checkboxes[suffix] = checkbox
		self.suffix_checkboxes_layout.addStretch(1)
		log.debug("后缀复选框更新完成。")

	def _get_selected_suffixes(self) -> Set[str]:
		"""获取当前所有选中的后缀集合 (带 '.')。"""
		return {suffix for suffix, checkbox in self._suffix_checkboxes.items() if checkbox.isChecked()}

	def _select_all_suffixes(self, select=True):
		"""全选或全不选所有后缀复选框。"""
		if not self._suffix_checkboxes: return # 如果没有复选框，则不执行任何操作
		# 在修改状态前断开连接，避免触发多次保存
		for checkbox in self._suffix_checkboxes.values():
			try:
				checkbox.stateChanged.disconnect(self._trigger_save_config)
			except RuntimeError: # 如果信号未连接，会抛出 RuntimeError
				pass # 忽略错误，继续执行
			checkbox.setChecked(select)
			checkbox.stateChanged.connect(self._trigger_save_config)
		self._trigger_save_config() # 手动触发一次保存
		action = "全选" if select else "全不选"
		self.status_bar.showMessage(f"已{action}所有后缀。")
		log.info(f"用户已{action}所有后缀。")

	def _create_progress_dialog(self, title: str, label: str, max_value: int = 0, show_cancel: bool = True) -> QProgressDialog:
		"""创建并配置进度对话框。"""
		cancel_text = "取消" if show_cancel else None
		# 如果 max_value 为 0，表示不确定模式
		progress = QProgressDialog(label, cancel_text, 0, max_value if max_value > 0 else 0, self)
		if max_value == 0:
			progress.setMaximum(0) # 显式设置为不确定模式
		progress.setWindowModality(Qt.WindowModality.WindowModal)
		progress.setWindowTitle(title)
		progress.setAutoClose(False) # 防止自动关闭
		progress.setAutoReset(False) # 防止自动重置
		if not show_cancel:
			progress.setCancelButton(None)
		progress.setValue(0)
		return progress

	def _show_message_box(self, icon: QMessageBox.Icon, title: str, text: str):
		"""显示一个简单的消息框。"""
		msg_box = QMessageBox(self)
		msg_box.setIcon(icon)
		msg_box.setWindowTitle(title)
		msg_box.setText(text)
		if icon == QMessageBox.Icon.Question:
			msg_box.setStandardButtons(QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No)
			msg_box.button(QMessageBox.StandardButton.Yes).setText("是")
			msg_box.button(QMessageBox.StandardButton.No).setText("否")
		else:
			msg_box.setStandardButtons(QMessageBox.StandardButton.Ok)
			msg_box.button(QMessageBox.StandardButton.Ok).setText("确定")
		return msg_box.exec()

	def _show_info(self, title: str, text: str):
		"""显示信息消息框。"""
		self._show_message_box(QMessageBox.Icon.Information, title, text)

	def _show_warning(self, title: str, text: str):
		"""显示警告消息框。"""
		self._show_message_box(QMessageBox.Icon.Warning, title, text)

	def _show_error(self, title: str, text: str):
		"""显示错误消息框。"""
		self._show_message_box(QMessageBox.Icon.Critical, title, text)

	def _ask_question(self, title: str, text: str) -> QMessageBox.StandardButton:
		"""显示询问对话框并返回用户的选择 (Yes/No)。"""
		return self._show_message_box(QMessageBox.Icon.Question, title, text)

	# --- 排除项处理辅助方法 ---
	def _update_parsed_exclusions_display(self):
		"""更新用于显示已解析排除规则的文本区域。"""
		exclude_str = self.exclude_entry.text()
		# 使用 file_processor 中的函数
		excluded_patterns, excluded_suffixes_no_dot = parse_exclusions(exclude_str)

		display_lines = []
		if excluded_patterns:
			display_lines.append("排除的文件名/路径模式:")
			for name in sorted(list(excluded_patterns)):
				display_lines.append(f"  - {name}")
		if excluded_suffixes_no_dot:
			display_lines.append("排除的后缀:")
			for suffix in sorted(list(excluded_suffixes_no_dot)):
				display_lines.append(f"  - .{suffix}") # 显示时加上点

		if not display_lines:
			self.parsed_exclusions_display.setPlainText("无有效排除规则。")
		else:
			self.parsed_exclusions_display.setPlainText("\n".join(display_lines))
		self.parsed_exclusions_display.setToolTip(f"原始输入:\n{exclude_str}")

	# --- 槽方法 (处理用户交互) ---
	def _browse_dir(self, title: str, line_edit: QLineEdit):
		"""浏览目录的通用辅助方法。"""
		directory = QFileDialog.getExistingDirectory(self, title, line_edit.text())
		if directory:
			abs_path = os.path.abspath(directory)
			line_edit.setText(abs_path)
			self.status_bar.showMessage(f"{title}: {abs_path}")
			log.info(f"{title} 已选择: {abs_path}")

	def _browse_source_dir(self):
		"""浏览项目源目录。"""
		self._browse_dir("选择项目源目录", self.source_dir_entry)

	def _browse_output_dir(self):
		"""浏览输出目录。"""
		self._browse_dir("选择输出目录", self.output_dir_entry)

	def _open_output_directory(self):
		"""在系统文件浏览器中打开选定的输出目录。"""
		output_path = self.output_dir_entry.text().strip()
		if not output_path:
			log.warning("尝试打开输出目录，但路径为空。")
			return
		if os.path.isdir(output_path):
			try:
				QDesktopServices.openUrl(QUrl.fromLocalFile(output_path))
				log.info(f"已打开输出目录: {output_path}")
				self.status_bar.showMessage(f"已打开: {output_path}")
			except Exception as e:
				log.error(f"无法打开输出目录 '{output_path}': {e}")
				self._show_error("错误", f"无法打开目录:\n{output_path}\n\n错误: {e}")
				self.status_bar.showMessage("打开目录时出错。")
		else:
			log.warning(f"尝试打开不存在的目录: {output_path}")
			self._show_warning("目录未找到", f"指定的输出目录不存在或不是一个目录:\n{output_path}")
			self.status_bar.showMessage("输出目录未找到。")

	def _reset_suffix_map_to_defaults(self):
		"""将内部后缀映射重置为默认值，并更新UI和保存配置。"""
		# 使用常量获取默认映射
		if self._current_suffix_map == constants.DEFAULT_SUFFIX_MAP:
			self.status_bar.showMessage("后缀映射已经是默认值。")
			return

		self._current_suffix_map = constants.DEFAULT_SUFFIX_MAP.copy()
		self._selected_suffixes_on_load = None # 重置时清除加载的选中状态，触发默认全选
		self._update_suffix_checkboxes() # 重新生成复选框（将默认全选）
		self.status_bar.showMessage("后缀映射已重置为默认值。")
		log.info("用户已将后缀映射重置为默认值。")
		self._trigger_save_config() # 触发保存重置后的映射和默认选中状态

	def _open_suffix_map_editor(self):
		"""打开对话框以编辑后缀映射。"""
		dialog = SuffixMapEditorDialog(self._current_suffix_map, self)
		result = dialog.exec()

		if result == QDialog.DialogCode.Accepted:
			new_map = dialog.get_edited_map()
			if new_map != self._current_suffix_map:
				self._current_suffix_map = new_map
				self._selected_suffixes_on_load = None # 编辑后清除加载的选中状态
				self._update_suffix_checkboxes() # 更新复选框
				self.status_bar.showMessage("后缀映射已更新。")
				log.info(f"通过编辑器更新了后缀映射: {self._current_suffix_map}")
				self._trigger_save_config() # 触发保存编辑后的配置
			else:
				self.status_bar.showMessage("后缀映射未更改。")
				log.info("后缀映射编辑完成，但未做更改。")
		else:
			self.status_bar.showMessage("后缀映射编辑已取消。")
			log.info("用户取消了后缀映射编辑。")

	def _combine_files(self):
		"""处理合并文件的用户请求，调用 file_processor 并更新 UI。"""
		selected_suffixes = self._get_selected_suffixes()
		exclude_str = self.exclude_entry.text()
		source_path = self.source_dir_entry.text().strip()

		if not self._current_suffix_map:
			self.status_bar.showMessage("合并失败: 未定义后缀映射。"); return
		if not selected_suffixes:
			self.status_bar.showMessage("合并失败: 没有选择任何后缀。"); return
		if not source_path or not os.path.isdir(source_path):
			self._show_warning("输入错误", "请选择一个有效的源目录。")
			self.status_bar.showMessage("错误: 无效的源目录。"); log.error("合并失败: 无效的源目录。"); return

		self.status_bar.showMessage("准备合并文件..."); log.info(f"开始从以下位置合并: {source_path}")
		QApplication.processEvents()

		# --- 进度对话框 ---
		# 估算总数在 file_processor.combine_files 内部完成
		progress = self._create_progress_dialog("合并中", "正在准备...", 0, True) # 初始为不确定模式
		progress.show()
		QApplication.processEvents() # 确保对话框显示

		# --- 定义进度回调函数 ---
		def progress_callback_handler(processed: int, total: int, name: str, is_dir: bool) -> bool:
			"""更新进度对话框并检查取消。"""
			nonlocal progress # 允许修改外部作用域的 progress 对象
			if not progress.isVisible(): # 如果用户过早关闭了对话框
				log.warning("进度对话框在操作完成前被关闭。")
				return True # 视为取消

			# 首次获得 total > 0 时，设置对话框最大值
			if total > 0 and progress.maximum() == 0:
				progress.setMaximum(total)

			progress.setValue(processed)
			type_str = "目录" if is_dir else "文件"
			progress.setLabelText(f"正在处理 {type_str}: {name}\n({processed}/{total if total > 0 else '?'})")
			QApplication.processEvents() # 保持 UI 响应
			return progress.wasCanceled()

		# --- 调用核心合并逻辑 ---
		try:
			# 将绝对路径传递给 file_processor
			abs_source_path = os.path.abspath(source_path)
			combine_result = combine_files(
				abs_source_path,
				self._current_suffix_map,
				selected_suffixes,
				exclude_str,
				progress_callback=progress_callback_handler
			)
		except Exception as e:
			# 捕获 file_processor 可能抛出的未预料错误
			log.exception("调用 combine_files 时发生意外错误。")
			self._show_error("合并错误", f"合并过程中发生意外错误:\n{e}")
			self.status_bar.showMessage("合并时发生严重错误。")
			if progress.isVisible(): progress.close()
			self._update_button_states()
			return
		finally:
			# 确保进度对话框关闭
			if progress.isVisible():
				progress.close()

		# --- 处理合并结果 ---
		if combine_result['cancelled']:
			self.status_bar.showMessage("用户取消了合并操作。")
			log.info("用户取消了合并操作。")
			self.text_area.clear()
			self._show_warning("已取消", "文件合并过程已取消。")
		else:
			self.text_area.clear()
			file_count = combine_result['file_count']
			skipped_count = combine_result['skipped_count']
			error_count = combine_result['error_count']

			if combine_result['combined_text']:
				self.text_area.setPlainText(combine_result['combined_text'])
				msg = f"合并完成: {file_count} 个文件。"
				if skipped_count: msg += f" 跳过: {skipped_count}。"
				if error_count: msg += f" 错误: {error_count}。"
				log.info(f"合并摘要: {msg}")
				self.status_bar.showMessage(msg)
				if error_count or skipped_count:
					self._show_warning("合并完成", f"已合并: {file_count}\n已跳过/排除: {skipped_count}\n错误: {error_count}\n详细信息请查看日志。")
				else:
					self._show_info("成功", f"成功合并 {file_count} 个文件。")
			else:
				msg = "未找到符合条件的文件。"
				if skipped_count: msg += f" 跳过了 {skipped_count} 个文件/目录 (未选中/排除/错误)。"
				log.info(f"合并摘要: {msg}")
				self.status_bar.showMessage(msg)
				self._show_info("提示", msg)

		self._update_button_states()

	def _reconstruct_project(self):
		"""处理重建项目的用户请求，调用 file_processor 并更新 UI。"""
		output_path = self.output_dir_entry.text().strip()
		if not output_path:
			self._show_warning("输入错误", "请选择一个输出目录。")
			self.status_bar.showMessage("错误: 未设置输出目录。"); log.error("重建失败: 未设置输出目录。"); return

		combined_text = self.text_area.toPlainText().strip()
		if not combined_text:
			self._show_warning("输入错误", "输入文本区域为空。")
			self.status_bar.showMessage("错误: 输入文本为空。"); log.error("重建失败: 输入为空。"); return

		# 检查输出目录是否非空
		abs_output_path = os.path.abspath(output_path)
		if os.path.exists(abs_output_path) and os.listdir(abs_output_path):
			reply = self._ask_question("确认覆盖",
									  f"输出目录 '{abs_output_path}' 非空。\n现有文件将被覆盖。\n是否继续？")
			if reply != QMessageBox.StandardButton.Yes:
				self.status_bar.showMessage("重建已取消。"); log.info("用户取消了重建操作。"); return

		self.status_bar.showMessage("正在重建项目..."); log.info(f"开始重建到: {abs_output_path}")
		QApplication.processEvents()

		# --- 进度对话框 (不确定模式，无取消按钮) ---
		progress = self._create_progress_dialog("重建中", "正在重建项目...", 0, False)
		progress.show()
		QApplication.processEvents()

		try:
			# 使用 file_processor 中的类
			reconstructor = ProjectReconstructor(output_root_dir=abs_output_path)
			success, files_created, errors = reconstructor.reconstruct_from_content(combined_text)

			if not success: # 通常指无法创建输出目录等致命错误
				self._show_error("严重错误", "重建过程中发生严重错误。请检查日志。")
				self.status_bar.showMessage("严重的重建错误。"); log.critical("重建过程中发生严重错误。")
			else:
				msg = f"重建完成。已创建: {files_created} 个文件。"
				if errors: msg += f" 错误: {errors}。"
				log.info(msg); self.status_bar.showMessage(msg)
				if errors: self._show_warning("警告", f"重建完成，但有 {errors} 个错误。请检查日志。")
				elif files_created == 0:
					# 检查输入文本中是否有代码块
					block_count_check = len(list(constants.CODE_BLOCK_PATTERN.finditer(combined_text)))
					info_msg = "未创建任何文件 (请检查输入格式/路径)。" if block_count_check > 0 else "未找到 '```<lang>...' 代码块。"
					self._show_info("提示", f"重建完成。{info_msg}")
				else: self._show_info("成功", f"成功重建 {files_created} 个文件。")
				# 可选：重建成功后自动打开输出目录
				# if files_created > 0: self._open_output_directory()
		except Exception as e:
			self._show_error("错误", f"发生意外的重建错误: {e}")
			self.status_bar.showMessage(f"重建错误: {e}"); log.exception("意外的重建错误。")
		finally:
			if progress.isVisible(): progress.close()
			self._update_button_states() # 更新按钮状态（例如“打开”按钮）

	# --- 文本区域操作的槽方法 ---
	def _clear_text_area(self):
		"""清空主文本区域。"""
		self.text_area.clear()
		self.status_bar.showMessage("文本区域已清空。")
		log.info("用户清空了文本区域。")
		self._update_button_states()

	def _load_text_from_file(self):
		"""从文件加载文本到主文本区域。"""
		file_path, _ = QFileDialog.getOpenFileName(self, "加载合并后的文本文件", "", "文本文件 (*.txt);;所有文件 (*)")
		if file_path:
			try:
				with open(file_path, 'r', encoding='utf-8') as f:
					content = f.read()
				self.text_area.setPlainText(content)
				self.status_bar.showMessage(f"已从文件加载文本: {os.path.basename(file_path)}")
				log.info(f"已从文件加载文本: {file_path}")
			except Exception as e:
				self._show_error("文件加载错误", f"加载文件 '{file_path}' 时出错:\n{e}")
				self.status_bar.showMessage(f"加载文件时出错: {e}")
				log.error(f"加载文本文件 '{file_path}' 时出错: {e}")
			self._update_button_states()

	def _save_text_to_file(self):
		"""将主文本区域的内容保存到文件。"""
		content = self.text_area.toPlainText()
		if not content:
			self._show_warning("保存错误", "文本区域为空，无法保存。")
			self.status_bar.showMessage("保存已取消: 文本区域为空。")
			return

		file_path, _ = QFileDialog.getSaveFileName(self, "将合并后的文本另存为", "", "文本文件 (*.txt);;所有文件 (*)")
		if file_path:
			try:
				# 确保有 .txt 扩展名 (如果用户没有输入)
				if not file_path.lower().endswith(('.txt', '.md')): # 允许 .md
					root, ext = os.path.splitext(file_path)
					if not ext: file_path += '.txt'

				with open(file_path, 'w', encoding='utf-8', newline='\n') as f:
					f.write(content)
				self.status_bar.showMessage(f"文本已保存到: {os.path.basename(file_path)}")
				log.info(f"文本区域内容已保存到文件: {file_path}")
				self._show_info("成功", f"文本已成功保存到:\n{file_path}")
			except Exception as e:
				self._show_error("文件保存错误", f"保存文件 '{file_path}' 时出错:\n{e}")
				self.status_bar.showMessage(f"保存文件时出错: {e}")
				log.error(f"保存文本文件 '{file_path}' 时出错: {e}")

	# --- 配置持久化方法 ---
	def _trigger_save_config(self):
		"""触发延迟保存配置。"""
		log.debug("触发延迟保存配置...")
		# 重启计时器
		self._save_config_timer.start()

	def _save_current_config(self):
		"""收集当前配置并使用 ConfigManager 保存。"""
		log.info("正在保存当前配置...")
		current_selected_suffixes = list(self._get_selected_suffixes())
		current_exclude_patterns = self.exclude_entry.text().strip()

		config_data = {
			'suffix_map': self._current_suffix_map,
			'selected_suffixes': current_selected_suffixes,
			'exclude_patterns': current_exclude_patterns
		}
		if not self.config_manager.save_config(config_data):
			# 保存失败时通知用户
			self._show_warning("配置保存错误", f"无法保存配置文件到:\n{self.config_manager.config_file_path}\n请检查日志获取详细信息。")
			self.status_bar.showMessage("配置保存失败。")
		else:
			log.info("当前配置已成功保存。")
			# 可选：在状态栏显示短暂的成功消息
			# self.status_bar.showMessage("配置已保存。", 2000) # 显示 2 秒

	def _apply_styles(self):
		"""应用新的现代化暗色 QSS 样式表。"""
		# 尝试从外部文件加载 QSS
		qss_path = os.path.join(os.path.dirname(__file__), "style.qss")
		qss = ""
		if os.path.exists(qss_path):
			try:
				with open(qss_path, "r", encoding="utf-8") as f:
					qss = f.read()
				log.info(f"已从 '{qss_path}' 加载样式表。")
			except Exception as e:
				log.error(f"加载样式文件 '{qss_path}' 时出错: {e}。将使用默认调色板。")
				qss = "" # 加载失败则清空
		else:
			log.warning(f"样式文件 '{qss_path}' 未找到。将使用默认调色板。")

		# 优先应用 QSS 文件，如果 QSS 为空或加载失败，则应用默认暗色调色板
		if qss:
			self.setStyleSheet(qss)
		else:
			# 备用：应用暗色主题调色板 (如果 QSS 加载失败)
			dark_palette = QPalette()
			dark_palette.setColor(QPalette.ColorRole.Window, QColor(53, 53, 53))
			dark_palette.setColor(QPalette.ColorRole.WindowText, Qt.GlobalColor.white)
			dark_palette.setColor(QPalette.ColorRole.Base, QColor(42, 42, 42))
			dark_palette.setColor(QPalette.ColorRole.AlternateBase, QColor(66, 66, 66))
			dark_palette.setColor(QPalette.ColorRole.ToolTipBase, Qt.GlobalColor.white)
			dark_palette.setColor(QPalette.ColorRole.ToolTipText, Qt.GlobalColor.white)
			dark_palette.setColor(QPalette.ColorRole.Text, Qt.GlobalColor.white)
			dark_palette.setColor(QPalette.ColorRole.Button, QColor(53, 53, 53))
			dark_palette.setColor(QPalette.ColorRole.ButtonText, Qt.GlobalColor.white)
			dark_palette.setColor(QPalette.ColorRole.BrightText, Qt.GlobalColor.red)
			dark_palette.setColor(QPalette.ColorRole.Link, QColor(42, 130, 218))
			dark_palette.setColor(QPalette.ColorRole.Highlight, QColor(42, 130, 218))
			dark_palette.setColor(QPalette.ColorRole.HighlightedText, Qt.GlobalColor.black)
			dark_palette.setColor(QPalette.ColorGroup.Disabled, QPalette.ColorRole.ButtonText, QColor(127, 127, 127))
			dark_palette.setColor(QPalette.ColorGroup.Disabled, QPalette.ColorRole.WindowText, QColor(127, 127, 127))
			dark_palette.setColor(QPalette.ColorGroup.Disabled, QPalette.ColorRole.Text, QColor(127, 127, 127))
			QApplication.setPalette(dark_palette)

	# --- 重写关闭事件以确保配置被保存 ---
	def closeEvent(self, event):
		"""在关闭窗口前，确保最后的配置更改被保存。"""
		log.debug("窗口关闭事件触发。")
		if self._save_config_timer.isActive():
			log.info("检测到待处理的配置保存，立即执行...")
			self._save_config_timer.stop() # 停止计时器
			self._save_current_config() # 立即保存
		super().closeEvent(event)


# --- 脚本执行入口点 ---
if __name__ == "__main__":
	# --- 基本日志配置 ---
	log_level = logging.INFO # 默认级别
	# 可以根据环境变量或命令行参数设置更详细的日志级别
	# if os.environ.get("DEBUG"): log_level = logging.DEBUG
	logging.basicConfig(level=log_level,
						format=constants.LOG_FORMAT_CONSOLE, # 控制台使用特定格式
						handlers=[logging.StreamHandler(sys.stdout)]) # 默认输出到控制台

	log.info("应用程序启动...")

	app = QApplication(sys.argv)
	# 尝试设置 Fusion 样式
	app.setStyle('Fusion')

	window = ModernProjectManagerApp()
	window.show()

	sys.exit(app.exec())
