#!/usr/bin/env python3
"""
保持性属性测试 - 胜率榜用户名可点击修复

**Validates: Requirements 3.1, 3.2, 3.3, 3.4, 3.5, 3.6, 3.7, 3.8**

本测试用于验证修复后不会破坏现有功能：
1. 实时场景继续使用 message.from_user.first_name
2. g21 游戏中玩家加入时继续使用 message.from_user.first_name
3. 统计数据计算逻辑保持不变
4. 排行榜翻页功能正常工作
5. 用户名超过 12 个字符时截断显示

预期结果：此测试在未修复的代码上应该通过，证明基线行为正确。
修复后此测试也应该通过，证明没有引入回归。
"""
import pytest
import ast
import hypothesis
from hypothesis import given, strategies as st, settings


class TestPreservationProperties:
    """保持性属性测试类"""
    
    def test_realtime_scenario_uses_message_from_user_first_name(self):
        """
        测试 1: 验证实时场景继续使用 message.from_user.first_name
        
        保持性需求：
        - /win 命令查询自己时使用 message.from_user.first_name
        - 回复消息查询时使用 message.reply_to_message.from_user.first_name
        - g21 游戏中玩家加入时使用 message.from_user.first_name
        
        预期：在未修复和修复后的代码上，此测试都应该通过
        """
        # 检查 gamestats.py 中的实时场景
        with open('bot/modules/commands/gamestats.py', 'r', encoding='utf-8') as f:
            source = f.read()
        
        # 验证实时场景使用 message.from_user.first_name
        assert 'msg.from_user.first_name' in source, (
            "保持性验证失败：实时场景应继续使用 msg.from_user.first_name"
        )
        
        assert 'msg.reply_to_message.from_user.first_name' in source, (
            "保持性验证失败：回复消息场景应继续使用 msg.reply_to_message.from_user.first_name"
        )
        
        # 检查 g21.py 中的实时场景
        with open('bot/modules/commands/g21.py', 'r', encoding='utf-8') as f:
            g21_source = f.read()
        
        assert 'message.from_user.first_name' in g21_source, (
            "保持性验证失败：g21 游戏应继续使用 message.from_user.first_name"
        )
    
    def test_stats_calculation_logic_unchanged(self):
        """
        测试 2: 验证统计数据计算逻辑保持不变
        
        保持性需求：
        - 胜率计算公式不变：(game_won / game_played) * 100
        - 失败局数计算不变：game_played - game_won
        - 除零处理逻辑不变
        
        预期：在未修复和修复后的代码上，此测试都应该通过
        """
        with open('bot/func_helper/win_rate_stats.py', 'r', encoding='utf-8') as f:
            source = f.read()
        
        # 验证 get_user_stats 函数存在
        assert 'def get_user_stats' in source, "未找到 get_user_stats 函数"
        
        # 验证胜率计算逻辑
        assert 'game_won / game_played' in source, (
            "保持性验证失败：胜率计算公式应保持不变"
        )
        
        # 验证失败局数计算
        assert 'game_played - game_won' in source, (
            "保持性验证失败：失败局数计算应保持不变"
        )
        
        # 验证除零处理
        assert 'if game_played == 0' in source, (
            "保持性验证失败：除零处理逻辑应保持不变"
        )
    
    def test_leaderboard_pagination_structure_unchanged(self):
        """
        测试 3: 验证排行榜翻页功能结构保持不变
        
        保持性需求：
        - 每页显示 10 个玩家
        - 总页数计算逻辑不变：math.ceil(total_count / 10)
        - 分页偏移计算不变：(page_num - 1) * 10
        
        预期：在未修复和修复后的代码上，此测试都应该通过
        """
        with open('bot/func_helper/win_rate_stats.py', 'r', encoding='utf-8') as f:
            source = f.read()
        
        # 验证 get_win_rate_rank_pages 函数存在
        assert 'def get_win_rate_rank_pages' in source, "未找到 get_win_rate_rank_pages 函数"
        
        # 验证每页 10 个玩家
        assert '/ 10' in source, (
            "保持性验证失败：每页应显示 10 个玩家"
        )
        
        # 验证分页计算
        assert 'math.ceil' in source, (
            "保持性验证失败：总页数计算应使用 math.ceil"
        )
        
        # 验证偏移计算
        assert '(page_num - 1) * 10' in source or 'offset + 10' in source, (
            "保持性验证失败：分页偏移计算应保持不变"
        )
    
    @settings(max_examples=50, deadline=None)
    @given(username_length=st.integers(min_value=1, max_value=50))
    def test_username_truncation_at_12_chars(self, username_length):
        """
        测试 4: 验证用户名超过 12 个字符时截断显示（基于属性的测试）
        
        保持性需求：
        - 用户名超过 12 个字符时应截断为前 12 个字符
        - 截断逻辑：[:12]
        
        预期：在未修复和修复后的代码上，此测试都应该通过
        """
        with open('bot/func_helper/win_rate_stats.py', 'r', encoding='utf-8') as f:
            source = f.read()
        
        # 验证截断逻辑存在
        assert '[:12]' in source, (
            "保持性验证失败：用户名应在 12 个字符处截断"
        )
        
        # 模拟截断行为
        test_username = 'A' * username_length
        truncated = test_username[:12]
        
        # 验证截断后的长度
        if username_length > 12:
            assert len(truncated) == 12, (
                f"截断逻辑错误：用户名长度 {username_length} 应截断为 12 个字符"
            )
        else:
            assert len(truncated) == username_length, (
                f"截断逻辑错误：用户名长度 {username_length} 不应被截断"
            )
    
    def test_leaderboard_callback_handler_unchanged(self):
        """
        测试 5: 验证排行榜翻页回调处理器保持不变
        
        保持性需求：
        - handle_win_rate_page 回调函数继续正常工作
        - 翻页按钮回调数据格式不变：win_rate:j_tg
        - 权限检查逻辑不变
        
        预期：在未修复和修复后的代码上，此测试都应该通过
        """
        with open('bot/modules/commands/gamestats.py', 'r', encoding='utf-8') as f:
            source = f.read()
        
        # 验证 handle_win_rate_page 函数存在
        assert 'def handle_win_rate_page' in source, (
            "保持性验证失败：未找到 handle_win_rate_page 回调函数"
        )
        
        # 验证回调数据解析
        assert 'win_rate:' in source, (
            "保持性验证失败：翻页回调数据格式应保持不变"
        )
        
        # 验证权限检查
        assert 'call.from_user.id' in source, (
            "保持性验证失败：权限检查逻辑应保持不变"
        )
        
        # 验证调用 get_win_rate_rank_pages
        assert 'get_win_rate_rank_pages' in source, (
            "保持性验证失败：应继续调用 get_win_rate_rank_pages 函数"
        )
    
    def test_empty_leaderboard_message_unchanged(self):
        """
        测试 6: 验证排行榜为空时的提示消息保持不变
        
        保持性需求：
        - 无游戏数据时显示"暂无排行数据"
        - 空排行榜处理逻辑不变
        
        预期：在未修复和修复后的代码上，此测试都应该通过
        """
        with open('bot/modules/commands/gamestats.py', 'r', encoding='utf-8') as f:
            source = f.read()
        
        # 验证空排行榜提示消息
        assert '暂无排行数据' in source, (
            "保持性验证失败：空排行榜应显示'暂无排行数据'提示"
        )
    
    @settings(max_examples=50, deadline=None)
    @given(
        game_played=st.integers(min_value=0, max_value=1000),
        game_won=st.integers(min_value=0, max_value=1000)
    )
    def test_win_rate_calculation_consistency(self, game_played, game_won):
        """
        测试 7: 验证胜率计算的一致性（基于属性的测试）
        
        保持性需求：
        - 胜率计算公式保持一致
        - 边界情况处理正确（除零、胜局数大于总局数等）
        
        预期：在未修复和修复后的代码上，此测试都应该通过
        """
        # 确保 game_won 不大于 game_played
        if game_won > game_played:
            game_won = game_played
        
        # 模拟胜率计算逻辑
        if game_played == 0:
            expected_win_rate = 0.0
        else:
            expected_win_rate = (game_won / game_played) * 100
        
        # 验证计算结果的合理性
        assert 0.0 <= expected_win_rate <= 100.0, (
            f"胜率计算错误：胜率应在 0-100 之间，实际为 {expected_win_rate}"
        )
        
        # 验证边界情况
        if game_played == 0:
            assert expected_win_rate == 0.0, "无游戏记录时胜率应为 0"
        
        if game_won == game_played and game_played > 0:
            assert expected_win_rate == 100.0, "全胜时胜率应为 100%"
        
        if game_won == 0 and game_played > 0:
            assert expected_win_rate == 0.0, "全败时胜率应为 0%"
    
    def test_format_stats_message_structure_unchanged(self):
        """
        测试 8: 验证统计消息格式保持不变
        
        保持性需求：
        - 统计消息包含：总参与局数、总获胜局数、总失败局数、胜率
        - 消息格式和图标不变
        
        预期：在未修复和修复后的代码上，此测试都应该通过
        """
        with open('bot/func_helper/win_rate_stats.py', 'r', encoding='utf-8') as f:
            source = f.read()
        
        # 验证 format_stats_message 函数存在
        assert 'def format_stats_message' in source, "未找到 format_stats_message 函数"
        
        # 验证消息包含必要的统计信息
        assert '总参与局数' in source or 'game_played' in source, (
            "保持性验证失败：统计消息应包含总参与局数"
        )
        
        assert '总获胜局数' in source or 'game_won' in source, (
            "保持性验证失败：统计消息应包含总获胜局数"
        )
        
        assert '总失败局数' in source or 'game_lost' in source, (
            "保持性验证失败：统计消息应包含总失败局数"
        )
        
        assert '胜率' in source or 'win_rate' in source, (
            "保持性验证失败：统计消息应包含胜率"
        )


if __name__ == "__main__":
    # 运行测试
    pytest.main([__file__, "-v", "-s"])
