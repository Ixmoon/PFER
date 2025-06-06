# -*- coding: utf-8 -*-
"""文件处理模块，包含项目重建和文件合并逻辑"""

import os
import re
import logging
from typing import Dict, List, Tuple, Set, Callable, Optional, Any
import time # 用于进度回调的节流

# 从同级目录导入常量
try:
	from . import constants
except ImportError:
	import constants # 在直接运行脚本时回退

log = logging.getLogger(__name__)

# --- 排除规则处理函数 ---

def parse_exclusions(exclude_str: str) -> Tuple[Set[str], Set[str]]:
	"""
	解析排除字符串，返回排除的文件名/路径模式集合和排除的后缀集合。
	路径模式以 '/' 结尾。后缀不包含 '.'。

	:param exclude_str: 逗号分隔的排除项字符串。
	:return: 一个元组 (excluded_patterns, excluded_suffixes_no_dot)
	"""
	excluded_patterns = set()
	excluded_suffixes_no_dot = set()
	if not exclude_str:
		return excluded_patterns, excluded_suffixes_no_dot

	items = [item.strip() for item in exclude_str.split(',') if item.strip()]
	for item in items:
		if item.startswith('*.'): # 排除后缀，例如 *.log
			suffix = item[2:].lower() # 从 *.<suffix> 提取后缀，不带点
			if suffix: excluded_suffixes_no_dot.add(suffix)
		elif item.startswith('.') and len(item) > 1 and '.' not in item[1:]: # 排除后缀，例如 .log (确保不是文件名如 .gitignore)
			suffix = item[1:].lower() # 从 .<suffix> 提取后缀，不带点
			if suffix: excluded_suffixes_no_dot.add(suffix)
		elif item.endswith('/'): # 排除目录
			excluded_patterns.add(item) # 存储为目录形式，例如 build/
		else: # 排除特定文件名或文件路径模式
			excluded_patterns.add(item) # 例如 test.py, .git
	return excluded_patterns, excluded_suffixes_no_dot

def is_excluded(file_or_dir_path: str, source_root: str, excluded_patterns: Set[str], excluded_suffixes_no_dot: Set[str]) -> Optional[str]:
	"""
	检查给定的文件或目录路径是否应根据排除规则被排除。

	:param file_or_dir_path: 要检查的文件或目录的绝对路径。
	:param source_root: 源根目录的绝对路径。
	:param excluded_patterns: 排除的文件名/路径模式集合。
	:param excluded_suffixes_no_dot: 排除的后缀集合 (不带 '.')。
	:return: 排除原因字符串，如果不应排除则返回 None。
	"""
	try:
		rel_path = os.path.relpath(file_or_dir_path, source_root).replace(os.sep, '/')
	except ValueError:
		# 如果 file_or_dir_path 不在 source_root 下 (例如不同驱动器)，relpath 会失败
		log.warning(f"无法计算相对路径: '{file_or_dir_path}' 相对于 '{source_root}'。假定不排除。")
		return None # 或者根据需要决定是否排除

	basename = os.path.basename(file_or_dir_path)
	_, suffix = os.path.splitext(basename)
	suffix_no_dot = suffix.lower().lstrip('.')

	# 检查文件名/路径模式排除
	for pattern in excluded_patterns:
		if pattern.endswith('/'): # 目录排除
			# 检查相对路径是否以目录模式开头，或文件名是否等于目录名 (处理根目录下的情况)
			# 确保比较的模式也使用 '/'
			pattern_normalized = pattern.replace(os.sep, '/')
			if rel_path == pattern_normalized.strip('/') or rel_path.startswith(pattern_normalized):
				return f"匹配排除路径 '{pattern}'"
			# 特殊处理：如果模式是 '.git/' 且文件是 '.git' 本身
			if pattern == '.git/' and basename == '.git':
				return f"匹配排除路径 '{pattern}'"

		elif pattern == basename: # 文件名完全匹配
			return f"匹配排除文件名 '{pattern}'"
		elif pattern == rel_path: # 相对路径完全匹配
			return f"匹配排除路径 '{pattern}'"
		# TODO: 可以添加更复杂的模式匹配，例如 fnmatch

	# 检查后缀排除 (比较不带点的后缀)
	if suffix_no_dot in excluded_suffixes_no_dot:
		return f"匹配排除后缀 '.{suffix_no_dot}'"

	return None # 未被排除


# --- 项目重建器类 ---
class ProjectReconstructor:
	"""
	从单个组合的文本块或文件中重建项目目录结构和文件。
	- 使用 ```language 标记查找代码块。
	- 仅使用代码块内的第一行注释作为文件路径。
	- 如果发现重复路径，则以最后一次出现的内容为准。
	"""
	def __init__(self, output_root_dir: str):
		"""
		初始化重建器。
		:param output_root_dir: 输出项目根目录。
		"""
		self.output_root_dir = output_root_dir
		log.info(f"初始化重建器:")
		log.info(f"  输出根目录: '{os.path.abspath(self.output_root_dir)}'")
		log.info(f"  代码块检测: 搜索 ```<language> ... ```")
		log.info(f"  路径来源: 仅代码块内第一行注释。")
		log.info(f"  重复处理: 最后出现者优先。")

	def _extract_path_from_comment(self, block_content_with_path: str) -> Optional[str]:
		"""
		从代码块内容的第一行提取文件路径注释。
		:param block_content_with_path: 包含路径注释的代码块内容。
		:return: 提取到的相对路径，如果无效则返回 None。
		"""
		if not block_content_with_path: return None
		first_line = block_content_with_path.split('\n', 1)[0].strip()
		match = constants.FIRST_LINE_PATH_COMMENT_PATTERN.match(first_line)
		if match:
			potential_path = match.group(1).strip()
			# 基础路径有效性检查（允许字母数字和常见路径字符）
			# 移除了 isalnum 检查，因为它过于严格，会排除像 a/b.py 这样的路径
			if potential_path and any(c in potential_path for c in '/\\._-'):
				# 清理路径前后可能存在的无关字符
				potential_path = re.sub(r"^[*(]+|[)*]+$", "", potential_path).strip('`')
				# 确保清理后路径有效且不以 '#' 开头
				if potential_path and not potential_path.startswith('#'):
					log.debug(f"	路径成功提取: '{potential_path}'")
					return potential_path
				else: log.debug(f"	清理后路径无效: '{first_line}'")
			else: log.debug(f"	注释不是有效的路径格式: '{first_line}'")
		else: log.debug(f"	第一行不是路径注释: '{first_line[:80]}...'")
		return None

	def _parse_content(self, full_content: str) -> Dict[str, str]:
		"""
		解析完整内容，提取所有有效的文件路径及其对应的代码块内容。
		:param full_content: 包含多个代码块的完整文本内容。
		:return: 一个字典，键是相对文件路径，值是对应的代码块内容（包含路径注释）。
		"""
		extracted_files: Dict[str, str] = {}
		code_block_matches = list(constants.CODE_BLOCK_PATTERN.finditer(full_content))
		if not code_block_matches:
			log.warning("未找到 '```<language> ... ```' 代码块。")
			return {}
		log.info(f"找到 {len(code_block_matches)} 个潜在的代码块。正在处理...")
		blocks_processed, blocks_skipped_no_path = 0, 0
		for i, code_match in enumerate(code_block_matches):
			language = code_match.group(1)
			block_content_with_path = code_match.group(2).strip() # 标记之间的内容，包括路径注释
			log.debug(f"--- 处理代码块 {i+1} (语言: {language}) ---")
			rel_path = self._extract_path_from_comment(block_content_with_path)
			if rel_path:
				# 检查路径中是否包含不允许的字符 (使用常量)
				if constants.INVALID_PATH_CHARS_PATTERN.search(rel_path):
					log.warning(f"  代码块 {i+1}: 路径 '{rel_path}' 包含无效字符。跳过。")
					blocks_skipped_no_path += 1; continue
				# 检查路径是否为绝对路径或包含 '..' (目录穿越风险)
				# 注意: os.path.isabs 在 Windows 上对 / 开头的路径可能判断错误，需额外检查
				is_potentially_unsafe = os.path.isabs(rel_path) or \
										(os.name == 'nt' and rel_path.startswith('/')) or \
										'..' in rel_path.split(os.sep) or \
										'..' in rel_path.split('/') # 同时检查两种分隔符
				if is_potentially_unsafe:
					log.warning(f"  代码块 {i+1}: 路径 '{rel_path}' 不安全 (绝对路径或包含 '..')。跳过。")
					blocks_skipped_no_path += 1; continue

				log.info(f"  代码块 {i+1}: 找到路径: '{rel_path}' (语言: {language})")
				if rel_path in extracted_files: log.info(f"	发现重复路径。将覆盖。")
				extracted_files[rel_path] = block_content_with_path
				blocks_processed += 1
				log.debug(f"	已存储 '{rel_path}' (长度: {len(block_content_with_path)})")
			else:
				log.warning(f"  代码块 {i+1} (语言: {language}): 未找到有效的路径注释。跳过。")
				blocks_skipped_no_path += 1
				first_line_debug = block_content_with_path.split('\n', 1)[0].strip()
				log.debug(f"	第一行内容: '{first_line_debug[:100]}...'")
		log.info(f"解析完成。已处理: {blocks_processed}, 已跳过: {blocks_skipped_no_path}。")
		return extracted_files

	def reconstruct_from_content(self, content: str) -> Tuple[bool, int, int]:
		"""
		根据提供的包含代码块的文本内容，重建项目文件结构。
		:param content: 包含代码块的完整文本内容。
		:return: 一个元组 (success, created_count, error_count)，表示操作是否成功、成功创建的文件数和发生错误的数量。
		"""
		log.info(f"开始重建到目录 '{self.output_root_dir}'。")
		# 确保输出根目录存在
		if not os.path.exists(self.output_root_dir):
			try:
				os.makedirs(self.output_root_dir)
				log.info(f"已创建基础输出目录: '{self.output_root_dir}'")
			except OSError as e:
				log.critical(f"致命错误: 无法创建输出目录 '{self.output_root_dir}': {e}")
				return False, 0, 0

		# 规范化换行符
		norm_content = content.replace('\r\n', '\n').replace('\r', '\n')
		if norm_content != content: log.info("已规范化换行符。")

		files_dict = self._parse_content(norm_content)
		if not files_dict:
			log.warning("未解析到包含有效路径的文件。")
			return True, 0, 0 # 解析本身没有失败，只是没有找到文件

		total_files, created_count, error_count = len(files_dict), 0, 0
		log.info(f"尝试创建 {total_files} 个唯一文件...")

		abs_output_root_dir = os.path.abspath(self.output_root_dir) # 获取绝对路径用于安全检查

		for rel_path, code_content in files_dict.items():
			log.debug(f"  处理中: '{rel_path}'")
			try:
				# 清理相对路径，移除开头和结尾的斜杠/反斜杠
				clean_rel_path = rel_path.strip('/\\')
				# 将路径分割成部分，并过滤掉空字符串和 '.'
				# 使用 re.split 支持混合分隔符
				path_parts = [p for p in re.split(r'[/\\]', clean_rel_path) if p and p != '.']
				if not path_parts:
					log.error(f"从 '{rel_path}' 得到的路径无效（为空）。跳过。")
					error_count += 1; continue
				# 构建完整的目标文件路径
				full_path = os.path.join(abs_output_root_dir, *path_parts)

				# 安全检查：确保目标路径在指定的输出根目录内
				abs_full_path = os.path.abspath(full_path)
				if not abs_full_path.startswith(abs_output_root_dir):
					log.error(f"安全风险: 路径 '{rel_path}' 解析后位于输出目录 '{abs_output_root_dir}' 之外 ('{abs_full_path}')。跳过。")
					error_count += 1; continue
			except Exception as e:
				log.error(f"处理路径 '{rel_path}' 时出错: {e}"); error_count += 1; continue

			# 创建文件所在的目录（如果不存在）
			try:
				out_dir = os.path.dirname(full_path)
				if out_dir and not os.path.exists(out_dir):
					os.makedirs(out_dir, exist_ok=True)
					log.info(f"	已创建目录: {out_dir}")
			except Exception as e:
				log.exception(f"为 '{rel_path}' 创建目录时出错: {e}"); error_count += 1; continue

			# 写入文件内容
			try:
				# 使用 'w' 模式（覆盖），UTF-8 编码，统一使用 '\n' 换行符
				# 写入包含路径注释的完整代码块内容
				with open(full_path, 'w', encoding='utf-8', newline='\n') as f:
					f.write(code_content)
				log.info(f"	已创建/覆盖: {full_path}")
				created_count += 1
			except Exception as e:
				log.exception(f"写入文件 '{rel_path}' ('{full_path}') 时出错: {e}"); error_count += 1

		# --- 重建摘要 ---
		log.info("\n--- 重建摘要 ---")
		block_count = len(list(constants.CODE_BLOCK_PATTERN.finditer(norm_content)))
		log.info(f"  找到的总 '```<lang>' 代码块数量: {block_count}")
		log.info(f"  识别出的唯一有效路径数量: {total_files}")
		log.info(f"  成功创建的文件数量: {created_count}")
		log.info(f"  写入过程中发生的错误数量: {error_count}")
		log.info("-----------------------------")

		if error_count > 0: log.warning("重建完成，但部分文件失败。")
		elif created_count == 0 and total_files > 0: log.warning("解析找到文件，但未能创建任何文件。")
		elif created_count == 0 and block_count == 0: log.info("未找到 '```<lang>' 代码块。")
		elif created_count == 0: log.info("未创建任何有效的文件块。")
		else: log.info("重建成功完成。")
		return True, created_count, error_count


# --- 文件合并函数 ---

# 类型别名，提高可读性
ProgressCallback = Callable[[int, int, str, bool], bool] # (processed, total, filename, is_dir) -> should_cancel

def combine_files(
	source_path: str,
	suffix_map: Dict[str, str],
	selected_suffixes: Set[str], # 改为 Set 以提高查找效率
	exclude_str: str,
	progress_callback: Optional[ProgressCallback] = None
) -> Dict[str, Any]:
	"""
	合并源目录中的文件，考虑选中的后缀和排除项。

	:param source_path: 源目录的绝对路径。
	:param suffix_map: 后缀到语言的映射字典。
	:param selected_suffixes: 用户选中的后缀集合 (带 '.')。
	:param exclude_str: 逗号分隔的排除项字符串。
	:param progress_callback: 可选的回调函数，用于报告进度。
							 签名: callback(processed_count, total_estimate, current_item_name, is_directory) -> should_cancel (bool)
	:return: 包含合并结果的字典:
			{
				'combined_text': str,
				'file_count': int,
				'skipped_count': int,
				'error_count': int,
				'merged_files_log': List[str],
				'skipped_files_log': List[str],
				'cancelled': bool
			}
	"""
	log.info(f"开始从以下位置合并: {source_path}")
	log.info(f"选中的后缀: {', '.join(sorted(selected_suffixes))}")
	excluded_patterns, excluded_suffixes_no_dot = parse_exclusions(exclude_str)
	log.info(f"排除的文件/路径模式: {', '.join(sorted(excluded_patterns))}")
	log.info(f"排除的后缀: {', '.join(sorted(['.' + s for s in excluded_suffixes_no_dot]))}")

	combined: List[str] = []
	file_count, error_count, skipped_count = 0, 0, 0
	merged_files_log: List[str] = [] # 记录合并的文件
	skipped_files_log: List[str] = [] # 记录跳过的文件
	processed_items = 0 # 包括文件和目录
	total_items_estimate = 0
	cancelled = False
	last_callback_time = 0
	callback_interval = 0.1 # 回调节流间隔（秒）

	# --- 估算总项目数以用于进度条 ---
	try:
		log.debug("开始估算总项目数...")
		# 初步遍历以估算，同时应用目录排除
		for root, dirs, files in os.walk(source_path, topdown=True):
			# 检查根目录本身是否被排除
			root_skip_reason = is_excluded(root, source_path, excluded_patterns, excluded_suffixes_no_dot)
			if root_skip_reason:
				log.debug(f"估算时跳过目录 '{root}': {root_skip_reason}")
				dirs[:] = [] # 清空 dirs 列表，阻止 os.walk 进入此目录
				continue

			# 过滤子目录
			original_dirs_count = len(dirs)
			dirs[:] = [d for d in dirs if is_excluded(os.path.join(root, d), source_path, excluded_patterns, excluded_suffixes_no_dot) is None]
			skipped_dirs_count = original_dirs_count - len(dirs)
			if skipped_dirs_count > 0:
				log.debug(f"估算时在 '{root}' 下排除了 {skipped_dirs_count} 个子目录。")

			# 计数（包括当前目录、未被排除的子目录和所有文件）
			total_items_estimate += 1 + len(dirs) + len(files)
		log.debug(f"估算的总项目数: {total_items_estimate}")
	except Exception as e:
		log.warning(f"无法估算进度条的总项目数: {e}")
		total_items_estimate = 0 # 回退到不确定模式

	# --- 实际处理遍历 ---
	try:
		log.debug("开始实际文件处理遍历...")
		for root, dirs, files in os.walk(source_path, topdown=True):
			current_time = time.time()
			processed_items += 1 # 处理当前目录

			# --- 检查根目录本身是否被排除 ---
			root_skip_reason = is_excluded(root, source_path, excluded_patterns, excluded_suffixes_no_dot)
			if root_skip_reason:
				log.debug(f"跳过目录及其内容 '{root}': {root_skip_reason}")
				skipped_files_log.append(f"{os.path.relpath(root, source_path).replace(os.sep, '/')} (目录被排除: {root_skip_reason})")
				skipped_count += 1 + len(dirs) + len(files) # 估算跳过的数量
				dirs[:] = [] # 清空 dirs 列表，阻止 os.walk 进入此目录
				continue # 处理下一个根目录

			# --- 进度回调 (针对目录) ---
			if progress_callback and (current_time - last_callback_time > callback_interval):
				if progress_callback(processed_items, total_items_estimate, os.path.basename(root), True):
					cancelled = True; break
				last_callback_time = current_time

			# --- 排除子目录 ---
			dirs_to_skip = []
			original_dirs = list(dirs) # 复制一份用于迭代
			dirs[:] = [] # 清空原始列表，稍后填充未被排除的
			for d in original_dirs:
				dir_path = os.path.join(root, d)
				dir_skip_reason = is_excluded(dir_path, source_path, excluded_patterns, excluded_suffixes_no_dot)
				if dir_skip_reason:
					dirs_to_skip.append(d)
					skipped_files_log.append(f"{os.path.relpath(dir_path, source_path).replace(os.sep, '/')} (目录被排除: {dir_skip_reason})")
					skipped_count += 1 # 只计数目录本身，其内容将在后续迭代中被跳过
					log.debug(f"排除子目录: {dir_path} ({dir_skip_reason})")
				else:
					dirs.append(d) # 保留未被排除的目录

			# --- 处理文件 ---
			for filename in files:
				processed_items += 1
				current_time = time.time()

				# --- 进度回调 (针对文件) ---
				if progress_callback and (current_time - last_callback_time > callback_interval):
					if progress_callback(processed_items, total_items_estimate, filename, False):
						cancelled = True; break
					last_callback_time = current_time

				fpath = os.path.join(root, filename)
				rel_path = os.path.relpath(fpath, source_path).replace(os.sep, '/')
				_, suffix = os.path.splitext(filename); suffix_lower = suffix.lower()

				# --- 检查是否应跳过 ---
				skip_reason = is_excluded(fpath, source_path, excluded_patterns, excluded_suffixes_no_dot)

				# --- 检查后缀是否被选中且已映射 ---
				if not skip_reason: # 仅在未被名称/路径排除时检查后缀
					if suffix_lower not in suffix_map:
						skip_reason = f"后缀 '{suffix_lower}' 未映射"
					elif suffix_lower not in selected_suffixes:
						skip_reason = f"后缀 '{suffix_lower}' 未选中"
				# --- 结束检查 ---

				if skip_reason:
					skipped_count += 1
					log_msg = f"{rel_path} ({skip_reason})"
					skipped_files_log.append(log_msg)
					log.debug(f"跳过: {log_msg}")
					continue # 跳过此文件

				# --- 文件符合条件，继续处理 ---
				lang = suffix_map.get(suffix_lower, "text") # 如果映射丢失，默认为 text
				try:
					# 以 UTF-8 读取文件, 添加 errors='ignore' 忽略无法解码的字符
					with open(fpath, 'r', encoding='utf-8', errors='ignore') as f: content = f.read()

					# --- 检查文件开头是否已有路径注释，并验证其正确性 ---
					first_line = content.split('\n', 1)[0].strip() if content else ""
					add_path_comment = True # 默认需要添加路径注释
					log_comment_reason = "添加路径注释" # 默认日志原因

					match = constants.FIRST_LINE_PATH_COMMENT_PATTERN.match(first_line)
					if match:
						existing_path_in_comment = match.group(1).strip()
						# 比较提取的路径和计算的相对路径 (都转换为 '/' 分隔符)
						if existing_path_in_comment.replace('\\', '/') == rel_path:
							add_path_comment = False # 注释存在且正确，不添加
							log_comment_reason = "保留正确的现有路径注释"
						else:
							add_path_comment = True # 注释存在但错误，需要添加正确的
							log_comment_reason = f"添加路径注释 (覆盖不正确的现有注释: '{existing_path_in_comment}')"

					# 构建代码块
					block_parts = [f"```{lang}\n"]
					if add_path_comment:
						block_parts.append(f"# {rel_path}\n")
					block_parts.append(content)
					# 确保代码块末尾有换行符，避免直接拼接 ```
					if not content.endswith('\n'):
						block_parts.append('\n')
					block_parts.append("```\n\n")
					block = "".join(block_parts)
					# --- 结束检查 ---

					combined.append(block); file_count += 1
					merged_files_log.append(rel_path) # 记录合并的文件相对路径
					# 构造完整的日志消息
					log_msg = f"已合并: {rel_path} (作为 {lang}, {log_comment_reason})"
					log.debug(log_msg)
				except Exception as e:
					log.error(f"读取或处理文件 '{fpath}' 时出错: {e}"); error_count += 1
					skipped_count += 1 # 发生错误也算跳过
					skipped_files_log.append(f"{rel_path} (读取/处理错误: {e})")

			if cancelled: break # 跳出外层循环
		# --- 遍历结束 ---

		# --- 最终进度回调 (确保达到最大值) ---
		if progress_callback and not cancelled:
			progress_callback(total_items_estimate, total_items_estimate, "完成", False)

	except Exception as e:
		log.exception(f"遍历或处理文件时发生意外错误: {e}")
		error_count += 1 # 记录为一般性错误
		skipped_files_log.append(f"处理中止 (意外错误: {e})")


	# --- 日志记录详细列表 ---
	if merged_files_log:
		log.info("--- 已合并文件 ---")
		for f in sorted(merged_files_log): log.info(f"  - {f}")
	if skipped_files_log:
		log.info("--- 已跳过文件/目录 ---")
		for f in sorted(skipped_files_log): log.info(f"  - {f}")
	log.info("--------------------")

	result = {
		'combined_text': "".join(combined),
		'file_count': file_count,
		'skipped_count': skipped_count,
		'error_count': error_count,
		'merged_files_log': merged_files_log,
		'skipped_files_log': skipped_files_log,
		'cancelled': cancelled
	}
	log.info(f"合并完成。结果: { {k: v if k=='cancelled' else len(v) if isinstance(v, list) else v for k, v in result.items() if k != 'combined_text'} }") # 简洁日志输出
	return result


# --- 示例用法 (用于测试) ---
if __name__ == "__main__":
	logging.basicConfig(level=logging.DEBUG, format='%(asctime)s - %(name)s - %(levelname)s - %(message)s')

	# --- 测试 ProjectReconstructor ---
	print("\n--- 测试 ProjectReconstructor ---")
	test_content = """
```python
# src/main.py
print("Hello")

def greet(name):
	# A comment
	print(f"Hello, {name}")
```

```javascript
# static/js/app.js
console.log("App started");

function showAlert() {
	alert("Button clicked!");
}
```

```python
# src/utils.py
# Utility functions
def add(a, b):
	return a + b
```

```text
# config/settings.txt
API_KEY=12345
DEBUG=true
```

```python
# ../../unsafe.py
# This should be skipped
import os
os.system("echo unsafe")

```

```python
# C:/absolute/path/test.py
# This should also be skipped
print("Absolute path")
```

```markdown
# README.md
# Project Readme
This is a test project.
```

```invalid
# no/valid/path
Content without valid path comment
```
	"""
	reconstructor = ProjectReconstructor("test_reconstructed_output")
	success, created, errors = reconstructor.reconstruct_from_content(test_content)
	print(f"重建结果: success={success}, created={created}, errors={errors}")
	# 清理测试目录 (如果需要)
	# import shutil
	# if os.path.exists("test_reconstructed_output"):
	#	shutil.rmtree("test_reconstructed_output")

	# --- 测试 combine_files ---
	print("\n--- 测试 combine_files ---")
	# 创建临时测试目录和文件
	test_source_dir = "test_combine_source"
	os.makedirs(os.path.join(test_source_dir, "src"), exist_ok=True)
	os.makedirs(os.path.join(test_source_dir, "docs"), exist_ok=True)
	os.makedirs(os.path.join(test_source_dir, ".git"), exist_ok=True) # 模拟 .git 目录
	os.makedirs(os.path.join(test_source_dir, "build/temp"), exist_ok=True) # 模拟 build 目录

	with open(os.path.join(test_source_dir, "src", "main.py"), "w") as f: f.write("print('main')")
	with open(os.path.join(test_source_dir, "src", "utils.py"), "w") as f: f.write("# src/utils.py\ndef helper(): pass") # 带正确注释
	with open(os.path.join(test_source_dir, "src", "data.json"), "w") as f: f.write('{"key": "value"}')
	with open(os.path.join(test_source_dir, "docs", "readme.md"), "w") as f: f.write("# Readme")
	with open(os.path.join(test_source_dir, "test.log"), "w") as f: f.write("Log entry")
	with open(os.path.join(test_source_dir, ".gitignore"), "w") as f: f.write("*.log\nbuild/")
	with open(os.path.join(test_source_dir, "build", "output.bin"), "w") as f: f.write("binary")
	with open(os.path.join(test_source_dir, ".git", "config"), "w") as f: f.write("[core]") # 模拟 .git 文件

	test_suffix_map = constants.DEFAULT_SUFFIX_MAP.copy()
	test_selected_suffixes = {'.py', '.json', '.md'} # 选择 py, json, md
	test_exclude_str = "*.log, build/, .git/, .gitignore" # 排除 log, build/, .git/, .gitignore

	# 定义简单的进度回调
	def test_progress(processed, total, name, is_dir):
		type_str = "Dir" if is_dir else "File"
		print(f"Progress: {processed}/{total if total > 0 else '?'} - {type_str}: {name}")
		# time.sleep(0.01) # 模拟耗时
		return False # 不取消

	combine_result = combine_files(
		os.path.abspath(test_source_dir),
		test_suffix_map,
		test_selected_suffixes,
		test_exclude_str,
		progress_callback=test_progress
	)

	print("\n--- 合并结果 ---")
	print(f"Cancelled: {combine_result['cancelled']}")
	print(f"File Count: {combine_result['file_count']}")
	print(f"Skipped Count: {combine_result['skipped_count']}")
	print(f"Error Count: {combine_result['error_count']}")
	print("Merged Files:")
	for f in combine_result['merged_files_log']: print(f"  - {f}")
	print("Skipped Files/Dirs:")
	for f in combine_result['skipped_files_log']: print(f"  - {f}")
	# print("\nCombined Text:")
	# print(combine_result['combined_text']) # 输出合并文本会很长，注释掉

	# 清理测试目录
	import shutil
	shutil.rmtree(test_source_dir)
	if os.path.exists("test_reconstructed_output"):
		shutil.rmtree("test_reconstructed_output")