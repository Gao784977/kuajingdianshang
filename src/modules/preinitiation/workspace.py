"""Owner 级数据分区 —— 本地演示契约（不是用户权限隔离，不是身份认证）。

规则与边界（显式声明，S3 验收修正）：
- 每个 owner_id 对应一个独立 DemoWorkspace（独立内存仓储、独立会话令牌）；
- owner 之间的输入集/候选/测算/快照**键空间完全分区**，互不可见、互不可改
  ——这只保证「不同 owner 值的数据互不串扰」，**不构成安全隔离**；
- **X-Owner-Id 完全由客户端自报，不是安全身份**：任何客户端提交 A 的
  owner 值即可冒充 A——`GET /api/state` 仅凭 owner 头即可读取 A 的全部
  状态；`GET /api/session` 会向任何提交 A 的 owner 头的调用方发放 A
  工作区的写令牌（本地演示设计如此，冒用事实由
  tests/test_preinitiation_partition.py::TestHttpImpersonation 固化）。
  因此本模块的能力**不得称为「用户权限隔离/多租户」**；
- 独立本地演示的定位是**单用户**：浏览器端（web/ 前端）不使用 owner 头，
  走服务级默认工作区；registry 模式仅用于程序化演示数据分区语义；
- 生产适配契约（未实现，NOT_IMPLEMENTED）：生产环境中的 owner 必须
  来自现有系统验证后的用户上下文（如 SSO 会话解析出的用户标识），
  **不得沿用客户端自报的 X-Owner-Id**；缺少可信身份上下文时，
  生产适配入口必须拒绝请求。旧系统 backend/services/auth_service.py
  （邀请码+会话+CSRF）依赖缺失的 backend.storage（B5 阻塞），
  当前不可复用，且本轮无授权新建认证体系；
- 服务仅监听 127.0.0.1，不对外网开放；进程内状态，重启即丢失
  （见 repository.GUARANTEE）。
"""
from __future__ import annotations

import re
import threading

from .webapp import DemoWorkspace

# owner_id 仅允许字母数字与 -_. （防头部注入），长度 1~64
_OWNER_PATTERN = re.compile(r'\A[A-Za-z0-9_.-]{1,64}\Z')
MAX_OWNERS = 64  # 本地演示防滥用上限（不是多租户配额管理）


class WorkspaceRegistry:
    """owner_id → DemoWorkspace 注册表（进程内，无持久化）。"""

    def __init__(self, max_owners: int = MAX_OWNERS):
        self._lock = threading.RLock()
        self._workspaces: dict = {}
        self._max_owners = max_owners

    def get(self, owner_id: str) -> DemoWorkspace:
        """取（或首次创建）该 owner 的独立工作区。非法 owner_id 直接拒绝。"""
        self._require_valid(owner_id)
        with self._lock:
            workspace = self._workspaces.get(owner_id)
            if workspace is None:
                if len(self._workspaces) >= self._max_owners:
                    raise ValueError('too_many_owners')
                workspace = DemoWorkspace()
                self._workspaces[owner_id] = workspace
            return workspace

    def owners(self) -> list:
        with self._lock:
            return sorted(self._workspaces)

    @staticmethod
    def _require_valid(owner_id) -> None:
        if not isinstance(owner_id, str) or not _OWNER_PATTERN.match(owner_id):
            raise ValueError('invalid_owner_id')
