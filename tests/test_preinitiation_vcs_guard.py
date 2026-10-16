"""本轮新增守护测试：防止 backend/storage 类源码丢失问题复发。

背景（见交付报告）：交接包声明的 backend/storage/ 四个源码文件在当前
仓库与远端均不存在（Git 历史仅 1 个提交，无其他分支/标签/本地副本；
.gitignore 的 `storage/*` 规则仅匹配仓库根级 storage/，不是丢失原因）。

本测试守护三件事：
1. src/modules/preinitiation 全部源码与静态资源不被 .gitignore 忽略
   （忽略源码 = 脱离版本管理 = 干净副本/克隆必然缺失）；
2. 模块目录不含数据库/上传/日志/密钥等运行期产物
   （修复忽略规则不得反向纳入运行数据）；
3. backend/storage/ 路径不被忽略规则覆盖（未来找回源码可直接纳入版本管理）。
"""
import os
import subprocess
import unittest

REPO_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
MODULE_DIR = os.path.join(REPO_ROOT, 'src', 'modules', 'preinitiation')
MODULE_PREFIX = os.path.join('src', 'modules', 'preinitiation')

EXPECTED_FILES = (
    '__init__.py', 'domain.py', 'providers.py', 'repository.py', 'service.py',
    'example.py', 'webapp.py', 'workspace.py',
    os.path.join('web', 'index.html'),
    os.path.join('web', 'app.css'),
    os.path.join('web', 'app.js'),
)

FORBIDDEN_EXTENSIONS = ('.db', '.sqlite', '.sqlite3', '.log', '.env', '.pem', '.key')


def _git_available() -> bool:
    try:
        subprocess.run(['git', '--version'], capture_output=True, check=True)
        return True
    except Exception:
        return False


def _in_git_work_tree() -> bool:
    """仅在真实 Git 工作树内守护（git archive 解包的干净副本无 .git，
    不存在忽略规则，跳过而非误报）。"""
    try:
        result = subprocess.run(
            ['git', 'rev-parse', '--is-inside-work-tree'],
            cwd=REPO_ROOT, capture_output=True, text=True)
        return result.returncode == 0 and result.stdout.strip() == 'true'
    except Exception:
        return False


@unittest.skipUnless(_git_available() and _in_git_work_tree(),
                     '非 Git 工作树（如 git archive 干净副本），忽略规则不生效，跳过守护')
class TestModuleUnderVersionControl(unittest.TestCase):
    def test_expected_module_files_exist(self):
        for name in EXPECTED_FILES:
            path = os.path.join(MODULE_DIR, name)
            self.assertTrue(os.path.isfile(path), f'缺少模块文件: {name}')

    def test_module_files_not_ignored(self):
        """模块源码/静态资源必须不被 .gitignore 忽略。"""
        for name in EXPECTED_FILES:
            rel = os.path.join(MODULE_PREFIX, name)
            result = subprocess.run(
                ['git', 'check-ignore', '-q', '--no-index', '--', rel],
                cwd=REPO_ROOT, capture_output=True)
            self.assertEqual(
                result.returncode, 1,
                f'{rel} 被 .gitignore 忽略——源码将脱离版本管理（backend/storage 丢失问题的复发路径）')

    def test_no_runtime_artifacts_in_module(self):
        """模块目录不得混入数据库/上传/日志/密钥等运行期产物。"""
        for root, dirs, files in os.walk(MODULE_DIR):
            dirs[:] = [d for d in dirs if d != '__pycache__']  # 解释器缓存由全局规则忽略
            for f in files:
                self.assertFalse(
                    f.endswith(FORBIDDEN_EXTENSIONS),
                    f'疑似运行期产物混入源码目录: {os.path.join(root, f)}')

    def test_backend_storage_path_not_ignored(self):
        """backend/storage/ 不被忽略规则覆盖（丢失根因不是忽略规则；本测试
        防止未来规则变更误伤该路径，找回源码后可直接 git add）。"""
        result = subprocess.run(
            ['git', 'check-ignore', '-q', '--no-index', '--', 'backend/storage/base.py'],
            cwd=REPO_ROOT, capture_output=True)
        self.assertEqual(
            result.returncode, 1,
            'backend/storage/ 被忽略规则覆盖——找回的源码将无法纳入版本管理')


if __name__ == '__main__':
    unittest.main()
