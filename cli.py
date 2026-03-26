#!/usr/bin/env python3
"""
抖音自动化平台 - 命令行工具
"""

import sys
from pathlib import Path
from dotenv import load_dotenv

from src.services import LiveService, UploadService, AccountService, ProfileService, SpyService


def main():
    """主函数"""
    load_dotenv(override=True)

    # 解析命令行参数
    if len(sys.argv) < 2:
        print("用法:")
        print("  python cli.py register                    # 注册新账号 Profile")
        print("  python cli.py profiles                     # 列出所有 Profile")
        print("  python cli.py delete-profile <名称>         # 删除指定 Profile")
        print("  python cli.py chat <主播名字> [消息] [--account 账号名]")
        print("  python cli.py upload <视频路径> [标题] [--account 账号名]")
        print("  python cli.py batch-upload <视频目录> [标题前缀] [--account 账号名]")
        print("  python cli.py account <任务描述> [--account 账号名]")
        print("  python cli.py account following [--account 账号名]      # 获取关注列表及直播状态")
        print("  python cli.py account followers [--account 账号名]      # 获取粉丝详细信息")
        print("  python cli.py account works [--account 账号名]          # 获取作品数据分析")
        print("  python cli.py spy <抖音号> [--works N] [--following N] [--followers N]  # 无账号侦察")
        print("")
        print("示例:")
        print("  python cli.py register                    # 扫码注册新账号")
        print("  python cli.py profiles                     # 查看所有已注册账号")
        print("  python cli.py delete-profile 张三           # 删除张三的 Profile")
        print("  python cli.py chat 喜宝")
        print("  python cli.py chat 喜宝 '你好主播' --account 张三")
        print("  python cli.py upload videos/test.mp4")
        print("  python cli.py upload videos/test.mp4 '我的视频标题' --account 李四")
        print("  python cli.py batch-upload videos/ '每日分享-'")
        print("  python cli.py account '查看我的主页信息'")
        print("  python cli.py account '编辑个人简介为：AI自动化专家' --account 张三")
        print("  python cli.py account '查看我的关注列表'")
        print("  python cli.py account following             # 查看关注列表及谁在直播")
        print("  python cli.py account followers             # 查看粉丝详细信息")
        print("  python cli.py account works                 # 查看作品数据分析")
        print("")
        print("说明:")
        print("  --account: 指定抖音账号名称（默认: cyberstroll跨境电商）")
        return
    
    command = sys.argv[1]

    # spy 命令不需要登录账号，单独处理
    if command == "spy":
        if len(sys.argv) < 3:
            print("❌ 请指定抖音号")
            print("示例: python cli.py spy someuser123")
            print("      python cli.py spy someuser123 --works 30 --following 50 --followers 50")
            return

        target_id = sys.argv[2]

        def get_opt(flag, default):
            if flag in sys.argv:
                idx = sys.argv.index(flag)
                if idx + 1 < len(sys.argv):
                    try:
                        return int(sys.argv[idx + 1])
                    except ValueError:
                        pass
            return default

        max_works     = get_opt("--works",     20)
        max_following = get_opt("--following", 20)
        max_followers = get_opt("--followers", 20)

        import json
        service = SpyService()
        if not service.connect(headless=False):
            print("❌ 连接失败")
            return

        try:
            report = service.research(
                target_id,
                max_works=max_works,
                max_following=max_following,
                max_followers=max_followers
            )
            if report.get("success"):
                out_file = f"spy_{target_id}.json"
                with open(out_file, "w", encoding="utf-8") as f:
                    json.dump(report, f, ensure_ascii=False, indent=2)
                print(f"\n💾 报告已保存: {out_file}")
        finally:
            service.cleanup()
        return

    elif command == "feed":
        max_works    = 20
        max_comments = 30
        with_comments = True
        expand_depth = 0  # 默认不扩展，--expand N 开启

        if "--max" in sys.argv:
            idx = sys.argv.index("--max")
            if idx + 1 < len(sys.argv):
                max_works = int(sys.argv[idx + 1])
        if "--max-comments" in sys.argv:
            idx = sys.argv.index("--max-comments")
            if idx + 1 < len(sys.argv):
                max_comments = int(sys.argv[idx + 1])
        if "--no-comments" in sys.argv:
            with_comments = False
        if "--expand" in sys.argv:
            idx = sys.argv.index("--expand")
            if idx + 1 < len(sys.argv):
                try:
                    expand_depth = int(sys.argv[idx + 1])
                except ValueError:
                    expand_depth = 1

        import json
        from src.services import FeedService
        service = FeedService()
        if not service.connect(headless=False):
            print("❌ 连接失败")
            return

        try:
            works = service.scrape_feed(
                max_works=max_works,
                with_comments=with_comments,
                max_comments=max_comments
            )
            out_file = "feed_result.json"
            with open(out_file, "w", encoding="utf-8") as f:
                json.dump(works, f, ensure_ascii=False, indent=2)
            print(f"\n💾 结果已保存: {out_file}")

            # 自动图谱扩展
            if expand_depth > 0:
                uids = list({w["author_uid"] for w in works if w.get("author_uid")})
                print(f"\n🕸️  开始图谱扩展（{len(uids)} 个作者，深度 {expand_depth}）...")
                from src.services import SpyService
                spy = SpyService()
                # 复用 feed 的浏览器实例，避免重复创建
                spy.pinchtab = service.pinchtab
                if spy.graph:
                    for uid in uids:
                        print(f"\n   扩展: {uid[:30]}...")
                        spy.research_graph(uid, depth=expand_depth, max_per_node=20)
        finally:
            service.cleanup()
        return
        from src.services import AccountPool
        pool = AccountPool()
        sub = sys.argv[2] if len(sys.argv) > 2 else "list"
        if sub == "list":
            accounts = pool.list_all()
            print(f"\n账号池（{len(accounts)} 个）:")
            for a in accounts:
                print(f"  [{a['status']}] {a['profile_name']} | 请求数: {a['request_count']} | 最后使用: {a.get('last_used','从未')}")
        elif sub == "add":
            name = sys.argv[3] if len(sys.argv) > 3 else ""
            if not name:
                print("❌ 请指定 profile 名称: python cli.py pool add <name>")
            else:
                pool.add(name)
        elif sub == "stats":
            print(pool.stats())
        return

    elif command == "watch":
        max_following = 100
        max_works = 20
        if "--max" in sys.argv:
            idx = sys.argv.index("--max")
            if idx + 1 < len(sys.argv):
                max_following = int(sys.argv[idx + 1])
        if "--works" in sys.argv:
            idx = sys.argv.index("--works")
            if idx + 1 < len(sys.argv):
                max_works = int(sys.argv[idx + 1])

        from src.services import WatchService
        service = WatchService()
        if not service.connect(headless=False):
            print("❌ 连接失败")
            return
        try:
            if "--deep" in sys.argv:
                max_fof = 30
                if "--fof" in sys.argv:
                    idx = sys.argv.index("--fof")
                    if idx + 1 < len(sys.argv):
                        max_fof = int(sys.argv[idx + 1])
                service.watch_deep(max_following=max_following, max_following_of_following=max_fof)
            else:
                service.watch(max_following=max_following, max_works_per_user=max_works)
        finally:
            service.cleanup()
        return

    elif command == "graph":
        from src.services import GraphService
        sub = sys.argv[2] if len(sys.argv) > 2 else "stats"
        g = GraphService()
        if g.connect():
            if sub == "stats":
                print(g.stats())
            g.close()
        return

    elif command == "analyze":
        # python cli.py analyze <视频链接> [--lang zh|en] [--duration 30]
        if len(sys.argv) < 3:
            print("❌ 请指定视频链接")
            print("示例: python cli.py analyze https://www.douyin.com/video/xxx")
            return

        video_url = sys.argv[2]
        lang      = "zh"
        duration  = 30

        if "--lang" in sys.argv:
            idx = sys.argv.index("--lang")
            if idx + 1 < len(sys.argv):
                lang = sys.argv[idx + 1]
        if "--duration" in sys.argv:
            idx = sys.argv.index("--duration")
            if idx + 1 < len(sys.argv):
                duration = int(sys.argv[idx + 1])

        from src.analysis import AnalysisPipeline
        pipeline = AnalysisPipeline()
        pipeline.run(video_url, lang=lang, duration_target=duration)
        return

    elif command == "graph-expand":
        if len(sys.argv) < 3:
            print("❌ 请指定种子 UID")
            print("示例: python cli.py graph-expand MS4wLjABAAAA... --depth 2 --max 20")
            return

        seed_uid = sys.argv[2]

        def get_opt(flag, default):
            if flag in sys.argv:
                idx = sys.argv.index(flag)
                if idx + 1 < len(sys.argv):
                    try:
                        return int(sys.argv[idx + 1])
                    except ValueError:
                        pass
            return default

        depth   = get_opt("--depth", 2)
        max_per = get_opt("--max",   20)

        import json
        service = SpyService()
        if not service.connect(headless=False):
            print("❌ 连接失败")
            return

        try:
            result = service.research_graph(seed_uid, depth=depth, max_per_node=max_per)
            print(f"\n✅ 完成: {result}")
        finally:
            service.cleanup()
        return

    # 解析 --account 参数（必须指定）
    if "--account" not in sys.argv:
        print("❌ 请用 --account 指定 profile 名称")
        print("示例: python cli.py account info --account cyberstroll跨境电商")
        print("\n可用 profiles:")
        try:
            import requests
            profiles = requests.get("http://localhost:9867/profiles", timeout=5).json()
            for p in profiles:
                print(f"  {p['name']}")
        except:
            print("  (无法获取，请确认 PinchTab 已启动)")
        return

    account_index = sys.argv.index("--account")
    if account_index + 1 >= len(sys.argv):
        print("❌ --account 参数需要指定 profile 名称")
        return
    account_name = sys.argv[account_index + 1]
    sys.argv.pop(account_index + 1)
    sys.argv.pop(account_index)

    if command == "relogin":
        import time
        print(f"\n🔑 重新登录 Profile: {account_name}")
        print("   浏览器将打开抖音，请手动扫码登录")
        print("   检测到登录成功后自动保存退出...")

        from src.core.pinchtab_client import PinchTabClient
        import requests as _req
        c = PinchTabClient("http://localhost:9867")
        if not c.connect(profile_name=account_name, headless=False):
            print("❌ 连接失败")
            return

        c.navigate("https://www.douyin.com", wait_seconds=5)
        print("\n   ✅ 浏览器已打开，请扫码登录...")

        # 自动检测登录状态，最多等 3 分钟
        for i in range(60):
            time.sleep(3)
            try:
                r = _req.post(
                    f"http://localhost:9867/tabs/{c.tab_id}/evaluate",
                    json={"expression": "document.querySelector('[data-e2e=\"user-info-fans\"]') ? 'logged_in' : 'not_logged_in'"},
                    timeout=5
                )
                status = r.json().get("result", "")
                if status == "logged_in":
                    print(f"\n   ✅ 检测到登录成功！等待 cookie 写入...")
                    time.sleep(5)
                    break
                else:
                    print(f"   ⏳ 等待登录... ({(i+1)*3}s)", end="\r")
            except Exception:
                pass
        else:
            print("\n   ⚠️  等待超时（3分钟），请检查是否登录成功")

        c.cleanup()
        print("✅ Cookie 已保存到 Profile")
        return

    elif command == "register":
        print("\n" + "="*60)
        print("注册新的抖音 Profile")
        print("="*60)

        service = ProfileService()
        result = service.register_douyin_profile()

        print("\n" + "="*60)
        if result["success"]:
            print("✅ 注册成功")
            print(f"Profile 名称: {result['profile_name']}")
            print(f"抖音昵称: {result['nickname']}")
            print(f"\n使用方式:")
            print(f"  python cli.py chat 喜宝 --account {result['profile_name']}")
        else:
            print("❌ 注册失败")
            print(f"原因: {result['message']}")
        print("="*60)

        sys.exit(0 if result["success"] else 1)

    elif command == "profiles":
        print("\n" + "="*60)
        print("所有 Profile 列表")
        print("="*60)

        service = ProfileService()
        result = service.list_profiles()

        if result["success"]:
            print(f"\n共有 {result['count']} 个 Profile:\n")
            for i, profile in enumerate(result["profiles"], 1):
                print(f"{i}. {profile['name']}")
                print(f"   ID: {profile['id']}")
                print(f"   大小: {profile.get('sizeMB', 0):.1f} MB")
                if profile.get("createdAt"):
                    from datetime import datetime
                    created = datetime.fromisoformat(profile["createdAt"].replace('Z', '+00:00'))
                    print(f"   创建时间: {created.strftime('%Y-%m-%d %H:%M:%S')}")
                print()
        else:
            print(f"❌ 获取失败: {result['message']}")

        print("="*60)
        sys.exit(0 if result["success"] else 1)

    elif command == "delete-profile":
        if len(sys.argv) < 3:
            print("❌ 请指定要删除的 Profile 名称")
            print("示例: python cli.py delete-profile 张三")
            return

        profile_name = sys.argv[2]

        print(f"\n⚠️  确认要删除 Profile '{profile_name}' 吗？")
        confirm = input("请输入 'yes' 确认删除: ")

        if confirm.lower() != "yes":
            print("已取消删除")
            return

        service = ProfileService()
        result = service.delete_profile(profile_name)

        print("\n" + "="*60)
        if result["success"]:
            print(f"✅ {result['message']}")
        else:
            print(f"❌ {result['message']}")
        print("="*60)

        sys.exit(0 if result["success"] else 1)

    elif command == "chat":
        if len(sys.argv) < 3:
            print("❌ 请指定主播名字")
            print("示例: python cli.py chat 喜宝")
            return
        
        keyword = sys.argv[2]
        message = sys.argv[3] if len(sys.argv) > 3 else "hello 我是ai"
        
        # 创建服务
        service = LiveService()
        
        # 连接
        if not service.connect(profile_name=account_name, headless=False):
            print("❌ 连接失败")
            return
        
        # 进入直播间并发送消息
        success = service.enter_and_chat(keyword, message)
        
        sys.exit(0 if success else 1)
    
    elif command == "upload":
        if len(sys.argv) < 3:
            print("❌ 请指定视频文件路径")
            print("示例: python cli.py upload videos/test.mp4")
            return
        
        video_path = Path(sys.argv[2])
        title = sys.argv[3] if len(sys.argv) > 3 else None
        
        if not video_path.exists():
            print(f"❌ 视频文件不存在: {video_path}")
            return
        
        # 创建服务
        service = UploadService()
        
        # 连接
        if not service.connect(profile_name=account_name, headless=False):
            print("❌ 连接失败")
            return
        
        # 上传视频
        success = service.upload_video(video_path, title=title)
        
        sys.exit(0 if success else 1)
    
    elif command == "batch-upload":
        if len(sys.argv) < 3:
            print("❌ 请指定视频目录")
            print("示例: python cli.py batch-upload videos/")
            return
        
        video_dir = Path(sys.argv[2])
        title_prefix = sys.argv[3] if len(sys.argv) > 3 else ""
        
        if not video_dir.exists() or not video_dir.is_dir():
            print(f"❌ 目录不存在: {video_dir}")
            return
        
        # 创建服务
        service = UploadService()
        
        # 连接
        if not service.connect(profile_name=account_name, headless=False):
            print("❌ 连接失败")
            return
        
        # 批量上传
        stats = service.batch_upload(video_dir, title_prefix=title_prefix)
        
        sys.exit(0 if stats["failed"] == 0 else 1)
    
    elif command == "account":
        # 检查是否指定了具体功能
        if len(sys.argv) < 3:
            print("❌ 请指定子命令")
            print("示例:")
            print("  python cli.py account info              # 昵称、简介、抖音号")
            print("  python cli.py account followers [N]     # 粉丝列表")
            print("  python cli.py account following [N]     # 关注列表")
            print("  python cli.py account works [N]         # 作品数据")
            print("  python cli.py account '任意任务描述'     # AI 驱动")
            return

        subcommand = sys.argv[2]

        service = AccountService()

        if not service.connect(profile_name=account_name, headless=False):
            print("❌ 连接失败")
            return

        if subcommand == "info":
            service.get_profile_info()
        elif subcommand == "followers":
            n = int(sys.argv[3]) if len(sys.argv) > 3 else 20
            service.get_followers(max_count=n)
        elif subcommand == "following":
            n = int(sys.argv[3]) if len(sys.argv) > 3 else 20
            service.get_following(max_count=n)
        elif subcommand == "following-detail":
            n = int(sys.argv[3]) if len(sys.argv) > 3 else 20
            service.get_following_with_detail(max_count=n)
        elif subcommand == "following-comments":
            n = int(sys.argv[3]) if len(sys.argv) > 3 else 20
            service.get_following_with_detail(max_count=n, with_comments=True)
        elif subcommand == "followers-detail":
            n = int(sys.argv[3]) if len(sys.argv) > 3 else 20
            service.get_followers_with_detail(max_count=n)
        elif subcommand == "followers-comments":
            n = int(sys.argv[3]) if len(sys.argv) > 3 else 20
            service.get_followers_with_detail(max_count=n, with_comments=True)
        elif subcommand == "works":
            n = int(sys.argv[3]) if len(sys.argv) > 3 else 20
            service.get_works(max_count=n)
        elif subcommand == "works-comments":
            n = int(sys.argv[3]) if len(sys.argv) > 3 else 20
            service.get_works_with_comments(max_works=n)
        else:
            success = service.manage_account(subcommand)
            sys.exit(0 if success else 1)
    
    else:
        print(f"❌ 未知命令: {command}")
        print("支持的命令: register, profiles, delete-profile, chat, upload, batch-upload, account")


if __name__ == "__main__":
    main()
