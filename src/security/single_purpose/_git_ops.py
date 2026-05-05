"""
Git 操作实现

包含 git status, diff, log, commit, push, pull, branch 等实现
"""

import subprocess


class GitOperations:
    """Git 操作实现类"""

    @staticmethod
    def git_status(args: dict) -> str:
        """Git status"""
        try:
            result = subprocess.run(
                ["git", "status"],
                capture_output=True,
                text=True,
            )
            return (
                result.stdout
                if result.stdout.strip()
                else "[OK] Clean working tree"
            )
        except FileNotFoundError:
            return "[ERROR] git not installed"

    @staticmethod
    def git_diff(args: dict) -> str:
        """Git diff"""
        file = args.get("file")
        staged = args.get("staged", False)

        try:
            cmd = ["git", "diff"]
            if staged:
                cmd.append("--staged")
            if file:
                cmd.append(file)

            result = subprocess.run(cmd, capture_output=True, text=True)
            return result.stdout if result.stdout.strip() else "[OK] No changes"
        except FileNotFoundError:
            return "[ERROR] git not installed"

    @staticmethod
    def git_log(args: dict) -> str:
        """Git log"""
        count = args.get("count", 10)
        oneline = args.get("oneline", True)

        try:
            cmd = ["git", "log", f"-{count}"]
            if oneline:
                cmd.append("--oneline")

            result = subprocess.run(cmd, capture_output=True, text=True)
            return result.stdout
        except FileNotFoundError:
            return "[ERROR] git not installed"

    @staticmethod
    def git_commit(args: dict) -> str:
        """Git commit"""
        message = args["message"]
        amend = args.get("amend", False)

        try:
            cmd = ["git", "commit", "-m", message]
            if amend:
                cmd.append("--amend")

            result = subprocess.run(cmd, capture_output=True, text=True)

            if result.returncode == 0:
                return f"[OK] Committed: {message}"
            return f"[ERROR] Commit failed: {result.stderr}"

        except FileNotFoundError:
            return "[ERROR] git not installed"

    @staticmethod
    def git_push(args: dict) -> str:
        """Git push"""
        branch = args.get("branch")
        remote = args.get("remote", "origin")
        force = args.get("force", False)

        try:
            cmd = ["git", "push", remote]
            if branch:
                cmd.append(branch)
            if force:
                cmd.append("--force")

            result = subprocess.run(cmd, capture_output=True, text=True)

            if result.returncode == 0:
                return f"[OK] Pushed to {remote}"
            return f"[ERROR] Push failed: {result.stderr}"

        except FileNotFoundError:
            return "[ERROR] git not installed"

    @staticmethod
    def git_pull(args: dict) -> str:
        """Git pull"""
        branch = args.get("branch")
        remote = args.get("remote", "origin")

        try:
            cmd = ["git", "pull", remote]
            if branch:
                cmd.append(branch)

            result = subprocess.run(cmd, capture_output=True, text=True)

            if result.returncode == 0:
                return f"[OK] Pulled from {remote}"
            return f"[ERROR] Pull failed: {result.stderr}"

        except FileNotFoundError:
            return "[ERROR] git not installed"

    @staticmethod
    def git_branch(args: dict) -> str:
        """Git branch"""
        action = args["action"]
        name = args.get("name")

        try:
            cmd = ["git", "branch"]
            if action == "create" and name:
                cmd.append(name)
            elif action == "delete" and name:
                cmd.extend(["-d", name])

            result = subprocess.run(cmd, capture_output=True, text=True)

            if action == "list":
                return result.stdout
            if result.returncode == 0:
                return f"[OK] Branch {action}: {name}"
            return f"[ERROR] Branch {action} failed: {result.stderr}"

        except FileNotFoundError:
            return "[ERROR] git not installed"