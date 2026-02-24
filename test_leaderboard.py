#!/usr/bin/env python3
"""
测试排行榜功能
"""
from bot.func_helper.win_rate_stats import WinRateStatsManager

def test_leaderboard():
    """测试排行榜查询和格式化"""
    print("=" * 50)
    print("测试排行榜功能")
    print("=" * 50)
    
    # 测试查询排行榜
    print("\n1. 查询排行榜（前10名）...")
    leaderboard = WinRateStatsManager.get_win_rate_leaderboard(limit=10)
    print(f"   查询结果: 共 {len(leaderboard)} 名玩家")
    
    if leaderboard:
        print("\n   排行榜数据示例:")
        for i, player in enumerate(leaderboard[:3], 1):
            print(f"   {i}. {player['username']} - 胜率: {player['win_rate']:.2f}% ({player['game_won']}/{player['game_played']})")
    
    # 测试格式化消息
    print("\n2. 格式化排行榜消息...")
    message = WinRateStatsManager.format_leaderboard_message(leaderboard)
    print("\n" + "=" * 50)
    print("格式化结果:")
    print("=" * 50)
    print(message)
    print("=" * 50)
    
    # 测试空排行榜
    print("\n3. 测试空排行榜...")
    empty_message = WinRateStatsManager.format_leaderboard_message([])
    print(f"   空排行榜消息: {empty_message}")
    
    print("\n✅ 测试完成！")

if __name__ == "__main__":
    test_leaderboard()
