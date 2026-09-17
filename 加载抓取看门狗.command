#!/bin/zsh
# 加载「抓取看门狗」——每 15 分钟自动巡检抓取任务，卡住超 1 小时自动重启
# 用法：双击本文件即可（终端会显示结果，看完按回车关闭）

PLIST="$HOME/Library/LaunchAgents/com.user.crawlwatch.plist"
UID_NUM=$(id -u)
LOG="$HOME/Library/Logs/crawlwatch.log"

echo "======================================"
echo "  加载抓取看门狗"
echo "======================================"
echo

if [ ! -f "$PLIST" ]; then
  echo "✗ 找不到 plist 文件：$PLIST"
  echo "  请把这条消息发给助理。"
  echo
  echo -n "按回车键关闭..."
  read _line
  exit 1
fi

echo "1) 先卸掉可能存在的旧实例（防止重复加载）..."
launchctl bootout "gui/$UID_NUM" "$PLIST" 2>/dev/null
launchctl unload "$PLIST" 2>/dev/null
echo "   完成"
echo

echo "2) 加载..."
launchctl bootstrap "gui/$UID_NUM" "$PLIST" 2>/dev/null || launchctl load "$PLIST"
echo "   完成"
echo

echo "3) 状态检查..."
if launchctl list | grep -q crawlwatch; then
  echo "   ✓ 已加载："
  launchctl list | grep crawlwatch | sed 's/^/     /'
else
  echo "   ✗ 未加载成功。请把上面的报错内容发给助理。"
fi
echo

echo "--------------------------------------"
echo "日志文件：$LOG"
echo "看门狗每 15 分钟跑一次，稍后回来看日志是否有内容。"
echo "（日志此前不存在，首次运行后会自动创建）"
echo "--------------------------------------"
echo
echo -n "按回车键关闭..."
read _line
