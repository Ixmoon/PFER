# -*- coding: utf-8 -*-
"""配置管理模块"""

import json
import os
import logging
from typing import Dict, List, Optional, Any

# 从同级目录导入常量
try:
	from . import constants
except ImportError:
	import constants # 在直接运行脚本时回退

log = logging.getLogger(__name__)

class ConfigManager:
	"""负责加载和保存应用程序配置。"""

	def __init__(self, config_file_path: str = constants.CONFIG_FILE_PATH):
		"""
		初始化 ConfigManager。

		:param config_file_path: 配置文件的路径。
		"""
		self.config_file_path = config_file_path
		log.debug(f"ConfigManager 初始化，配置文件路径: {self.config_file_path}")

	def load_config(self) -> Dict[str, Any]:
		"""
		从 JSON 文件加载配置。

		处理文件不存在、JSON 解析错误和数据类型无效的情况。

		:return: 一个包含配置的字典:
				{'suffix_map': dict, 'selected_suffixes': list | None, 'exclude_patterns': str}
				如果加载失败或特定键无效，则返回包含默认值的字典。
		"""
		loaded_map: Optional[Dict[str, str]] = None
		loaded_selected_suffixes: Optional[List[str]] = None
		loaded_exclude_patterns: str = "" # 默认为空字符串

		try:
			if os.path.exists(self.config_file_path):
				with open(self.config_file_path, 'r', encoding='utf-8') as f:
					config_data = json.load(f)

				if not isinstance(config_data, dict):
					log.warning(f"配置文件 '{self.config_file_path}' 格式无效 (不是 JSON 对象)。使用默认值。")
					config_data = {} # 置为空字典以便后续处理

				# 加载后缀映射
				if 'suffix_map' in config_data and isinstance(config_data['suffix_map'], dict):
					# 基础验证: 确保键和值都是字符串
					if all(isinstance(k, str) and isinstance(v, str) for k, v in config_data['suffix_map'].items()):
						loaded_map = config_data['suffix_map']
						log.info(f"已从 '{self.config_file_path}' 加载后缀映射。")
					else:
						log.warning(f"配置文件 '{self.config_file_path}' 中 suffix_map 包含非字符串键或值。使用默认映射。")
				else:
					log.warning(f"配置文件 '{self.config_file_path}' 中后缀映射格式无效或缺失。使用默认映射。")

				# 加载选中的后缀
				if 'selected_suffixes' in config_data and isinstance(config_data['selected_suffixes'], list):
					# 基础验证：确保列表中的项是字符串
					if all(isinstance(s, str) for s in config_data['selected_suffixes']):
						loaded_selected_suffixes = config_data['selected_suffixes']
						log.info(f"已从 '{self.config_file_path}' 加载选中的后缀列表: {len(loaded_selected_suffixes)} 个。")
					else:
						log.warning(f"配置文件 '{self.config_file_path}' 中 selected_suffixes 列表包含非字符串项。忽略此设置。")
				else:
					log.info(f"配置文件 '{self.config_file_path}' 中未找到有效的 selected_suffixes 列表。将默认全选。")

				# 加载排除项
				if 'exclude_patterns' in config_data and isinstance(config_data['exclude_patterns'], str):
					loaded_exclude_patterns = config_data['exclude_patterns']
					log.info(f"已从 '{self.config_file_path}' 加载排除项。")
				else:
					log.info(f"配置文件 '{self.config_file_path}' 中未找到 'exclude_patterns'。使用空值。")

			else:
				log.info(f"配置文件 '{self.config_file_path}' 未找到。使用默认设置。")
		except json.JSONDecodeError as e:
			log.error(f"解码配置文件 '{self.config_file_path}' 时出错: {e}。使用默认设置。")
		except Exception as e:
			log.error(f"加载配置文件 '{self.config_file_path}' 时出错: {e}。使用默认设置。")

		# 返回最终使用的值，如果加载失败则使用默认值
		final_config = {
			'suffix_map': loaded_map if loaded_map is not None else constants.DEFAULT_SUFFIX_MAP.copy(),
			'selected_suffixes': loaded_selected_suffixes, # 如果加载失败则为 None
			'exclude_patterns': loaded_exclude_patterns
		}
		return final_config

	def save_config(self, config_data: Dict[str, Any]) -> bool:
		"""
		将当前配置保存到 JSON 文件。

		:param config_data: 包含配置的字典，应包含键:
						  'suffix_map' (dict),
						  'selected_suffixes' (list),
						  'exclude_patterns' (str)
		:return: 如果保存成功则返回 True，否则返回 False。
		"""
		# 验证输入数据结构 (基本检查)
		if not all(key in config_data for key in ['suffix_map', 'selected_suffixes', 'exclude_patterns']):
			log.error("保存配置失败：提供的 config_data 缺少必要的键。")
			return False
		if not isinstance(config_data.get('suffix_map'), dict):
			log.error("保存配置失败：'suffix_map' 必须是字典。")
			return False
		if not isinstance(config_data.get('selected_suffixes'), list):
			log.error("保存配置失败：'selected_suffixes' 必须是列表。")
			return False
		if not isinstance(config_data.get('exclude_patterns'), str):
			log.error("保存配置失败：'exclude_patterns' 必须是字符串。")
			return False

		try:
			# 确保目录存在
			config_dir = os.path.dirname(self.config_file_path)
			if config_dir and not os.path.exists(config_dir):
				os.makedirs(config_dir)
				log.info(f"已创建配置目录: {config_dir}")

			with open(self.config_file_path, 'w', encoding='utf-8') as f:
				json.dump(config_data, f, indent=4, ensure_ascii=False) # 使用缩进和允许非 ASCII
			log.info(f"配置已成功保存到 '{self.config_file_path}'。")
			return True
		except IOError as e:
			log.error(f"保存配置到 '{self.config_file_path}' 时发生 IO 错误: {e}")
		except TypeError as e:
			log.error(f"序列化配置数据时发生类型错误: {e}")
		except Exception as e:
			log.error(f"保存配置到 '{self.config_file_path}' 时发生未知错误: {e}")

		return False

# --- 示例用法 (用于测试) ---
if __name__ == "__main__":
	logging.basicConfig(level=logging.DEBUG, format='%(asctime)s - %(name)s - %(levelname)s - %(message)s')

	# 使用默认路径创建 ConfigManager 实例
	manager = ConfigManager()

	# 加载配置
	print("--- 尝试加载配置 ---")
	loaded_config = manager.load_config()
	print(f"加载的配置: {json.dumps(loaded_config, indent=2)}")

	# 修改配置 (示例)
	print("\n--- 修改配置 ---")
	loaded_config['selected_suffixes'] = ['.py', '.js']
	loaded_config['exclude_patterns'] = "*.log, build/"
	loaded_config['suffix_map']['.java'] = 'java' # 添加新映射
	print(f"修改后的配置: {json.dumps(loaded_config, indent=2)}")

	# 保存配置
	print("\n--- 尝试保存配置 ---")
	save_success = manager.save_config(loaded_config)
	print(f"保存操作是否成功: {save_success}")

	# 再次加载以验证保存
	print("\n--- 再次加载配置以验证 ---")
	reloaded_config = manager.load_config()
	print(f"重新加载的配置: {json.dumps(reloaded_config, indent=2)}")

	# 检查是否与修改后的配置一致
	if reloaded_config == loaded_config:
		print("\n验证成功：重新加载的配置与保存的配置一致。")
	else:
		print("\n验证失败：重新加载的配置与保存的配置不一致。")