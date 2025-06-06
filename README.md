# 项目文件提取与重建工具 | Project File Extractor and Reconstructor

[![Python](https://img.shields.io/badge/Python-3.x-blue.svg)](https://www.python.org/)
[![PySide6](https://img.shields.io/badge/PySide6-Used-brightgreen.svg)](https://doc.qt.io/qtforpython/)

---

**[English](#english-version) | [中文](#中文版本)**

## 中文版本

### 简介

本项目是一个使用 Python 和 PySide6 构建的桌面应用程序，旨在提供一个图形化界面来帮助用户完成两项核心任务：

1.  **项目文件合并:** 将一个项目目录下的多个源文件，根据用户选择的文件类型和排除规则，合并成一个单一的、结构化的文本文件。
2.  **项目文件重建:** 从上述格式的文本文件中，解析出原始的文件路径和内容，并在指定位置重建项目的文件和目录结构。

### 解决的问题

该工具主要解决以下场景中遇到的问题：

*   **代码分享与传输:** 在某些平台（如聊天工具、在线论坛、部分在线编辑器）不方便直接发送文件夹或有文件大小限制时，可以将整个项目打包成一个文本文件进行分享。
*   **大语言模型 (LLM) 交互:** 将项目代码库整理成适合大型语言模型（如 GPT、Claude、Gemini 等）处理的格式。LLM 可以通过这个单一文件更好地理解项目结构和内容，从而进行代码分析、问答、重构建议、文档生成等任务。
*   **从 LLM 输出恢复项目:** 如果 LLM 生成的代码遵循了本工具定义的特定格式（Markdown 代码块 + 文件路径注释），可以方便地将这些输出还原成实际的项目文件结构。
*   **代码快照/备份:** 以文本形式快速创建项目在某个时间点的简单快照。

### 核心功能

*   **文件合并 (File Combining):**
    *   **选择性合并:** 用户可以勾选需要合并的文件后缀（如 `.py`, `.js`, `.css` 等）。
    *   **灵活排除:** 支持通过逗号分隔的规则排除特定的文件名（如 `test.py`）、目录（如 `build/`, `.git/`）或文件后缀（如 `*.log`, `.tmp`）。
    *   **格式化输出:** 自动将每个文件的内容包裹在 Markdown 风格的代码块中（例如 ```python ... ```），并根据文件后缀添加相应的语言标识符。
    *   **路径注释:** 在每个代码块的开头自动添加一行注释，标明该代码段对应的原始文件相对路径（例如 `# src/main.py`），方便后续重建或人工阅读。如果文件首行已有正确的路径注释，则保留。
*   **项目重建 (Project Reconstruction):**
    *   **结构恢复:** 能准确解析包含特定格式（```language\n# path/to/file\n...```）的文本输入，并在指定的输出目录中重新创建对应的文件和目录结构。
    *   **路径安全:** 包含基础的安全检查，防止创建输出目录之外的文件或使用不安全的路径（如绝对路径、包含 `..` 的路径）。
    *   **覆盖提示:** 如果指定的输出目录非空，会弹出警告提示用户确认是否覆盖现有文件。
*   **图形用户界面 (GUI):**
    *   基于 PySide6 开发，提供直观易用的操作界面。
    *   包含清晰的区域用于选择源目录、输出目录、勾选文件后缀、输入排除规则。
    *   提供文本编辑区域显示合并结果或用于粘贴待重建的文本。
    *   内置日志窗口，实时显示操作过程、警告和错误信息。
    *   支持浅色/深色主题（通过 `style.qss` 文件或默认调色板）。
*   **配置管理 (Configuration Management):**
    *   用户的设置（如自定义的后缀映射关系、上次选中的后缀、排除规则）会自动保存到工作目录下的 `buildGUi_config.json` 文件中。
    *   下次启动应用时会自动加载这些配置，无需重复设置。
*   **后缀映射编辑 (Suffix Mapping Editor):**
    *   提供一个独立的对话框，允许用户查看、编辑、添加或删除文件后缀到代码块语言标识符的映射关系（例如，将 `.vue` 映射为 `vue`）。
    *   支持将映射重置为内置的默认值。

### 如何使用

1.  **运行环境 (Prerequisites):**
    *   确保已安装 Python 3.x。
    *   安装 PySide6 库：
        ```bash
        pip install PySide6
        ```
2.  **启动应用 (Launch):**
    *   在项目根目录下运行主脚本：
        ```bash
        python buildGUi.py
        ```
3.  **合并文件 (Combining Files):**
    *   **选择源目录:** 点击“源设置”卡片中的“浏览...”按钮，选择你的项目所在的根目录。
    *   **选择后缀:** 在“选择要合并的文件后缀”区域，勾选你想要包含在合并文本中的文件类型对应的后缀。可以使用“全选”和“全不选”按钮。如果需要添加或修改后缀与语言的映射关系，点击“编辑映射...”。
    *   **设置排除项:** 在“排除文件/后缀”输入框中，输入你想要忽略的文件、目录或后缀，用逗号分隔。例如：`*.log, build/, .git/, temp.txt, __pycache__/`。下方的预览区域会实时显示当前生效的排除规则。
    *   **执行合并:** 点击右下角的“合并文件”按钮。程序将开始遍历源目录，处理文件，并在“重建”卡片的文本区域显示合并后的结果。状态栏和日志窗口会显示进度和结果信息。
    *   **保存结果:** 如果需要，可以点击文本区域上方的“保存...”按钮，将合并后的文本保存到一个 `.txt` 或 `.md` 文件中。
4.  **重建项目 (Reconstructing Project):**
    *   **设置输出目录:** 点击“输出设置”卡片中的“浏览...”按钮，选择一个用于存放重建后文件的目录。**注意：如果该目录已存在且包含文件，重建操作会覆盖同名文件！** 程序会弹出确认提示。建议选择一个空目录。
    *   **准备输入文本:** 将之前合并生成的文本内容，或者从其他来源（如 LLM 输出）获取的符合格式的文本，粘贴到“重建”卡片的文本区域。也可以点击“加载...”按钮从文件加载。
    *   **执行重建:** 点击右下角的“重建项目”按钮。程序将解析文本内容，并在指定的输出目录中创建文件和子目录。状态栏和日志窗口会显示进度和结果。
    *   **查看结果:** 重建完成后，可以点击“输出设置”卡片中的“打开”按钮，在系统文件浏览器中查看重建后的项目。

### 合并文本格式说明

为了确保“重建项目”功能能够正确工作，输入的文本必须遵循以下格式：

```language
# relative/path/to/your/file.ext
The exact content of your file goes here.
Make sure the path comment starts with '#' and is on the first line after the language identifier.
The relative path should use '/' as the separator.
```

*   `language`: 是文件的语言标识符（例如 `python`, `javascript`, `html`），由后缀映射决定。
*   `# relative/path/to/your/file.ext`: 是文件相对于项目源目录的路径，必须以 `#` 开头，并紧跟在语言标识符行的下一行。路径分隔符应为 `/`。
*   代码块之间可以有空行。

### 适用范围

*   主要适用于处理**文本类**的源代码文件和配置文件（如 `.py`, `.java`, `.js`, `.ts`, `.html`, `.css`, `.scss`, `.json`, `.xml`, `.yaml`, `.md`, `.txt`, `.sh`, `.bat` 等）。
*   对于非常庞大的项目（文件数量巨大或单个文件过大），合并和重建过程可能会消耗较多时间和内存。
*   不适合直接处理二进制文件（如图片、编译后的可执行文件等），虽然可以被包含，但重建后可能无法正确使用。

### 适用人群

*   **软件开发者:** 需要在不同环境分享代码、与 LLM 交互分析代码或从 LLM 输出恢复代码。
*   **技术博主/作者:** 需要将项目代码整理成易于展示和复制的格式。
*   **教育工作者/学生:** 需要提交或分发包含多个文件的编程作业。
*   **需要进行代码快照的用户:** 快速创建一个基于文本的项目版本。

### 技术栈

*   **核心语言:** Python 3
*   **GUI 框架:** PySide6 (Qt for Python)

---

## English Version

### Introduction

This project is a desktop application built with Python and PySide6, designed to provide a graphical user interface (GUI) to help users perform two core tasks:

1.  **Project File Combining:** Merges multiple source files from a project directory into a single, structured text file based on user-selected file types and exclusion rules.
2.  **Project File Reconstruction:** Parses a text file in the aforementioned format to extract original file paths and content, then rebuilds the project's file and directory structure at a specified location.

### Problem Solved

This tool primarily addresses challenges encountered in the following scenarios:

*   **Code Sharing and Transmission:** When it's inconvenient to send folders directly or when platforms (like chat tools, online forums, some online editors) have file size limits, the entire project can be packaged into a single text file for sharing.
*   **Large Language Model (LLM) Interaction:** Formats a project codebase into a structure suitable for processing by large language models (e.g., GPT, Claude, Gemini). The LLM can better understand the project structure and content from this single file for tasks like code analysis, Q&A, refactoring suggestions, documentation generation, etc.
*   **Restoring Projects from LLM Output:** If code generated by an LLM adheres to the specific format defined by this tool (Markdown code blocks + file path comments), it can be easily restored into an actual project file structure.
*   **Code Snapshot/Backup:** Quickly creates a simple, text-based snapshot of a project at a specific point in time.

### Core Features

*   **File Combining:**
    *   **Selective Merging:** Users can select file extensions (e.g., `.py`, `.js`, `.css`) to include in the combined text.
    *   **Flexible Exclusion:** Supports excluding specific filenames (e.g., `test.py`), directories (e.g., `build/`, `.git/`), or file extensions (e.g., `*.log`, `.tmp`) using comma-separated rules.
    *   **Formatted Output:** Automatically wraps the content of each file in Markdown-style code blocks (e.g., ```python ... ```) with the corresponding language identifier based on the file extension.
    *   **Path Comments:** Automatically adds a comment line at the beginning of each code block indicating the original relative file path (e.g., `# src/main.py`) for easy reconstruction or manual reading. Preserves existing correct path comments.
*   **Project Reconstruction:**
    *   **Structure Recovery:** Accurately parses text input adhering to the specific format (```language\n# path/to/file\n...```) and recreates the corresponding files and directory structure in the specified output directory.
    *   **Path Safety:** Includes basic safety checks to prevent creating files outside the designated output directory or using unsafe paths (like absolute paths or paths containing `..`).
    *   **Overwrite Warning:** If the specified output directory is not empty, a warning prompt asks the user to confirm before overwriting existing files.
*   **Graphical User Interface (GUI):**
    *   Developed using PySide6 for an intuitive user experience.
    *   Provides clear sections for selecting source and output directories, choosing file extensions, and entering exclusion rules.
    *   Includes a text editing area to display combined results or paste text for reconstruction.
    *   Features a built-in log window showing real-time operation progress, warnings, and errors.
    *   Supports light/dark themes (via `style.qss` file or default palette).
*   **Configuration Management:**
    *   User settings (like custom suffix mappings, last selected extensions, exclusion rules) are automatically saved to `buildGUi_config.json` in the working directory.
    *   These configurations are automatically loaded the next time the application starts, eliminating the need for reconfiguration.
*   **Suffix Mapping Editor:**
    *   Offers a separate dialog to view, edit, add, or delete mappings between file extensions and code block language identifiers (e.g., mapping `.vue` to `vue`).
    *   Supports resetting mappings to the built-in defaults.

### How to Use

1.  **Prerequisites:**
    *   Ensure Python 3.x is installed.
    *   Install the PySide6 library:
        ```bash
        pip install PySide6
        ```
2.  **Launch the Application:**
    *   Run the main script from the project's root directory:
        ```bash
        python buildGUi.py
        ```
3.  **Combining Files:**
    *   **Select Source Directory:** Click the "Browse..." button in the "Source Settings" card to choose the root directory of your project.
    *   **Select Suffixes:** In the "Select file suffixes to combine" area, check the boxes corresponding to the file types you want to include. Use the "Select All" and "Deselect All" buttons for convenience. To add or modify suffix-to-language mappings, click "Edit Mapping...".
    *   **Set Exclusions:** In the "Exclude files/suffixes" input field, enter the files, directories, or suffixes you want to ignore, separated by commas. For example: `*.log, build/, .git/, temp.txt, __pycache__/`. The preview area below will show the currently effective exclusion rules.
    *   **Execute Combine:** Click the "Combine Files" button in the bottom right. The program will traverse the source directory, process the files, and display the combined result in the text area of the "Reconstruct" card. The status bar and log window will show progress and result information.
    *   **Save Result:** If needed, click the "Save..." button above the text area to save the combined text to a `.txt` or `.md` file.
4.  **Reconstructing Project:**
    *   **Set Output Directory:** Click the "Browse..." button in the "Output Settings" card to choose a directory where the reconstructed files will be placed. **Note: If this directory already exists and contains files, the reconstruction will overwrite files with the same name!** A confirmation prompt will appear. It's recommended to choose an empty directory.
    *   **Prepare Input Text:** Paste the previously combined text, or text obtained from other sources (like LLM output) that follows the required format, into the text area of the "Reconstruct" card. Alternatively, click the "Load..." button to load from a file.
    *   **Execute Reconstruction:** Click the "Reconstruct Project" button in the bottom right. The program will parse the text content and create the files and subdirectories in the specified output directory. The status bar and log window will show progress and results.
    *   **View Result:** After reconstruction is complete, click the "Open" button in the "Output Settings" card to view the reconstructed project in your system's file browser.

### Combined Text Format Specification

To ensure the "Reconstruct Project" feature works correctly, the input text must adhere to the following format:

```language
# relative/path/to/your/file.ext
The exact content of your file goes here.
Make sure the path comment starts with '#' and is on the first line after the language identifier.
The relative path should use '/' as the separator.
```

*   `language`: The language identifier for the file (e.g., `python`, `javascript`, `html`), determined by the suffix mapping.
*   `# relative/path/to/your/file.ext`: The file's path relative to the project source directory. It **must** start with `#` and be on the line immediately following the language identifier line. The path separator **must** be `/`.
*   Empty lines are allowed between code blocks.

### Scope

*   Primarily suitable for processing **text-based** source code files and configuration files (e.g., `.py`, `.java`, `.js`, `.ts`, `.html`, `.css`, `.scss`, `.json`, `.xml`, `.yaml`, `.md`, `.txt`, `.sh`, `.bat`, etc.).
*   For very large projects (huge number of files or extremely large individual files), the combining and reconstruction process might consume significant time and memory.
*   Not suitable for directly processing binary files (like images, compiled executables, etc.). While they might be included, they likely won't be usable after reconstruction.

### Target Audience

*   **Software Developers:** Who need to share code in different environments, interact with LLMs for code analysis, or restore code from LLM outputs.
*   **Technical Bloggers/Writers:** Who need to present project code in an easy-to-display and copy format.
*   **Educators/Students:** Who need to submit or distribute programming assignments involving multiple files.
*   **Users needing code snapshots:** To quickly create a text-based version of a project.

### Technology Stack

*   **Core Language:** Python 3
*   **GUI Framework:** PySide6 (Qt for Python)