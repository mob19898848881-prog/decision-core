#!/usr/bin/env python3
"""经 GitHub API 发布仓库内容（github.com:443 被封锁时的备用通道）。

背景（2026-11-07 实测）：本机出口代理放行 api.github.com / codeload.github.com，
但 github.com 主站 CONNECT 502 且直连超时——标准 git push 的智能 HTTP 协议
走 github.com:443，此路不通。本脚本改经 api.github.com 发布：

  1. 空仓库引导：Git Data API 拒绝在空仓库上建 blob（409 Git Repository is
     empty）——先用 Contents API 落 README 产生首个 commit；
  2. 其余文件走 Git Data API（blob → tree → commit），parent 接引导 commit；
  3. PATCH refs/heads/main 指向最终 commit。

用法：
    export GH_TOKEN=<github_pat>
    python scripts/publish_via_api.py mob19898848881-prog/decision-core
"""
import base64
import json
import os
import subprocess
import sys
import time
import urllib.error
import urllib.request

API = "https://api.github.com"


def gh(token, method, path, body=None, retries=4):
    """带重试退避的 GitHub API 调用——出口代理有瞬时断连（RemoteDisconnected/5xx）。"""
    url = f"{API}{path}"
    data = json.dumps(body).encode("utf-8") if body is not None else None
    last = None
    for attempt in range(retries):
        req = urllib.request.Request(url, data=data, method=method)
        req.add_header("Authorization", f"token {token}")
        req.add_header("Accept", "application/vnd.github+json")
        if data:
            req.add_header("Content-Type", "application/json")
        try:
            with urllib.request.urlopen(req, timeout=60) as r:
                return json.loads(r.read().decode("utf-8"))
        except urllib.error.HTTPError as e:
            body = e.read().decode("utf-8", "replace")[:300]
            if e.code >= 500:
                last = e
            else:
                print(f"[http-{e.code}] {method} {path}: {body}")
                raise
        except (urllib.error.URLError, ConnectionError, OSError) as e:
            last = e
        wait = 2 * (attempt + 1)
        print(f"  [retry {attempt + 1}/{retries - 1}] {type(last).__name__}——{wait}s 后重试")
        time.sleep(wait)
    raise last


def main_has_ref(token, repo):
    try:
        gh(token, "GET", f"/repos/{repo}/git/refs/heads/main")
        return True
    except urllib.error.HTTPError as e:
        if e.code == 409:  # Git Repository is empty
            return False
        raise


def main():
    token = os.environ.get("GH_TOKEN")
    repo = sys.argv[1] if len(sys.argv) > 1 else ""
    if not token or "/" not in repo:
        print("[FAIL] 用法: GH_TOKEN=<pat> python publish_via_api.py <owner>/<repo>")
        sys.exit(1)

    # 0. 空仓库引导（Contents API 是唯一能在空仓库上创建 commit 的通道）
    parent = None
    if not main_has_ref(token, repo):
        print("[bootstrap] 仓库为空——Contents API 引导首个 commit")
        with open("README.md", "rb") as f:
            readme_b64 = base64.b64encode(f.read()).decode("ascii")
        r = gh(token, "PUT", f"/repos/{repo}/contents/README.md", {
            "message": "chore: 经 Contents API 引导空仓库（github.com 主站被出口代理封锁，git push 不可用）",
            "content": readme_b64,
        })
        parent = r["commit"]["sha"]
        print(f"[bootstrap] seed commit -> {parent[:10]}")

    # 1. 收集本地 HEAD 的 tracked 文件（.sh 强制 100755，Windows 检出无执行位）
    out = subprocess.run(["git", "ls-tree", "-r", "HEAD"],
                         capture_output=True, text=True, check=True).stdout
    entries = []
    for line in out.splitlines():
        meta, path = line.split("\t", 1)
        mode = meta.split()[0]
        if mode != "100644":
            continue
        entries.append(("100755" if path.endswith(".sh") else mode, path))
    print(f"[files] {len(entries)} 个待发布")

    # 2. 逐文件创建 blob（base64，二进制安全）
    #    注意：内容必须取 git 对象（git cat-file blob HEAD:path）而非工作区原文件——
    #    .gitattributes 的 eol=lf 会让 git 库存 LF 归一化内容，工作区在 Windows 上
    #    是 CRLF；上传工作区字节会导致远端 blob 与本地对象 SHA 不一致。
    tree_items = []
    for i, (mode, path) in enumerate(entries):
        blob_bytes = subprocess.run(["git", "cat-file", "blob", f"HEAD:{path}"],
                                    capture_output=True, check=True).stdout
        content = base64.b64encode(blob_bytes).decode("ascii")
        blob = gh(token, "POST", f"/repos/{repo}/git/blobs",
                  {"content": content, "encoding": "base64"})
        tree_items.append({"path": path, "mode": mode, "type": "blob", "sha": blob["sha"]})
        if (i + 1) % 10 == 0:
            print(f"  blob {i + 1}/{len(entries)}")

    # 3. tree → commit（复用本地 commit message；parent 接引导 commit）
    tree = gh(token, "POST", f"/repos/{repo}/git/trees", {"tree": tree_items})
    msg = subprocess.run(["git", "log", "-1", "--format=%B"],
                         capture_output=True, text=True, check=True).stdout.strip()
    commit_body = {"message": msg, "tree": tree["sha"]}
    if parent:
        commit_body["parents"] = [parent]
    commit = gh(token, "POST", f"/repos/{repo}/git/commits", commit_body)

    # 4. 指向 main（已存在则 PATCH 更新，不存在才 POST 新建）
    if main_has_ref(token, repo):
        gh(token, "PATCH", f"/repos/{repo}/git/refs/heads/main",
           {"sha": commit["sha"], "force": True})
    else:
        gh(token, "POST", f"/repos/{repo}/git/refs",
           {"ref": "refs/heads/main", "sha": commit["sha"]})
    print(f"[done] main -> {commit['sha'][:10]}  files={len(entries)}")


if __name__ == "__main__":
    main()
