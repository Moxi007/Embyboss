#!/usr/bin/env python3
"""
Bug 条件探索性测试 - 胜率榜用户名可点击修复

**Validates: Requirements 2.1, 2.2, 2.3, 2.4, 2.5, 2.6, 2.7, 2.8**

本测试用于在未修复的代码上暴露 bug 的具体表现：
1. 排行榜消息发送时缺少 parse_mode 参数
2. 排行榜显示时使用 user.name（Emby 账号名）而非 Telegram 用户名
3. 通过用户ID查询统计时使用 user.name 而非 Telegram 用户名

预期结果：此测试在未修复的代码上应该失败，证明 bug 存在。
"""
import pytest
import ast
import os


class TestBugConditionExploration:
    """Bug 条件探索性测试类"""
    
    def test_sendphoto_missing_parse_mode(self):
        """
        测试 1: 检查 sendPhoto() 调用是否缺少 parse_mode 参数
        
        Bug 条件：handle_leaderboard_command() 函数调用 sendPhoto() 时
        未指定 parse_mode 参数，导致 Markdown 链接语法未被解析
        
        预期：在未修复的代码上，此测试应该失败（找不到 parse_mode 参数）
        """
        # 读取源代码文件
        with open('bot/modules/commands/gamestats.py', 'r', encoding='utf-8') as f:
            source = f.read()
        tree = ast.parse(source)
        
        # 查找所有的函数调用
        sendphoto_calls = []
        for node in ast.walk(tree):
            if isinstance(node, ast.Call):
                # 检查是否是 sendPhoto 调用
                if isinstance(node.func, ast.Name) and node.func.id == 'sendPhoto':
                    sendphoto_calls.append(node)
                elif isinstance(node.func, ast.Attribute) and node.func.attr == 'sendPhoto':
                    sendphoto_calls.append(node)
        
        # 验证找到了 sendPhoto 调用
        assert len(sendphoto_calls) > 0, "未找到 sendPhoto 调用"
        
        # 检查 sendPhoto 调用是否包含 parse_mode 参数
        has_parse_mode = False
        for call in sendphoto_calls:
            for keyword in call.keywords:
                if keyword.arg == 'parse_mode':
                    has_parse_mode = True
                    break
        
        # Bug 条件：缺少 parse_mode 参数
        # 在未修复的代码上，这个断言应该失败
        assert has_parse_mode, (
            "Bug 确认：sendPhoto() 调用缺少 parse_mode 参数，"
            "导致 Markdown 链接语法无法被解析为可点击链接"
        )
    
    def test_leaderboard_uses_user_name_not_get_users(self):
        """
        测试 2: 检查 get_win_rate_rank_pages() 是否使用 user.name 而非 get_users()
        
        Bug 条件：排行榜显示时直接使用 user.name（Emby 账号名）
        而不是调用 get_users() 函数获取 Telegram 用户名字典
        
        预期：在未修复的代码上，此测试应该失败（找到 user.name 使用）
        """
        # 读取源代码文件
        with open('bot/func_helper/win_rate_stats.py', 'r', encoding='utf-8') as f:
            source = f.read()
        tree = ast.parse(source)
        
        # 检查是否调用了 get_users() 函数
        calls_get_users = False
        for node in ast.walk(tree):
            if isinstance(node, ast.Call):
                if isinstance(node.func, ast.Name) and node.func.id == 'get_users':
                    calls_get_users = True
                    break
        
        # 检查是否使用了 user.name
        uses_user_name = False
        for node in ast.walk(tree):
            if isinstance(node, ast.Attribute):
                if node.attr == 'name':
                    # 检查是否是 user.name 形式
                    if isinstance(node.value, ast.Name) and node.value.id == 'user':
                        uses_user_name = True
                        break
        
        # Bug 条件：使用 user.name 且未调用 get_users()
        # 在未修复的代码上，这些断言应该失败
        assert calls_get_users, (
            "Bug 确认：get_win_rate_rank_pages() 未调用 get_users() 函数获取 Telegram 用户名字典"
        )
        
        assert not uses_user_name or calls_get_users, (
            "Bug 确认：get_win_rate_rank_pages() 使用 user.name（Emby 账号名）"
            "而不是通过 get_users() 获取的 Telegram 用户名"
        )
    
    def test_gamestats_command_uses_user_name_for_id_query(self):
        """
        测试 3: 检查 handle_gamestats_command() 在通过ID查询时是否使用 user.name
        
        Bug 条件：通过用户ID查询统计时（len(msg.command) > 1 分支）
        使用 user.name（Emby 账号名）而不是调用 get_users() 获取 Telegram 用户名
        
        预期：在未修复的代码上，此测试应该失败（找到 user.name 使用）
        """
        # 读取源代码文件
        with open('bot/modules/commands/gamestats.py', 'r', encoding='utf-8') as f:
            source = f.read()
        tree = ast.parse(source)
        
        # 查找 len(msg.command) > 1 分支
        # 检查该分支中是否调用了 get_users()
        calls_get_users_in_id_branch = False
        uses_user_name_in_id_branch = False
        
        # 遍历所有 if 语句
        for node in ast.walk(tree):
            if isinstance(node, ast.If):
                # 检查条件是否是 len(msg.command) > 1
                if self._is_command_length_check(node.test):
                    # 在这个分支中检查是否调用 get_users()
                    for child in ast.walk(node):
                        if isinstance(child, ast.Call):
                            if isinstance(child.func, ast.Name) and child.func.id == 'get_users':
                                calls_get_users_in_id_branch = True
                        
                        # 检查是否使用 user.name
                        if isinstance(child, ast.Attribute):
                            if child.attr == 'name':
                                if isinstance(child.value, ast.Name) and child.value.id == 'user':
                                    uses_user_name_in_id_branch = True
        
        # Bug 条件：在通过ID查询分支中使用 user.name 且未调用 get_users()
        # 在未修复的代码上，这些断言应该失败
        assert calls_get_users_in_id_branch, (
            "Bug 确认：handle_gamestats_command() 在通过用户ID查询时"
            "未调用 get_users() 函数获取 Telegram 用户名字典"
        )
        
        assert not uses_user_name_in_id_branch or calls_get_users_in_id_branch, (
            "Bug 确认：handle_gamestats_command() 在通过用户ID查询时"
            "使用 user.name（Emby 账号名）而不是通过 get_users() 获取的 Telegram 用户名"
        )
    
    def _is_command_length_check(self, node):
        """
        辅助方法：检查 AST 节点是否是 len(msg.command) > 1 的比较
        """
        if isinstance(node, ast.Compare):
            # 检查左侧是否是 len(msg.command)
            if isinstance(node.left, ast.Call):
                if isinstance(node.left.func, ast.Name) and node.left.func.id == 'len':
                    if len(node.left.args) > 0:
                        arg = node.left.args[0]
                        if isinstance(arg, ast.Attribute) and arg.attr == 'command':
                            return True
        return False


if __name__ == "__main__":
    # 运行测试
    pytest.main([__file__, "-v", "-s"])
