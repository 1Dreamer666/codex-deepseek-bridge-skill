#!/usr/bin/env python3
"""Staryears 本机入口：复用 codex-deepseek-subagent 管理器，只注册 deepseek-v4.1-flash。

与原版入口 codex_deepseek.py 的差异：
- 只注册 deepseek-v4.1-flash，思考程度固定 max，Provider id 仍为 deepseek；
- Provider base_url 指向 https://api.staryears.net/v1；
- 系统凭据 target 独立为 codex-staryears-deepseek-api-key，Provider auth 回调本文件；
- 模型目录不联网获取，改为随附模板 resources/staryears-models.json；
- 目录中固定的原生父模型（gpt-6-astra、gpt-5.6-sol、gpt-5.6-terra、gpt-5.6-luna、
  gpt-5.5）一律写为明文 v1，原始值记录进管理状态 manifest 以便回滚。

角色文件、配置备份回滚、原生直连、spawn_agent 元数据与口令验收全部沿用原管理器。
本模块导入时改写共享的管理器常量，必须在独立进程中运行。
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import codex_deepseek as manager

STARYEARS_MODEL = "deepseek-v4.1-flash"
STARYEARS_EFFORT = "max"
STARYEARS_PROVIDER_NAME = "DeepSeek (Staryears)"
STARYEARS_PROVIDER_BASE_URL = "https://api.staryears.net/v1"
STARYEARS_CREDENTIAL_TARGET = "codex-staryears-deepseek-api-key"
STARYEARS_MANIFEST_KEY = "staryears_parent_original_versions"
PINNED_PARENT_MODELS = (
    "gpt-6-astra",
    "gpt-5.6-sol",
    "gpt-5.6-terra",
    "gpt-5.6-luna",
    "gpt-5.5",
)
MODELS_RESOURCE = Path(__file__).resolve().parents[1] / "resources" / "staryears-models.json"

_original_install = manager.install
_original_merged_catalog = manager.merged_catalog
_original_parent_versions: dict[str, Any] = {}


def load_local_models() -> dict[str, dict[str, Any]]:
    """从随附模板读取模型定义，替代联网获取官方目录。"""
    payload = json.loads(MODELS_RESOURCE.read_text(encoding="utf-8"))
    models = {
        item["slug"]: item
        for item in payload.get("models", [])
        if isinstance(item, dict) and isinstance(item.get("slug"), str)
    }
    missing = [slug for slug in manager.SUPPORTED_MODELS if slug not in models]
    if missing:
        raise manager.ManagerError(
            "local_models_missing",
            "本机模型模板缺少模型：" + ", ".join(missing),
            {"path": str(MODELS_RESOURCE)},
        )
    return models


def store_credential_key(secret: str) -> None:
    """Staryears 网关 Key 前缀未确认：只校验非空，实际可用性由验收会话把关。"""
    if not secret.strip():
        raise manager.ManagerError("invalid_api_key", "API Key 不能为空。")
    backend = manager.credential_backend()
    if backend == "macos-keychain":
        manager._macos_store_credential(secret)
        return
    if backend == "windows-credential-manager":
        manager._windows_store_credential(secret)
        return
    raise manager.ManagerError("unsupported_platform", "当前只支持 macOS 和 Windows 系统凭据库。")


def pin_parent_models(
    base: dict[str, Any],
    deepseek_models: dict[str, dict[str, Any]],
    parent_model: str,
) -> dict[str, Any]:
    """合并目录时把原生父模型写为明文 v1，并暂存原始值供 manifest 记录。"""
    _original_parent_versions.clear()
    for item in base.get("models", []):
        slug = item.get("slug")
        if slug in PINNED_PARENT_MODELS:
            _original_parent_versions[slug] = item.get("multi_agent_version")
    catalog = _original_merged_catalog(base, deepseek_models, parent_model)
    for item in catalog["models"]:
        if item.get("slug") in PINNED_PARENT_MODELS:
            item["multi_agent_version"] = manager.PARENT_MULTI_AGENT_VERSION
    return catalog


def install(paths: manager.Paths, codex_bin: str, selected_model: str) -> dict[str, Any]:
    """安装后把父模型固定记录并入管理状态；已记录的原始值保持首次结果。"""
    previous = manager.read_manifest(paths).get(STARYEARS_MANIFEST_KEY)
    outcome = _original_install(paths, codex_bin, selected_model)
    manifest = manager.read_manifest(paths)
    recorded = dict(previous) if isinstance(previous, dict) else {}
    for slug, value in _original_parent_versions.items():
        recorded.setdefault(slug, value)
    manifest[STARYEARS_MANIFEST_KEY] = dict(sorted(recorded.items()))
    manager.write_manifest(paths, manifest)
    return outcome


manager.FLASH_MODEL = STARYEARS_MODEL
manager.PRO_MODEL = STARYEARS_MODEL
manager.SUPPORTED_MODELS = (STARYEARS_MODEL,)
manager.MODEL = STARYEARS_MODEL
manager.MODEL_OPTIONS = [
    {
        "id": STARYEARS_MODEL,
        "label": "DeepSeek V4.1 Flash (Staryears)",
        "description": "本机 Staryears 网关的 DeepSeek V4.1 Flash，思考程度固定 max。",
    },
]
manager.EFFORT = STARYEARS_EFFORT
manager.PROVIDER_NAME = STARYEARS_PROVIDER_NAME
manager.PROVIDER_BASE_URL = STARYEARS_PROVIDER_BASE_URL
manager.CREDENTIAL_TARGET = STARYEARS_CREDENTIAL_TARGET
manager.ENTRY_SCRIPT = Path(__file__).resolve()
manager.fetch_official_deepseek_models = load_local_models
manager.store_credential_key = store_credential_key
manager.merged_catalog = pin_parent_models
manager.install = install


def main() -> int:
    return manager.main()


if __name__ == "__main__":
    raise SystemExit(main())
