# AI生成
# generate_report.py 覆盖模式补丁
# ============================================================
# 修改说明：
#   将"已有报告则跳过"改为"默认覆盖"
#   通过环境变量 FORCE_OVERWRITE 控制（默认 true）
#
# 改动位置：main() 函数，原第 527-532 行
#
# 原逻辑：
#     report_path = REPORTS_DIR / f"{today}.html"
#     if report_path.exists():
#         print(f"ℹ️ {today} 的报告已存在，跳过生成")
#         print(f"  如需重新生成，请先删除 {report_path}")
#         return
#
# 新逻辑：
#     report_path = REPORTS_DIR / f"{today}.html"
#     force_overwrite = os.environ.get("FORCE_OVERWRITE", "true").lower() in ("true", "1", "yes")
#     if report_path.exists() and not force_overwrite:
#         print(f"ℹ️ {today} 的报告已存在，跳过生成")
#         print(f"  如需重新生成，请先删除 {report_path} 或设置 FORCE_OVERWRITE=true")
#         return
#     if report_path.exists():
#         print(f"🔄 {today} 的报告已存在，将覆盖生成")
#
# ============================================================
# 使用方式：
#   1. 直接替换 generate_report.py 中 main() 函数内的对应代码块
#   2. 或在 GitHub Actions workflow 中设置环境变量：
#      env:
#        FORCE_OVERWRITE: "true"   # 默认覆盖
#        # FORCE_OVERWRITE: "false"  # 恢复跳过行为
#
# ============================================================

# --- 以下是完整的替换代码块，可直接复制到 main() 函数中 ---

    # 检查是否已有该日期的报告（默认覆盖）
    report_path = REPORTS_DIR / f"{today}.html"
    force_overwrite = os.environ.get("FORCE_OVERWRITE", "true").lower() in ("true", "1", "yes")
    if report_path.exists() and not force_overwrite:
        print(f"ℹ️ {today} 的报告已存在，跳过生成")
        print(f"  如需重新生成，请先删除 {report_path} 或设置 FORCE_OVERWRITE=true")
        return
    if report_path.exists():
        print(f"🔄 {today} 的报告已存在，将覆盖生成")
